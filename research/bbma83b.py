"""Round 83b (12 Nov 2026): owner doubted ~1 trade a day ("tak kan sehari 1 trade? ... momentum m15 tu").
Counts the funnel (M15 momentum candles, M5 EMA 50 rejections after a momentum, M1 CSAKs after a rejection) and
re-runs TP 2R with longer windows. Engine of round 83:

Round 83 (12 Nov 2026): the owner's BBMA multi-timeframe entry on gold.

Owner: "cari mom m15, m5 reject ema50, m1 cari csak dan untuk kuat kan lagi signal csak, kau cari melalui indikator
apa yang sesuai menandakan itu sebagai signal buy/sell".  Definitions are the ones in bbma_scanner.py (BBMA Oma Ally):
  BB 20, 2 (population sd), EMA 50, MA5 / MA10 = LWMA of highs / lows.
  MOM (M15)   a closed M15 candle closes above the top BB (buy) / below the bottom BB (sell); valid for MOM_BARS M15
              candles, cancelled by a momentum the other way
  REJ (M5)    after that momentum, a closed M5 candle touches EMA 50 (low <= EMA, buy) and closes back above it, the
              M5 close before it also above its EMA 50; valid for REJ_BARS M5 candles
  CSAK (M1)   after that rejection, ONE closed M1 candle opens below min(mid BB, EMA 50) and closes above max(mid BB,
              EMA 50), and not above the top BB (that would already be a momentum candle) -> BUY at the next open
  Exit        SL under the M5 rejection's low (buy) minus the spread; TP 1R / 2R / at the M15 top BB; 120-minute cap;
              flat at 23:45 server.  One position at a time, one trade per M5 rejection.
CONFIRMATION INDICATORS tested on top of the CSAK (all known at the CSAK close): RSI(14) > 50, MACD(12,26,9) histogram
> 0 and rising, Stochastic(5,3,3) %K > %D, ADX(14) > 20 with +DI > -DI, CCI(20) > 0, Parabolic SAR below price,
Heikin Ashi candle bullish, tick volume > 1.5 x its 20-bar mean, CSAK body >= 1 ATR, cost gate ATR >= 8 x spread,
MA5/10: close above MA5 high and MA10 high (BBMA's own CSAK strength).  Each alone, then the best pairs.
Controls: the same entries with a random direction; CSAK on M1 with no MOM / REJ context.  $ per 0.01 lot.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)
MOM_BARS, REJ_BARS = int(os.environ.get("MOMB", 8)), int(os.environ.get("REJB", 6))


def bbma(df):
    c = df.c; h = df.h; l = df.l
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    w5 = np.arange(1, 6, dtype=float); w10 = np.arange(1, 11, dtype=float)
    lw = lambda x, w: x.rolling(len(w)).apply(lambda a: (a * w).sum() / w.sum(), raw=True)
    out = pd.DataFrame({"mid": mid, "top": mid + 2 * sd, "bot": mid - 2 * sd, "ema": c.ewm(span=50, adjust=False).mean(),
                        "ma5h": lw(h, w5), "ma10h": lw(h, w10), "ma5l": lw(l, w5), "ma10l": lw(l, w10)}, index=df.index)
    return out


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    B = B[["o", "h", "l", "c", "s"] + (["v"] if "v" in B.columns else [])].copy()
    T = B.index; n = len(B); end = T[-1]
    O, H, L, C, S = (B[x].values.astype(float) for x in ("o", "h", "l", "c", "s"))
    V = B.v.values.astype(float) if "v" in B.columns else np.ones(n)
    hm = T.hour.values * 60 + T.minute.values
    say(f"XAUUSD M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars (tick volume {'yes' if 'v' in B.columns else 'NOT in export'})")

    def tf(m):
        g = B.resample(f"{m}min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        return X
    # ---- M15 momentum, as of the CLOSE of each M15 bar (available from bar start + 15 min)
    X15 = tf(15); I15 = bbma(X15)
    mu = (X15.c > I15.top).values; md = (X15.c < I15.bot).values
    avail15 = X15.index + pd.Timedelta(minutes=15)
    # ---- M5 EMA 50 rejection
    X5 = tf(5); I5 = bbma(X5)
    e5 = I5.ema.values; c5 = X5.c.values; l5 = X5.l.values; h5 = X5.h.values
    pc_above = np.r_[False, (c5 > e5)[:-1]]; pc_below = np.r_[False, (c5 < e5)[:-1]]
    rbuy = (l5 <= e5) & (c5 > e5) & pc_above
    rsell = (h5 >= e5) & (c5 < e5) & pc_below
    avail5 = X5.index + pd.Timedelta(minutes=5)
    # ---- M1 indicators
    I1 = bbma(B.rename(columns={}))
    mid1, top1, bot1, ema1 = I1.mid.values, I1.top.values, I1.bot.values, I1.ema.values
    c1p = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1p), np.abs(L - c1p)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    a1 = np.r_[np.nan, atr[:-1]]
    gate = a1 / np.where(S > 0, S, np.nan)
    lo_, hi_ = np.minimum(mid1, ema1), np.maximum(mid1, ema1)
    csak_b = (O < lo_) & (C > hi_) & (C <= top1)
    csak_s = (O > hi_) & (C < lo_) & (C >= bot1)
    dC = np.diff(C, prepend=C[0])
    up = pd.Series(np.maximum(dC, 0)).ewm(alpha=1 / 14, adjust=False).mean(); dn = pd.Series(np.maximum(-dC, 0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    ef = pd.Series(C).ewm(span=12, adjust=False).mean(); es = pd.Series(C).ewm(span=26, adjust=False).mean()
    macd = ef - es; hist = (macd - macd.ewm(span=9, adjust=False).mean()).values; histp = np.r_[np.nan, hist[:-1]]
    ll = pd.Series(L).rolling(5).min(); hh = pd.Series(H).rolling(5).max()
    K = (100 * (pd.Series(C) - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean(); Dd = K.rolling(3).mean()
    K, Dd = K.values, Dd.values
    upm = H - np.r_[H[0], H[:-1]]; dnm = np.r_[L[0], L[:-1]] - L
    pdm = np.where((upm > dnm) & (upm > 0), upm, 0); ndm = np.where((dnm > upm) & (dnm > 0), dnm, 0)
    sm = lambda x: pd.Series(x).ewm(alpha=1 / 14, adjust=False).mean().values
    pdi = 100 * sm(pdm) / np.where(atr > 0, atr, np.nan); ndi = 100 * sm(ndm) / np.where(atr > 0, atr, np.nan)
    adx = sm(100 * np.abs(pdi - ndi) / np.where(pdi + ndi > 0, pdi + ndi, np.nan))
    tp_ = (H + L + C) / 3; sma = pd.Series(tp_).rolling(20).mean(); mdv = pd.Series(tp_).rolling(20).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True)
    cci = ((pd.Series(tp_) - sma) / (0.015 * mdv)).values
    # parabolic SAR
    sar = np.zeros(n); bull = True; af = 0.02; ep = H[0]; sar[0] = L[0]
    for i in range(1, n):
        s = sar[i - 1] + af * (ep - sar[i - 1])
        if bull:
            s = min(s, L[i - 1], L[i - 2] if i > 1 else L[i - 1])
            if L[i] < s: bull = False; s = ep; ep = L[i]; af = 0.02
            elif H[i] > ep: ep = H[i]; af = min(af + 0.02, 0.2)
        else:
            s = max(s, H[i - 1], H[i - 2] if i > 1 else H[i - 1])
            if H[i] > s: bull = True; s = ep; ep = H[i]; af = 0.02
            elif L[i] < ep: ep = L[i]; af = min(af + 0.02, 0.2)
        sar[i] = s
    hac = (O + H + L + C) / 4; hao = np.zeros(n); hao[0] = (O[0] + C[0]) / 2
    for i in range(1, n): hao[i] = (hao[i - 1] + hac[i - 1]) / 2
    vol_hi = V > 1.5 * pd.Series(V).rolling(20).mean().shift(1).values
    body_big = np.abs(C - O) >= a1
    filt = {
        "RSI14 > 50 (< 50 sell)": (rsi > 50, rsi < 50),
        "MACD hist > 0 and rising": ((hist > 0) & (hist > histp), (hist < 0) & (hist < histp)),
        "Stoch 5,3,3 %K > %D": (K > Dd, K < Dd),
        "ADX14 > 20 and +DI > -DI": ((adx > 20) & (pdi > ndi), (adx > 20) & (ndi > pdi)),
        "CCI20 > 0": (cci > 0, cci < 0),
        "CCI20 > 100": (cci > 100, cci < -100),
        "Parabolic SAR on the right side": (sar < C, sar > C),
        "Heikin Ashi candle same colour": (hac > hao, hac < hao),
        "tick volume > 1.5 x 20-bar mean": (vol_hi, vol_hi),
        "CSAK body >= 1 ATR": (body_big, body_big),
        "cost gate ATR >= 8 x spread": (gate >= 8, gate >= 8),
        "close beyond MA5 / MA10 (BBMA)": (C > np.maximum(I1.ma5h.values, I1.ma10h.values), C < np.minimum(I1.ma5l.values, I1.ma10l.values)),
    }
    # ---- walk the M1 bars: state of the latest M15 momentum and the latest M5 rejection
    i15 = np.searchsorted(avail15.values, T.values, side="right") - 1          # last M15 bar closed at or before T (bar start)
    i5 = np.searchsorted(avail5.values, T.values, side="right") - 1
    last_up = pd.Series(np.where(mu, np.arange(len(mu)), np.nan)).ffill().values
    last_dn = pd.Series(np.where(md, np.arange(len(md)), np.nan)).ffill().values
    last_rb = pd.Series(np.where(rbuy, np.arange(len(rbuy)), np.nan)).ffill().values
    last_rs = pd.Series(np.where(rsell, np.arange(len(rsell)), np.nan)).ffill().values
    # a signal at M1 bar k uses bars CLOSED by the close of k, i.e. available at T[k] + 1 min
    k15 = np.searchsorted(avail15.values, (T + pd.Timedelta(minutes=1)).values, side="right") - 1
    k5 = np.searchsorted(avail5.values, (T + pd.Timedelta(minutes=1)).values, side="right") - 1
    ok = (hm >= 90) & (hm < 1320) & (T.dayofweek.values < 5)
    sig = np.zeros(n, int); rejid = np.full(n, -1); rejx = np.zeros(n)
    for k in np.where((csak_b | csak_s) & ok)[0]:
        a, b = k15[k], k5[k]
        if a < 0 or b < 0: continue
        dr = 1 if csak_b[k] else -1
        lu, ld = last_up[a], last_dn[a]
        if dr == 1:
            if np.isnan(lu) or (not np.isnan(ld) and ld > lu) or a - lu >= MOM_BARS: continue
            r = last_rb[b]
            if np.isnan(r) or b - r >= REJ_BARS: continue
            if X5.index[int(r)] + pd.Timedelta(minutes=5) < avail15[int(lu)]: continue   # rejection after the momentum
            rejx[k] = l5[int(r)]
        else:
            if np.isnan(ld) or (not np.isnan(lu) and lu > ld) or a - ld >= MOM_BARS: continue
            r = last_rs[b]
            if np.isnan(r) or b - r >= REJ_BARS: continue
            if X5.index[int(r)] + pd.Timedelta(minutes=5) < avail15[int(ld)]: continue
            rejx[k] = h5[int(r)]
        sig[k] = dr; rejid[k] = int(r) * dr
    top15 = I15.top.values; bot15 = I15.bot.values
    say(f"setups (MOM M15 -> REJ M5 -> CSAK M1): {int((sig != 0).sum())} candidate CSAK bars")
    nd = pd.Series(T.normalize()).nunique()
    say(f"FUNNEL per trading day ({nd} days): M15 momentum candles {(mu.sum() + md.sum()) / nd:.1f} (buy {mu.sum() / nd:.1f}, sell {md.sum() / nd:.1f}); "
        f"M5 EMA 50 rejection candles (any) {(rbuy.sum() + rsell.sum()) / nd:.1f}; M1 CSAK candles (any) {((csak_b | csak_s) & ok).sum() / nd:.1f}; "
        f"CSAK bars that complete the full chain {(sig != 0).sum() / nd:.2f}; distinct rejections with a CSAK {len(set(rejid[sig != 0])) / nd:.2f}")

    def sim(mask, tpm="2R", rand=False, ctx=True):
        res = []; busy = -1; used = set(); rg = np.random.default_rng(83)
        src = sig if ctx else np.where(csak_b & ok, 1, np.where(csak_s & ok, -1, 0))
        for k in np.where((src != 0) & mask)[0]:
            if k <= busy or k + 1 >= n: continue
            if ctx:
                if rejid[k] in used: continue
            dr = int(src[k]); e = O[k + 1] + (S[k + 1] if dr == 1 else 0)
            if ctx: sl = rejx[k] - S[k + 1] if dr == 1 else rejx[k] + S[k + 1]
            else: sl = (L[k] - 0.2 * atr[k]) if dr == 1 else (H[k] + 0.2 * atr[k] + S[k + 1])
            if rand: dr = 1 if rg.random() < 0.5 else -1; e = O[k + 1] + (S[k + 1] if dr == 1 else 0); sl = e - dr * abs(e - sl)
            risk = (e - sl) * dr
            if risk <= 0.05: continue
            if tpm.endswith("R"): tp = e + dr * float(tpm[:-1]) * risk
            else:
                a = k15[k]; tp = top15[a] if dr == 1 else bot15[a]
                if (tp - e) * dr <= 0: continue
            x = None; q = k + 1
            while q < n:
                if q - (k + 1) >= 120 or hm[q] >= 1425 or T[q].date() != T[k + 1].date():
                    x = O[q] + (S[q] if dr == -1 else 0); break
                if dr == 1:
                    if L[q] <= sl: x = min(O[q], sl) if q > k + 1 else sl; break
                    if H[q] >= tp and q > k + 1: x = max(O[q], tp); break
                else:
                    if H[q] + S[q] >= sl: x = max(O[q] + S[q], sl) if q > k + 1 else sl; break
                    if L[q] + S[q] <= tp and q > k + 1: x = min(O[q] + S[q], tp); break
                q += 1
            if x is None: continue
            res.append((T[k + 1], (x - e) * dr * usd)); busy = q
            if ctx: used.add(rejid[k])
        return pd.DataFrame(res, columns=["t", "net"])

    pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0
    mid = T[n // 2]; days = pd.Series(T.normalize()).nunique()
    W = lambda R, a, b=None: R[(R.t >= end - pd.Timedelta(days=a)) & (R.t < (end - pd.Timedelta(days=b) if b else end + pd.Timedelta(minutes=1)))].net
    rows = []
    def rec(name, R):
        if len(R) < 20: rows.append((name, len(R)) + (0,) * 10); return
        dly = R.groupby(R.t.dt.normalize()).net.sum()
        rows.append((name, len(R), len(R) / days, 100 * (R.net > 0).mean(), pf(R.net), pf(R.net[R.t < mid]), pf(R.net[R.t >= mid]),
                     W(R, 30).sum(), W(R, 60, 30).sum(), W(R, 91).sum(), W(R, 365).sum(), dly.min()))
    allm = np.ones(n, bool)
    for tpm in ("1R", "2R", "BB"):
        rec(f"BBMA MOM-REJ-CSAK, TP {tpm}", sim(allm, tpm))
    rec("CONTROL: same, random direction, TP 2R", sim(allm, "2R", rand=True))
    rec("CONTROL: CSAK on M1 alone (no MOM / REJ), SL under the bar, TP 2R", sim(allm, "2R", ctx=False))
    say(f"\n{'variant':78s} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'half1':>5} {'half2':>5} | {'last mo':>7} {'mo before':>9} {'3 mo':>6} {'12 mo':>7} {'worst d':>7}")
    for r in rows:
        if r[1] < 20: say(f"{r[0]:78s} {r[1]:6d}  too few"); continue
        say(f"{r[0]:78s} {r[1]:6d} {r[2]:5.2f} {r[3]:4.0f} {r[4]:5.2f} {r[5]:5.2f} {r[6]:5.2f} | {r[7]:+7.0f} {r[8]:+9.0f} {r[9]:+6.0f} {r[10]:+7.0f} {r[11]:+7.0f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
