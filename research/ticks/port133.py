import numpy as np, pandas as pd, itertools
D = pd.read_pickle("xau_m1.pkl"); T = D.index; C = D.c.values; SP = D.spread.values; N = len(T)
G = pd.concat([pd.read_pickle("gold133.pkl"), pd.read_pickle("flip133.pkl")])
Z = pd.concat([pd.read_pickle("../rcs133.pkl"), pd.read_pickle("../btcsmc133.pkl")])
end = T[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
MARGIN = {"XAUUSD": 4000 / 3000, "BTCUSD": 900 / 100}            # $ margin per 0.01 lot (1:3000; BTC assumed 1:100)
def curve(mods, lo, hi):
    """equity path on the gold minute grid from $100 at lo; gold trades marked to market, others booked at their exit."""
    m = (T >= lo) & (T < hi); idx = np.flatnonzero(m); i0, i1 = idx[0], idx[-1] + 1
    closed = np.zeros(N + 1); fl_nl = np.zeros(N + 1); fl_ns = np.zeros(N + 1); fl_el = np.zeros(N + 1); fl_es = np.zeros(N + 1); mg = np.zeros(N + 1)
    g = G[G["mod"].isin(mods) & (G.t >= lo) & (G.t < hi)]
    a = T.searchsorted(g.t.values); b = T.searchsorted(g.tx.values)
    for ai, bi, d, e, net in zip(a, b, g.d.values, g.e.values, g.net.values):
        closed[bi] += net; mg[ai] += MARGIN["XAUUSD"]; mg[bi] -= MARGIN["XAUUSD"]
        if d == 1: fl_nl[ai] += 1; fl_nl[bi] -= 1; fl_el[ai] += e; fl_el[bi] -= e
        else: fl_ns[ai] += 1; fl_ns[bi] -= 1; fl_es[ai] += e; fl_es[bi] -= e
    z = Z[Z["mod"].isin(mods) & (Z.t >= lo) & (Z.t < hi)]
    a = T.searchsorted(z.t.values); b = T.searchsorted(pd.to_datetime(z.tx.values))
    for ai, bi, sym, net in zip(a, b, z.sym.values, z.net.values):
        closed[bi] += net; mm = MARGIN.get(sym, 0.4); mg[ai] += mm; mg[bi] -= mm
    cs = lambda v: np.cumsum(v[:N])
    eq = 100 + cs(closed) + cs(fl_nl) * C - cs(fl_el) + cs(fl_es) - cs(fl_ns) * (C + SP)
    marg = cs(mg)
    eq, marg = eq[i0:i1], marg[i0:i1]; tt = T[i0:i1]
    so = np.flatnonzero((marg > 0) & (eq <= 0.4 * marg))
    day = pd.Series(eq, index=tt).resample("1D").last().dropna()
    dd = (eq - np.maximum.accumulate(eq)).min()
    n = len(g) + len(z); net = g.net.sum() + z.net.sum()
    return dict(n=n, net=net, minEq=eq.min(), dd=dd, worst=day.diff().fillna(day.iloc[0] - 100).min(), stop=(tt[so[0]].strftime("%d %b") if len(so) else "-"),
                below50=(eq < 50).mean() * 100)
def show(lab, mods):
    r1 = curve(mods, a3, end + pd.Timedelta(minutes=1)); r0 = curve(mods, a6, a3)
    f = lambda r: f"{r['n']:5d} {r['net']:+7.0f} {r['minEq']:7.0f} {r['dd']:+6.0f} {r['worst']:+6.0f} {r['stop']:>7s}"
    print(f"{lab:34s} | {f(r1)} | {f(r0)}", flush=True)
    return r1, r0
ALLM = sorted(set(G["mod"]) | set(Z["mod"]))
print(f"last 3 months {a3:%d %b} .. {end:%d %b} | previous {a6:%d %b} .. {a3:%d %b}; start $100 each window, 0.01 lot; stop-out = equity <= 40% of margin (1:3000)")
print(f"{'modules':34s} | {'trd':>5} {'net$':>7} {'minEq':>7} {'maxDD':>6} {'wDay':>6} {'STOPOUT':>7} | previous 3 months")
for m in ALLM: show(m, [m])
FL = ["FLIP-A", "FLIP-B", "FLIP-C", "FLIP-D"]; rest = [m for m in ALLM if m not in FL]
print("-- groups --")
show("FLIP 4 lanes", FL)
show("FLIP A only", ["FLIP-A"])
show("FLIP A+B", ["FLIP-A", "FLIP-B"])
show("all except FLIP", rest)
show("all except FLIP + FLIP A", rest + ["FLIP-A"])
show("all except FLIP + FLIP A+B", rest + ["FLIP-A", "FLIP-B"])
show("ALL LIVE (v2.48)", ALLM)
show("all live without CMX, CRS, RCS-fx", [m for m in ALLM if m not in ("CMX", "CRS", "RCS-fx")])
show("same + FLIP A only", [m for m in rest if m not in ("CMX", "CRS", "RCS-fx")] + ["FLIP-A"])
