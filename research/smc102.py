"""Round 102 (13 Nov 2026): Smart Money Concepts, the full mechanical model, on the broker's data, LAST 2 YEARS,
28 forex pairs + XAUUSD.  Owner: "kau tolong fahami teknik smc bro, aku nak kali ni versi yang paling tepat dan stabil.
kau test pada tf yg relevan".

The rules are the common checklist of the SMC guides (TradingView "SMC Mechanical Entry Models" cheatsheet, MQL5
"Complete SMC Trading Guide", LuxAlgo SMC/ICT family, XS.com SMC course):
  structure   fractal swing highs / lows (n 3 or 5 bars, known only n bars later = no look-ahead); a close beyond the last
              swing high is a bullish break: BOS when the trend was already bullish, CHoCH when it was bearish (sell mirrored)
  impulse     the leg from the lowest low between the broken swing high and the break (the protected low) to the break
  liquidity   SWEEP = that protected low took out the swing low that stood before it (sell-side liquidity grabbed)
  order block the last bearish candle at or just before the protected low (bull); unmitigated until price returns
  FVG         a 3-candle gap inside the impulse (low[i] > high[i-2]); "displacement" = the impulse left an FVG
  entries     limit at the OB top (proximal), OB 50%, FVG top, FVG 50% (consequent encroachment), OTE 0.705 of the leg
  cancel      the limit is cancelled if price closes beyond the protected low, if structure breaks the other way first,
              or after 30 bars unfilled
  SL          beyond the protected low (the swing low of the leg) + 0.1 ATR + spread
  TP          2R, 3R, or the external liquidity = the high of the impulse (only when it is >= 1R away)
  HTF bias    the same structure logic on the higher timeframe: trade only with its last break
  discount    buy only below the middle of the HTF dealing range (last HTF swing low .. high); sell only above it
  killzone    the fill happens in London 09-12 or New York 14-17 server time (07-10 / 12-15 London)
Timeframe pairs (setup / bias): M5 / H1, M15 / H4, H1 / D1.  Simulated on the entry timeframe's bars, SL first when SL and
TP fall in one bar (conservative), swaps per night, rollover fills (00:00-01:30 server) dropped, one position per symbol.
Controls: every trade has a RANDOM-direction twin at the same fill time and price with the same risk and target in R.
Pass rule: >= 150 trades, PF >= 1.15 (in R), both years >= 1.05, last 12 months positive, PF >= random + 0.10;
settings chosen on YEAR 1 are then judged on YEAR 2.
"""
import os, sys, time, itertools, zlib
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87
import div100 as D

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
SYMS = [s for s in B87.SYMS if s != "BTCUSD"]
PAIRS = ((5, 60), (15, 240), (60, 1440))
NS = (3, 5)
WAIT, HOLD = 30, 48
ENTRIES = ("OB top", "OB 50%", "FVG top", "FVG 50%", "OTE 0.705")
TPS = ("2R", "3R", "liquidity")
try:
    from numba import njit
except Exception:
    njit = None


def _kernel(O, H, L, C, S, day, wd, t0, dr, E, SLp, cancel, tpp, rdir, W, HOLD, swl, sws, d3):
    """per setup: fill bar, then for each of 3 targets the exit R for the signal and for a random-direction twin"""
    n = len(O); m = len(t0)
    fill = np.full(m, -1, np.int64); fp = np.zeros(m)
    R = np.full((m, 3), np.nan); RR = np.full((m, 3), np.nan); X = np.full((m, 3), -1, np.int64)
    for s in range(m):
        d = dr[s]; e = E[s]; sl = SLp[s]; z = t0[s] + 1; zend = min(t0[s] + W, cancel[s] - 1, n - 2)
        f = -1; px = 0.0
        while z <= zend:
            if d == 1:
                if L[z] + S[z] <= e: f = z; px = min(e, O[z] + S[z]); break
                if C[z] < sl: break
            else:
                if H[z] >= e: f = z; px = max(e, O[z]); break
                if C[z] > sl: break
            z += 1
        if f < 0: continue
        risk = (px - sl) * d
        if risk <= 2 * S[f]: continue
        fill[s] = f; fp[s] = px
        for k in range(3):
            tpR = tpp[s, k]
            if not (tpR >= 1.0): continue
            for twin in range(2):
                dd = d if twin == 0 else rdir[s]
                # the twin enters at the same moment at the market price of its side
                ent = px if twin == 0 else (O[f] + S[f] if dd == 1 else O[f])
                stop = ent - dd * risk; tgt = ent + dd * tpR * risk
                zz = f; nights = 0; xr = np.nan; xb = -1
                while zz < n:
                    if zz > f and day[zz] != day[zz - 1]:
                        nights += 3 if (1 <= d3 <= 5 and wd[zz - 1] == d3 - 1) else 1
                    if zz - f >= HOLD:
                        xp = O[zz] + (S[zz] if dd == -1 else 0.0); xr = (xp - ent) * dd / risk; xb = zz; break
                    if dd == 1:
                        if L[zz] <= stop:
                            xp = min(O[zz], stop) if zz > f else stop; xr = (xp - ent) / risk; xb = zz; break
                        if zz > f and H[zz] >= tgt:
                            xp = max(O[zz], tgt); xr = (xp - ent) / risk; xb = zz; break
                    else:
                        if H[zz] + S[zz] >= stop:
                            xp = max(O[zz] + S[zz], stop) if zz > f else stop; xr = (ent - xp) / risk; xb = zz; break
                        if zz > f and L[zz] + S[zz] <= tgt:
                            xp = min(O[zz] + S[zz], tgt); xr = (ent - xp) / risk; xb = zz; break
                    zz += 1
                if xb < 0: continue
                xr += ((swl if dd == 1 else sws) * nights) / risk
                if twin == 0: R[s, k] = xr; X[s, k] = xb
                else: RR[s, k] = xr
    return fill, fp, R, RR, X


KER = njit(cache=False)(_kernel) if njit else _kernel


def structure(H, L, C, n):
    """online swings and breaks.  Returns per-bar trend after the bar, and the list of breaks
    (bar, dir, type BOS/CHoCH, broken swing index, protected extreme index, sweep flag)"""
    N = len(C); ph, pl = D.pivots(H, n, False), D.pivots(L, n, True)
    sh = sl = np.nan; shi = sli = -1; sh_used = sl_used = True
    prev_sl = prev_sh = np.nan; tr = 0; trend = np.zeros(N, np.int8); brk = []
    for t in range(N):
        j = t - n                                   # a pivot at j becomes known at t
        if j >= 0:
            if ph[j]: prev_sh = sh; sh, shi, sh_used = H[j], j, False
            if pl[j]: prev_sl = sl; sl, sli, sl_used = L[j], j, False
        if not sh_used and C[t] > sh:
            a = shi; lo = a + int(np.argmin(L[a:t + 1])); typ = "BOS" if tr == 1 else "CHoCH"
            ref = sl if sli < lo else prev_sl                   # the swing low standing before the protected low
            brk.append((t, 1, typ, a, lo, bool(not np.isnan(ref) and L[lo] < ref))); tr = 1; sh_used = True
        elif not sl_used and C[t] < sl:
            a = sli; hi = a + int(np.argmax(H[a:t + 1])); typ = "BOS" if tr == -1 else "CHoCH"
            ref = sh if shi < hi else prev_sh
            brk.append((t, -1, typ, a, hi, bool(not np.isnan(ref) and H[hi] > ref))); tr = -1; sl_used = True
        trend[t] = tr
    return trend, brk


def bars(B, m):
    if m == 5: X = B.copy()
    else:
        g = B.resample(f"{m}min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        X["s"] = g.s.median().reindex(X.index).values
    return X


def run(sym, mt, sw):
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    B = d[["o", "h", "l", "c", "s"]].copy(); del d
    end = B.index[-1]; start = end - pd.Timedelta(days=730)
    swl = (sw["long"] * mt["point"]) if sw and sw["mode"] == 1 else 0.0
    sws = (sw["short"] * mt["point"]) if sw and sw["mode"] == 1 else 0.0
    d3 = int(sw["d3"]) if sw else 3
    rows = []
    for m, hm_ in PAIRS:
        X = bars(B, m); X = X[X.index >= start - pd.Timedelta(minutes=m * 3000)]
        HX = bars(B, hm_)
        O, H, L, C, S = (X[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
        T = X.index; N = len(X); day = T.normalize().values.astype("datetime64[D]").astype(np.int64)
        wd = T.day_of_week.values.astype(np.int64); hmin = (T.hour.values * 60 + T.minute.values)
        c1 = np.r_[C[0], C[:-1]]
        atr = pd.Series(np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))).ewm(alpha=1 / 14, adjust=False).mean().values
        cl = (T + pd.Timedelta(minutes=m)).values
        hO, hH, hL, hC = (HX[k].values.astype(float) for k in ("o", "h", "l", "c"))
        hcl = (HX.index + pd.Timedelta(minutes=hm_)).values
        htr, _ = structure(hH, hL, hC, 3)
        hph, hpl = D.pivots(hH, 3, False), D.pivots(hL, 3, True)
        # last confirmed HTF swing high / low (known 3 bars later)
        lsh = pd.Series(np.where(np.r_[np.zeros(3, bool), hph[:-3]], np.r_[np.full(3, np.nan), hH[:-3]], np.nan)).ffill().values
        lsl = pd.Series(np.where(np.r_[np.zeros(3, bool), hpl[:-3]], np.r_[np.full(3, np.nan), hL[:-3]], np.nan)).ffill().values
        kH = np.searchsorted(hcl, cl, side="right") - 1          # last HTF bar closed by the entry bar's close
        valid = T >= start
        for n in NS:
            trend, brk = structure(H, L, C, n)
            bt = np.array([b[0] for b in brk]); bd = np.array([b[1] for b in brk])
            setups = []
            for q, (t, dr, typ, a, ex, sweep) in enumerate(brk):
                if not valid[t] or t >= N - 2 or kH[t] < 0: continue
                # next break the other way cancels the order
                nxt = np.where((bt > t) & (bd == -dr))[0]; cancel = bt[nxt[0]] if len(nxt) else N
                legx = (H[ex:t + 1].max() if dr == 1 else L[ex:t + 1].min())    # the impulse's far end
                prot = L[ex] if dr == 1 else H[ex]
                # order block: last opposite candle at or up to 5 bars before the protected extreme
                ob = -1
                for k in range(ex, max(ex - 6, 0), -1):
                    if (dr == 1 and C[k] < O[k]) or (dr == -1 and C[k] > O[k]): ob = k; break
                if ob < 0: ob = ex
                obt, obb = (H[ob], L[ob]) if dr == 1 else (L[ob], H[ob])    # proximal, distal
                # FVG inside the impulse
                fv = -1
                for i in range(ex + 2, t + 1):
                    if (dr == 1 and L[i] > H[i - 2]) or (dr == -1 and H[i] < L[i - 2]): fv = i; break
                buf = 0.1 * atr[t] + S[t]
                slp = prot - buf if dr == 1 else prot + buf
                ent = {"OB top": obt, "OB 50%": (obt + obb) / 2, "OTE 0.705": legx - dr * 0.705 * abs(legx - prot)}
                if fv > 0:
                    ftop, fbot = (L[fv], H[fv - 2]) if dr == 1 else (H[fv], L[fv - 2])
                    ent["FVG top"] = ftop; ent["FVG 50%"] = (ftop + fbot) / 2
                hb = kH[t]
                hmid = (lsh[hb] + lsl[hb]) / 2 if not (np.isnan(lsh[hb]) or np.isnan(lsl[hb])) else np.nan
                for en, e in ent.items():
                    if (e - slp) * dr <= 0 or (legx - e) * dr <= 0: continue
                    disc = (not np.isnan(hmid)) and ((e < hmid) if dr == 1 else (e > hmid))
                    setups.append((t, dr, e, slp, cancel, legx, en, typ, sweep, htr[hb] == dr, disc, fv > 0))
            if not setups: continue
            sa = np.array([s[0] for s in setups], np.int64); sd = np.array([s[1] for s in setups], np.int64)
            se = np.array([s[2] for s in setups]); ss = np.array([s[3] for s in setups]); sc = np.array([s[4] for s in setups], np.int64)
            liqR = np.array([abs(s[5] - s[2]) / abs(s[2] - s[3]) for s in setups])
            tpp = np.column_stack([np.full(len(setups), 2.0), np.full(len(setups), 3.0), liqR])
            rdir = np.where(np.random.default_rng(zlib.crc32(f"{sym}{m}{n}".encode())).random(len(setups)) < 0.5, 1, -1).astype(np.int64)
            fill, fp, Rm, RRm, Xm = KER(O, H, L, C, S, day, wd, sa, sd, se, ss, sc, tpp, rdir, WAIT, HOLD, swl, sws, d3)
            for i, s in enumerate(setups):
                f = fill[i]
                if f < 0 or hmin[f] < 90: continue
                hr = T[f].hour
                kz = (9 <= hr < 12) or (14 <= hr < 17)
                risk_usd = abs(fp[i] - ss[i]) * usd
                for k, tpn in enumerate(TPS):
                    if np.isnan(Rm[i, k]): continue
                    rows.append((m, n, s[1], s[6], tpn, s[7], s[8], s[9], s[10], s[11], kz, T[f], f, Xm[i, k], Rm[i, k], RRm[i, k],
                                 risk_usd, S[f] / abs(fp[i] - ss[i])))
    df = pd.DataFrame(rows, columns=["tf", "n", "d", "entry", "tp", "typ", "sweep", "htf", "disc", "fvg", "kz", "t", "fb", "xb", "r", "rr", "risk", "sp"])
    for c in ("entry", "tp", "typ"): df[c] = df[c].astype("category")
    for c in ("r", "rr", "risk", "sp"): df[c] = df[c].astype("float32")
    df["sym"] = sym; df["sym"] = df["sym"].astype("category")
    return df, end


def busy(df):
    """one position per symbol per variant: keep a trade only if the symbol has no open trade"""
    keep = np.zeros(len(df), bool); last = {}
    for i, (sy, f, x) in enumerate(zip(df.sym.values, df.fb.values, df.xb.values)):
        if f > last.get(sy, -1): keep[i] = True; last[sy] = x
    return df[keep]


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    say(f"numba: {'yes' if njit else 'no (pure python)'}")
    parts = []; END = None
    for sym in SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        df, end = run(sym, meta[sym], SW.get(sym)); parts.append(df); END = end if END is None else max(END, end)
        say(f"{sym} done, {len(df)} trade rows [{time.time() - T0:.0f} s]")
    A = pd.concat(parts, ignore_index=True)
    for c in ("entry", "tp", "typ", "sym"): A[c] = A[c].astype(str).astype("category")
    A = A.sort_values("t", kind="stable").reset_index(drop=True)
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; 28 forex + XAUUSD; R = profit / initial risk, pooled; "
        f"{len(A):,} trade rows")
    TFN = {5: "M5/H1", 15: "M15/H4", 60: "H1/D1"}
    FILT = {"typ": ("any", "BOS", "CHoCH"), "sweep": ("any", True), "htf": ("any", True), "disc": ("any", True), "kz": ("any", True)}
    res = []; KEEP = {}
    for (tf, n, en, tp), g0 in A.groupby(["tf", "n", "entry", "tp"], observed=True):
        for combo in itertools.product(*FILT.values()):
            msk = np.ones(len(g0), bool)
            for col, v in zip(FILT.keys(), combo):
                if v != "any": msk &= (g0[col].values == v)
            if msk.sum() < 40: continue
            g = busy(g0[msk])
            if len(g) < 40: continue
            r = g.r.values.astype(float); rr = g.rr.values.astype(float); t = g.t
            y1 = (t < mid).values
            P, P1, P2, PR = pf(r), pf(r[y1]), pf(r[~y1]), pf(rr[~np.isnan(rr)])
            st = pf(r - 0.5 * g.sp.values); l12 = r[~y1].sum(); gg = g[g.sym == "XAUUSD"]
            ok = len(g) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and st >= 1.05 and l12 > 0 and P >= PR + 0.10
            name = f"{TFN[tf]} n{n} | {en:9s} | TP {tp:9s} | " + " ".join(f"{k}={'Y' if v is True else v}" for k, v in zip(FILT.keys(), combo) if v != "any")
            eq = (g.r * g.risk).cumsum().values; dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min() if len(eq) else 0
            res.append(dict(name=name, tf=tf, entry=en, n=len(g), n1=int(y1.sum()), win=100 * (r > 0).mean(), PF=P, y1=P1, y2=P2, st=st,
                            r12=l12, r3=r[(t >= a3).values].sum(), p3=r[((t >= a6) & (t < a3)).values].sum(), usd=float((g.r * g.risk).sum()),
                            gold=float((gg.r * gg.risk).sum()), gpf=pf(gg.r.values.astype(float)), gn=len(gg), rand=PR, ok=ok, wk=len(g) / 104,
                            risk=float(g.risk.mean()), dd=dd, worst=float((g.r * g.risk).min()), buy=np.nan, sell=np.nan,
                            symp=int((g.groupby("sym", observed=True).r.sum() > 0).sum()), nsym=g.sym.nunique()))
            KEEP[name] = g
    R = pd.DataFrame(res)
    hdr = (f"{'variant':84s} {'n':>5} {'/wk':>4} {'win':>3} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'12mR':>6} {'3mR':>6} {'p3mR':>6} "
           f"{'net$':>6} {'maxDD':>6} {'worst':>5} {'risk$':>5} {'gold$':>6} {'sym+':>6} {'RAND':>5}")
    fm = lambda r: (f"{r.name:84s} {r.n:5d} {r.wk:4.1f} {r.win:3.0f} {r.PF:5.2f} {r.y1:5.2f} {r.y2:5.2f} {r.st:5.2f} {r.r12:+6.1f} {r.r3:+6.1f} "
                    f"{r.p3:+6.1f} {r.usd:+6.0f} {r.dd:+6.0f} {r.worst:+5.0f} {r.risk:5.1f} {r.gold:+6.0f} {r.symp:3d}/{r.nsym:<2d} {r.rand:5.2f} "
                    f"{'PASS' if r.ok else ''}")
    big = R[R.n >= 150]
    say(f"PASS: {int(R.ok.sum())} of {len(big)} variants with >= 150 trades ({len(R)} with >= 40)")
    say("\nmedian PF by timeframe x entry (>= 150 trades), random-twin median beside it")
    for (tf, en), g in big.groupby(["tf", "entry"]):
        say(f"  {TFN[tf]:7s} {en:9s} rows {len(g):4d}  PF median {g.PF.median():.2f}  best {g.PF.max():.2f}  rand median {g.rand.median():.2f}")
    say("\nmedian PF by filter (>= 150 trades): with the filter vs the same cell without it")
    for col in FILT:
        for v in FILT[col][1:]:
            tag = f"{col}={'Y' if v is True else v}"
            w = big[big.name.str.contains(tag, regex=False)]
            say(f"  {tag:11s} rows {len(w):4d}  PF median {w.PF.median():.2f}  rand {w.rand.median():.2f}")
    say(f"  (all rows       {len(big):4d}  PF median {big.PF.median():.2f}  rand {big.rand.median():.2f})")
    say("\nTHE TEXTBOOK MODELS (as the guides teach them)"); say(hdr)
    TB = [("A continuation: BOS + HTF bias + OB top, TP liquidity", "OB top", "liquidity", ("BOS", "any", True, "any", "any")),
          ("A + discount + killzone", "OB top", "liquidity", ("BOS", "any", True, True, True)),
          ("A with the OB 50% and TP 3R", "OB 50%", "3R", ("BOS", "any", True, True, "any")),
          ("B ICT reversal: sweep + CHoCH + FVG 50%, TP 2R", "FVG 50%", "2R", ("CHoCH", True, "any", "any", "any")),
          ("B + HTF bias + killzone", "FVG 50%", "2R", ("CHoCH", True, True, "any", True)),
          ("C OTE: HTF bias + discount + OTE 0.705, TP liquidity", "OTE 0.705", "liquidity", ("any", "any", True, True, "any")),
          ("C + sweep + killzone", "OTE 0.705", "liquidity", ("any", True, True, True, True))]
    for label, en, tp, combo in TB:
        say(f"-- {label}")
        for tf in (5, 15, 60):
            for n in NS:
                nm = f"{TFN[tf]} n{n} | {en:9s} | TP {tp:9s} | " + " ".join(f"{k}={'Y' if v is True else v}" for k, v in zip(FILT.keys(), combo) if v != "any")
                hit = R[R.name == nm]
                say(fm(next(hit.itertuples())) if len(hit) else f"{nm:84s}  (fewer than 40 trades)")
    say("\nTOP 30 by PF (>= 150 trades)"); say(hdr)
    for r in big.sort_values("PF", ascending=False).head(30).itertuples(): say(fm(r))
    if R.ok.any():
        say("\nALL PASSES, with buys / sells / gold / forex apart"); say(hdr)
        for r in R[R.ok].sort_values("PF", ascending=False).itertuples():
            say(fm(r)); g = KEEP[r.name]; rv = g.r.values.astype(float); dv = g.d.values; gs = (g.sym == "XAUUSD").values
            say(f"      buys {pf(rv[dv == 1]):.2f} ({(dv == 1).sum()})  sells {pf(rv[dv == -1]):.2f} ({(dv == -1).sum()})  "
                f"gold {pf(rv[gs]):.2f} ({gs.sum()})  forex {pf(rv[~gs]):.2f} ({(~gs).sum()})  last 3m {r.r3:+.1f}R  prev 3m {r.p3:+.1f}R")
    say("\nchosen on YEAR 1 (top 20 by year-1 PF, >= 75 year-1 trades) -> YEAR 2:")
    c = big[big.n1 >= 75].sort_values("y1", ascending=False).head(20)
    for r in c.itertuples(): say(f"  {r.name:84s} yr1 {r.y1:5.2f} -> yr2 {r.y2:5.2f}  (n {r.n}, rand {r.rand:.2f})")
    say(f"  median year 2 of those: {c.y2.median():.2f}; median year 2 of all: {big.y2.median():.2f}; "
        f"share of all with year 2 >= 1: {(big.y2 >= 1).mean():.0%}")
    say("\nGOLD alone, top 15 by gold PF (>= 60 gold trades)")
    for r in R[R.gn >= 60].sort_values("gpf", ascending=False).head(15).itertuples():
        say(f"  {r.name:84s} gold n {r.gn:4d} PF {r.gpf:5.2f} ${r.gold:+6.0f}  (all symbols {r.PF:.2f})")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
