"""Round 90 (12 Nov 2026): TUNED indicator settings on the BBMA M15 CSAK, chosen in sample and checked out of sample.

Owner: "kau tak boleh ikut tetapan default untuk indikator, kau kena smart iaitu modified ke arah yang lebih tepat".
Rule, exits and costs: research/bbma87.py (H4 EMA 50/90 + H4 momentum + M30 / H1 EMA 50 rejection, M15 CSAK either
way, SL beyond the CSAK, TP 1R / 2R, broker swaps), on all 30 instruments.
Grid on the CSAK candle, signed in the CSAK direction: RSI 5 / 7 / 9 / 14 / 21 above 50 / 55 / 60 / 65 and rising
above 50; Stochastic %K 5 / 9 / 14 / 21 with smoothing 1 / 3 (%D = 3-bar mean): K>D, K>50, K>D & K>50, K rising,
K>D & K<80; CCI 10 / 14 / 20 / 30 / 50 above 0 / 50 / 100 and rising above 0.  86 filters x 2 rejection TF x 3
populations x 2 TP = 1,032 variants, each also with a random direction.
HONEST TUNING: the settings are chosen on the IN-SAMPLE period only (start .. 6 months before the end of the data),
then judged on the 6 months the choice never saw (the 3 months before the last 3, and the last 3).  Also per pair:
the best variant of each pair chosen in sample, its out-of-sample result summed over the pairs, against picking a
variant at random for each pair.
"""
import os, sys, time
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87

say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0


def feat(X):
    c, h, l = X.c, X.h, X.l
    out = {}
    dl = c.diff()
    for p in (5, 7, 9, 14, 21):
        up = dl.clip(lower=0).ewm(alpha=1 / p, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=1 / p, adjust=False).mean()
        out[f"rsi{p}"] = ((100 - 100 / (1 + up / dn.replace(0, np.nan))).values, "osc")
    for k in (5, 9, 14, 21):
        ll, hh = l.rolling(k).min(), h.rolling(k).max()
        raw = 100 * (c - ll) / (hh - ll).replace(0, np.nan)
        for s in (1, 3):
            K = raw.rolling(s).mean() if s > 1 else raw
            out[f"sk{k}_{s}"] = (K.values, "osc"); out[f"sd{k}_{s}"] = (K.rolling(3).mean().values, "osc")
    tp = ((h + l + c) / 3).values
    for p in (10, 14, 20, 30, 50):
        w = swv(tp, p); m = w.mean(1); md = np.abs(w - m[:, None]).mean(1)
        cci = np.full(len(tp), np.nan); cci[p - 1:] = (tp[p - 1:] - m) / (0.015 * np.where(md > 0, md, np.nan))
        out[f"cci{p}"] = (cci, "sym")
    return out


FL = [("none", lambda F: F["r"] > -1e9)]
for p in (5, 7, 9, 14, 21):
    for t in (50, 55, 60, 65):
        FL.append((f"RSI{p}>{t}", lambda F, p=p, t=t: F[f"rsi{p}"] > t))
    FL.append((f"RSI{p} rising >50", lambda F, p=p: (F[f"rsi{p}"] > 50) & (F[f"rsi{p}"] > F[f"rsi{p}_p"])))
for k in (5, 9, 14, 21):
    for s in (1, 3):
        K, D = f"sk{k}_{s}", f"sd{k}_{s}"
        FL += [(f"ST{k},{s} K>D", lambda F, K=K, D=D: F[K] > F[D]), (f"ST{k},{s} K>50", lambda F, K=K: F[K] > 50),
               (f"ST{k},{s} K>D&K>50", lambda F, K=K, D=D: (F[K] > F[D]) & (F[K] > 50)),
               (f"ST{k},{s} K rising", lambda F, K=K: F[K] > F[K + "_p"]),
               (f"ST{k},{s} K>D&K<80", lambda F, K=K, D=D: (F[K] > F[D]) & (F[K] < 80))]
for p in (10, 14, 20, 30, 50):
    for t in (0, 50, 100):
        FL.append((f"CCI{p}>{t}", lambda F, p=p, t=t: F[f"cci{p}"] > t))
    FL.append((f"CCI{p} rising >0", lambda F, p=p: (F[f"cci{p}"] > 0) & (F[f"cci{p}"] > F[f"cci{p}_p"])))
B87.FEAT = feat
B87.EXTRA = FL


def main():
    DATA = B87.DATA
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    ALL = {}; ends = []
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        res, end, _ = B87.run_symbol(sym, meta[sym], SW.get(sym)); ends.append(end)
        for k, df in res.items():
            if len(df): ALL.setdefault(k, []).append(df.assign(sym=sym))
        say(f"{sym} done [{time.time() - T0:.0f} s]")
    END = max(ends); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\ndata end {END:%Y-%m-%d}. IN SAMPLE = start .. {a6:%Y-%m-%d}; OUT OF SAMPLE = {a6:%Y-%m-%d} .. {a3:%Y-%m-%d} (OOS-1) and {a3:%Y-%m-%d} .. end (OOS-2)")
    rows = []
    for key, L in ALL.items():
        if key[2].endswith("RANDOM dir"): continue
        R = pd.concat(L); Rr = pd.concat(ALL.get(key[:2] + (key[2] + " RANDOM dir",) + key[3:], [R.iloc[:0]]))
        for side, sd in (("BUY", 1), ("SELL", -1), ("ALL", 0)):
            x = R if sd == 0 else R[R.d == sd]; xr = Rr if sd == 0 else Rr[Rr.d == sd]
            ins = x[x.t < a6]; o1 = x[(x.t >= a6) & (x.t < a3)]; o2 = x[x.t >= a3]
            r1 = xr[(xr.t >= a6) & (xr.t < a3)]; r2 = xr[xr.t >= a3]
            mi = ins.t.min() + (ins.t.max() - ins.t.min()) / 2 if len(ins) else a6
            rows.append(dict(name=" | ".join(map(str, key[:3])) + f" | TP {key[3]}R", side=side, n=len(ins), pf=pf(ins.r.values),
                             h1=pf(ins.r[ins.t < mi].values), h2=pf(ins.r[ins.t >= mi].values), sym=(ins.groupby("sym").net.sum() > 0).sum(),
                             n1=len(o1), pf1=pf(o1.r.values), R1=o1.r.sum(), n2=len(o2), pf2=pf(o2.r.values), R2=o2.r.sum(),
                             rR1=r1.r.sum(), rR2=r2.r.sum()))
    D = pd.DataFrame(rows)
    say(f"{len(D)} variant x side rows.  In-sample PF over all rows: median {D.pf.median():.2f}, best {D.pf.max():.2f}")
    hdr = (f"{'variant':44s} {'side':4s} | {'IS n':>5} {'PF':>5} {'h1':>5} {'h2':>5} {'sym+':>4} | {'OOS-1 n':>7} {'PF':>5} {'R':>6} | {'OOS-2 n':>7} {'PF':>5} {'R':>6} | {'random R1':>9} {'R2':>6}")
    def show(T):
        say(hdr)
        for _, r in T.iterrows():
            say(f"{r['name']:44s} {r.side:4s} | {r.n:5d} {r.pf:5.2f} {r.h1:5.2f} {r.h2:5.2f} {r.sym:4d} | {r.n1:7d} {r.pf1:5.2f} {r.R1:+6.1f} | {r.n2:7d} {r.pf2:5.2f} {r.R2:+6.1f} | {r.rR1:+9.1f} {r.rR2:+6.1f}")
    ok = D[(D.n >= 300)]
    say(f"\n=== TOP 25 BY IN-SAMPLE PF (>= 300 in-sample trades pooled), then what they did out of sample ===")
    show(ok.sort_values("pf", ascending=False).head(25))
    ok2 = D[(D.n >= 300) & (D.h1 >= 1) & (D.h2 >= 1)]
    say(f"\n=== in-sample PF >= 1 in BOTH in-sample halves (>= 300 trades): {len(ok2)} rows ===")
    if len(ok2): show(ok2.sort_values("pf", ascending=False).head(25))
    E = D[(D.n >= 300) & (D.n1 >= 20) & (D.n2 >= 20)]
    if len(E) > 10:
        say(f"\nDoes in-sample rank predict out of sample?  {len(E)} rows with >= 20 trades in each OOS window: "
            f"Spearman(IS PF, OOS-1 PF) {E.pf.corr(E.pf1, method='spearman'):+.2f}, (IS PF, OOS-2 PF) {E.pf.corr(E.pf2, method='spearman'):+.2f}")
        top = E.sort_values("pf", ascending=False).head(max(10, len(E) // 10))
        say(f"positive in BOTH OOS windows: top 10% by IS PF {((top.R1 > 0) & (top.R2 > 0)).mean() * 100:.0f}% of {len(top)}, all rows {((E.R1 > 0) & (E.R2 > 0)).mean() * 100:.0f}% of {len(E)}; "
            f"mean OOS R per row: top {top.R1.mean():+.1f} / {top.R2.mean():+.1f}, all {E.R1.mean():+.1f} / {E.R2.mean():+.1f}")
    say(f"\n=== best variant per PAIR chosen in sample (>= 40 in-sample trades for that pair), out-of-sample $ per 0.01 lot ===")
    per = {}
    for key, L in ALL.items():
        if key[2].endswith("RANDOM dir"): continue
        for x in L:
            s = x.sym.iloc[0]; ins = x[x.t < a6]
            if len(ins) < 40: continue
            per.setdefault(s, []).append((pf(ins.r.values), key, x[(x.t >= a6) & (x.t < a3)].net.sum(), x[x.t >= a3].net.sum(), len(x[x.t >= a6])))
    rg = np.random.default_rng(90); tot = [0.0, 0.0]; rnd = []
    say(f"{'sym':8s} {'chosen in sample':52s} {'IS PF':>5} | {'OOS-1 $':>8} {'OOS-2 $':>8} {'n':>4}")
    for s, v in per.items():
        b = max(v, key=lambda z: z[0]); tot[0] += b[2]; tot[1] += b[3]
        say(f"{s:8s} {' | '.join(map(str, b[1])):52s} {b[0]:5.2f} | {b[2]:+8.1f} {b[3]:+8.1f} {b[4]:4d}")
    for _ in range(200):
        a = [0.0, 0.0]
        for s, v in per.items():
            z = v[rg.integers(len(v))]; a[0] += z[2]; a[1] += z[3]
        rnd.append(a)
    rnd = np.array(rnd)
    say(f"TOTAL tuned per pair: OOS-1 ${tot[0]:+.0f}, OOS-2 ${tot[1]:+.0f}  |  a RANDOM variant per pair (200 draws): mean ${rnd[:, 0].mean():+.0f} / ${rnd[:, 1].mean():+.0f}, "
        f"share of draws beating tuned {(rnd.sum(1) > sum(tot)).mean() * 100:.0f}%")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
