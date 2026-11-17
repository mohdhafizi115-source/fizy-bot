# Round 137: martingale on the FLIP lanes (owner: "cuba la martiangle"). Lot (in 0.01 units) per trade from the lane's
# own closed trades today: reset to 1 at the server day and after a win. Modes: linear 1,2,3..; double 1,2,4..; daily
# (lot doubles after a losing DAY for the whole next day). Real-tick trades, P&L scaled by the lot (spread scales too).
import numpy as np, pandas as pd
D = pd.read_pickle("xau_m1.pkl"); T = D.index; C = D.c.values; SP = D.spread.values; N = len(T)
G0 = pd.read_pickle("flip133.pkl").sort_values("t").reset_index(drop=True)
MG = 4000 / 3000
CUT = pd.Timestamp("2026-08-16")
def weights(g, mode, cap):
    w = np.ones(len(g)); g = g.copy(); g["day"] = g.t.dt.normalize()
    for m, gg in g.groupby("mod"):
        idx = gg.index.values; lot = 1; prevday = None; daypnl = {}
        dpl = gg.groupby("day").net.sum()
        for i in idx:
            d = g.at[i, "day"]
            if d != prevday:
                if mode == "daily":
                    prev = dpl[dpl.index < d]
                    k = 0
                    for v in prev.values[::-1]:
                        if v < 0: k += 1
                        else: break
                    lot = min(2 ** k, cap)
                else: lot = 1
                prevday = d
            w[i] = lot
            if mode in ("linear", "double"):
                if g.at[i, "net"] < 0: lot = min(lot + 1 if mode == "linear" else lot * 2, cap)
                else: lot = 1
    return w
def path(g, w):
    a = T.searchsorted(g.t.values); b = T.searchsorted(g.tx.values)
    cl = np.zeros(N + 1); nl = np.zeros(N + 1); ns = np.zeros(N + 1); el = np.zeros(N + 1); es = np.zeros(N + 1)
    np.add.at(cl, b, g.net.values * w); L = g.d.values == 1
    np.add.at(nl, a[L], w[L]); np.add.at(nl, b[L], -w[L]); np.add.at(el, a[L], g.e.values[L] * w[L]); np.add.at(el, b[L], -g.e.values[L] * w[L])
    np.add.at(ns, a[~L], w[~L]); np.add.at(ns, b[~L], -w[~L]); np.add.at(es, a[~L], g.e.values[~L] * w[~L]); np.add.at(es, b[~L], -g.e.values[~L] * w[~L])
    c = lambda v: np.cumsum(v[:N])
    return c(cl) + c(nl) * C - c(el) + c(es) - c(ns) * (C + SP), c(nl) + c(ns)
days = T.normalize(); starts = [i for i in np.flatnonzero(np.r_[True, days[1:] != days[:-1]]) if T[i].dayofweek < 5]
def run(lab, mods, mode, cap):
    g = G0[G0["mod"].isin(mods)].reset_index(drop=True)
    w = weights(g, mode, cap) if mode != "flat" else np.ones(len(g))
    P, no = path(g, w)
    s = pd.Series(g.net.values * w, index=g.tx)
    out = [f"{lab:34s} maxlot {0.01*w.max():.2f}"]
    for wn, lo, hi in (("last3", CUT, T[-1]), ("prev3", CUT - pd.Timedelta(days=92), CUT)):
        x = s[(s.index >= lo) & (s.index < hi)]; d = x.groupby(x.index.normalize()).sum()
        i0, i1 = T.searchsorted(lo), T.searchsorted(hi); p = P[i0:i1] - P[i0]; dd = (p - np.maximum.accumulate(np.maximum(p, 0))).min()
        out.append(f"{wn} net {x.sum():+.0f} PF {x[x>0].sum()/max(-x[x<0].sum(),1e-9):.2f} days+ {100*(d>0).mean():.0f}% worst day {d.min():+.0f} DD(mtm) {dd:+.0f}")
    bl = 0; fast = []
    for i in starts:
        eq = 100 + P[i:] - P[i]; bad = np.flatnonzero(eq <= 0.4 * MG * no[i:])
        if len(bad): bl += 1; fast.append((T[i + bad[0]] - T[i]).total_seconds() / 86400)
    out.append(f"$100 starts stopped out {bl}/{len(starts)} ({100*bl/len(starts):.0f}%), median days {np.median(fast) if fast else 0:.1f}")
    print(" | ".join(out), flush=True)
for sn, mods in (("A", ["FLIP-A"]), ("4 lanes", ["FLIP-A", "FLIP-B", "FLIP-C", "FLIP-D"])):
    run(f"{sn} flat 0.01", mods, "flat", 1)
    for cap in (3, 5, 10): run(f"{sn} linear cap {cap}", mods, "linear", cap)
    for cap in (4, 8, 16, 32): run(f"{sn} double cap {cap}", mods, "double", cap)
    for cap in (2, 4): run(f"{sn} daily double cap {cap}", mods, "daily", cap)
