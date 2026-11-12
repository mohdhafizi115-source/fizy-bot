"""Round 93 (12 Nov 2026): the BBMA CSAK with the owner's exit: NO SL, cut on an opposite M15 momentum, TP at Fibo 161.8.

Owner: "tiada sl, position cut loss jika berlaku momentum berlawanan di m15. tp di 161 fibo".  Exit (research/bbma87.py
EXIT_MODE = "fib"): no stop loss; a BUY is closed at the next M5 open after an M15 candle closes below the bottom BB
(bearish momentum), a SELL after one closes above the top BB; TP at the Fibonacci extension of the leg from the
lowest low of the 8 M15 candles up to the CSAK to the CSAK's high (sell mirrored): 161.8% (and 127.2 / 261.8% as
neighbours); no time limit; broker swaps.  R = profit / the fib leg.  Entries: the M15 CSAK either way (old 2-line
"basic" and the full-break "all"), after an M30 / H1 EMA 50 rejection aligned with H4 (SOP), or with only the H4
EMA 50/90 direction (NOREJ).  M15 indicator filters on the CSAK candle: none / RSI14 > 55 / CCI20 > 0 / MFI14 > 50 /
MFI14 > 55.  Window: the last 2 years.  Also reported: the worst trade and the worst FLOATING loss of any trade in $ per
0.01 lot (no SL means the floating loss is the real risk to a $100 account), median hold, share of trades reaching TP.
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


def feat(X):
    tp = (X.h + X.l + X.c) / 3; mf = tp * X.v; d = tp.diff()
    pos = mf.where(d > 0, 0.0).rolling(14).sum(); neg = mf.where(d < 0, 0.0).rolling(14).sum()
    return {"mfi14": ((100 - 100 / (1 + pos / neg.replace(0, np.nan))).values, "osc")}


B87.FEAT = feat
B87.EXTRA = [("none", lambda F: F["r"] > -1e9), ("RSI14>55", lambda F: F["r"] > 55), ("CCI20>0", lambda F: F["c"] > 0),
             ("MFI14>50", lambda F: F["mfi14"] > 50), ("MFI14>55", lambda F: F["mfi14"] > 55)]
B87.RAND_EXTRA = True
B87.RTFS = ((30, "M30", 8), (60, "H1", 4), (0, "NOREJ", 0))
B87.EXIT_MODE = "fib"
B87.TPS = (1.272, 1.618, 2.618)


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
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; R pooled over 30 symbols (R = profit / fib leg); RAND = same entries, random "
        f"direction.  PASS = >=150 trades, PF >= 1.15, both years >= 1.05, stress >= 1.05, last 12 months > 0, PF >= RAND + 0.10.  Rows with < 30 trades skipped.")
    say(f"{'csak | context | pop | filter | fib':52s} {'side':4s} {'n':>5} {'win%':>4} {'TP%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | "
        f"{'12m R':>6} {'3m R':>5} {'p3m R':>6} | {'sym>1':>6} | {'hold h':>6} {'worst$':>7} {'float$':>7} | {'RAND PF':>7}")
    rows = []
    for key, L in ALL.items():
        if key[3].endswith("RANDOM dir"): continue
        R = pd.concat(L); Rr = pd.concat(ALL.get(key[:3] + (key[3] + " RANDOM dir",) + key[4:], [R.iloc[:0]]))
        for side, sd in (("BUY", 1), ("SELL", -1), ("ALL", 0)):
            x = R if sd == 0 else R[R.d == sd]; xr = Rr if sd == 0 else Rr[Rr.d == sd]
            if len(x) < 30: continue
            g = [pf(v.net.values) > 1 for _, v in x.groupby("sym") if len(v) >= 10]
            P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values)
            l12 = x.r[x.t >= mid].sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
            rows.append((P, f"{' | '.join(map(str, key[:4])) + f' | {key[4]:.3f}':52s} {side:4s} {len(x):5d} {100 * (x.r > 0).mean():4.0f} {100 * x.tp.mean():4.0f} "
                            f"{P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | {l12:+6.1f} {x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | "
                            f"{sum(g):2d}/{len(g):<3d} | {x.hours.median():6.1f} {x.net.min():+7.0f} {x.mae.min():+7.0f} | {PR:7.2f} {'PASS' if ok else ''}", len(x)))
    for _, line, _ in rows: say(line)
    big = [r for r in rows if r[2] >= 150]
    say(f"\n=== {len(big)} rows with >= 150 trades; best 20 by PF ===")
    for _, line, _ in sorted(big, key=lambda z: -z[0])[:20]: say(line)
    say(f"PASS count: {sum('PASS' in r[1] for r in rows)}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
