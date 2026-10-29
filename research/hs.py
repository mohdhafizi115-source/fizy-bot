"""Head and shoulders (top -> sell, inverse/bottom -> buy), classic textbook rules turned into code:
  1. Swings on the pattern TF: fractal with L candles each side, made alternating (high, low, high, ...).
  2. Top: left shoulder P1 < head P2 > right shoulder P3, troughs T1 (between P1-P2) and T2 (P2-P3).
     Shoulders similar: |P1 - P3| <= sym x pattern height. Head stands out: P2 - max(P1, P3) >= 0.15 x height.
     Optional prior trend: P1 is above the lowest low of the `trend_bars` candles before it by >= 1 x height.
  3. Neckline through T1 and T2. Entry when a candle CLOSES below the neckline (within `max_wait` candles of
     the right shoulder, before price goes above P3); enter at the next open.
  4. SL above the right shoulder + 0.1 ATR (or above the head). TP = measured move (head-to-neckline height
     projected from the break) or 2R.
Inverse pattern mirrored."""
import numpy as np, pandas as pd
from bt import resample, atr
from strategies import run_bars, first_bar


def alt_swings(h, l, L, upto):
    """alternating confirmed swings up to index `upto` (inclusive confirmation): list of (idx, price, +1 high / -1 low)"""
    raw = []
    for k in range(L, upto - L + 1):
        if all(h[k] > h[k - q] for q in range(1, L + 1)) and all(h[k] >= h[k + q] for q in range(1, L + 1)):
            raw.append((k, h[k], 1))
        if all(l[k] < l[k - q] for q in range(1, L + 1)) and all(l[k] <= l[k + q] for q in range(1, L + 1)):
            raw.append((k, l[k], -1))
    out = []
    for s in raw:
        if out and out[-1][2] == s[2]:
            if (s[2] == 1 and s[1] > out[-1][1]) or (s[2] == -1 and s[1] < out[-1][1]):
                out[-1] = s
        else:
            out.append(s)
    return out


def head_shoulders(e, tf="1h", L=3, sym=0.35, trend=True, trend_bars=40, max_wait=20, sl_mode="shoulder",
                   tp_mode="measured", swap=True):
    d = resample(e, tf)
    A = atr(d).values
    h, l, c = d.high.values, d.low.values, d.close.values
    n = len(d)
    sig, used = {}, set()
    # incremental swing list (recomputed cheaply: swings at k are known at k + L)
    sw_hi, sw_lo = [], []
    seq = []
    for i in range(2 * L + trend_bars + 5, n - 1):
        k = i - L
        new = []
        if all(h[k] > h[k - q] for q in range(1, L + 1)) and all(h[k] >= h[k + q] for q in range(1, L + 1)):
            new.append((k, h[k], 1))
        if all(l[k] < l[k - q] for q in range(1, L + 1)) and all(l[k] <= l[k + q] for q in range(1, L + 1)):
            new.append((k, l[k], -1))
        for s in new:
            if seq and seq[-1][2] == s[2]:
                if (s[2] == 1 and s[1] > seq[-1][1]) or (s[2] == -1 and s[1] < seq[-1][1]):
                    seq[-1] = s
            else:
                seq.append(s)
        a = A[i]
        if np.isnan(a) or len(seq) < 5:
            continue
        cands = [seq[-5:]] + ([seq[-6:-1]] if len(seq) >= 6 else [])
        for dr, s5 in [(dr_, c5) for dr_ in (-1, 1) for c5 in cands]:   # -1: top (sell), +1: inverse (buy)
            # 5 alternating swings P1 T1 P2 T2 P3 (P = highs for a top); a newer opposite swing after P3 is allowed
            want = 1 if dr == -1 else -1
            if s5[0][2] != want:
                continue
            (x1, p1, _), (xt1, t1, _), (x2, p2, _), (xt2, t2, _), (x3, p3, _) = s5
            if (x1, x2, x3, dr) in used:
                continue
            sgn = -dr                           # +1 for a top (peaks are highs)
            if not (sgn * (p2 - p1) > 0 and sgn * (p2 - p3) > 0):
                continue
            neck_at = lambda x: t1 + (t2 - t1) * (x - xt1) / (xt2 - xt1)
            height = sgn * (p2 - neck_at(x2))
            if height <= 0.5 * a:
                continue
            if abs(p1 - p3) > sym * height or sgn * (p2 - (max(p1, p3) if sgn > 0 else min(p1, p3))) < 0.15 * height:
                continue
            if trend:
                lo_before = l[max(0, x1 - trend_bars):x1].min() if sgn > 0 else h[max(0, x1 - trend_bars):x1].max()
                if sgn * (p1 - lo_before) < height:
                    continue                    # needs a prior trend into the pattern
            if i - x3 > max_wait + L:
                continue
            seg = slice(x3 + 1, i + 1)
            if (sgn > 0 and h[seg].max() > p3) or (sgn < 0 and l[seg].min() < p3):
                used.add((x1, x2, x3, dr)); continue   # right shoulder broken: pattern void
            nk, nk_prev = neck_at(i), neck_at(i - 1)
            broke = (c[i] < nk and c[i - 1] >= nk_prev) if sgn > 0 else (c[i] > nk and c[i - 1] <= nk_prev)
            if not broke:
                continue
            used.add((x1, x2, x3, dr))
            nt = first_bar(e, d.index[i + 1])
            if nt is None:
                continue
            ref = p3 if sl_mode == "shoulder" else p2
            sl = ref + sgn * 0.1 * a
            risk = (sl - c[i]) * sgn
            if risk <= 0:
                continue
            tp = c[i] - sgn * height if tp_mode == "measured" else c[i] - sgn * 2.0 * risk
            if (c[i] - tp) * sgn <= 0:
                continue
            sig[nt] = [dict(type="market", dir=dr, price=None, sl=sl, tp=tp, tag="HS")]
    import strategies
    old = strategies.swap_cost
    if not swap:
        strategies.swap_cost = lambda t0, t1, dr: 0.0
    try:
        return run_bars(e, sig, lambda pos, t, n_: None)
    finally:
        strategies.swap_cost = old
