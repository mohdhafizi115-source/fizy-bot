"""BabyPips "Combining Fibs with Trend Lines", turned into fixed rules (buy shown, sell mirrored):
  1. H1 swings: fractal with L candles each side (known L candles after the swing).
  2. Up leg: last confirmed swing low SL1 -> later confirmed swing high SH, size >= min_leg x ATR,
     and no high above SH since then.
  3. Rising trend line through the two last swing lows SL0 < SL1 (higher low), extended to now.
  4. Confluence: the trend line value now sits inside the 50%-61.8% retracement of SL1 -> SH
     (+/- tol x leg).
  5. Bounce: the H1 candle dips to the zone (low <= the higher of fib 50% / trend line), stays above
     SL1, and closes bullish above both the trend line and fib 61.8%. Enter at the next candle open.
  6. SL: below SL1 (swing) or below the bounce candle low (bar), - 0.1 ATR. TP: back to SH
     (needs RR >= 1) or 2R. One trade per leg.
  Optional trend filter: H4 close vs H4 EMA 200."""
import numpy as np, pandas as pd
from bt import resample, atr
from strategies import run_bars, first_bar


def fib_tl(e, tf="1h", L=3, min_leg=2.0, tol=0.05, sl_mode="swing", tp_mode="high", trend=False, swap=True):
    d = resample(e, tf)
    A = atr(d).values
    h, l, o, c = (d[x].values for x in ("high", "low", "open", "close"))
    n = len(d)
    if trend:
        h4 = resample(e, "4h"); ema = h4.close.ewm(span=200, adjust=False).mean()
        st = ((h4.close > ema).astype(int) - (h4.close < ema).astype(int))
        st.index = st.index + pd.Timedelta("4h"); st = st.iloc[200:]
        tdir = st.reindex(d.index + pd.Timedelta(tf), method="ffill").fillna(0).values
    sh, sl = [], []                                   # confirmed swings (index, price)
    used, sig = set(), {}
    for i in range(2 * L + 20, n - 1):
        k = i - L
        if all(h[k] > h[k - q] for q in range(1, L + 1)) and all(h[k] >= h[k + q] for q in range(1, L + 1)):
            sh.append((k, h[k]))
        if all(l[k] < l[k - q] for q in range(1, L + 1)) and all(l[k] <= l[k + q] for q in range(1, L + 1)):
            sl.append((k, l[k]))
        a = A[i]
        if np.isnan(a) or a <= 0:
            continue
        for dr in (1, -1):
            if trend and tdir[i] != dr:
                continue
            ext, piv = (sh, sl) if dr == 1 else (sl, sh)    # ext = leg end, piv = trend line points
            if not ext or len(piv) < 2:
                continue
            xe, pe = ext[-1]
            before = [p for p in piv if p[0] < xe]
            if len(before) < 2:
                continue
            (x0, p0), (x1, p1) = before[-2], before[-1]
            if (dr == 1 and not p1 > p0) or (dr == -1 and not p1 < p0):
                continue                                   # need a higher low / lower high
            leg = (pe - p1) * dr
            if leg < min_leg * a or (dr, x1, xe) in used:
                continue
            seg_h = h[xe + 1:i + 1].max() if i > xe else -np.inf
            seg_l = l[xe + 1:i + 1].min() if i > xe else np.inf
            if (dr == 1 and seg_h > pe) or (dr == -1 and seg_l < pe):
                continue                                   # the leg was extended: wait for a new swing
            if (dr == 1 and seg_l <= p1) or (dr == -1 and seg_h >= p1):
                continue                                   # swing point broken: leg failed
            tl = p1 + (i - x1) * (p1 - p0) / (x1 - x0)
            f50, f618 = pe - dr * 0.5 * leg, pe - dr * 0.618 * leg
            zlo, zhi = min(f50, f618) - tol * leg, max(f50, f618) + tol * leg
            if not (zlo <= tl <= zhi):
                continue
            if dr == 1:
                bounce = l[i] <= max(f50, tl) and c[i] > o[i] and c[i] > tl and c[i] > f618
            else:
                bounce = h[i] >= min(f50, tl) and c[i] < o[i] and c[i] < tl and c[i] < f618
            if not bounce:
                continue
            nt = first_bar(e, d.index[i + 1])
            if nt is None:
                continue
            ref = p1 if sl_mode == "swing" else (l[i] if dr == 1 else h[i])
            stop = ref - dr * 0.1 * a
            risk = (c[i] - stop) * dr
            if risk <= 0:
                continue
            if tp_mode == "high":
                tp = pe
                if (tp - c[i]) * dr < 1.0 * risk:
                    continue
            else:
                tp = c[i] + dr * 2.0 * risk
            used.add((dr, x1, xe))
            sig[nt] = [dict(type="market", dir=dr, price=None, sl=stop, tp=tp, tag="FIBTL")]
            break
    import bt
    old = bt.swap_cost
    if not swap:
        import strategies
        strategies.swap_cost = lambda t0, t1, dr: 0.0
    try:
        return run_bars(e, sig, lambda pos, t, n_: None)
    finally:
        import strategies
        strategies.swap_cost = old
