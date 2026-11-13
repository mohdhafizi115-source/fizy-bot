"""Round 111 (14 Nov 2026): a second batch of popular TradingView indicators never tested here, gold M1 / M5 / M15.
Owner: "lagi bro cari. dekat trading view bersepah teknik".
Data: gold M1 export run 43450356142 (from 2024-09), last 2 years; M5 / M15 resampled.  Entry at the open of the first
M1 bar after the signal bar closes; real spread; rollover dropped; out by 23:30 server.  Same machinery as round 110.
  STATE systems (enter when the state turns to +1 / -1, exit when it changes or at a cap; SL 2 x ATR of the frame;
  plain, Choppiness(14) < 50, and gate 8 on M1):
     Range Filter (DonovanWall, 100 / 3), HalfTrend (everget, amplitude 2, deviation 2), AlphaTrend (Kivanc, RSI mode,
     14 / 1), OTT (Ozeksi, VAR 2, 0.2% and 0.6%), PMax (EMA 10, ATR 10 x 3), Trend Magic (CCI 20, ATR 5 x 1, price vs
     line), Coral Trend (LazyBear 21 / 0.4 slope), McGinley Dynamic 14 (price side), Alligator (lips > teeth > jaw,
     flat otherwise), Elder Impulse (EMA 13 + MACD hist slopes, flat otherwise), TSI 25/13 vs signal 13
  EVENT systems (SL 1.5 x ATR of the frame, fixed hold, plain / with the EMA 200 side / TP 1.5 ATR; gate 8 on M1):
     WaveTrend (LazyBear 10 / 21) cross below -53 / above +53 and -60 / +60, Nadaraya-Watson envelope (LuxAlgo, endpoint
     non-repainting, h 8, mult 3): fade the close beyond the band and buy back inside, Schaff Trend Cycle (23 / 50 / 10)
     cross of 25 / 75, Inverse Fisher RSI (5, WMA 9) cross of -0.5 / +0.5, Ultimate Oscillator 7/14/28 cross of 30 / 70
  ML: Lorentzian Classification (jdehorty) done causally: features RSI 14, WaveTrend 10/11, CCI 20, ADX 20, RSI 9
     (min-max normalised over 500 bars), label = sign of the close 4 bars LATER (known only after 4 bars), exact 8
     nearest neighbours by Lorentzian distance among every 4th bar of the last 2,000 that already have a label;
     trade the prediction's sign change, hold 4 bars or until it flips.
Every trade has a random-direction and an always-buy twin.  $ per 0.01 lot.  Pass rule as always."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import scalp110 as S1

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()
jit = G.jit
ema, rma, sma, wma, rsi = S1.ema, S1.rma, S1.sma, S1.wma, S1.rsi
KNN_ON = True


@jit
def range_filter(C, R):
    n = len(C); f = np.zeros(n); st = np.zeros(n, np.int64); f[0] = C[0]
    for i in range(1, n):
        p = f[i - 1]; x = C[i]; r = R[i]
        if np.isnan(r): f[i] = x; continue
        if x > p: f[i] = p if x - r < p else x - r
        else: f[i] = p if x + r > p else x + r
        if f[i] > p: st[i] = 1
        elif f[i] < p: st[i] = -1
        else: st[i] = st[i - 1]
    return st


@jit
def half_trend(H, L, C, hp, lp, hma, lma):
    n = len(C); st = np.zeros(n, np.int64)
    trend = 0; nxt = 0; maxl = L[0]; minh = H[0]
    for i in range(1, n):
        if nxt == 1:
            maxl = max(lp[i], maxl)
            if hma[i] < maxl and C[i] < L[i - 1]: trend = 1; nxt = 0; minh = hp[i]
        else:
            minh = min(hp[i], minh)
            if lma[i] > minh and C[i] > H[i - 1]: trend = 0; nxt = 1; maxl = lp[i]
        st[i] = 1 if trend == 0 else -1
    return st


@jit
def ratchet_line(up, dn, cond):
    """AlphaTrend / Trend Magic: line = cond ? max(up, prev) : min(dn, prev)"""
    n = len(up); a = np.zeros(n); a[0] = up[0]
    for i in range(1, n):
        if np.isnan(up[i]) or np.isnan(dn[i]): a[i] = a[i - 1]; continue
        if np.isnan(a[i - 1]): a[i] = up[i] if cond[i] else dn[i]; continue
        if cond[i]: a[i] = up[i] if up[i] > a[i - 1] else a[i - 1]
        else: a[i] = dn[i] if dn[i] < a[i - 1] else a[i - 1]
    return a


@jit
def var_ma(C, length):
    n = len(C); v = np.zeros(n); v[0] = C[0]; al = 2.0 / (length + 1)
    for i in range(1, n):
        ud = 0.0; dd = 0.0
        for j in range(max(1, i - 8), i + 1):
            d = C[j] - C[j - 1]
            if d > 0: ud += d
            else: dd -= d
        cmo = (ud - dd) / (ud + dd) if ud + dd > 0 else 0.0
        k = al * abs(cmo)
        v[i] = k * C[i] + (1 - k) * v[i - 1]
    return v


@jit
def trail_stop(MA, dist):
    """OTT / PMax core: ratcheting long / short stops around a moving average; returns the stop line MT"""
    n = len(MA); ls = np.zeros(n); ss = np.zeros(n); mt = np.zeros(n); d = 1
    ls[0] = MA[0] - dist[0]; ss[0] = MA[0] + dist[0]; mt[0] = ls[0]
    for i in range(1, n):
        if np.isnan(dist[i]): ls[i] = ls[i - 1]; ss[i] = ss[i - 1]; mt[i] = mt[i - 1]; continue
        l = MA[i] - dist[i]; s = MA[i] + dist[i]
        ls[i] = max(l, ls[i - 1]) if MA[i] > ls[i - 1] else l
        ss[i] = min(s, ss[i - 1]) if MA[i] < ss[i - 1] else s
        if d == -1 and MA[i] > ss[i - 1]: d = 1
        elif d == 1 and MA[i] < ls[i - 1]: d = -1
        mt[i] = ls[i] if d == 1 else ss[i]
    return mt


@jit
def mcginley(C, n_):
    n = len(C); m = np.zeros(n); m[0] = C[0]
    for i in range(1, n):
        m[i] = m[i - 1] + (C[i] - m[i - 1]) / (0.6 * n_ * (C[i] / m[i - 1]) ** 4)
    return m


@jit
def stc(m, cyc):
    n = len(m); f1 = np.zeros(n); pf_ = np.zeros(n); f2 = np.zeros(n); s = np.zeros(n)
    for i in range(n):
        lo = m[i]; hi = m[i]
        for j in range(max(0, i - cyc + 1), i + 1):
            lo = min(lo, m[j]); hi = max(hi, m[j])
        f1[i] = (m[i] - lo) / (hi - lo) * 100 if hi - lo > 0 else (f1[i - 1] if i > 0 else 0.0)
        pf_[i] = f1[i] if i == 0 else pf_[i - 1] + 0.5 * (f1[i] - pf_[i - 1])
        lo = pf_[i]; hi = pf_[i]
        for j in range(max(0, i - cyc + 1), i + 1):
            lo = min(lo, pf_[j]); hi = max(hi, pf_[j])
        f2[i] = (pf_[i] - lo) / (hi - lo) * 100 if hi - lo > 0 else (f2[i - 1] if i > 0 else 0.0)
        s[i] = f2[i] if i == 0 else s[i - 1] + 0.5 * (f2[i] - s[i - 1])
    return s


@jit
def knn_lorentz(F, lab_fut, horizon, back, step, k):
    """F: n x d features; lab_fut[j] = sign(c[j+h] - c[j]) (only usable once j + h <= t). returns the sum of the k labels"""
    n, dd = F.shape; out = np.zeros(n)
    bd = np.full(k, 1e18); bl = np.zeros(k)
    for t in range(back, n):
        for q in range(k): bd[q] = 1e18; bl[q] = 0.0
        ok = True
        for c_ in range(dd):
            if np.isnan(F[t, c_]): ok = False
        if not ok: continue
        j = t - horizon
        while j > t - back:
            dist = 0.0
            for c_ in range(dd): dist += np.log(1.0 + abs(F[t, c_] - F[j, c_]))
            if dist < bd[k - 1] and not np.isnan(dist):
                q = k - 1
                while q > 0 and bd[q - 1] > dist:
                    bd[q] = bd[q - 1]; bl[q] = bl[q - 1]; q -= 1
                bd[q] = dist; bl[q] = lab_fut[j]
            j -= step
        s = 0.0
        for q in range(k): s += bl[q]
        out[t] = s
    return out


def norm_mm(x, n=500):
    s = pd.Series(x); lo = s.rolling(n, min_periods=50).min(); hi = s.rolling(n, min_periods=50).max()
    return ((s - lo) / (hi - lo).replace(0, np.nan)).values


def adx(h, l, c, n):
    up = np.diff(h, prepend=h[0]); dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    c1 = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    at = rma(tr, n); pdi = 100 * rma(pdm, n) / np.maximum(at, 1e-12); mdi = 100 * rma(mdm, n) / np.maximum(at, 1e-12)
    dx = 100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12)
    return rma(dx, n)


def cci(h, l, c, n):
    tp = (h + l + c) / 3; m = pd.Series(tp).rolling(n).mean()
    md = pd.Series(tp).rolling(n).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True)
    return ((tp - m) / (0.015 * md)).values


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=30)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    S = bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    res = []

    def go(name, sg, one=True):
        if sg is None or len(sg) == 0: return
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.d != 0)]
        if len(sg) < 20: return
        x = M.line(name, bk.run(sg, one), mid, end)
        if x:
            x["tf"] = name.split()[0]; x["sys"] = name.split()[1]; res.append(x); M.show(x)

    for tf in (1, 5, 15):
        X = Bw if tf == 1 else M.resample(Bw, tf)
        o, h, l, c = (X[k].values.astype(float) for k in ("o", "h", "l", "c"))
        nx = len(c)
        xa = M.atr(X).values
        at = np.searchsorted(tv, (X.index + pd.Timedelta(minutes=tf)).values.astype("datetime64[ns]"))
        gate_ok = (a1[np.maximum(at - 1, 0)] >= 8 * S[np.maximum(at - 1, 0)]) if tf == 1 else np.ones(nx, bool)
        cap = {1: 60, 5: 240, 15: 480}[tf]
        hold = {1: (15, 30), 5: (30, 60), 15: (60, 120)}[tf]
        c1 = np.r_[c[0], c[:-1]]
        trr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
        chop = 100 * np.log10(pd.Series(trr).rolling(14).sum().values /
                              np.maximum(pd.Series(h).rolling(14).max().values - pd.Series(l).rolling(14).min().values, 1e-9)) / np.log10(14)
        e200 = ema(c, 200)
        say(f"\n{'=' * 20} M{tf}: {nx:,} bars {'=' * 20}"); say(M.HDR)

        # ------------------------------------------------ STATE systems
        st = {}
        dc = np.abs(np.diff(c, prepend=c[0]))
        st["RANGEFILT"] = range_filter(c, ema(ema(dc, 100), 199) * 3.0)
        hp = pd.Series(h).rolling(2).max().values; lp = pd.Series(l).rolling(2).min().values
        st["HALFTREND"] = half_trend(h, l, c, np.nan_to_num(hp, nan=h[0]), np.nan_to_num(lp, nan=l[0]),
                                     np.nan_to_num(sma(h, 2), nan=h[0]), np.nan_to_num(sma(l, 2), nan=l[0]))
        at14 = sma(trr, 14)
        alpha = ratchet_line(l - at14, h + at14, rsi(c, 14) >= 50)
        st["ALPHATREND"] = np.sign(alpha - np.r_[alpha[:2], alpha[:-2]])
        vm = var_ma(c, 2)
        for pc in (0.2, 0.6):
            mt_ = trail_stop(vm, vm * pc * 0.01)
            ott = np.where(vm > mt_, mt_ * (200 + pc) / 200, mt_ * (200 - pc) / 200)
            st[f"OTT{pc}"] = np.sign(vm - np.r_[ott[:2], ott[:-2]])
        e10 = ema(c, 10)
        st["PMAX"] = np.sign(e10 - trail_stop(e10, 3.0 * rma(trr, 10)))
        cc = cci(h, l, c, 20); a5 = sma(trr, 5)
        magic = ratchet_line(l - a5, h + a5, np.nan_to_num(cc) >= 0)
        st["TRENDMAGIC"] = np.sign(c - magic)
        cd = 0.4; di = (21 - 1) / 2 + 1; k1 = 2 / (di + 1)
        i1 = pd.Series(c).ewm(alpha=k1, adjust=False).mean(); i2 = i1.ewm(alpha=k1, adjust=False).mean(); i3 = i2.ewm(alpha=k1, adjust=False).mean()
        i4 = i3.ewm(alpha=k1, adjust=False).mean(); i5 = i4.ewm(alpha=k1, adjust=False).mean(); i6 = i5.ewm(alpha=k1, adjust=False).mean()
        bfr = (-cd ** 3 * i6 + 3 * (cd * cd + cd ** 3) * i5 - 3 * (2 * cd * cd + cd + cd ** 3) * i4 + (3 * cd + 1 + cd ** 3 + 3 * cd * cd) * i3).values
        st["CORAL"] = np.sign(np.diff(bfr, prepend=bfr[0]))
        st["MCGINLEY"] = np.sign(c - np.r_[c[0], mcginley(c, 14)[:-1]])
        hl2 = (h + l) / 2
        jaw = np.r_[np.full(8, np.nan), rma(hl2, 13)[:-8]]; teeth = np.r_[np.full(5, np.nan), rma(hl2, 8)[:-5]]; lips = np.r_[np.full(3, np.nan), rma(hl2, 5)[:-3]]
        st["ALLIGATOR"] = np.where((lips > teeth) & (teeth > jaw), 1, np.where((lips < teeth) & (teeth < jaw), -1, 0))
        e13 = ema(c, 13); hist = ema(c, 12) - ema(c, 26); hist = hist - ema(hist, 9)
        de, dh = np.diff(e13, prepend=e13[0]), np.diff(hist, prepend=hist[0])
        st["ELDER"] = np.where((de > 0) & (dh > 0), 1, np.where((de < 0) & (dh < 0), -1, 0))
        pcd = np.diff(c, prepend=c[0])
        tsi = 100 * ema(ema(pcd, 25), 13) / np.maximum(ema(ema(np.abs(pcd), 25), 13), 1e-12)
        st["TSI"] = np.sign(tsi - ema(tsi, 13))
        for nm, s in st.items():
            s = np.nan_to_num(np.asarray(s, float)).astype(np.int64)
            chg = np.where(np.r_[False, s[1:] != s[:-1]])[0]                       # bars where the state changes
            k = chg[s[chg] != 0]
            k = k[(k > 300) & (at[k] < n - 2)]
            if len(k) < 30: continue
            nxt_chg = chg[np.minimum(np.searchsorted(chg, k, side="right"), len(chg) - 1)]
            nxt_chg = np.where(nxt_chg > k, nxt_chg, nx - 1)
            ii = at[k]; dr = s[k]
            xe = at[np.minimum(nxt_chg, nx - 1)]
            x = np.maximum(np.minimum(np.minimum(xe, ii + cap), exb(ii)), ii + 1)
            base = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 2.0 * xa[k], "tp": np.nan, "x": x, "g": gate_ok[k], "ch": chop[k]})
            go(f"M{tf} {nm} state", base.drop(columns=["g", "ch"]), one=False)
            go(f"M{tf} {nm} state CHOP<50", base[base.ch < 50].drop(columns=["g", "ch"]), one=False)
            if tf == 1: go(f"M{tf} {nm} state gate8", base[base.g].drop(columns=["g", "ch"]), one=False)

        # ------------------------------------------------ EVENT systems
        ev = {}
        ap = (h + l + c) / 3; esa = ema(ap, 10); dd_ = ema(np.abs(ap - esa), 10)
        wt1 = ema((ap - esa) / np.maximum(0.015 * dd_, 1e-12), 21); wt2 = sma(wt1, 4)
        w1p, w2p = np.r_[0, wt1[:-1]], np.r_[0, wt2[:-1]]
        xu = (wt1 > wt2) & (w1p <= w2p); xd = (wt1 < wt2) & (w1p >= w2p)
        for lv in (53, 60):
            ev[f"WAVETREND{lv}"] = np.where(xu & (wt1 < -lv), 1, np.where(xd & (wt1 > lv), -1, 0))
        wts = np.exp(-np.arange(64) ** 2 / (2 * 8.0 ** 2)); wts /= wts.sum()
        nw = np.convolve(c, wts)[:nx]; nw[:64] = np.nan
        mae = pd.Series(np.abs(c - nw)).rolling(499, min_periods=200).mean().values * 3.0
        up_, lo_ = nw + mae, nw - mae
        cp = np.r_[c[0], c[:-1]]; upp = np.r_[np.nan, up_[:-1]]; lop = np.r_[np.nan, lo_[:-1]]
        ev["NWE-FADE"] = np.where((c < lo_) & (cp >= lop), 1, np.where((c > up_) & (cp <= upp), -1, 0))
        ev["NWE-BACKIN"] = np.where((c > lo_) & (cp <= lop), 1, np.where((c < up_) & (cp >= upp), -1, 0))
        sc = stc(ema(c, 23) - ema(c, 50), 10); scp = np.r_[50, sc[:-1]]
        ev["STC"] = np.where((sc > 25) & (scp <= 25), 1, np.where((sc < 75) & (scp >= 75), -1, 0))
        v2 = wma(0.1 * (rsi(c, 5) - 50), 9); ifr = np.tanh(v2); ifp = np.r_[0, ifr[:-1]]
        ev["IFISHRSI"] = np.where((ifr > -0.5) & (ifp <= -0.5), 1, np.where((ifr < 0.5) & (ifp >= 0.5), -1, 0))
        lowm = np.minimum(l, c1); bp = c - lowm
        avg = lambda q: pd.Series(bp).rolling(q).sum().values / np.maximum(pd.Series(trr).rolling(q).sum().values, 1e-12)
        uo = 100 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7; uop = np.r_[50, uo[:-1]]
        ev["ULTOSC"] = np.where((uo > 30) & (uop <= 30), 1, np.where((uo < 70) & (uop >= 70), -1, 0))
        for nm, e in ev.items():
            e = np.nan_to_num(e).astype(int)
            k = np.where(e != 0)[0]; k = k[(k > 600) & (at[k] < n - 2)]
            if len(k) < 30: continue
            ii = at[k]; dr = e[k]; side = np.where(dr == 1, c[k] > e200[k], c[k] < e200[k])
            for hd in hold:
                base = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 1.5 * xa[k], "tp": np.nan, "x": np.minimum(ii + hd, exb(ii)), "g": gate_ok[k], "e": side})
                go(f"M{tf} {nm} {hd}m", base.drop(columns=["g", "e"]))
                go(f"M{tf} {nm} {hd}m EMA200", base[base.e].drop(columns=["g", "e"]))
                if tf == 1: go(f"M{tf} {nm} {hd}m gate8", base[base.g].drop(columns=["g", "e"]))
                b2 = base.copy(); b2["tp"] = 1.5 * xa[k]
                go(f"M{tf} {nm} {hd}m TP1R", b2.drop(columns=["g", "e"]))

        # ------------------------------------------------ Lorentzian classification (causal kNN)
        if KNN_ON:
            t1 = time.time()
            wtn = norm_mm(wt1); ccn = norm_mm(np.nan_to_num(cc)); adn = adx(h, l, c, 20) / 100
            F = np.column_stack([rsi(c, 14) / 100, wtn, ccn, adn, rsi(c, 9) / 100]).astype(float)
            lab = np.zeros(nx); lab[:-4] = np.sign(c[4:] - c[:-4])
            pred = knn_lorentz(F, lab, 4, 2000, 4, 8)
            say(f"   (Lorentzian kNN on M{tf}: {time.time() - t1:.0f} s)")
            s = np.sign(pred).astype(np.int64)
            for flt in ("", "EMA200"):
                chg = np.where(np.r_[False, s[1:] != s[:-1]])[0]
                k = chg[s[chg] != 0]; k = k[(k > 2600) & (at[k] < n - 2)]
                if flt: k = k[np.where(s[k] == 1, c[k] > e200[k], c[k] < e200[k])]
                if len(k) < 30: continue
                ii = at[k]; dr = s[k]
                for hb in (4, 8):
                    x = np.maximum(np.minimum(ii + hb * tf, exb(ii)), ii + 1)
                    go(f"M{tf} LORENTZ hold{hb}bars{(' ' + flt) if flt else ''}",
                       pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 2.0 * xa[k], "tp": np.nan, "x": x}), one=False)

    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        say(f"{len(R)} variants; PASS {int(R.ok.sum())}; median PF {R.PF.median():.2f}, random {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
        say("by timeframe: " + "  ".join(f"{f}: {g.PF.median():.2f} (rand {g.rand.median():.2f}, n {len(g)}, trades/wk {g.wk.median():.0f})" for f, g in R.groupby("tf")))
        say("by system: " + "  ".join(f"{f}: {g.PF.median():.2f}" for f, g in R.groupby("sys")))
        say("\nTOP 25 by PF with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(25).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
