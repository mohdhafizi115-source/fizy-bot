"""Round 91 (12 Nov 2026): the CSAK as ONE candle that breaks EVERY line, last 2 years, all 30 instruments.

Owner: "csak tu sebatang yang break semua".  Rounds 83-90 used open beyond min / max(mid BB, EMA 50) and close beyond
both.  Now the lines are mid BB (20), EMA 50 and the BBMA LWMA 5 / 10 of the highs and of the lows ("all"); a BUY CSAK
same plus the M15 EMA 90 ("all90"); a BUY CSAK opens below every line and closes above every line, not above the top
BB (sell mirrored).  "basic" (the old definition) is kept for comparison.
Contexts: the SOP (H4 EMA 50/90 + H4 momentum in 8 + M30 (8) / H1 (4) EMA 50 rejection with H4), and NOREJ = the CSAK
with only the H4 EMA 50/90 direction known (WITH = CSAK in the H4 direction).  Filters none / RSI14 > 55 / CCI20 > 0 /
both, in the CSAK direction.  Exits, costs, swaps: research/bbma87.py.  Window: the last 2 years (owner); the two years
are the halves.  Each line also shows the same entries with a RANDOM direction.
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
B87.EXTRA = [("none", lambda F: F["r"] > -1e9), ("RSI14>55", lambda F: F["r"] > 55), ("CCI20>0", lambda F: F["c"] > 0),
             ("RSI>55+CCI>0", lambda F: (F["r"] > 55) & (F["c"] > 0))]
B87.RAND_EXTRA = True
B87.RTFS = ((30, "M30", 8), (60, "H1", 4), (0, "NOREJ", 0))


def main():
    DATA = B87.DATA
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    ALL = {}; END = None
    for mode in ("basic", "all"):
        B87.CSAK_MODE = mode
        for sym in B87.SYMS:
            if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
            res, end, _ = B87.run_symbol(sym, meta[sym], SW.get(sym)); END = end if END is None else max(END, end)
            for k, df in res.items():
                df = df[df.t >= end - pd.Timedelta(days=730)]
                if len(df): ALL.setdefault((mode,) + k, []).append(df.assign(sym=sym))
        say(f"mode {mode} done [{time.time() - T0:.0f} s]")
    y0, mid = END - pd.Timedelta(days=730), END - pd.Timedelta(days=365)
    a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\nwindow {y0:%Y-%m-%d} .. {END:%Y-%m-%d}; year 1 / year 2 split {mid:%Y-%m-%d}; R = profit / risk, pooled over 30 symbols; "
        f"'sym>1' = symbols with PF($) > 1 among those with >= 10 trades; RAND = same entries, random direction.  PASS = pass rule + PF >= RAND + 0.10")
    say(f"{'csak | context | pop | filter | TP':48s} {'side':4s} {'n':>5} {'/wk':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | "
        f"{'12m R':>6} {'3m R':>5} {'p3m R':>6} | {'sym>1':>6} | {'RAND PF':>7} {'12m R':>6}")
    for key, L in ALL.items():
        if key[3].endswith("RANDOM dir"): continue
        R = pd.concat(L); Rr = pd.concat(ALL.get(key[:3] + (key[3] + " RANDOM dir",) + key[4:], [R.iloc[:0]]))
        for side, sd in (("BUY", 1), ("SELL", -1), ("ALL", 0)):
            x = R if sd == 0 else R[R.d == sd]; xr = Rr if sd == 0 else Rr[Rr.d == sd]
            if len(x) < 20: continue
            g = [pf(v.net.values) > 1 for _, v in x.groupby("sym") if len(v) >= 10]
            P, P1, P2, PS = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values)
            l12 = x.r[x.t >= mid].sum(); PR = pf(xr.r.values)
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
            name = " | ".join(map(str, key[:4])) + f" | {key[4]}R"
            say(f"{name:48s} {side:4s} {len(x):5d} {len(x) / 104:4.1f} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | "
                f"{l12:+6.1f} {x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | {sum(g):2d}/{len(g):<3d} | "
                f"{PR:7.2f} {xr.r[xr.t >= mid].sum():+6.1f} {'PASS' if ok else ''}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
