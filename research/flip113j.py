"""Round 113j (15 Nov 2026): GOLD FLIP stop gap sweep on the live v2.31 rule.  Owner: "jadi 5$ tu paling okay atau boleh minimum kan lagi".
Gap $2 / 2.5 / 3 / 3.5 / 4 / 4.5 / 5 / 6 / 7 / 8 / 10, lock +$1, OCO +- $3, out 23:30, with and without the $25 own target.
Day stats: losing days, average losing day, worst day, max DD.  Gold M1, last 2 years, 0.01 lot.  Uses flip113i.sim (bemode 0 = live freeze)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flip113i as F

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; F.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize())); nd = len(days)
    say(f"GOLD FLIP gap sweep: gold M1 {days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}, {nd} days, lock +$1, OCO +-$3, $ at 0.01 lot")
    hdr = (f"{'gap':>5} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'net$':>6} {'12m$':>6} {'3m$':>5} {'pr3m':>5} | "
           f"{'DD':>5} {'wDay':>5} {'lossD':>5} {'avgLD':>6} {'d<-50':>5} {'d<-100':>6} {'big':>4}")
    for tgt in (25.0, 0.0):
        say(f"\n==== {'WITH the $25 target (live)' if tgt else 'WITHOUT the target'}\n" + hdr)
        for g in (2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7, 8, 10):
            args = (live, dayid, usd, one, 3 * one, tgt, 0.0, 0, 0)
            xi, p = F.sim(O, H, L, S, g * one, *args)
            _, ps = F.sim(O, H, L, S * 1.5, g * one, *args)
            te = T[xi]
            dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
            eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
            say(f"{'$' + format(g, 'g'):>5} {len(p):6d} {len(p) / nd:5.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(ps):5.2f} | "
                f"{p.sum():+6.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | "
                f"{dd:+5.0f} {dp.min():+5.0f} {(dp < 0).sum():5d} {dp[dp < 0].mean():+6.1f} {(dp < -50).sum():5d} {(dp < -100).sum():6d} {p.max():4.0f}")


if __name__ == "__main__":
    main()
