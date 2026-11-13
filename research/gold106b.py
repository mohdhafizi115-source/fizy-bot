"""Round 106b (13 Nov 2026): the one round-106 survivor, mapped.  F1 "VWAP follow" (close crosses beyond +-3 sd of the session
VWAP, gate 8, follow, SL at the VWAP, out after 60 min) passed, but its control - the same rule on a ROLLING 120-bar VWAP with
no session anchor - also passed at 3.5 sd.  So the question is whether this is a session-VWAP effect or a general "stretched
z-score continues" effect, and whether any setting is a plateau rather than a peak.
For each anchor (session London / NY, rolling 60 / 120 / 240 / 480 bars) and each NON-OVERLAPPING z band (2.5-3, 3-3.5, 3.5-4,
4-5), gate 8, out after 60 / 120 min: PF, years, twins, worst day, months positive, last 3 months and the 3 before."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=40)][["o", "h", "l", "c", "s", "v"]].copy()
    bk = M.Book(Bw[["o", "h", "l", "c", "s"]], usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    V = np.maximum(Bw.v.values.astype(float), 1.0); T = Bw.index; n = len(Bw)
    a1 = M.atr(Bw).values
    tp_ = (H + L + C) / 3
    dates = pd.DatetimeIndex(T.normalize().unique())
    a_l = W.ldn_to_server(dates, 8, 0); a_n = W.ny_to_server(dates, 9, 30)
    st = np.sort(np.r_[a_l.dropna().values, a_n.dropna().values]).astype("datetime64[ns]")
    nd = np.minimum(np.r_[st[1:], st[-1:]], (pd.DatetimeIndex(st).normalize() + pd.Timedelta(minutes=1410)).values)
    tv = T.values.astype("datetime64[ns]")
    seg = np.searchsorted(st, tv, side="right") - 1
    seg = np.where((seg >= 0) & (tv < nd[np.maximum(seg, 0)]), seg, -1)
    g = pd.DataFrame({"seg": seg, "v": V, "pv": V * tp_, "pv2": V * tp_ * tp_})
    cv, cpv, cpv2 = (g.groupby("seg")[k].cumsum().values for k in ("v", "pv", "pv2"))
    cnt = g.groupby("seg").cumcount().values
    vw = cpv / cv; sd = np.sqrt(np.maximum(cpv2 / cv - vw * vw, 0))
    vw[seg < 0] = np.nan; sd[(seg < 0) | (cnt < 15)] = np.nan
    segend = np.searchsorted(tv, nd[np.maximum(seg, 0)])
    anchors = {"session": (vw, sd, segend)}
    for w in (60, 120, 240, 480):
        rv = pd.Series(V * tp_).rolling(w).sum().values / pd.Series(V).rolling(w).sum().values
        rv2 = pd.Series(V * tp_ * tp_).rolling(w).sum().values / pd.Series(V).rolling(w).sum().values
        anchors[f"rolling {w}"] = (rv, np.sqrt(np.maximum(rv2 - rv * rv, 0)), np.full(n, n - 1))
    exb = lambda i: M.exit_bar(Bw, i)
    res = []

    def run(name, vw_, sd_, se_, klo, khi, hold, gg=8):
        z = (C - vw_) / np.where(sd_ > 0, sd_, np.nan); az = np.abs(z)
        beyond = (az > klo) & np.isfinite(az)
        cr = beyond & ~np.r_[False, beyond[:-1]] & (az <= khi) & (a1 >= gg * S)
        j = np.where(cr)[0]; ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
        dr = np.sign(z[j]).astype(int)
        e = np.where(dr == 1, O[ii] + S[ii], O[ii]); sl = np.abs(e - vw_[j])
        x = np.maximum(np.minimum(np.minimum(ii + hold, se_[j]), exb(ii)), ii + 1)
        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": np.nan, "x": x})
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl)]
        r = bk.run(sg)
        xl = M.line(name, r, mid, end)
        if not xl: return
        p = pd.Series(r["pnl"], index=r["t"])
        xl["wday"] = float(p.groupby(p.index.normalize()).sum().min())
        mo = p.groupby(p.index.to_period("M")).sum(); xl["mpos"] = f"{int((mo > 0).sum())}/{len(mo)}"
        res.append(xl)
        M.show(xl); say(f"{'':52s} worst day {xl['wday']:+.0f}, months positive {xl['mpos']}")

    for nm, (vw_, sd_, se_) in anchors.items():
        say(f"\n-- anchor {nm}: non-overlapping z bands, gate 8, follow, SL at the anchor, no TP"); say(M.HDR)
        for hold in (60, 120):
            for klo, khi in ((2.5, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 5.0), (3.0, 99)):
                run(f"{nm} z {klo}-{khi} {hold}m", vw_, sd_, se_, klo, khi, hold)

    say("\n-- the session centre: gate 8 / 10 / 12 x hold 60 / 90 / 120 at K 3.0 (and 3.0-3.5 only)"); say(M.HDR)
    vw_, sd_, se_ = anchors["session"]
    for gg in (8, 10, 12):
        for hold in (60, 90, 120):
            for khi in (99, 3.5):
                run(f"session z 3.0-{khi} gate {gg} {hold}m", vw_, sd_, se_, 3.0, khi, hold, gg)

    R = pd.DataFrame(res)
    say(f"\n{len(R)} rows, PASS {int(R.ok.sum())}; by anchor (median PF over its rows): " +
        "  ".join(f"{k}: {v.PF.median():.2f}" for k, v in R.groupby(R.name.str.rsplit(" z ", n=1).str[0])))
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
