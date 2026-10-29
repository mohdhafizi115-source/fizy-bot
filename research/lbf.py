"""London breakout + one indicator filter at a time. All indicator values use only candles closed
before 08:00 (broker time) of the trading day, or earlier days.
Filters (each returns the allowed directions for the day: {1, -1}, {1}, {-1} or empty):
  none        both sides (the live rules)
  d1_ema20    only with the daily trend: yesterday's close vs daily EMA 20
  d1_ema50    same with daily EMA 50
  h4_ema50    H4 close vs H4 EMA 50 at 08:00
  ema_stack   H1 EMA 50 vs EMA 200 at 08:00
  adx20       skip the day when H1 ADX(14) at 08:00 < 20 (no trend)
  adx_low     only trade when H1 ADX(14) < 25 (quiet morning before the break)
  squeeze     only when the Asian range is narrow vs daily ATR(14): range < 0.6 x ATR
  wide_skip   skip when the Asian range > 1.0 x daily ATR(14)
  rsi_ok      buy only if H1 RSI(14) < 70, sell only if > 30 at 08:00
  bb_squeeze  only when H1 Bollinger width at 08:00 is in the lowest 40% of the last 100 hours
  prev_dir    only in the direction of yesterday's candle
  mid_bias    buy only if price at 08:00 is above yesterday's mid, sell only if below"""
import numpy as np, pandas as pd
from strategies import run_bars


def rsi(s, n=14):
    d = s.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def adx(d, n=14):
    up = d.high.diff(); dn = -d.low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - d.close.shift()), abs(d.low - d.close.shift())))
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, d.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    mdi = 100 * pd.Series(mdm, d.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * abs(pdi - mdi) / (pdi + mdi)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def prepare(m):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    h1 = m.resample("1h", label="left", closed="left", origin="start_day").agg(agg).dropna()
    h4 = m.resample("4h", label="left", closed="left", origin="start_day").agg(agg).dropna()
    d1 = m.resample("1D").agg(agg).dropna(); d1 = d1[d1.index.dayofweek < 5]
    f = {}
    # values known at 08:00: last closed H1 = 07:00 bar, last closed H4 = 04:00 bar, daily = yesterday
    f["h1_ema50"] = h1.close.ewm(span=50, adjust=False).mean()
    f["h1_ema200"] = h1.close.ewm(span=200, adjust=False).mean()
    f["h1_close"] = h1.close
    f["h1_adx"] = adx(h1)
    f["h1_rsi"] = rsi(h1.close)
    mid = h1.close.rolling(20).mean(); sd = h1.close.rolling(20).std(ddof=0)
    bw = (4 * sd / mid)
    f["h1_bbw_pct"] = bw.rolling(100).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
    f["h4_close"] = h4.close; f["h4_ema50"] = h4.close.ewm(span=50, adjust=False).mean()
    tr = np.maximum(d1.high - d1.low, np.maximum(abs(d1.high - d1.close.shift()), abs(d1.low - d1.close.shift())))
    f["d1"] = d1.assign(ema20=d1.close.ewm(span=20, adjust=False).mean(), ema50=d1.close.ewm(span=50, adjust=False).mean(),
                        atr=tr.rolling(14).mean())
    return f


def allowed(name, F, day, hi, lo, px8):
    if "+" in name:                         # combination: every part must allow the side
        out = {1, -1}
        for part in name.split("+"):
            out &= allowed(part, F, day, hi, lo, px8)
        return out
    both = {1, -1}
    t_h1 = day + pd.Timedelta(hours=7); t_h4 = day + pd.Timedelta(hours=4)
    d1 = F["d1"]; prev = d1[d1.index < day]
    if len(prev) < 60:
        return set()                       # same start date for every filter (indicators warmed up)
    if name == "none":
        return both
    y = prev.iloc[-1]
    g = lambda s, t: s.get(t, np.nan)
    if name in ("d1_ema20", "d1_ema50"):
        e = y.ema20 if name == "d1_ema20" else y.ema50
        return {1} if y.close > e else {-1}
    if name == "h4_ema50":
        c, e = g(F["h4_close"], t_h4), g(F["h4_ema50"], t_h4)
        return set() if np.isnan(c) else ({1} if c > e else {-1})
    if name == "ema_stack":
        a, b = g(F["h1_ema50"], t_h1), g(F["h1_ema200"], t_h1)
        return set() if np.isnan(a) else ({1} if a > b else {-1})
    if name == "adx20":
        v = g(F["h1_adx"], t_h1); return both if v >= 20 else set()
    if name == "adx_low":
        v = g(F["h1_adx"], t_h1); return both if v < 25 else set()
    if name == "squeeze":
        return both if (hi - lo) < 0.6 * y.atr else set()
    if name == "wide_skip":
        return set() if (hi - lo) > 1.0 * y.atr else both
    if name == "rsi_ok":
        v = g(F["h1_rsi"], t_h1); s = set()
        if v < 70: s.add(1)
        if v > 30: s.add(-1)
        return s
    if name == "bb_squeeze":
        v = g(F["h1_bbw_pct"], t_h1); return both if v < 0.4 else set()
    if name == "prev_dir":
        return {1} if y.close > y.open else {-1}
    if name == "mid_bias":
        return {1} if px8 > (y.high + y.low) / 2 else {-1}
    raise ValueError(name)


def london_f(m, filt="none", F=None, bars_per_hour=4, r0=3, r1=8, tp_r=2.5, be_r=1.5, close_h=21,
             fmin=0.30, fmax=1.60, cap=0.6, buf=0.10):
    F = F or prepare(m)
    sig = {}
    for day, gg in m.groupby(m.index.normalize()):
        rg = gg[(gg.index.hour >= r0) & (gg.index.hour < r1)]
        if len(rg) < (r1 - r0) * bars_per_hour - 2:
            continue
        hi, lo = rg.high.max(), rg.low.min()
        mid = (hi + lo) / 2; width = (hi - lo) / mid * 100
        if width < fmin or width > fmax:
            continue
        t = day + pd.Timedelta(hours=r1)
        if t not in m.index:
            continue
        ok = allowed(filt, F, day, hi, lo, float(rg.close.iloc[-1]))
        if not ok:
            continue
        exp = day + pd.Timedelta(hours=close_h)
        capd = mid * cap / 100
        sl_b = max(lo, hi + buf - capd); sl_s = min(hi, lo - buf + capd)
        rb = hi + buf - sl_b; rs = sl_s - (lo - buf)
        orders = []
        if 1 in ok:
            orders.append(dict(type="stop", dir=1, price=hi + buf, sl=sl_b, tp=hi + buf + tp_r * rb, expire=exp, be_at=be_r, close_at=exp, tag="LB"))
        if -1 in ok:
            orders.append(dict(type="stop", dir=-1, price=lo - buf, sl=sl_s, tp=lo - buf - tp_r * rs, expire=exp, be_at=be_r, close_at=exp, tag="LB"))
        sig[t] = orders
    return run_bars(m, sig, lambda pos, t, n: "close" if pos.close_at is not None and t >= pos.close_at else None)


COMBOS = ["none", "squeeze"] + [f"squeeze+{x}" for x in ("d1_ema20", "d1_ema50", "h4_ema50", "ema_stack", "adx20", "adx_low",
                                                       "rsi_ok", "bb_squeeze", "prev_dir", "mid_bias")]
FILTERS = ["none", "d1_ema20", "d1_ema50", "h4_ema50", "ema_stack", "adx20", "adx_low", "squeeze", "wide_skip",
           "rsi_ok", "bb_squeeze", "prev_dir", "mid_bias"]
