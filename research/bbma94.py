"""Round 94 (12 Nov 2026): what, if anything, validates an M15 CSAK by itself?  Measure first, then trade.

Owner: "aduh tolong la cari satu signal yang boleh validkan csak tu sendiri! tolong lahh".  Rounds 83-93 bolted
indicators onto the CSAK one by one.  This round MEASURES every M15 CSAK (old 2-line definition, either direction,
01:30-22:00 server) on all 30 instruments over the last 2 years: its features at the close, and how far price then moves
IN the CSAK direction after 1 / 4 / 8 / 16 M15 candles, in ATR(14, M15) units, with the spread in ATR next to it.
Features (signed so that "more" = more in the CSAK direction where a sign makes sense): body / ATR, range / ATR,
close location in the candle, the wick against the CSAK, tick volume / its 20-candle mean, BB width / its 100-candle
median (squeeze < 1), distance from EMA 50 in ATR, EMA 50 slope over 4 candles in ATR, the move of the 8 candles before
it in ATR, H1 close vs H1 EMA 50 (+1 / -1), H4 EMA 50 vs 90 (+1 / -1), ADX 14, RSI 14, spread / ATR, session.
Buckets are the pooled quintiles of YEAR 1 (the first of the two years); the best bucket of each feature is picked
on year 1 only and then traded (part B) with that fixed threshold, so YEAR 2 is out of sample.
Part B: entries "next" (next open), "follow" (wait up to 2 M15 candles for a close beyond the CSAK's extreme) and
"retest" (limit at the CSAK's 50% within 4 M15 candles); SL beyond the CSAK, TP 1R / 2R, 48 h; context: H4 direction
only (NOREJ) and the SOP's M30 rejection; each row with a random-direction twin.  research/bbma87.py does the trading.
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


def feats(X):
    """features of each M15 candle, known at its close.  -> {name: (array | (buy, sell), kind)}"""
    I = B87.ind(X)
    c, o, h, l = X.c, X.o, X.h, X.l
    c1 = c.shift()
    tr = np.maximum(h - l, np.maximum((h - c1).abs(), (l - c1).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    rng = (h - l).replace(0, np.nan)
    up = h - h.shift(); dn = l.shift() - l
    pdm = up.where((up > dn) & (up > 0), 0.0); ndm = dn.where((dn > up) & (dn > 0), 0.0)
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr; ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    adx = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)).ewm(alpha=1 / 14, adjust=False).mean()
    bw = I.top - I.bot
    cl15 = (X.index + pd.Timedelta(minutes=15)).values
    def htf(m, span_a, span_b=None):
        g = X.resample(f"{m}min", label="left", closed="left")
        Y = pd.DataFrame({"c": g.c.last()}).dropna()
        ea = Y.c.ewm(span=span_a, adjust=False).mean().values
        eb = Y.c.ewm(span=span_b, adjust=False).mean().values if span_b else Y.c.values
        k = np.searchsorted((Y.index + pd.Timedelta(minutes=m)).values, cl15, side="right") - 1
        v = np.where(k >= 0, np.sign((eb if span_b is None else ea)[np.maximum(k, 0)] - (ea if span_b is None else eb)[np.maximum(k, 0)]), np.nan)
        return v
    hm = X.index.hour.values * 60 + X.index.minute.values
    return {
        "body/ATR": ((c - o).abs() / atr).values, "range/ATR": ((h - l) / atr).values,
        "close loc %": ((100 * (c - l) / rng).values, (100 * (h - c) / rng).values),
        "wick against %": ((100 * (h - np.maximum(o, c)) / rng).values, (100 * (np.minimum(o, c) - l) / rng).values),
        "tickvol/avg20": (X.v / X.v.rolling(20).mean().shift(1).replace(0, np.nan)).values,
        "BBwidth/med100": (bw / bw.rolling(100).median()).values,
        "dist EMA50 ATR": ((c - I.e50) / atr).values, "EMA50 slope4 ATR": ((I.e50 - I.e50.shift(4)) / atr).values,
        "move prior8 ATR": ((c1 - c.shift(9)) / atr).values,
        "H1 vs EMA50": htf(60, 50), "H4 EMA50vs90": htf(240, 50, 90),
        "ADX14": adx.values, "RSI14": I.rsi.values, "spread/ATR": (X.s / atr).values,
        "session": np.where(hm < 540, 0, np.where(hm < 930, 1, 2)).astype(float), "_atr": atr.values,
    }


KIND = {"close loc %": "pair", "wick against %": "pair", "dist EMA50 ATR": "sym", "EMA50 slope4 ATR": "sym", "move prior8 ATR": "sym",
        "H1 vs EMA50": "sym", "H4 EMA50vs90": "sym", "RSI14": "osc"}


def measure(DATA, meta):
    rows = []; END = None
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        d = SA.load(os.path.join(DATA, sym + ".csv"), meta[sym]["point"])
        B = d[["o", "h", "l", "c", "s", "v"]]
        g = B.resample("15min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        X["v"] = g.v.sum().reindex(X.index).fillna(0).values; X["s"] = g.s.median().reindex(X.index).values
        I = B87.ind(X); Fm = feats(X)
        lo, hi = np.minimum(I.mid, I.e50).values, np.maximum(I.mid, I.e50).values
        o, c = X.o.values, X.c.values
        cb = (o < lo) & (c > hi) & (c <= I.top.values); cs = (o > hi) & (c < lo) & (c >= I.bot.values)
        end = X.index[-1]; END = end if END is None else max(END, end)
        hm = X.index.hour.values * 60 + X.index.minute.values
        ks = np.where((cb | cs) & (hm >= 90) & (hm < 1320) & (X.index >= end - pd.Timedelta(days=730)) & (np.arange(len(X)) < len(X) - 17))[0]
        dr = np.where(cb[ks], 1, -1); atr = Fm["_atr"][ks]
        r = {"sym": sym, "t": X.index[ks], "dir": dr}
        for hh in (1, 4, 8, 16): r[f"f{hh}"] = (c[ks + hh] - c[ks]) * dr / atr
        for nm, a in Fm.items():
            if nm == "_atr": continue
            kd = KIND.get(nm, "raw")
            if kd == "pair": r[nm] = np.where(dr == 1, a[0][ks], a[1][ks])
            elif kd == "osc": r[nm] = np.where(dr == 1, a[ks], 100 - a[ks])
            elif kd == "sym": r[nm] = a[ks] * dr
            else: r[nm] = a[ks]
        rows.append(pd.DataFrame(r))
        say(f"{sym}: {len(ks)} CSAKs [{time.time() - T0:.0f} s]")
    D = pd.concat(rows, ignore_index=True)
    D["yr"] = (D.t >= END - pd.Timedelta(days=365)).astype(int)
    return D, END


def tstat(v):
    v = v[np.isfinite(v)]
    return v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 2 else 0.0


def main():
    DATA = B87.DATA
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    D, END = measure(DATA, meta)
    y1, y2 = D[D.yr == 0], D[D.yr == 1]
    say(f"\n===== PART A: {len(D):,} M15 CSAKs on 30 instruments, {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d} =====")
    say("forward move IN the CSAK direction, in ATR(M15); a real validator shifts f8 up in BOTH years.  Spread/ATR is the cost of one trade in the same unit.")
    say(f"ALL CSAKs: f1 {D.f1.mean():+.3f}  f4 {D.f4.mean():+.3f}  f8 {D.f8.mean():+.3f}  f16 {D.f16.mean():+.3f}  | year1 f8 {y1.f8.mean():+.3f}  year2 f8 {y2.f8.mean():+.3f} | "
        f"mean spread/ATR {D['spread/ATR'].mean():.3f}")
    say(f"\n{'feature':18s} {'bucket':>17s} {'n':>6} {'f1':>7} {'f4':>7} {'f8':>7} {'f16':>7} {'t(f8)':>6} | {'yr1 f8':>7} {'yr2 f8':>7} | {'spr':>5} {'f8-spr':>7}")
    chosen = {}
    feats_ = [c for c in D.columns if c not in ("sym", "t", "dir", "f1", "f4", "f8", "f16", "yr")]
    for nm in feats_:
        v1 = y1[nm].values; v1 = v1[np.isfinite(v1)]
        if len(v1) < 100: continue
        u = np.unique(v1)
        if len(u) <= 5: edges = [(a - 1e-9, a + 1e-9) for a in u]
        else:
            q = np.nanquantile(v1, [0, .2, .4, .6, .8, 1]); q[0], q[-1] = -np.inf, np.inf
            edges = list(zip(q[:-1], q[1:]))
        best = None
        for a, b in edges:
            m = (D[nm] > a) & (D[nm] <= b); x = D[m]; m1 = x[x.yr == 0]; m2 = x[x.yr == 1]
            lab = f"{a:.2f}..{b:.2f}" if len(u) > 5 else f"= {a + 1e-9:.0f}"
            say(f"{nm:18s} {lab:>17s} {len(x):6d} {x.f1.mean():+7.3f} {x.f4.mean():+7.3f} {x.f8.mean():+7.3f} {x.f16.mean():+7.3f} {tstat(x.f8.values):+6.1f} | "
                f"{m1.f8.mean():+7.3f} {m2.f8.mean():+7.3f} | {x['spread/ATR'].mean():5.3f} {x.f8.mean() - x['spread/ATR'].mean():+7.3f}")
            if len(m1) >= 300 and (best is None or m1.f8.mean() > best[0]): best = (m1.f8.mean(), a, b, m2.f8.mean())
        if best: chosen[nm] = best
        say()
    base1, base2 = y1.f8.mean(), y2.f8.mean()
    say("=== best bucket of each feature, chosen on YEAR 1; YEAR 2 is out of sample ===")
    for nm, (m1, a, b, m2) in sorted(chosen.items(), key=lambda z: -(z[1][0] - base1)):
        say(f"{nm:18s} ({a:.2f}, {b:.2f}]  year1 f8 {m1:+.3f} (base {base1:+.3f})  ->  year2 f8 {m2:+.3f} (base {base2:+.3f})  {'HOLDS' if m1 > base1 and m2 > base2 + 0.02 else ''}")
    # ---------- PART B: trade the year-1 choices
    top = [nm for nm, (m1, a, b, m2) in sorted(chosen.items(), key=lambda z: -(z[1][0] - base1)) if m1 > base1 + 0.02][:8]
    def rng_f(nm, a, b): return lambda F: (F[nm] > a) & (F[nm] <= b)
    FL = [("none", lambda F: F["r"] > -1e9)] + [(f"{nm} in yr1 best", rng_f(nm, chosen[nm][1], chosen[nm][2])) for nm in top]
    if len(top) >= 2:
        (n1, n2) = top[:2]
        FL.append((f"{n1} + {n2}", lambda F, f1=rng_f(n1, *chosen[n1][1:3]), f2=rng_f(n2, *chosen[n2][1:3]): f1(F) & f2(F)))
    def featB(X): return {nm: (v, KIND.get(nm, "raw")) for nm, v in feats(X).items() if nm != "_atr"}
    B87.FEAT = featB; B87.EXTRA = FL; B87.RAND_EXTRA = True
    B87.RTFS = ((30, "M30", 8), (0, "NOREJ", 0)); B87.CSAK_MODE = "basic"; B87.EXIT_MODE = "sl"; B87.TPS = (1, 2)
    ALL = {}
    for em in ("next", "follow", "retest"):
        B87.ENTRY_MODE = em
        for sym in B87.SYMS:
            if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
            res, end, _ = B87.run_symbol(sym, meta[sym], SW.get(sym))
            for k, df in res.items():
                df = df[df.t >= end - pd.Timedelta(days=730)]
                if len(df): ALL.setdefault((em,) + k, []).append(df.assign(sym=sym))
        say(f"part B entry {em} done [{time.time() - T0:.0f} s]")
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\n===== PART B: trading the year-1 choices (year 2 out of sample).  R pooled over 30 symbols.  PASS = >=150 trades, PF >= 1.15, both years >= 1.05, "
        f"stress >= 1.05, last 12 months > 0, PF >= RAND + 0.10 =====")
    say(f"{'entry | context | pop | filter | TP':70s} {'side':4s} {'n':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'12m R':>6} {'3m R':>5} {'p3m R':>6} | {'RAND':>5}")
    for key, L in ALL.items():
        if key[3].endswith("RANDOM dir") or key[2] != "ANY": continue
        R = pd.concat(L); Rr = pd.concat(ALL.get(key[:3] + (key[3] + " RANDOM dir",) + key[4:], [R.iloc[:0]]))
        for side, sd in (("BUY", 1), ("SELL", -1), ("ALL", 0)):
            x = R if sd == 0 else R[R.d == sd]; xr = Rr if sd == 0 else Rr[Rr.d == sd]
            if len(x) < 30: continue
            P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values)
            l12 = x.r[x.t >= mid].sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
            say(f"{' | '.join(map(str, key[:4])) + f' | {key[4]}R':70s} {side:4s} {len(x):5d} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | "
                f"{l12:+6.1f} {x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | {PR:5.2f} {'PASS' if ok else ''}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
