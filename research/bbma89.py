"""Round 89 (12 Nov 2026): does the Stochastic help the M15 CSAK?  Round 87's BBMA SOP on all 30 instruments, judged
on the last 3 months (and the 3 before as a repeat check), BUY and SELL apart, plus the full 6.6 years for reference.

Owner: "stoch tidak membantu ke".  Stochastic 14,3,3 on the M15 CSAK candle, every value signed in the CSAK
direction (for a sell, 100 - value):  %K > %D;  %K > 50;  %K rising;  %K left oversold (lowest %K of the last 5 M15
candles < 20) and %K > %D;  %K < 80 (not overbought);  %K > %D and %K < 80;  RSI14 > 55 and %K > %D.  Every filter is
also run with a RANDOM direction on the same entries.  Rule, exits and costs: research/bbma87.py.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87

say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
B87.EXTRA = [("none", lambda F: F["r"] > -1), ("K>D", lambda F: F["k"] > F["d"]), ("K>50", lambda F: F["k"] > 50),
             ("K rising", lambda F: F["k"] > F["kp"]), ("K out of 20, K>D", lambda F: (F["km"] < 20) & (F["k"] > F["d"])),
             ("K<80", lambda F: F["k"] < 80), ("K>D and K<80", lambda F: (F["k"] > F["d"]) & (F["k"] < 80)),
             ("RSI>55 and K>D", lambda F: (F["r"] > 55) & (F["k"] > F["d"]))]


def main():
    DATA = B87.DATA
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    ALL = {}; ends = []
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        res, end, _ = B87.run_symbol(sym, meta[sym], SW.get(sym)); ends.append(end)
        for k, df in res.items():
            if len(df): ALL.setdefault(k, []).append(df.assign(sym=sym))
    END = max(ends); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"data end {END:%Y-%m-%d}; last 3 months from {a3:%Y-%m-%d}, previous 3 months from {a6:%Y-%m-%d}; {time.time() - T0:.0f} s")
    say("Pooled over 30 symbols in R (profit / risk).  'sym+' = symbols with a positive $ result in the window.  6.6 y = all data.\n")
    say(f"{'variant':44s} {'side':4s} | {'LAST 3 MO n':>11} {'win%':>4} {'PF R':>5} {'R':>6} {'sym+':>7} | {'PREV 3 MO n':>11} {'win%':>4} {'PF R':>5} {'R':>6} {'sym+':>7} | {'6.6y n':>6} {'PF R':>5} {'h1':>5} {'h2':>5}")
    def cell(x):
        if len(x) == 0: return f"{0:11d} {'':4s} {'':5s} {'':6s} {'':7s}"
        g = x.groupby("sym").net.sum()
        return f"{len(x):11d} {100 * (x.r > 0).mean():4.0f} {pf(x.r.values):5.2f} {x.r.sum():+6.1f} {int((g > 0).sum()):3d}/{len(g):<3d}"
    for key, L in ALL.items():
        R = pd.concat(L)
        for side, m in (("BUY", R.d == 1), ("SELL", R.d == -1), ("ALL", R.d != 0)):
            x = R[m]
            name = " | ".join(map(str, key[:3])) + f" | TP {key[3]}R"
            say(f"{name:44s} {side:4s} | {cell(x[x.t >= a3])} | {cell(x[(x.t >= a6) & (x.t < a3)])} | "
                f"{len(x):6d} {pf(x.r.values):5.2f} {pf(x.r[x.t < B87.MIDDAY].values):5.2f} {pf(x.r[x.t >= B87.MIDDAY].values):5.2f}")
        if key[2] == "RSI>55 and K>D": say()
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
