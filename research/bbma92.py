"""Round 92 (12 Nov 2026): Money Flow Index on the BBMA M15 CSAK, last 2 years, all 30 instruments.

Owner: "kau tak cuba dengan money flow index".  MFI(n) from the broker's tick volume (the export's v column, summed
into M15): typical price x volume, positive vs negative flow over n bars.  Signed in the CSAK direction (sell: 100 - MFI).
Filters: MFI 7 / 10 / 14 / 21 above 50 / 55 / 60 / 65; MFI rising and above 50; MFI 14 > 50 with RSI 14 > 55; MFI 14 < 80
(not overbought).  CSAK: the old 2-line one ("basic") and the one that breaks mid BB, EMA 50 and LWMA 5 / 10 high / low
("all").  Contexts: SOP with an M30 (8) / H1 (4) EMA 50 rejection, and NOREJ (H4 EMA 50/90 direction only).  Rule,
exits, costs: research/bbma87.py.  Window: the last 2 years (owner); each line also with a RANDOM direction.
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
    out = {}
    for n in (7, 10, 14, 21):
        pos = mf.where(d > 0, 0.0).rolling(n).sum(); neg = mf.where(d < 0, 0.0).rolling(n).sum()
        out[f"mfi{n}"] = ((100 - 100 / (1 + pos / neg.replace(0, np.nan))).values, "osc")
    return out


FL = [("none", lambda F: F["r"] > -1e9)]
for n in (7, 10, 14, 21):
    for t in (50, 55, 60, 65):
        FL.append((f"MFI{n}>{t}", lambda F, n=n, t=t: F[f"mfi{n}"] > t))
    FL.append((f"MFI{n} rising >50", lambda F, n=n: (F[f"mfi{n}"] > 50) & (F[f"mfi{n}"] > F[f"mfi{n}_p"])))
FL += [("MFI14>50 & RSI14>55", lambda F: (F["mfi14"] > 50) & (F["r"] > 55)), ("MFI14<80", lambda F: F["mfi14"] < 80)]
B87.FEAT = feat
B87.EXTRA = FL
B87.RAND_EXTRA = True
B87.RTFS = ((30, "M30", 8), (60, "H1", 4), (0, "NOREJ", 0))


def main():
    DATA = B87.DATA
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    ALL = {}; END = None; vol0 = []
    for mode in ("basic", "all"):
        B87.CSAK_MODE = mode
        for sym in B87.SYMS:
            if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
            res, end, _ = B87.run_symbol(sym, meta[sym], SW.get(sym)); END = end if END is None else max(END, end)
            for k, df in res.items():
                df = df[df.t >= end - pd.Timedelta(days=730)]
                if len(df): ALL.setdefault((mode,) + k, []).append(df.assign(sym=sym))
        say(f"mode {mode} done [{time.time() - T0:.0f} s]")
    v = pd.read_csv(os.path.join(DATA, "XAUUSD.csv"), usecols=["v"]).v
    say(f"tick volume check (XAUUSD M5): median {v.median():.0f}, zero bars {100 * (v == 0).mean():.1f}%")
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; R pooled over 30 symbols; RAND = same entries, random direction; "
        f"PASS = >=150 trades, PF >= 1.15, both years >= 1.05, stress >= 1.05, last 12 months > 0, PF >= RAND + 0.10.  Rows with < 30 trades skipped.")
    say(f"{'csak | context | pop | filter | TP':52s} {'side':4s} {'n':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | "
        f"{'12m R':>6} {'3m R':>5} {'p3m R':>6} | {'sym>1':>6} | {'RAND PF':>7}")
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
            rows.append((P, f"{' | '.join(map(str, key[:4])) + f' | {key[4]}R':52s} {side:4s} {len(x):5d} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | "
                            f"{l12:+6.1f} {x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | {sum(g):2d}/{len(g):<3d} | {PR:7.2f} {'PASS' if ok else ''}", len(x)))
    for _, line, _ in rows: say(line)
    big = [r for r in rows if r[2] >= 150]
    say(f"\n=== {len(big)} rows with >= 150 trades; best 20 by PF ===")
    for _, line, _ in sorted(big, key=lambda z: -z[0])[:20]: say(line)
    say(f"PASS count: {sum('PASS' in r[1] for r in rows)}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
