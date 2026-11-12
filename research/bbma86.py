"""Round 86 (12 Nov 2026): owner: "csak tak perlu ikut arah bro. ikut arah tu cuma di m30 atau h1 je kena sama dengan h4".
The rejection (H1 / M30) must follow the H4 direction; the M15 CSAK after it may go EITHER way and the trade follows the
CSAK. Same filters and controls as round 85. From round 85:

Round 85 (12 Nov 2026): which indicator helps the M15 CSAK (owner: "kau check lagi indikator yang membantu csak").
Three populations: (A) every M15 CSAK, (B) M15 CSAK in the H4 EMA 50 / 90 direction, (C) the full round 84 SOP (M30
rejection, 8 bars). About 30 filters known at the CSAK close, alone, then the best pairs. A filter only counts if it
keeps >= 150 trades (A / B), lifts PF in BOTH halves, and beats random masks that keep the same share of trades.
Exit: SL under the CSAK candle, TP 2R and 1R, 48 h cap, swap. Engine of round 84:

Round 84 (12 Nov 2026): the owner's BBMA SOP on its original timeframes, with a CCI filter on the CSAK.

Owner: "arah h4, ema50 90 jadi penentu. h4 cari candle mom 8 candle lookback. lepas mom, di h1/m30 tunggu reject
ema50, lepas reject di jumpai, tggu di m15 candle buat csak. gabungkan sekali dengan cci ... sekarang kita guna sop
asal dan tf asal".  BUY (SELL mirrored):
  1 H4 trend     EMA 50 above EMA 90 on the last closed H4 candle
  2 H4 momentum  one of the last 8 closed H4 candles closed above the top BB (20, 2), no bottom-BB momentum after it,
                 and no H4 close below the H4 EMA 50 since it (the old SOP's cancel rule)
  3 rejection    after the momentum candle closed, an H1 (or M30) candle touches EMA 50 (low <= EMA) and closes back
                 above it, the candle before it also closed above its EMA 50; valid REJ_BARS candles of that TF
  4 CSAK (M15)   after that rejection, an M15 candle opens below min(mid BB, EMA 50) and closes above max(mid BB,
                 EMA 50), not above the top BB -> BUY at the next M15 open; CCI(20) of that M15 candle > 100 / > 0 /
                 any (the filter the owner asked for, from round 83 where CCI > 100 was the one cell above 1)
  Exit           SL under the rejection candle's low (minus the spread) or under the CSAK candle's low; TP 1R / 2R /
                 the H4 top BB; 48-hour cap; swap $0.80 per 0.01 lot per night held.  One trade per rejection, one
                 position at a time.  Executed on the broker's M1 bars.  $ per 0.01 lot.
Controls: the same entries with a random direction; the same CSAK + CCI on M15 with no H4 / rejection context.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)
SWAP = 0.80
ANYDIR = True


def ind(X):
    c = X.c
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    tp = (X.h + X.l + X.c) / 3; sm = tp.rolling(20).mean()
    md = tp.rolling(20).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True)
    return pd.DataFrame({"mid": mid, "top": mid + 2 * sd, "bot": mid - 2 * sd, "e50": c.ewm(span=50, adjust=False).mean(),
                         "e90": c.ewm(span=90, adjust=False).mean(), "cci": (tp - sm) / (0.015 * md)}, index=X.index)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    B = B[["o", "h", "l", "c", "s"]].copy()
    T = B.index; n = len(B); end = T[-1]
    O, H, L, C, S = (B[x].values.astype(float) for x in ("o", "h", "l", "c", "s"))
    day = T.normalize().values
    say(f"XAUUSD M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars")

    def tf(m):
        g = B.resample(f"{m}min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        I = ind(X)
        return X, I, (X.index + pd.Timedelta(minutes=m)).values      # bar data is known from its close
    X4, I4, cl4 = tf(240)
    X15, I15, cl15 = tf(15)
    c4, top4, bot4, e50_4, e90_4 = X4.c.values, I4.top.values, I4.bot.values, I4.e50.values, I4.e90.values
    mu4 = c4 > top4; md4 = c4 < bot4
    o15, h15, l15, c15 = (X15[x].values for x in ("o", "h", "l", "c"))
    mid15, top15, bot15, e15, cci15 = I15.mid.values, I15.top.values, I15.bot.values, I15.e50.values, I15.cci.values
    lo_, hi_ = np.minimum(mid15, e15), np.maximum(mid15, e15)
    csak_b = (o15 < lo_) & (c15 > hi_) & (c15 <= top15)
    csak_s = (o15 > hi_) & (c15 < lo_) & (c15 >= bot15)
    m1_at = np.searchsorted(T.values, cl15)                            # first M1 bar at / after each M15 close
    hm15 = X15.index.hour.values * 60 + X15.index.minute.values

    def setups(rtf, rej_bars):
        XR, IR, clR = tf(rtf)
        cR, lR, hR, eR = XR.c.values, XR.l.values, XR.h.values, IR.e50.values
        pa = np.r_[False, (cR > eR)[:-1]]; pb = np.r_[False, (cR < eR)[:-1]]
        rb = (lR <= eR) & (cR > eR) & pa
        rs = (hR >= eR) & (cR < eR) & pb
        out = []                                                       # (k15, dir, rejection id, rejection extreme)
        k4 = np.searchsorted(cl4, cl15, side="right") - 1              # last H4 closed by each M15 close
        kR = np.searchsorted(clR, cl15, side="right") - 1
        lastrb = pd.Series(np.where(rb, np.arange(len(rb)), np.nan)).ffill().values
        lastrs = pd.Series(np.where(rs, np.arange(len(rs)), np.nan)).ffill().values
        for k in np.where(csak_b | csak_s)[0]:
            a, r = k4[k], kR[k]
            if a < 100 or r < 1: continue
            cd = 1 if csak_b[k] else -1                                    # the CSAK's own direction
            dr = 1 if e50_4[a] > e90_4[a] else (-1 if e50_4[a] < e90_4[a] else 0)   # H4 direction, for momentum + rejection
            if dr == 0: continue
            win = np.arange(a - 7, a + 1)
            moms = win[mu4[win]] if dr == 1 else win[md4[win]]
            if len(moms) == 0: continue
            j = moms[-1]
            if dr == 1 and (md4[j + 1:a + 1].any() or (c4[j + 1:a + 1] < e50_4[j + 1:a + 1]).any()): continue
            if dr == -1 and (mu4[j + 1:a + 1].any() or (c4[j + 1:a + 1] > e50_4[j + 1:a + 1]).any()): continue
            q = lastrb[r] if dr == 1 else lastrs[r]
            if np.isnan(q): continue
            q = int(q)
            if r - q >= rej_bars or XR.index[q] < pd.Timestamp(cl4[j]): continue   # rejection after the momentum closed
            if ANYDIR or cd == dr: out.append((k, cd, q, lR[q] if dr == 1 else hR[q]))
        return out

    def sim(S_, cci_min=None, sl_mode="rej", tpm="2R", rand=False, ctx=True):
        res = []; busy = -1; used = set(); rg = np.random.default_rng(84)
        for k, dr, q, ext in S_:
            if cci_min is not None and not (cci15[k] * dr > cci_min): continue
            if ctx and q in used: continue
            i = m1_at[k]
            if i >= n or i <= busy: continue
            if not (90 <= hm15[k] < 1320): continue
            e = O[i] + (S[i] if dr == 1 else 0)
            if sl_mode == "rej": sl = ext - S[i] if dr == 1 else ext + S[i]
            else: sl = l15[k] - S[i] if dr == 1 else h15[k] + S[i]
            if rand:
                risk = abs(e - sl); dr = 1 if rg.random() < 0.5 else -1
                e = O[i] + (S[i] if dr == 1 else 0); sl = e - dr * risk
            risk = (e - sl) * dr
            if risk <= 0.1: continue
            if tpm.endswith("R"): tp = e + dr * float(tpm[:-1]) * risk
            else:
                a = np.searchsorted(cl4, cl15[k], side="right") - 1
                tp = top4[a] if dr == 1 else bot4[a]
                if (tp - e) * dr <= 0: continue
            x = None; z = i; nights = 0
            while z < n:
                if z > i and day[z] != day[z - 1]: nights += 1
                if z - i >= 48 * 60:
                    x = O[z] + (S[z] if dr == -1 else 0); break
                if dr == 1:
                    if L[z] <= sl: x = min(O[z], sl) if z > i else sl; break
                    if z > i and H[z] >= tp: x = max(O[z], tp); break
                else:
                    if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; break
                    if z > i and L[z] + S[z] <= tp: x = min(O[z] + S[z], tp); break
                z += 1
            if x is None: continue
            res.append((T[i], (x - e) * dr * usd - SWAP * nights, (z - i) / 60)); busy = z
            if ctx: used.add(q)
        return pd.DataFrame(res, columns=["t", "net", "hours"])


    # ---------- indicators on M15 (known at the CSAK close) ----------
    X = X15; c = X.c; h = X.h; l = X.l; o = X.o
    dC = c.diff()
    rsi = lambda p: (100 - 100 / (1 + dC.clip(lower=0).ewm(alpha=1 / p, adjust=False).mean() / (-dC.clip(upper=0)).ewm(alpha=1 / p, adjust=False).mean().replace(0, np.nan))).values
    r14 = rsi(14); r7 = rsi(7)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); sig = macd.ewm(span=9, adjust=False).mean()
    hist = (macd - sig).values; histp = np.r_[np.nan, hist[:-1]]; macdv = macd.values; sigv = sig.values
    ll = l.rolling(14).min(); hh = h.rolling(14).max()
    K = (100 * (c - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean(); Dd = K.rolling(3).mean(); K, Dd = K.values, Dd.values
    wpr = (-100 * (hh - c) / (hh - ll).replace(0, np.nan)).values
    pc = c.shift(1); tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().values; atrp = np.r_[np.nan, atr[:-1]]
    up = h.diff(); dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    ew = lambda x: pd.Series(x).ewm(alpha=1 / 14, adjust=False).mean().values
    pdi = 100 * ew(pdm) / atr; ndi = 100 * ew(ndm) / atr
    adx = ew(100 * np.abs(pdi - ndi) / np.where(pdi + ndi > 0, pdi + ndi, np.nan))
    e200 = c.ewm(span=200, adjust=False).mean().values; e20 = c.ewm(span=20, adjust=False).mean().values
    eslope = I15.e50.values - np.r_[[np.nan] * 5, I15.e50.values[:-5]]
    width = (I15.top - I15.bot).values; widthp = np.r_[[np.nan] * 3, width[:-3]]
    hac = ((o + h + l + c) / 4).values; hao = np.zeros(len(c)); hao[0] = (o.iloc[0] + c.iloc[0]) / 2
    for i in range(1, len(c)): hao[i] = (hao[i - 1] + hac[i - 1]) / 2
    rng = (h - l).values; body = (c - o).values
    pos = np.where(rng > 0, (c.values - l.values) / np.where(rng > 0, rng, 1), 0.5)
    arup = (100 * (25 - h.rolling(26).apply(lambda a: 25 - a.argmax(), raw=True)) / 25).values
    ardn = (100 * (25 - l.rolling(26).apply(lambda a: 25 - a.argmin(), raw=True)) / 25).values
    don_h = h.rolling(20).max().shift(1).values; don_l = l.rolling(20).min().shift(1).values
    # supertrend 10, 3
    hl2 = ((h + l) / 2).values; ub = hl2 + 3 * atr; lb = hl2 - 3 * atr; st = np.ones(len(c)); fu = ub.copy(); fl = lb.copy(); cv = c.values
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or cv[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or cv[i - 1] < fl[i - 1]) else fl[i - 1]
        st[i] = 1 if cv[i] > fu[i - 1] else (-1 if cv[i] < fl[i - 1] else st[i - 1])
    # Ichimoku cloud on M15
    tk = (h.rolling(9).max() + l.rolling(9).min()) / 2; kj = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa = ((tk + kj) / 2).shift(26).values; sb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26).values
    ctop = np.fmax(sa, sb); cbot = np.fmin(sa, sb)
    # higher-timeframe RSI, as of the M15 close
    def htf_rsi(m):
        Xh, _, clh = tf(m); dd = Xh.c.diff()
        rr = (100 - 100 / (1 + dd.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-dd.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan))).values
        j = np.searchsorted(clh, cl15, side="right") - 1
        return np.where(j >= 0, rr[np.clip(j, 0, None)], np.nan)
    rH1 = htf_rsi(60); rH4 = htf_rsi(240)
    a4 = np.searchsorted(cl4, cl15, side="right") - 1
    trend4 = np.where(a4 >= 0, np.sign(e50_4[np.clip(a4, 0, None)] - e90_4[np.clip(a4, 0, None)]), 0)
    gateok = True
    ma5h = (h.rolling(5).apply(lambda a: (a * np.arange(1, 6)).sum() / 15, raw=True)).values
    ma10h = (h.rolling(10).apply(lambda a: (a * np.arange(1, 11)).sum() / 55, raw=True)).values
    ma5l = (l.rolling(5).apply(lambda a: (a * np.arange(1, 6)).sum() / 15, raw=True)).values
    ma10l = (l.rolling(10).apply(lambda a: (a * np.arange(1, 11)).sum() / 55, raw=True)).values
    sess = (hm15 >= 540) & (hm15 < 1260)                                # London + New York, server time
    # each filter: (buy mask, sell mask)
    F = {
        "RSI14 > 50": (r14 > 50, r14 < 50), "RSI14 > 55": (r14 > 55, r14 < 45), "RSI14 > 60": (r14 > 60, r14 < 40),
        "RSI7 > 60": (r7 > 60, r7 < 40),
        "MACD hist > 0": (hist > 0, hist < 0), "MACD hist rising": (hist > histp, hist < histp),
        "MACD line > signal and > 0": ((macdv > sigv) & (macdv > 0), (macdv < sigv) & (macdv < 0)),
        "Stoch14 %K > %D, %K < 80": ((K > Dd) & (K < 80), (K < Dd) & (K > 20)),
        "Williams %R > -50": (wpr > -50, wpr < -50),
        "ADX > 20 and DI aligned": ((adx > 20) & (pdi > ndi), (adx > 20) & (ndi > pdi)),
        "ADX > 25 and DI aligned": ((adx > 25) & (pdi > ndi), (adx > 25) & (ndi > pdi)),
        "ADX < 20 (quiet)": (adx < 20, adx < 20),
        "CCI20 > 0": (cci15 > 0, cci15 < 0), "CCI20 > 50": (cci15 > 50, cci15 < -50), "CCI20 0..100": ((cci15 > 0) & (cci15 < 100), (cci15 < 0) & (cci15 > -100)),
        "Heikin Ashi same colour": (hac > hao, hac < hao),
        "Supertrend 10,3 aligned": (st == 1, st == -1),
        "above / below EMA 200": (cv > e200, cv < e200),
        "EMA 50 rising / falling (5 bars)": (eslope > 0, eslope < 0),
        "EMA 20 above / below EMA 50": (e20 > I15.e50.values, e20 < I15.e50.values),
        "BB width expanding": (width > widthp, width > widthp),
        "BB width contracting": (width < widthp, width < widthp),
        "close beyond MA5 / MA10": (cv > np.fmax(ma5h, ma10h), cv < np.fmin(ma5l, ma10l)),
        "body >= 0.6 ATR": (np.abs(body) >= 0.6 * atrp, np.abs(body) >= 0.6 * atrp),
        "body >= 1 ATR": (np.abs(body) >= atrp, np.abs(body) >= atrp),
        "body <= 0.6 ATR": (np.abs(body) <= 0.6 * atrp, np.abs(body) <= 0.6 * atrp),
        "close in the top / bottom 25% of the candle": (pos >= 0.75, pos <= 0.25),
        "ATR rising": (atr > atrp, atr > atrp),
        "Aroon up > 70 / down > 70": (arup > 70, ardn > 70),
        "Donchian 20 breakout": (cv > don_h, cv < don_l),
        "M15 close above / below the Ichimoku cloud": (cv > ctop, cv < cbot),
        "H1 RSI > 50": (rH1 > 50, rH1 < 50), "H4 RSI > 50": (rH4 > 50, rH4 < 50),
        "London + New York session only": (sess, sess),
    }
    pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0
    mid = T[n // 2]
    W = lambda R, a, b=None: R[(R.t >= end - pd.Timedelta(days=a)) & (R.t < (end - pd.Timedelta(days=b) if b else end + pd.Timedelta(minutes=1)))].net

    def run(S_, mask_b, mask_s, tpm):
        keep = [x for x in S_ if (mask_b[x[0]] if x[1] == 1 else mask_s[x[0]])]
        return sim(keep, None, "csak", tpm, ctx=False)

    base_all = [(k, 1 if csak_b[k] else -1, k, l15[k] if csak_b[k] else h15[k]) for k in np.where(csak_b | csak_s)[0]]
    base_trend = [x for x in base_all if trend4[x[0]] == x[1]]
    rg = np.random.default_rng(85)
    S30 = setups(30, 8); S60 = setups(60, 8)
    pops = (("M30 rejection (H4 direction) -> M15 CSAK, ANY direction", S30), ("H1 rejection (H4 direction) -> M15 CSAK, ANY direction", S60),
            ("M30: only CSAKs AGAINST the rejection", [x for x in S30 if x[1] != (1 if x[3] < 1e9 and x in S30 else 0)]))
    def against(S_):
        out = []
        for x in S_:
            a = np.searchsorted(cl4, cl15[x[0]], side="right") - 1
            if x[1] != (1 if e50_4[a] > e90_4[a] else -1): out.append(x)
        return out
    pops = pops[:2] + (("M30 rejection -> only CSAKs AGAINST the H4 / rejection direction", against(S30)),
                       ("M30 rejection -> only CSAKs WITH the H4 / rejection direction", [x for x in S30 if x not in against(S30)]))
    for pname, P in pops:
        for tpm in ("2R", "1R"):
            ones = np.ones(len(cl15), bool)
            R0 = run(P, ones, ones, tpm)
            if len(R0) < 30: say(f"\n{pname}: too few"); continue
            p0, h1_0, h2_0 = pf(R0.net), pf(R0.net[R0.t < mid]), pf(R0.net[R0.t >= mid])
            say(f"\n===== {pname}, SL CSAK, TP {tpm}: {len(R0)} trades, PF {p0:.2f}, halves {h1_0:.2f} / {h2_0:.2f}, 12 mo ${W(R0, 365).sum():+.0f}, 3 mo ${W(R0, 91).sum():+.0f}, 6.6 y ${R0.net.sum():+.0f} =====")
            # random-mask control: keep the same share of trades at random, 30 draws, for shares 30 / 50 / 70%
            rc = {}
            for share in (0.3, 0.5, 0.7):
                v = []
                for _ in range(30):
                    m = rg.random(len(cl15)) < share
                    Rr = run(P, m, m, tpm); v.append(pf(Rr.net))
                rc[share] = (np.percentile(v, 50), np.percentile(v, 95))
            say("random filters keeping 30 / 50 / 70% of trades: median PF " + " / ".join(f"{rc[s][0]:.2f}" for s in rc) + ", 95th percentile " + " / ".join(f"{rc[s][1]:.2f}" for s in rc))
            rows = []
            for nm, (mb, ms) in F.items():
                mb = np.where(np.isnan(mb.astype(float)), False, mb).astype(bool); ms = np.where(np.isnan(ms.astype(float)), False, ms).astype(bool)
                R = run(P, mb, ms, tpm)
                if len(R) < 20: continue
                share = len(R) / len(R0)
                p95 = rc[min(rc, key=lambda s: abs(s - share))][1]
                rows.append((pf(R.net), nm, len(R), share, pf(R.net[R.t < mid]), pf(R.net[R.t >= mid]), W(R, 30).sum(), W(R, 91).sum(), W(R, 365).sum(), R.net.sum(), p95, mb, ms))
            rows.sort(key=lambda r: -r[0])
            say(f"{'filter':46s} {'trades':>6} {'kept':>5} {'PF':>5} {'half1':>5} {'half2':>5} | {'last mo':>7} {'3 mo':>6} {'12 mo':>6} {'6.6 y':>7} | beats random 95%?")
            for r in rows:
                ok = "YES" if (r[0] > r[10] and r[4] > h1_0 and r[5] > h2_0) else ""
                say(f"{r[1]:46s} {r[2]:6d} {100 * r[3]:4.0f}% {r[0]:5.2f} {r[4]:5.2f} {r[5]:5.2f} | {r[6]:+7.0f} {r[7]:+6.0f} {r[8]:+6.0f} {r[9]:+7.0f} | {ok}")
            # best pairs among the top 6
            top = rows[:6]; pairs = []
            for i in range(len(top)):
                for j in range(i + 1, len(top)):
                    R = run(P, top[i][11] & top[j][11], top[i][12] & top[j][12], tpm)
                    if len(R) >= 20: pairs.append((pf(R.net), f"{top[i][1]} + {top[j][1]}", len(R), pf(R.net[R.t < mid]), pf(R.net[R.t >= mid]), W(R, 91).sum(), W(R, 365).sum(), R.net.sum()))
            pairs.sort(key=lambda r: -r[0])
            say("best pairs (from the top 6):")
            for r in pairs[:6]:
                say(f"   {r[1]:84s} {r[2]:5d} PF {r[0]:.2f} halves {r[3]:.2f} / {r[4]:.2f} | 3 mo ${r[5]:+.0f} 12 mo ${r[6]:+.0f} 6.6 y ${r[7]:+.0f}")
        say(f"   [{time.time() - T0:.0f} s]")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
