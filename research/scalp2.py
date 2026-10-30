"""Gold M5 scalping, round 2: techniques not tested before (rules fixed in advance, 30 Oct 2026).
Data: Deriv frxXAUUSD 5m (as far back as the API gives) and Yahoo GC=F 5m (60 days, real volume).
Costs: one spread per trade ($0.25 Deriv, $0.30 GC=F), no swap (intraday). Lot 0.01 = $1 per $1 move.
Intrabar path: bull bar O-L-H-C, bear bar O-H-L-C; a limit fill only sees the prices after the fill.
Times: chart time = Europe/Athens (JustMarkets), New York time for the ICT windows.

  SB  ICT Silver Bullet: the first M5 fair value gap (3-candle gap >= 0.2 ATR, middle candle in the gap
      direction) formed inside the window; limit at the gap edge, SL beyond the first two candles - 0.1 ATR,
      TP 2R, order valid to the window end, flat 60 min after it.
        SB_NY  10:00-11:00 New York        SB_LDN 03:00-04:00 New York
        "+sweep": the gap must follow a sweep: since the window start price traded beyond the low (bullish)
        / high (bearish) of the 60 minutes before the window.
  VW  VWAP band fade: daily VWAP from 00:00 chart time (GC=F volume; Deriv has no volume, so equal weights),
      bands +-2 std. Previous candle closed outside the band, this one closes back inside in the fade
      direction -> enter next open; SL beyond the two candles + 0.2 ATR; TP = VWAP (skip if < 0.8R);
      max 36 candles; entries 08:00-20:00 chart time, from 2 h after the anchor.
  PV  Daily pivot R1 / S1 rejection: first touch today of R1 (S1), the candle closes back below (above)
      it in the fade direction -> enter next open; SL beyond the candle + 0.3 ATR; TP 1.5R or the pivot P;
      max 36 candles; 08:00-20:00 chart time.
  BR  Bollinger (20, 2) + RSI(14) range fade: previous candle closed outside the band with RSI < 30 (> 70),
      this one closes back inside in the fade direction, ADX(14) < 20 -> enter next open; SL beyond the
      two candles + 0.3 ATR; TP = middle band (skip if < 0.8R); max 24 candles; 08:00-20:00. Also without ADX.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
CHART, NY = ZoneInfo("Europe/Athens"), ZoneInfo("America/New_York")
out = []


def say(x=""):
    print(x, flush=True); out.append(x)


def yahoo5():
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": "5m", "range": "60d"},
                     headers=UA, timeout=60)
    res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
    g = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                     index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
    return g[~g.index.duplicated()].sort_index()


def deriv5(pages=60):
    got = {}; end = "latest"
    for p in range(pages):
        js = S._deriv_call({"ticks_history": "frxXAUUSD", "style": "candles", "granularity": 300, "count": 5000, "end": end})
        if js.get("error"):
            say(f"  deriv page {p}: {js['error'].get('message')}"); break
        rows = js.get("candles") or []
        new = [r for r in rows if int(r["epoch"]) not in got]
        for r in rows:
            got[int(r["epoch"])] = r
        if not rows or not new:
            break
        end = min(int(r["epoch"]) for r in rows) - 1
        time.sleep(0.8)
    df = pd.DataFrame([got[e] for e in sorted(got)])
    df.index = pd.to_datetime(df["epoch"].astype(int), unit="s", utc=True)
    df = df[["open", "high", "low", "close"]].astype(float)
    df["volume"] = 1.0
    return df


def indicators(d):
    c = d.close
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - c.shift()), abs(d.low - c.shift())))
    d["atr"] = tr.rolling(14).mean()
    ch = d.index.tz_convert(CHART); ny = d.index.tz_convert(NY)
    d["ch_h"] = ch.hour + ch.minute / 60; d["ny_h"] = ny.hour + ny.minute / 60
    d["ch_day"] = pd.DatetimeIndex(ch.date)
    d["ny_day"] = pd.DatetimeIndex(ny.date)
    # daily VWAP (anchor 00:00 chart time) and bands
    tp = (d.high + d.low + c) / 3; v = d.volume.clip(lower=0) + 1e-9
    g = d.ch_day
    cv = v.groupby(g).cumsum(); cpv = (tp * v).groupby(g).cumsum(); cp2v = (tp * tp * v).groupby(g).cumsum()
    d["vwap"] = cpv / cv
    d["vsd"] = np.sqrt(np.maximum(cp2v / cv - d.vwap ** 2, 0))
    d["bars_today"] = g.groupby(g).cumcount()
    # Bollinger, RSI 14, ADX 14
    d["bb_mid"] = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    d["bb_up"], d["bb_lo"] = d.bb_mid + 2 * sd, d.bb_mid - 2 * sd
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn)
    upm = d.high.diff(); dnm = -d.low.diff()
    pdm = np.where((upm > dnm) & (upm > 0), upm, 0.0); ndm = np.where((dnm > upm) & (dnm > 0), dnm, 0.0)
    atrw = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=d.index).ewm(alpha=1 / 14, adjust=False).mean() / atrw
    ndi = 100 * pd.Series(ndm, index=d.index).ewm(alpha=1 / 14, adjust=False).mean() / atrw
    dx = 100 * abs(pdi - ndi) / (pdi + ndi)
    d["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
    # daily pivots from the previous chart-time day
    day = d.groupby("ch_day").agg(H=("high", "max"), L=("low", "min"), C=("close", "last"))
    day = day[day.index.dayofweek < 5]
    P = (day.H + day.L + day.C) / 3
    piv = pd.DataFrame({"P": P, "R1": 2 * P - day.L, "S1": 2 * P - day.H}).shift(1)
    m = piv.reindex(d.ch_day.values)
    for k in ("P", "R1", "S1"):
        d[k] = m[k].values
    return d


def run(d, sig, sp, flat=None):
    """sig: {i: order placed at the close of bar i}; order: type market|limit, dir, price, sl, tp, exp, maxb."""
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    trades, pend, pos = [], None, None
    n = len(d)
    for k in range(1, n):
        if pos is not None and (k - pos["k"] >= pos["maxb"] or (flat is not None and flat[k])):
            trades.append((pos["t"], (o[k] - pos["entry"]) * pos["dir"] - sp, "time")); pos = None
        if pos is None and pend is None and (k - 1) in sig:
            pend = dict(sig[k - 1])
        if pend is not None and (k > pend["exp"] or (flat is not None and flat[k])):
            pend = None
        path = [o[k], l[k], h[k], c[k]] if c[k] >= o[k] else [o[k], h[k], l[k], c[k]]
        for a, b in zip(path[:-1], path[1:]):
            lo, hi = min(a, b), max(a, b)
            if pos is None and pend is not None:
                P, dr = pend["price"], pend["dir"]
                fill = None
                if pend["type"] == "market":
                    fill = a
                elif dr == 1 and lo <= P:
                    fill = min(P, a)
                elif dr == -1 and hi >= P:
                    fill = max(P, a)
                if fill is None:
                    continue
                pos = dict(k=k, t=d.index[k], dir=dr, entry=fill, sl=pend["sl"], tp=pend["tp"], maxb=pend["maxb"])
                pend = None
                lo, hi = min(fill, b), max(fill, b)          # only the prices after the fill
            if pos is not None:
                dr = pos["dir"]
                if dr == 1:
                    ex = pos["sl"] if lo <= pos["sl"] else (pos["tp"] if hi >= pos["tp"] else None)
                else:
                    ex = pos["sl"] if hi >= pos["sl"] else (pos["tp"] if lo <= pos["tp"] else None)
                if ex is not None:
                    if ex == pos["sl"] and (pos["entry"] - pos["sl"]) * dr <= 0:
                        ex = pos["entry"]                 # filled already beyond the SL (gap): out at the fill
                    trades.append((pos["t"], (ex - pos["entry"]) * dr - sp, "SL" if ex == pos["sl"] else "TP"))
                    pos = None
                    break
    return pd.DataFrame(trades, columns=["t", "pnl", "res"])


def sig_sb(d, w0, w1, sweep, tp_r=2.0, gap=0.2, ce=False):
    A = d.atr.values; o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    nyh = d.ny_h.values; nyday = d.ny_day.values
    sig = {}; used = set(); flat = np.zeros(len(d), bool)
    inwin = (nyh >= w0) & (nyh < w1)
    flat |= (nyh >= w1 + 1) & (np.roll(nyh, 1) < w1 + 1)
    pre_hi, pre_lo, win_lo, win_hi, cur = np.nan, np.nan, np.inf, -np.inf, None
    idx = np.arange(len(d))
    for i in range(3, len(d)):
        if nyday[i] != cur:
            cur = nyday[i]; pre = (nyday == cur) & (nyh >= w0 - 1) & (nyh < w0)
            sel = idx[max(0, i - 400):i + 400][pre[max(0, i - 400):i + 400]]
            pre_hi = h[sel].max() if len(sel) else np.nan; pre_lo = l[sel].min() if len(sel) else np.nan
            win_lo, win_hi = np.inf, -np.inf
        if inwin[i]:
            win_lo, win_hi = min(win_lo, l[i]), max(win_hi, h[i])
        if not (inwin[i] and inwin[i - 2]) or cur in used or np.isnan(A[i]):
            continue
        dr = 0
        if l[i] > h[i - 2] and c[i - 1] > o[i - 1] and l[i] - h[i - 2] >= gap * A[i]:
            dr = 1
        elif h[i] < l[i - 2] and c[i - 1] < o[i - 1] and l[i - 2] - h[i] >= gap * A[i]:
            dr = -1
        if not dr:
            continue
        if sweep and (np.isnan(pre_lo) or (dr == 1 and not win_lo < pre_lo) or (dr == -1 and not win_hi > pre_hi)):
            continue
        used.add(cur)
        if dr == 1:
            entry = (l[i] + h[i - 2]) / 2 if ce else l[i]; sl = min(l[i - 2], l[i - 1]) - 0.1 * A[i]
        else:
            entry = (h[i] + l[i - 2]) / 2 if ce else h[i]; sl = max(h[i - 2], h[i - 1]) + 0.1 * A[i]
        risk = (entry - sl) * dr
        if risk <= 0:
            continue
        j = i
        while j + 1 < len(d) and inwin[j + 1]:
            j += 1
        sig[i] = dict(type="limit", dir=dr, price=entry, sl=sl, tp=entry + dr * tp_r * risk, exp=j, maxb=10 ** 6)
    return sig, flat


def _sess(d, i):
    return 8 <= d.ch_h.values[i] < 20


def sig_fade(d, kind, adx=True, tp_mode="r"):
    A = d.atr.values; o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    chh = d.ch_h.values; sig = {}
    if kind == "VW":
        up, lo_, mid = (d.vwap + 2 * d.vsd).values, (d.vwap - 2 * d.vsd).values, d.vwap.values
        bt = d.bars_today.values
    elif kind == "BR":
        up, lo_, mid = d.bb_up.values, d.bb_lo.values, d.bb_mid.values
        rsi, ad = d.rsi.values, d.adx.values
    elif kind == "PV":
        R1, S1, P = d.R1.values, d.S1.values, d.P.values
        day = d.ch_day.values
        touched = {}
    for i in range(30, len(d) - 1):
        a = A[i]
        if np.isnan(a) or not (8 <= chh[i] < 20):
            if kind == "PV":                          # still record touches outside the session
                if not np.isnan(R1[i]):
                    t = touched.setdefault(day[i], [False, False])
                    t[0] |= h[i] >= R1[i]; t[1] |= l[i] <= S1[i]
            continue
        dr = 0
        if kind in ("VW", "BR"):
            if kind == "VW" and bt[i] < 24:
                continue
            if np.isnan(up[i - 1]) or np.isnan(up[i]):
                continue
            if kind == "VW":
                ok_s = ok_b = True; pad = 0.2
            else:                                     # BR: RSI extreme on the outside candle, optional ADX < 20
                rng = (not adx) or ad[i] < 20
                ok_s, ok_b, pad = rng and rsi[i - 1] > 70, rng and rsi[i - 1] < 30, 0.3
            if ok_s and c[i - 1] > up[i - 1] and c[i] < up[i] and c[i] < o[i]:
                dr = -1; sl = max(h[i - 1], h[i]) + pad * a; tp = mid[i]
            elif ok_b and c[i - 1] < lo_[i - 1] and c[i] > lo_[i] and c[i] > o[i]:
                dr = 1; sl = min(l[i - 1], l[i]) - pad * a; tp = mid[i]
            if not dr:
                continue
            risk = (c[i] - sl) * dr
            if risk <= 0 or (tp - c[i]) * dr < 0.8 * risk:
                continue
            maxb = 36 if kind == "VW" else 24
        else:
            if np.isnan(R1[i]):
                continue
            t = touched.setdefault(day[i], [False, False])
            if not t[0] and h[i] >= R1[i] and c[i] < R1[i] and c[i] < o[i]:
                dr = -1; sl = h[i] + 0.3 * a
            elif not t[1] and l[i] <= S1[i] and c[i] > S1[i] and c[i] > o[i]:
                dr = 1; sl = l[i] - 0.3 * a
            t[0] |= h[i] >= R1[i]; t[1] |= l[i] <= S1[i]
            if not dr:
                continue
            risk = (c[i] - sl) * dr
            if risk <= 0:
                continue
            tp = c[i] + dr * 1.5 * risk if tp_mode == "r" else P[i]
            if (tp - c[i]) * dr < 0.8 * risk:
                continue
            maxb = 36
        sig[i] = dict(type="market", dir=dr, price=None, sl=sl, tp=tp, exp=i + 1, maxb=maxb)
    return sig, None


pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99.0
VARIANTS = [
    ("SB_NY", "Silver Bullet 10-11 NY", lambda d: sig_sb(d, 10, 11, False)),
    ("SB_NY+sweep", "Silver Bullet 10-11 NY after a sweep", lambda d: sig_sb(d, 10, 11, True)),
    ("SB_LDN", "Silver Bullet 03-04 NY (London)", lambda d: sig_sb(d, 3, 4, False)),
    ("SB_LDN+sweep", "Silver Bullet 03-04 NY after a sweep", lambda d: sig_sb(d, 3, 4, True)),
    ("VW", "VWAP 2-std band fade, TP VWAP", lambda d: sig_fade(d, "VW")),
    ("PV_1.5R", "Pivot R1/S1 rejection, TP 1.5R", lambda d: sig_fade(d, "PV", tp_mode="r")),
    ("PV_P", "Pivot R1/S1 rejection, TP pivot", lambda d: sig_fade(d, "PV", tp_mode="p")),
    ("BR_adx", "BB+RSI fade, ADX < 20, TP mid", lambda d: sig_fade(d, "BR", adx=True)),
    ("BR", "BB+RSI fade, no ADX, TP mid", lambda d: sig_fade(d, "BR", adx=False)),
]

if __name__ == "__main__":
    for src, loader, sp in (("Deriv XAUUSD 5m", deriv5, 0.25), ("Yahoo GC=F 5m (real volume)", yahoo5, 0.30)):
        try:
            d = indicators(loader())
        except Exception as e:
            say(f"{src}: data error {e}"); continue
        days = d.ch_day.nunique()
        say(f"\n{src}: {len(d)} candles, {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d} ({days} days), spread ${sp}")
        mid_t = d.index[len(d) // 2]
        for key, name, fn in VARIANTS:
            try:
                sig, flat = fn(d)
                tr = run(d, sig, sp, flat)
            except Exception as e:
                import traceback; say(f"  {key}: error {traceback.format_exc()[-300:]}"); continue
            if not len(tr):
                say(f"  {key:13s} {name}: no trades"); continue
            x = tr.pnl.values; h1 = tr[tr.t < mid_t].pnl.values; h2 = tr[tr.t >= mid_t].pnl.values
            cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
            dayp = tr.groupby(tr.t.dt.tz_convert(CHART).dt.date).pnl.sum()
            say(f"  {key:13s} {name}: {len(tr)} trades ({len(tr) / days:.1f}/day), win {np.mean(x > 0) * 100:.0f}%, "
                f"PF {pf(x):.2f}, net ${x.sum():+.0f}/0.01 lot, halves PF {pf(h1):.2f} / {pf(h2):.2f}, "
                f"avg win ${x[x > 0].mean() if (x > 0).any() else 0:.2f} / loss ${x[x < 0].mean() if (x < 0).any() else 0:.2f}, "
                f"winning days {np.mean(dayp > 0) * 100:.0f}%, max DD ${dd:.0f}, exits {tr.res.value_counts().to_dict()}")
    os.makedirs("status", exist_ok=True)
    open("status/research.txt", "w").write("Gold M5 scalping, round 2\n" + "\n".join(out) + "\n")
