"""Round 87 (12 Nov 2026): the owner's BBMA SOP on ALL 30 exported instruments (forex, gold, BTC), M15 CSAK in any
direction, looking for an indicator that supports the CSAK CONSISTENTLY across pairs.

Owner: "aku nak yang menarik tu kau bina ... bukan hanya untuk gold sahaja, tapi aku akan guna ke semua pair forex
termasuk btc untuk teknik ni. yang penting csak di m15 tu ada sokongan indikator yang valid dan konsisten!"

Rule (from rounds 84-86, built from the broker's M5 bars):
  1 H4 direction  EMA 50 vs EMA 90 on the last closed H4 candle
  2 H4 momentum   one of the last 8 closed H4 candles closed beyond the BB (20, 2) in that direction, no opposite
                  momentum after it and no H4 close back through the H4 EMA 50 since
  3 rejection     after that momentum closed, an M30 (valid 8 candles) or H1 (valid 4) candle touches EMA 50 and closes
                  back on the H4 side, the candle before also on that side
  4 CSAK (M15)    one candle opens beyond min/max(mid BB, EMA 50) and closes beyond both, not beyond the outer BB.
                  The CSAK may go EITHER way (owner, round 86); the trade follows the CSAK.  Populations: ANY,
                  WITH (CSAK in the H4 / rejection direction), AGAINST.
  5 indicator     on the CSAK candle, signed in the CSAK direction: none / RSI14 > 55 / RSI14 > 60 / CCI20 > 0 /
                  CCI20 > 100 / RSI14 > 55 and CCI20 > 0
  Entry at the next M5 open (buys pay the bar's spread), SL beyond the CSAK candle + spread, TP 1R / 2R, 48 h cap,
  the broker's swap for each symbol (research/swaps23.csv, triple day included).  One trade per rejection, one
  position per symbol at a time, CSAKs 01:30-22:00 server only.  SL checked before TP inside an M5 bar.
Pooled across symbols in R (profit / risk), since $ per 0.01 lot differs by 100x between symbols; per symbol in $.
Controls: the same entries with a random direction; random masks keeping the same share of trades as a filter.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)
SYMS = ("XAUUSD,BTCUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,EURNZD,"
        "GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY").split(",")
MIDDAY = pd.Timestamp("2023-07-01")
FEAT = None         # optional f(X15) -> {name: (array over M15 bars, "osc" | "sym")}, set by later rounds (bbma90)
RAND_EXTRA = True
CSAK_MODE = "basic"  # "basic": mid BB + EMA 50; "all": + LWMA 5 / 10 of highs and lows; "all90": + EMA 90 too (bbma91)
RTFS = ((30, "M30", 8), (60, "H1", 4))   # rejection TFs; (0, "NOREJ", 0) = CSAK + H4 direction only (bbma91)


def lwma(a, n):
    w = np.arange(1, n + 1, dtype=float)
    out = np.full(len(a), np.nan)
    if len(a) >= n: out[n - 1:] = np.convolve(a, w[::-1], mode="valid") / w.sum()
    return out
EXTRA = None        # optional list of (name, f(F)) filters on a feature dict, set by later rounds (bbma89)
FILTS = (("none", lambda r, c: np.ones_like(r, bool)), ("RSI>55", lambda r, c: r > 55), ("RSI>60", lambda r, c: r > 60),
         ("CCI>0", lambda r, c: c > 0), ("CCI>100", lambda r, c: c > 100), ("RSI>55+CCI>0", lambda r, c: (r > 55) & (c > 0)))


def ind(X):
    c = X.c
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    tp = (X.h + X.l + X.c) / 3; sm = tp.rolling(20).mean()
    md = tp.rolling(20).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True)
    ll = X.l.rolling(14).min(); hh = X.h.rolling(14).max()
    sk = (100 * (c - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean()          # Stochastic 14,3,3: slow %K
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    return pd.DataFrame({"mid": mid, "top": mid + 2 * sd, "bot": mid - 2 * sd, "e50": c.ewm(span=50, adjust=False).mean(),
                         "e90": c.ewm(span=90, adjust=False).mean(), "cci": (tp - sm) / (0.015 * md),
                         "rsi": 100 - 100 / (1 + up / dn.replace(0, np.nan)), "sk": sk, "sd": sk.rolling(3).mean()}, index=X.index)


def run_symbol(sym, mt, sw):
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    B = d[["o", "h", "l", "c", "s", "v"]].copy(); del d
    T = B.index; n = len(B)
    O, H, L, C, S = (B[x].values.astype(float) for x in ("o", "h", "l", "c", "s"))
    ts = T.values.astype("datetime64[s]").astype(np.int64)
    day = T.normalize().values; wd = T.day_of_week.values

    def tf(m):
        g = B.resample(f"{m}min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        X["v"] = g.v.sum().reindex(X.index).fillna(0).values           # tick volume (for MFI, bbma92)
        return X, ind(X), (X.index + pd.Timedelta(minutes=m)).values
    X4, I4, cl4 = tf(240); X15, I15, cl15 = tf(15)
    c4, top4, bot4, e50_4, e90_4 = X4.c.values, I4.top.values, I4.bot.values, I4.e50.values, I4.e90.values
    mu4 = c4 > top4; md4 = c4 < bot4
    o15, h15, l15, c15 = (X15[x].values for x in ("o", "h", "l", "c"))
    mid15, top15, bot15, e15 = I15.mid.values, I15.top.values, I15.bot.values, I15.e50.values
    cci15, rsi15 = I15.cci.values, I15.rsi.values
    sk15, sd15 = I15.sk.values, I15.sd.values
    kmin5, kmax5 = pd.Series(sk15).rolling(5).min().values, pd.Series(sk15).rolling(5).max().values
    feats = FEAT(X15) if FEAT else {}
    lo_, hi_ = np.minimum(mid15, e15), np.maximum(mid15, e15)
    if CSAK_MODE in ("all", "all90"):
        lines = [mid15, e15, lwma(h15, 5), lwma(h15, 10), lwma(l15, 5), lwma(l15, 10)] + ([I15.e90.values] if CSAK_MODE == "all90" else [])
        lo_, hi_ = np.min(np.vstack(lines), 0), np.max(np.vstack(lines), 0)
    csak_b = (o15 < lo_) & (c15 > hi_) & (c15 <= top15)
    csak_s = (o15 > hi_) & (c15 < lo_) & (c15 >= bot15)
    at = np.searchsorted(T.values, cl15)
    hm15 = X15.index.hour.values * 60 + X15.index.minute.values
    k4 = np.searchsorted(cl4, cl15, side="right") - 1

    def setups(rtf, rej_bars):
        XR, IR, clR = tf(rtf)
        cR, lR, hR, eR = XR.c.values, XR.l.values, XR.h.values, IR.e50.values
        pa = np.r_[False, (cR > eR)[:-1]]; pb = np.r_[False, (cR < eR)[:-1]]
        rb = (lR <= eR) & (cR > eR) & pa; rs = (hR >= eR) & (cR < eR) & pb
        kR = np.searchsorted(clR, cl15, side="right") - 1
        lastrb = pd.Series(np.where(rb, np.arange(len(rb)), np.nan)).ffill().values
        lastrs = pd.Series(np.where(rs, np.arange(len(rs)), np.nan)).ffill().values
        out = []                                            # (k15, csak dir, H4 dir, rejection id)
        for k in np.where(csak_b | csak_s)[0]:
            a, r = k4[k], kR[k]
            if a < 100 or r < 1 or not (90 <= hm15[k] < 1320): continue
            dr = 1 if e50_4[a] > e90_4[a] else -1
            win = np.arange(a - 7, a + 1)
            moms = win[mu4[win]] if dr == 1 else win[md4[win]]
            if len(moms) == 0: continue
            j = moms[-1]
            if dr == 1 and (md4[j + 1:a + 1].any() or (c4[j + 1:a + 1] < e50_4[j + 1:a + 1]).any()): continue
            if dr == -1 and (mu4[j + 1:a + 1].any() or (c4[j + 1:a + 1] > e50_4[j + 1:a + 1]).any()): continue
            q = lastrb[r] if dr == 1 else lastrs[r]
            if np.isnan(q): continue
            q = int(q)
            if r - q >= rej_bars or XR.index[q] < pd.Timestamp(cl4[j]): continue
            out.append((k, 1 if csak_b[k] else -1, dr, q))
        return np.array(out, dtype=np.int64).reshape(-1, 4)

    rg = np.random.default_rng(87)

    def sim(SU, tpR, rand=False):
        res = []; busy = -1; used = set()
        for k, cd, dr, q in SU:
            if q in used: continue
            i = at[k]
            if i >= n or i <= busy: continue
            d_ = cd if not rand else (1 if rg.random() < 0.5 else -1)
            e = O[i] + (S[i] if cd == 1 else 0)
            sl = l15[k] - S[i] if cd == 1 else h15[k] + S[i]
            risk = (e - sl) * cd
            if risk <= S[i]: continue
            e = O[i] + (S[i] if d_ == 1 else 0); sl = e - d_ * risk; tp = e + d_ * tpR * risk
            x = None; z = i; nights = 0
            while z < n:
                if z > i and day[z] != day[z - 1]:
                    nights += 3 if (1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
                if ts[z] - ts[i] >= 48 * 3600: x = O[z] + (S[z] if d_ == -1 else 0); break
                if d_ == 1:
                    if L[z] <= sl: x = min(O[z], sl) if z > i else sl; break
                    if z > i and H[z] >= tp: x = max(O[z], tp); break
                else:
                    if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; break
                    if z > i and L[z] + S[z] <= tp: x = min(O[z] + S[z], tp); break
                z += 1
            if x is None: break
            swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
            net = (x - e) * d_ * usd + swp
            rk = risk * usd
            res.append((T[i], net, net / rk, (net - 0.5 * S[i] * usd) / rk, rk, d_))
            busy = z; used.add(q)
        return pd.DataFrame(res, columns=["t", "net", "r", "rs", "risk", "d"])

    out = {}
    for rtf, rn, rbars in RTFS:
        if rtf == 0:                                                   # CSAK + H4 EMA 50/90 direction only
            ks = np.where((csak_b | csak_s) & (hm15 >= 90) & (hm15 < 1320) & (k4 >= 100))[0]
            SU = np.c_[ks, np.where(csak_b[ks], 1, -1), np.where(e50_4[k4[ks]] > e90_4[k4[ks]], 1, -1), ks].astype(np.int64)
        else:
            SU = setups(rtf, rbars)
        if len(SU) == 0: continue
        sr = np.where(SU[:, 1] == 1, rsi15[SU[:, 0]], 100 - rsi15[SU[:, 0]])
        sc = cci15[SU[:, 0]] * SU[:, 1]
        ix, dd = SU[:, 0], SU[:, 1]
        sg = lambda a: np.where(dd == 1, a, 100 - a)                 # signed in the CSAK direction (sell mirrored)
        F = dict(r=sr, c=sc, k=sg(sk15[ix]), d=sg(sd15[ix]), kp=sg(sk15[ix - 1]), km=np.where(dd == 1, kmin5[ix], 100 - kmax5[ix]))
        for nm, (arr, kind) in feats.items():
            F[nm] = sg(arr[ix]) if kind == "osc" else arr[ix] * dd
            F[nm + "_p"] = sg(arr[ix - 1]) if kind == "osc" else arr[ix - 1] * dd
        if EXTRA:
            for pop in ("ANY", "WITH", "AGAINST"):
                pm = np.ones(len(SU), bool) if pop == "ANY" else (SU[:, 1] == SU[:, 2]) if pop == "WITH" else (SU[:, 1] != SU[:, 2])
                for fn, f in EXTRA:
                    m = pm & np.nan_to_num(f(F)).astype(bool)
                    for tpR in (1, 2):
                        out[(rn, pop, fn, tpR)] = sim(SU[m], tpR)
                        if RAND_EXTRA: out[(rn, pop, fn + " RANDOM dir", tpR)] = sim(SU[m], tpR, rand=True)
            continue
        for pop in ("ANY", "WITH", "AGAINST"):
            pm = np.ones(len(SU), bool) if pop == "ANY" else (SU[:, 1] == SU[:, 2]) if pop == "WITH" else (SU[:, 1] != SU[:, 2])
            for fn, f in FILTS:
                m = pm & f(sr, sc)
                for tpR in (1, 2):
                    out[(rn, pop, fn, tpR)] = sim(SU[m], tpR)
                    if fn in ("none", "RSI>55", "RSI>60") and pop == "ANY":
                        out[(rn, pop, fn + " RANDOM dir", tpR)] = sim(SU[m], tpR, rand=True)
            if pop == "ANY":
                for fn, f in FILTS[1:3]:
                    share = (pm & f(sr, sc)).sum() / max(pm.sum(), 1)
                    for s in range(3):
                        mm = pm & (rg.random(len(SU)) < share)
                        for tpR in (1, 2):
                            out.setdefault((rn, pop, fn + " RANDOM mask x3", tpR), []).append(sim(SU[mm], tpR))
    if EXTRA: return out, T[-1], T[0]
    # context control: every M15 CSAK in the window, no H4 / rejection
    allk = np.where((csak_b | csak_s) & (hm15 >= 90) & (hm15 < 1320))[0]
    cdir = np.where(csak_b[allk], 1, -1)
    AL = np.c_[allk, cdir, cdir, allk]
    sr = np.where(cdir == 1, rsi15[allk], 100 - rsi15[allk])
    for fn, f in FILTS[:3]:
        out[("ALL", "CSAK only", fn, 1)] = sim(AL[f(sr, sr)], 1)
    for key, v in out.items():
        if isinstance(v, list): out[key] = pd.concat(v).assign(r=lambda x: x.r / 3, rs=lambda x: x.rs / 3, net=lambda x: x.net / 3)
    return out, T[-1], T[0]


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    SW = R23.load_swaps()
    pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
    ALLR = {}; ends = []
    say(f"{'symbol':8s} {'from':10s} {'to':10s}  M30-ANY trades by filter (TP 1R): " + " ".join(f"{fn:>12s}" for fn, _ in FILTS))
    for sym in SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")):
            say(f"{sym:8s} missing"); continue
        res, end, start = run_symbol(sym, meta[sym], SW.get(sym))
        ends.append(end)
        for key, df in res.items():
            ALLR.setdefault(key, [])
            if len(df): ALLR[key].append(df.assign(sym=sym))
        cells = []
        for fn, _ in FILTS:
            x = res.get(("M30", "ANY", fn, 1))
            cells.append(f"{len(x):4d} PF{pf(x.net.values):4.2f}" if x is not None and len(x) else f"{'-':>12s}")
        say(f"{sym:8s} {start:%Y-%m-%d} {end:%Y-%m-%d}  " + " ".join(f"{c:>12s}" for c in cells) + f"   [{time.time() - T0:.0f} s]")
    END = max(ends)
    say(f"\n===== POOLED over all symbols, in R (1R = the risk of each trade). half split {MIDDAY:%Y-%m-%d}. "
        f"'sym>1' = symbols with PF($) > 1 among those with >= 10 trades; '12m+' = symbols positive in the last 12 months =====")
    say(f"{'variant':44s} {'trades':>6} {'/wk':>5} {'win%':>4} {'PF R':>5} {'half1':>5} {'half2':>5} {'stress':>6} | {'R 12m':>6} {'R 3m':>5} {'R all':>6} | {'sym>1':>7} {'12m+':>7}")
    weeks = 6.6 * 52
    for key in ALLR:
        R = pd.concat(ALLR[key]) if ALLR[key] else pd.DataFrame(columns=["t", "net", "r", "rs", "risk", "sym"])
        if len(R) < 20:
            say(f"{' | '.join(map(str, key)):44s} {len(R):6d} too few"); continue
        bys = R.groupby("sym")
        ok = [pf(g.net.values) > 1 for _, g in bys if len(g) >= 10]
        y1 = [g[g.t >= END - pd.Timedelta(days=365)].net.sum() > 0 for _, g in bys if len(g) >= 10]
        say(f"{' | '.join(map(str, key[:3])) + f' | TP {key[3]}R':44s} {len(R):6d} {len(R) / weeks:5.1f} {100 * (R.r > 0).mean():4.0f} {pf(R.r.values):5.2f} "
            f"{pf(R.r[R.t < MIDDAY].values):5.2f} {pf(R.r[R.t >= MIDDAY].values):5.2f} {pf(R.rs.values):6.2f} | "
            f"{R.r[R.t >= END - pd.Timedelta(days=365)].sum():+6.0f} {R.r[R.t >= END - pd.Timedelta(days=91)].sum():+5.0f} {R.r.sum():+6.0f} | "
            f"{sum(ok):3d}/{len(ok):<3d} {sum(y1):3d}/{len(y1):<3d}")
    # per-symbol detail for the main candidates
    for key in (("M30", "ANY", "RSI>55", 1), ("M30", "ANY", "RSI>60", 1), ("M30", "ANY", "RSI>55", 2), ("M30", "AGAINST", "none", 1),
                ("M30", "AGAINST", "RSI>55", 1), ("H1", "ANY", "RSI>55", 1)):
        if not ALLR.get(key): continue
        say(f"\n--- per symbol: {' | '.join(map(str, key))}R  ($ per 0.01 lot) ---")
        say(f"{'sym':8s} {'n':>4} {'PF$':>5} {'half1':>5} {'half2':>5} {'net$':>8} {'12m$':>7} {'3m$':>6} {'worst$':>7} {'avg risk$':>9}")
        for x in ALLR[key]:
            if len(x) == 0: continue
            s = x.sym.iloc[0]
            say(f"{s:8s} {len(x):4d} {pf(x.net.values):5.2f} {pf(x.net[x.t < MIDDAY].values):5.2f} {pf(x.net[x.t >= MIDDAY].values):5.2f} "
                f"{x.net.sum():+8.0f} {x.net[x.t >= END - pd.Timedelta(days=365)].sum():+7.0f} {x.net[x.t >= END - pd.Timedelta(days=91)].sum():+6.0f} "
                f"{x.net.min():+7.0f} {x.risk.mean():9.2f}")
        R = pd.concat(ALLR[key])
        say("by year (pooled R): " + " ".join(f"{y}:{pf(v.r.values):.2f}({v.r.sum():+.0f})" for y, v in R.groupby(R.t.dt.year)))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
