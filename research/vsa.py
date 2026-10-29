"""VSA (Volume Spread Analysis, Tom Williams style) signals turned into fixed rules, on one timeframe.
Needs a 'vol' column (tick volume or real volume). Trend = close vs EMA 50 of the same TF.
Relative volume = bar volume / average volume of the same hour over the previous 20 days (removes the
intraday volume pattern); spread = bar range / ATR14.
Buy signals (sell mirrored):
  NS  No supply: uptrend, down bar, narrow spread (< 0.8), volume lower than each of the 2 previous bars
  TST Test: uptrend, low below the lows of the 2 previous bars, close in the upper third, volume lower
      than each of the 2 previous bars
  SV  Stopping volume / climax: wide down bar (spread > 1.5) on very high relative volume (> 2), closing
      in the upper half (sellers absorbed); no trend filter (it is a reversal signal)
Sell mirrors: ND no demand, TST up-test (upthrust on low volume), SV buying climax / upthrust on high
volume closing in the lower half.
Entry at the next open; SL beyond the signal bar's extreme + 0.1 ATR; TP = rr x risk."""
import numpy as np, pandas as pd
from bt import atr
from strategies import run_bars, first_bar


def bars(e, tf):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}
    if "spread" in e:
        agg["spread"] = "max"
    return e.resample(tf, label="left", closed="left", origin="start_day").agg(agg).dropna()


def vsa(e, tf="1h", kinds=("NS", "TST", "SV"), rr=2.0, swap=True):
    d = bars(e, tf)
    d = d[d.vol > 0]
    A = atr(d).values
    o, h, l, c, v = (d[x].values for x in ("open", "high", "low", "close", "vol"))
    ema = d.close.ewm(span=50, adjust=False).mean().values
    hr = d.index.hour
    relv = (d.vol / d.vol.groupby(hr).transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())).values
    sig = {}
    for i in range(60, len(d) - 1):
        a = A[i]
        rng = h[i] - l[i]
        if np.isnan(a) or a <= 0 or rng <= 0 or np.isnan(relv[i]):
            continue
        sp = rng / a
        pos = (c[i] - l[i]) / rng                     # 0 = close at low, 1 = close at high
        low_v = v[i] < v[i - 1] and v[i] < v[i - 2]
        up = c[i] > ema[i]; dn = c[i] < ema[i]
        dr, kind = 0, ""
        if "NS" in kinds and up and c[i] < c[i - 1] and sp < 0.8 and low_v:
            dr, kind = 1, "NS"
        elif "NS" in kinds and dn and c[i] > c[i - 1] and sp < 0.8 and low_v:
            dr, kind = -1, "ND"
        elif "TST" in kinds and up and l[i] < min(l[i - 1], l[i - 2]) and pos > 0.67 and low_v:
            dr, kind = 1, "TST"
        elif "TST" in kinds and dn and h[i] > max(h[i - 1], h[i - 2]) and pos < 0.33 and low_v:
            dr, kind = -1, "TST"
        elif "SV" in kinds and sp > 1.5 and relv[i] > 2.0 and c[i] < o[i] and pos > 0.5:
            dr, kind = 1, "SV"
        elif "SV" in kinds and sp > 1.5 and relv[i] > 2.0 and c[i] > o[i] and pos < 0.5:
            dr, kind = -1, "BC"
        if not dr:
            continue
        nt = first_bar(e, d.index[i + 1])
        if nt is None:
            continue
        sl = (l[i] - 0.1 * a) if dr == 1 else (h[i] + 0.1 * a)
        risk = (c[i] - sl) * dr
        if risk <= 0:
            continue
        sig[nt] = [dict(type="market", dir=dr, price=None, sl=sl, tp=c[i] + dr * rr * risk, tag=kind)]
    import strategies
    old = strategies.swap_cost
    if not swap:
        strategies.swap_cost = lambda t0, t1, dr: 0.0
    try:
        return run_bars(e, sig, lambda pos, t, n: None)
    finally:
        strategies.swap_cost = old
