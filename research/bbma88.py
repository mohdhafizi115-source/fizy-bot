"""Round 88 (12 Nov 2026): round 87's BBMA SOP judged on the LAST 3 MONTHS, BUY and SELL apart.

Owner: "sell mana? kau test 3 bulan je cukup, tak perlu sampai 6 tahun".  Same rule, filters, exits and costs as
research/bbma87.py (run_symbol is reused); trades follow the CSAK, so buys are buy CSAKs and sells are sell CSAKs.
Windows: last 3 months, and the 3 months before as a repeat check.  Pooled in R across the 30 symbols, and per symbol
in $ per 0.01 lot for the main variants.  Control: the same entries with a random direction.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87

DATA = B87.DATA
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    ALL = {}; ends = []
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        res, end, _ = B87.run_symbol(sym, meta[sym], SW.get(sym)); ends.append(end)
        for k, df in res.items():
            if len(df): ALL.setdefault(k, []).append(df.assign(sym=sym))
    END = max(ends)
    a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"data end {END:%Y-%m-%d}; last 3 months from {a3:%Y-%m-%d}, previous 3 months from {a6:%Y-%m-%d}; {time.time() - T0:.0f} s\n")
    say("Pooled over 30 symbols, R = profit / risk of each trade.  'sym+' = symbols with a positive $ result in the window.")
    say(f"{'variant':40s} {'side':4s} | {'LAST 3 MONTHS: n':>16} {'win%':>4} {'PF R':>5} {'R':>6} {'sym+':>7} | {'PREV 3 MONTHS: n':>16} {'win%':>4} {'PF R':>5} {'R':>6} {'sym+':>7}")
    def cell(x):
        if len(x) == 0: return f"{0:16d} {'':4s} {'':5s} {'':6s} {'':7s}"
        g = x.groupby("sym").net.sum()
        return f"{len(x):16d} {100 * (x.r > 0).mean():4.0f} {pf(x.r.values):5.2f} {x.r.sum():+6.1f} {int((g > 0).sum()):3d}/{len(g):<3d}"
    for key, L in ALL.items():
        if key[2].endswith("mask x3"): continue
        R = pd.concat(L)
        for side, m in (("BUY", R.d == 1), ("SELL", R.d == -1), ("ALL", R.d != 0)):
            x = R[m]
            l3, p3 = x[x.t >= a3], x[(x.t >= a6) & (x.t < a3)]
            name = " | ".join(map(str, key[:3])) + f" | TP {key[3]}R"
            say(f"{name:40s} {side:4s} | {cell(l3)} | {cell(p3)}")
    for key in (("M30", "ANY", "none", 1), ("M30", "ANY", "RSI>55", 1), ("M30", "ANY", "RSI>55", 2), ("M30", "WITH", "RSI>55", 1),
                ("M30", "AGAINST", "RSI>55", 2), ("H1", "ANY", "RSI>55", 1)):
        if key not in ALL: continue
        R = pd.concat(ALL[key])
        say(f"\n--- per symbol, {' | '.join(map(str, key))}R, $ per 0.01 lot: last 3 months BUY / SELL, previous 3 months BUY / SELL ---")
        say(f"{'sym':8s} {'L3 buy n':>8} {'$':>6} {'L3 sell n':>9} {'$':>6} | {'P3 buy n':>8} {'$':>6} {'P3 sell n':>9} {'$':>6}")
        for sym, g in R.groupby("sym", sort=False):
            l3, p3 = g[g.t >= a3], g[(g.t >= a6) & (g.t < a3)]
            f = lambda x, d: (len(x[x.d == d]), x[x.d == d].net.sum())
            v = f(l3, 1) + f(l3, -1) + f(p3, 1) + f(p3, -1)
            say(f"{sym:8s} {v[0]:8d} {v[1]:+6.1f} {v[2]:9d} {v[3]:+6.1f} | {v[4]:8d} {v[5]:+6.1f} {v[6]:9d} {v[7]:+6.1f}")
        l3 = R[R.t >= a3]; p3 = R[(R.t >= a6) & (R.t < a3)]
        say(f"{'TOTAL $':8s} {len(l3[l3.d == 1]):8d} {l3[l3.d == 1].net.sum():+6.0f} {len(l3[l3.d == -1]):9d} {l3[l3.d == -1].net.sum():+6.0f} | "
            f"{len(p3[p3.d == 1]):8d} {p3[p3.d == 1].net.sum():+6.0f} {len(p3[p3.d == -1]):9d} {p3[p3.d == -1].net.sum():+6.0f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
