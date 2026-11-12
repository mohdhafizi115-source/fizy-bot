"""Round 84 (12 Nov 2026): the owner's BBMA SOP on its original timeframes, with a CCI filter on the CSAK.

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
            dr = 1 if csak_b[k] else -1
            if dr == 1 and not e50_4[a] > e90_4[a]: continue
            if dr == -1 and not e50_4[a] < e90_4[a]: continue
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
            out.append((k, dr, q, lR[q] if dr == 1 else hR[q]))
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

    pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0
    mid = T[n // 2]; days = pd.Series(T.normalize()).nunique()
    W = lambda R, a, b=None: R[(R.t >= end - pd.Timedelta(days=a)) & (R.t < (end - pd.Timedelta(days=b) if b else end + pd.Timedelta(minutes=1)))].net
    say(f"\n{'variant':72s} {'trades':>6} {'/week':>5} {'win%':>4} {'PF':>5} {'half1':>5} {'half2':>5} | {'last mo':>7} {'mo bef':>6} {'3 mo':>6} {'12 mo':>6} {'6.6 y':>7} {'worst':>6} {'hold h':>6}")
    def row(name, R):
        if len(R) < 15: say(f"{name:72s} {len(R):6d}  too few"); return
        eq = R.net.cumsum()
        say(f"{name:72s} {len(R):6d} {len(R) / days * 5:5.1f} {100 * (R.net > 0).mean():4.0f} {pf(R.net):5.2f} {pf(R.net[R.t < mid]):5.2f} {pf(R.net[R.t >= mid]):5.2f} | "
            f"{W(R, 30).sum():+7.0f} {W(R, 60, 30).sum():+6.0f} {W(R, 91).sum():+6.0f} {W(R, 365).sum():+6.0f} {R.net.sum():+7.0f} {R.net.min():+6.0f} {R.hours.median():6.1f}")
    for rtf, rn in ((60, "H1"), (30, "M30")):
        for rb in (4, 8):
            S_ = setups(rtf, rb)
            say(f"\n--- rejection on {rn}, valid {rb} {rn} candles: {len(S_)} CSAK candidates ---")
            for cm, cn in ((None, "no CCI"), (0, "CCI > 0"), (100, "CCI > 100")):
                for sm in ("rej", "csak"):
                    for tpm in ("1R", "2R", "BB"):
                        row(f"{rn} rej{rb} | {cn} | SL {'rejection' if sm == 'rej' else 'CSAK'} | TP {tpm}", sim(S_, cm, sm, tpm))
                row(f"{rn} rej{rb} | {cn} | SL rejection | TP 2R | RANDOM direction", sim(S_, cm, "rej", "2R", rand=True))
        say(f"   [{time.time() - T0:.0f} s]")
    # context control: M15 CSAK + CCI with no H4 / rejection conditions
    allc = [(k, 1 if csak_b[k] else -1, k, l15[k] if csak_b[k] else h15[k]) for k in np.where(csak_b | csak_s)[0]]
    for cm, cn in ((None, "no CCI"), (100, "CCI > 100")):
        row(f"CONTROL: M15 CSAK alone, {cn}, SL CSAK, TP 2R", sim(allc, cm, "csak", "2R", ctx=False))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
