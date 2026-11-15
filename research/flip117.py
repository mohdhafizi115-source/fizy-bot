"""Round 117 (15 Nov 2026): GOLD FLIP turned upside down (counter-trend), last 3 months + the 3 before.  Owner: "itu kalau follow trend
kan? kalau lawan trend?".  The round 114c FADE engine on XAUUSD with fixed $ gaps: the day starts with an OCO of LIMITS (SELL LIMIT open
+ K, BUY LIMIT open - K), in a position the flip is a LIMIT on the profit side (long -> SELL LIMIT at entry + gap and go short), static or
trailed against the trade (a zigzag fade), optional stop X x gap, flat 23:30.  Compared with the live trend FLIP on the same window.
Gold M1, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flip113h as F
import flipbtc114 as FB
import flipbtc114c as FC

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
for mod in (M, W, G, F, FB, FC): mod.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= a6 - pd.Timedelta(days=3)][["o", "h", "l", "c", "s"]]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd; N = len(O)
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize()))
    say(f"GOLD FLIP vs COUNTER-TREND FADE, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    hdr = (f"{'variant':40s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'wTrd':>5} {'lossD':>5} | "
           f"{'prev: trd':>9} {'PF':>5} {'net$':>6} {'DD':>5} {'wDay':>5}")
    say("\n" + hdr)

    def show(nm, xi, p, xS, pS):
        te = T[xi]; tS = T[xS]; out = []
        for lo, hi in ((a3, end + pd.Timedelta(days=1)), (a6, a3)):
            m = (te >= lo) & (te < hi); x = p[m]
            dd_ = days[(days >= lo) & (days < hi)]
            dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum().reindex(dd_, fill_value=0.0)
            eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
            out.append((len(x), len(x) / max(len(dd_), 1), 100 * (x > 0).mean() if len(x) else 0, pf(x), pf(pS[(tS >= lo) & (tS < hi)]),
                        x.sum(), ddn, dp.min(), x.min() if len(x) else 0, (dp < 0).sum()))
        a, b = out
        say(f"{nm:40s} | {a[0]:5d} {a[1]:4.1f} {a[2]:4.0f} {a[3]:5.2f} {a[4]:5.2f} {a[5]:+6.0f} {a[6]:+5.0f} {a[7]:+5.0f} {a[8]:+5.0f} {a[9]:5d} | "
            f"{b[0]:9d} {b[3]:5.2f} {b[5]:+6.0f} {b[6]:+5.0f} {b[7]:+5.0f}")

    xi, p = F.sim(O, H, L, S, 5 * one, live, dayid, usd, one, 3 * one, 25.0)
    xS, pS = F.sim(O, H, L, S * 1.5, 5 * one, live, dayid, usd, one, 3 * one, 25.0)
    show("TREND FLIP (live v2.31)", xi, p, xS, pS)
    for trail in (False, True):
        for X in (0, 1, 2, 3):
            say(f"-- COUNTER-TREND FADE, {'trailed' if trail else 'static'} limit, stop {X} x gap{' (none)' if X == 0 else ''}")
            for gap in (2.0, 3.0, 5.0, 8.0, 10.0, 15.0):
                Dv = np.full(N, gap * one); Kv = Dv * 0.6
                xi, p, _ = FC.fade(O, H, L, S, Dv, Kv, float(X), trail, live, dayid, usd)
                xS, pS, _ = FC.fade(O, H, L, S * 1.5, Dv, Kv, float(X), trail, live, dayid, usd)
                if len(p) < 10: continue
                show(f"   gap ${gap:g}", xi, p, xS, pS)


if __name__ == "__main__":
    main()
