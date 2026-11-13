"""Round 108b (13 Nov 2026): is the COMEX-open first-minute follow real, or any New York morning minute?
Round 108's survivor: at 08:20 New York (COMEX gold open) take the direction of the first 1-minute bar and follow it for
5-30 min (515 trades, PF 1.33, years 1.14 / 1.44, random 0.78).  The fake-time control: the same rule at every minute
from 07:00 to 11:00 New York, every 5 minutes, plus details (threshold, hold, SL, side, worst day, months)."""
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
    Bw = d[d.index >= start - pd.Timedelta(days=20)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    dates = pd.DatetimeIndex(T.normalize().unique())
    dates = dates[dates.dayofweek < 5]

    def sig(hh, mm, m=1, thr=0.0, hold=5, slk=2.0, side=None, mode="follow"):
        ts = W.ny_to_server(dates, hh, mm).dropna()
        a = np.searchsorted(tv, ts.values.astype("datetime64[ns]"))
        ok = (a < n - 40) & (np.abs(tv[np.minimum(a, n - 1)] - ts.values.astype("datetime64[ns]")) < np.timedelta64(60, "s"))
        a = a[ok]
        mv = C[a + m - 1] - O[a]
        sel = np.abs(mv) >= thr * a1[a]
        ii = a[sel] + m; dr = np.sign(mv[sel]).astype(int) * (1 if mode == "follow" else -1)
        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slk * a1[ii - 1], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))})
        sg = sg[(sg.d != 0) & (sg.sl > 0)]
        if side: sg = sg[sg.d == side]
        return sg

    def row(name, sg, show=True):
        r = bk.run(sg)
        x = M.line(name, r, mid, end)
        if not x: return None
        p = pd.Series(r["pnl"], index=r["t"])
        x["wday"] = float(p.groupby(p.index.normalize()).sum().min())
        mo = p.groupby(p.index.to_period("M")).sum(); x["mpos"] = f"{int((mo > 0).sum())}/{len(mo)}"
        if show:
            M.show(x); say(f"{'':52s} worst day {x['wday']:+.0f}, months + {x['mpos']}")
        return x

    say("== fake-time control: 'follow the first 1-minute bar' at every 5th minute 07:00-11:00 New York, hold 5 / 15 min")
    say(f"{'NY time':8s} {'n':>4} {'PF 5m':>6} {'yr1':>5} {'yr2':>5} {'net$':>6} | {'PF 15m':>6} {'yr1':>5} {'yr2':>5} {'net$':>6} | {'PF 5m >=1ATR':>12} {'n':>4}")
    grid = []
    for h_ in range(7, 11):
        for m_ in range(0, 60, 5):
            out = []
            for hold, thr in ((5, 0.0), (15, 0.0), (5, 1.0)):
                r = bk.run(sig(h_, m_, hold=hold, thr=thr))
                if r is None or r["n"] < 20: out.append((0, 0, 0, 0, 0)); continue
                p, t = r["pnl"], r["t"]; y1 = t < mid
                out.append((r["n"], pf(p), pf(p[y1]), pf(p[~y1]), p.sum()))
            grid.append((h_, m_, out))
            say(f"{h_:02d}:{m_:02d}    {out[0][0]:4d} {out[0][1]:6.2f} {out[0][2]:5.2f} {out[0][3]:5.2f} {out[0][4]:+6.0f} | {out[1][1]:6.2f} {out[1][2]:5.2f} {out[1][3]:5.2f} {out[1][4]:+6.0f} | {out[2][1]:12.2f} {out[2][0]:4d}")
    pf5 = np.array([g[2][0][1] for g in grid]); pf15 = np.array([g[2][1][1] for g in grid])
    lab = [f"{g[0]:02d}:{g[1]:02d}" for g in grid]
    i20 = lab.index("08:20")
    say(f"\n08:20 hold 5: PF {pf5[i20]:.2f}, rank {int((pf5 > pf5[i20]).sum()) + 1} of {len(pf5)}; median of all times {np.median(pf5):.2f}; "
        f"times with PF >= 1.15: {', '.join(l for l, v in zip(lab, pf5) if v >= 1.15)}")
    say(f"08:20 hold 15: PF {pf15[i20]:.2f}, rank {int((pf15 > pf15[i20]).sum()) + 1} of {len(pf15)}; median {np.median(pf15):.2f}; "
        f"times with PF >= 1.15: {', '.join(l for l, v in zip(lab, pf15) if v >= 1.15)}")

    say("\n== detail at 08:20 and its neighbours"); say(M.HDR)
    for mm in (15, 19, 20, 21, 25):
        row(f"NY 08:{mm:02d} first 1m follow 5m", sig(8, mm))
    for hold in (2, 3, 5, 10, 15, 30):
        row(f"08:20 first 1m follow {hold}m", sig(8, 20, hold=hold))
    for thr in (0.0, 0.5, 1.0, 1.5):
        row(f"08:20 first 1m >= {thr} ATR follow 5m", sig(8, 20, thr=thr))
    for slk in (1.0, 1.5, 3.0, 99.0):
        row(f"08:20 first 1m follow 5m SL {slk} ATR", sig(8, 20, slk=slk))
    row("08:20 first 1m follow 5m BUYS", sig(8, 20, side=1))
    row("08:20 first 1m follow 5m SELLS", sig(8, 20, side=-1))
    for m in (2, 3):
        row(f"08:20 first {m}m follow 5m", sig(8, 20, m=m))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
