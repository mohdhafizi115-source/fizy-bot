"""Round 119 (15 Nov 2026): the TikTok clip exactly as shown (round 113's tight trailing stop-and-reverse), judged on the LAST 3 MONTHS
with the 3 months before as a repeat check.  Owner: "flip ni macam lain dari video aku send tu" -> "cuba kau test jap macam video tu dalam
3 bulan".  Uses the round 113c simulator: TRAIL (stop trails D behind the best price every bar, reverse when hit) and TRAIL+TP$1 (take
10 pips per entry, re-enter the same way), gaps $0.3-3, with / without the $25 daily target; the live FREEZE $5 as a reference
(market BUY start, not the OCO).  Gold M1, 01:30-23:30 server weekdays, 0.01 lot, $100 account refilled after each wipe-out.
Note: at most one flip per bar, so tight gaps UNDER-count flips and spread (optimistic)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flip113c as FC

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; FC.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= a6][["o", "h", "l", "c", "s"]]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410); one = 1.0 / usd
    say(f"TIKTOK FLIP on XAUUSD, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    say(f"median spread ${np.median(S) * usd:.2f}")
    say(f"{'variant':30s} | {'trd':>6} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>7} {'DD':>6} {'wDay':>5} {'bDay':>5} {'blow':>4} {'@0.5lot$':>9} | "
        f"{'prev trd':>8} {'PF':>5} {'net$':>7}")
    nd3 = len(np.unique(dayid[live & (T >= a3)]))
    rows = [("TRAIL", 0, g) for g in (0.3, 0.5, 1.0, 2.0, 3.0)] + [("TRAIL+TP$1", 1, g) for g in (0.5, 1.0, 2.0, 3.0)] + [("LIVE-ish FREEZE", 3, 5.0)]
    for nm0, mode, gap in rows:
        for tgt in (1e9, 25.0):
            xi, p = FC.sim(O, H, L, S, gap * one, live, dayid, usd, tgt, mode, one, one)
            xS, pS = FC.sim(O, H, L, S * 1.5, gap * one, live, dayid, usd, tgt, mode, one, one)
            te = T[xi]; teS = T[xS]
            m = te >= a3; m2 = te < a3; x = p[m]
            dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
            bal = 100.0; blow = 0
            for v in x:
                bal += v
                if bal <= 0: blow += 1; bal = 100.0
            nm = f"{nm0} gap${gap:g}" + (" T25" if tgt < 1e8 else "")
            say(f"{nm:30s} | {len(x):6d} {len(x) / nd3:4.0f} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {pf(pS[teS >= a3]):5.2f} {x.sum():+7.0f} {dd:+6.0f} "
                f"{dp.min():+5.0f} {dp.max():+5.0f} {blow:4d} {x.sum() * 50:+9.0f} | {m2.sum():8d} {pf(p[m2]):5.2f} {p[m2].sum():+7.0f}")
        say("")


if __name__ == "__main__":
    main()
