"""Round 121d (16 Nov 2026): a DAILY STOP for the real-time FLIP.  Owner, after a choppy morning (7+ stops in a row in a $5 range):
"teruk ni bro".  Live v2.35 rule, plus: stop the module for the rest of the server day after N losing closes in a row, or once its
closed P&L today is <= -$X.  N 2 / 3 / 4 / 5 / 6, X $10 / 15 / 20 / 30 / 40, and both.  Last 3 months and the 3 before, OHLC and coin
order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf


def main():
    mt, sw = F.W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = F.SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    nd = len(np.unique(dayid[live & (T >= a3)]))
    say(f"REAL-TIME FLIP + DAILY STOP, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), gap $5, $25 target, 0.01 lot")
    say(f"{'rule':28s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} {'+25d':>4} | {'prev PF':>7} {'net$':>6} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    cells = [(0, 0.0)] + [(n, 0.0) for n in (2, 3, 4, 5, 6)] + [(0, x) for x in (10.0, 15.0, 20.0, 30.0, 40.0)] + [(3, 20.0), (4, 20.0), (4, 30.0)]
    for n, x in cells:
        res = []
        for orr in (False, True):
            xi, p = F.sim(O, H, L, C, S, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, True, orr, 1, -999.0, 0.0, n, x)
            res.append((xi, p))
        xS, pS = F.sim(O, H, L, C, S * 1.5, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, True, False, 1, -999.0, 0.0, n, x)
        xi, p = res[0]; te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum()
        xc, pc = res[1]; tc = T[xc]
        lab = "LIVE (no daily stop)" if n == 0 and x == 0 else ("" if n == 0 else f"{n} SL in a row") + (" or " if n and x else "") + ("" if x == 0 else f"-${x:g} today")
        say(f"{lab:28s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} {(dp >= 25).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")


if __name__ == "__main__":
    main()
