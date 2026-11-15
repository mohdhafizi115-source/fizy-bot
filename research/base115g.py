"""Round 115g (15 Nov 2026): is the ZONE THICKNESS the missing validation?  Round 115f split the live v2.32 fills by base height /
ATR(H1): thin (< 0.41) PF 0.86 with both years < 1, mid 1.66, thick (> 0.58) 2.41 with both years 2.4.  Checks:
  1. finer non-overlapping bands of height / ATR(H1) (ATR = mean H1 range of the 14 H1 bars up to and including the base bar),
  2. the cumulative filter "height >= x ATR" judged with the full pass rule,
  3. bands of the height in $,
  4. SL control: the same zones but the SL at least 0.6 ATR(H1) from the level (if thin bases then work, the cause is the tight stop,
     not the zone),
  5. RANDOM H1 bar of the same day (02-20, 3 seeds) as the zone, same colour rule and the same thickness filter.
Gold M1, last 2 years, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit


@jit
def run_g(O, H, L, C, S, hm, eod, dayend, zhi, zlo, zs, ze, zdir, zminsl, usd):
    nz = len(zhi); pn = np.zeros(nz); xi = np.full(nz, -1, np.int64)
    for z in range(nz):
        hi = zhi[z]; lo = zlo[z]; ht = hi - lo; want = zdir[z]; j = zs[z]
        if ht <= 0 or want == 0: continue
        side = False; d = 0; ent = 0.0; sl = 0.0; dead = False
        while j < ze[z]:
            if dayend[j]:
                if (want == 1 and C[j] < lo) or (want == -1 and C[j] > hi): dead = True; break
            if hm[j] < 90 or hm[j] >= 1380: j += 1; continue
            if not side:
                if (want == 1 and C[j] > hi) or (want == -1 and C[j] < lo): side = True
                j += 1; continue
            buf = S[j] + 0.1 * ht
            if want == 1 and L[j] + S[j] <= hi:
                d = 1; ent = min(O[j] + S[j], hi); sl = min(lo - buf, hi - zminsl[z]); break
            if want == -1 and H[j] >= lo:
                d = -1; ent = max(O[j], lo); sl = max(hi + buf, lo + zminsl[z]); break
            j += 1
        if dead or d == 0: continue
        e = eod[j]; px = 0.0; done = False
        if d == 1 and L[j] <= sl: px = sl; done = True
        if d == -1 and H[j] + S[j] >= sl: px = sl; done = True
        k = j + 1
        while not done and k <= e:
            if d == 1 and L[k] <= sl: px = min(O[k], sl); done = True
            elif d == -1 and H[k] + S[k] >= sl: px = max(O[k] + S[k], sl); done = True
            if not done: k += 1
        if not done:
            k = e; px = O[e] if d == 1 else O[e] + S[e]
        pn[z] = (px - ent) * d * usd; xi[z] = k
    return pn, xi


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start - pd.Timedelta(days=10)][["o", "h", "l", "c", "s"]]
    O, H, L, C, S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = B.index; N = len(O)
    hm = (T.hour.values * 60 + T.minute.values).astype(np.int64)
    day = T.normalize()
    pos = pd.Series(np.arange(N), index=T)
    lastbar = pos.groupby(day).transform("max").values
    cut = pd.Series(np.where(hm >= 1410, np.arange(N), N + 1), index=T).groupby(day).transform("min").values
    eod = np.minimum(cut, lastbar).astype(np.int64)
    dayend = (np.arange(N) == lastbar)
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["d"] = day
    d1 = b.groupby("d").agg(o=("o", "first"), c=("c", "last"))
    h1 = b.groupby(["d", "hr"]).agg(h=("h", "max"), l=("l", "min"))
    h1["atr"] = (h1.h - h1.l).rolling(14).mean().values
    say(f"ZONE THICKNESS: gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot, live v2.32 rule, filter on base height / ATR(H1)")
    hdr = (f"{'variant':46s} {'trades':>6} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5} {'risk$':>5}")

    def zones(randseed=None):
        rng = np.random.default_rng(randseed if randseed is not None else 0)
        rows = []
        for dd in days:
            if dd < start or dd not in d1.index: continue
            nx = days[days > dd]
            if len(nx) < 1: continue
            D = d1.loc[dd]; col = -1 if D.c < D.o else (1 if D.c > D.o else 0)
            if col == 0: continue
            hr = 23 if randseed is None else int(rng.integers(2, 21))
            if (dd, hr) not in h1.index: continue
            r = h1.loc[(dd, hr)]
            if r.h <= r.l or not np.isfinite(r.atr) or r.atr <= 0: continue
            rows.append(dict(hi=r.h, lo=r.l, want=-col, zs=first_of_day[nx[0]], ze=eod[first_of_day[nx[min(5, len(nx)) - 1]]] + 1,
                             ratio=(r.h - r.l) / r.atr, usdh=(r.h - r.l) * usd, atr=r.atr))
        return pd.DataFrame(rows)

    def run(Z, mask, nm, minsl=None):
        Zm = Z[mask]
        if len(Zm) == 0: say(f"{nm:46s}      0"); return
        ms = np.zeros(len(Zm)) if minsl is None else minsl[mask]
        args = (Zm.hi.values, Zm.lo.values, Zm.zs.values.astype(np.int64), Zm.ze.values.astype(np.int64), Zm.want.values.astype(np.int64), ms)
        p, xi = run_g(O, H, L, C, S, hm, eod, dayend, *args, usd)
        pS, xS = run_g(O, H, L, C, S * 1.5, hm, eod, dayend, *args, usd)
        ok = xi >= 0; p = p[ok]; te = T[xi[ok]]
        if len(p) < 15: say(f"{nm:46s} {len(p):6d}  (too few)"); return
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        risk = (Zm.usdh.values[ok] * 1.1)
        say(f"{nm:46s} {len(p):6d} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(pS[xS >= 0]):5.2f} | "
            f"{p.sum():+6.0f} {p[te >= mid].sum():+5.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {ddn:+5.0f} {dp.min():+5.0f} {np.median(risk):5.1f}")

    Z = zones()
    say(f"\nbase height / ATR(H1): quartiles {np.round(Z.ratio.quantile([.25, .5, .75]).values, 2)}, in $ at 0.01 lot {np.round(Z.usdh.quantile([.25, .5, .75]).values, 1)}")
    say("\n== 1. bands of height / ATR(H1), each on its own\n" + hdr)
    for lo_, hi_ in ((0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, .8), (.8, 1.2), (1.2, 99)):
        run(Z, (Z.ratio >= lo_) & (Z.ratio < hi_), f"   {lo_:.1f}-{hi_:.1f} ATR")
    say("\n== 2. filter: height >= x ATR(H1)\n" + hdr)
    for x in (0, .3, .4, .5, .6, .7, .8, 1.0):
        run(Z, Z.ratio >= x, f"   >= {x:.1f} ATR" + ("  (live, no filter)" if x == 0 else ""))
    say("\n== 3. bands of the height in $ (0.01 lot)\n" + hdr)
    for lo_, hi_ in ((0, 3), (3, 5), (5, 7), (7, 10), (10, 15), (15, 999)):
        run(Z, (Z.usdh >= lo_) & (Z.usdh < hi_), f"   ${lo_}-{hi_}")
    say("\n== 4. SL control: SL at least k x ATR(H1) from the level (thin bases get a wider stop)\n" + hdr)
    for k in (0.6, 0.8, 1.0):
        ms = (k * Z.atr).values
        run(Z, Z.ratio < 0.5, f"   thin (< 0.5 ATR) bases, SL >= {k} ATR", ms)
        run(Z, Z.ratio >= 0, f"   all bases, SL >= {k} ATR", ms)
    say("\n== 5. control: a RANDOM H1 bar of the same day (02-20) as the zone, same colour rule\n" + hdr)
    for sd in (1, 2, 3):
        R = zones(sd)
        run(R, R.ratio >= 0, f"   random bar seed {sd}, no filter")
        run(R, R.ratio < 0.5, f"   random bar seed {sd}, < 0.5 ATR")
        run(R, R.ratio >= 0.5, f"   random bar seed {sd}, >= 0.5 ATR")


if __name__ == "__main__":
    main()
