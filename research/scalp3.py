"""Gold scalping, round 3: high-frequency techniques (2+ trades a day), rules fixed in advance (30 Oct 2026).
Data: Deriv frxXAUUSD 5m and 1m, Yahoo GC=F 5m. Costs: one spread per trade ($0.25 Deriv, $0.30 GC=F).
Entries 08:00-20:00 chart time (Europe/Athens = JustMarkets), every trade closed by 21:00. 0.01 lot = $1 per $1.
  ST   Supertrend (10, 3) flip -> enter next open, exit on the opposite flip (stop-and-reverse); "+ema" = only
       in the EMA 200 direction.
  HA   Heikin Ashi turns to the trend colour with no opposite wick, close on the EMA 50 side -> next open;
       SL 1.5 ATR; exit when the HA colour changes.
  MACD MACD (12, 26, 9) crosses its signal line below zero (buy) / above zero (sell) with the close on the
       EMA 200 side -> next open; SL 1.5 ATR; TP 1.5R; max 24 candles.
  MOM  Momentum candle: body >= 1.5 ATR and close in the outer 20% of the range -> follow at the next open;
       SL at the candle middle; TP 1R; max 6 candles.
  IB   Inside bar in the EMA 50 direction -> stop order 0.05 beyond the mother candle (valid 3 candles);
       SL at the other side of the mother candle; TP 1.5R.
  KC   Keltner breakout: close beyond EMA 20 +- 2 ATR on the EMA 200 side -> next open; SL 1.5 ATR; exit when
       a close crosses back over the EMA 20; max 36 candles.
  RN   Round number ($10 levels): first touch after 6 candles at least 1 ATR away, the candle closes
       0.2 ATR back off the level in the fade direction -> next open; SL 0.5 ATR beyond the level; TP 1.5R.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import scalp2 as X
say, pf, CHART = X.say, X.pf, X.CHART


def deriv(gran, pages):
    got = {}; end = "latest"
    for p in range(pages):
        js = X.S._deriv_call({"ticks_history": "frxXAUUSD", "style": "candles", "granularity": gran, "count": 5000, "end": end})
        if js.get("error"):
            say(f"  deriv {gran}s page {p}: {js['error'].get('message')}"); break
        rows = js.get("candles") or []
        new = [r for r in rows if int(r["epoch"]) not in got]
        for r in rows:
            got[int(r["epoch"])] = r
        if not rows or not new:
            break
        end = min(int(r["epoch"]) for r in rows) - 1
        time.sleep(1.5)
    df = pd.DataFrame([got[e] for e in sorted(got)])
    df.index = pd.to_datetime(df["epoch"].astype(int), unit="s", utc=True)
    df = df[["open", "high", "low", "close"]].astype(float); df["volume"] = 1.0
    return df


def prep(d):
    d = X.indicators(d)
    c = d.close
    for n in (20, 50, 200):
        d[f"e{n}"] = c.ewm(span=n, adjust=False).mean()
    # Supertrend (10, 3)
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - c.shift()), abs(d.low - c.shift())))
    a10 = tr.rolling(10).mean().values
    hl2 = ((d.high + d.low) / 2).values; cc = c.values
    ub, lb = hl2 + 3 * a10, hl2 - 3 * a10
    fu, fl, st = ub.copy(), lb.copy(), np.zeros(len(d))
    for i in range(1, len(d)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or cc[i - 1] > fu[i - 1] or np.isnan(fu[i - 1])) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or cc[i - 1] < fl[i - 1] or np.isnan(fl[i - 1])) else fl[i - 1]
        st[i] = 1 if cc[i] > fu[i - 1] else (-1 if cc[i] < fl[i - 1] else st[i - 1])
    d["st"] = st
    # Heikin Ashi
    hc = ((d.open + d.high + d.low + c) / 4).values; ho = np.empty(len(d)); ho[0] = (d.open.iloc[0] + c.iloc[0]) / 2
    for i in range(1, len(d)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    d["ha_c"], d["ha_o"] = hc, ho
    d["ha_lo"] = np.minimum(d.low.values, np.minimum(ho, hc)); d["ha_hi"] = np.maximum(d.high.values, np.maximum(ho, hc))
    # MACD
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["macd"], d["macd_s"] = macd, macd.ewm(span=9, adjust=False).mean()
    d["flat"] = (d.ch_h >= 21) & (d.ch_h.shift(1) < 21)
    return d


def run3(d, sig, sp, xl=None, xs=None):
    """Like scalp2.run, plus stop orders and exit flags: xl[i] / xs[i] = close a long / short at the next open."""
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    flat = d.flat.values
    trades, pend, pos = [], None, None
    for k in range(1, len(d)):
        if pos is not None:
            dr = pos["dir"]
            ex_sig = (dr == 1 and xl is not None and xl[k - 1]) or (dr == -1 and xs is not None and xs[k - 1])
            if k - pos["k"] >= pos["maxb"] or flat[k] or ex_sig:
                trades.append((pos["t"], (o[k] - pos["entry"]) * dr - sp, "exit")); pos = None
        if pos is None and pend is None and (k - 1) in sig:
            pend = dict(sig[k - 1])
        if pend is not None and (k > pend["exp"] or flat[k]):
            pend = None
        path = [o[k], l[k], h[k], c[k]] if c[k] >= o[k] else [o[k], h[k], l[k], c[k]]
        for a, b in zip(path[:-1], path[1:]):
            lo, hi = min(a, b), max(a, b)
            if pos is None and pend is not None:
                P, dr, ty = pend["price"], pend["dir"], pend["type"]
                fill = None
                if ty == "market":
                    fill = a
                elif ty == "stop" and dr == 1 and hi >= P:
                    fill = max(P, a)
                elif ty == "stop" and dr == -1 and lo <= P:
                    fill = min(P, a)
                if fill is None:
                    continue
                sl = pend["sl"]; tp = pend["tp"]
                if pend.get("tp_r"):
                    tp = fill + dr * pend["tp_r"] * abs(fill - sl)
                pos = dict(k=k, t=d.index[k], dir=dr, entry=fill, sl=sl, tp=tp, maxb=pend["maxb"]); pend = None
                lo, hi = min(fill, b), max(fill, b)
            if pos is not None:
                dr = pos["dir"]; sl, tp = pos["sl"], pos["tp"]
                if dr == 1:
                    ex = sl if (sl is not None and lo <= sl) else (tp if (tp is not None and hi >= tp) else None)
                else:
                    ex = sl if (sl is not None and hi >= sl) else (tp if (tp is not None and lo <= tp) else None)
                if ex is not None:
                    if ex == sl and (pos["entry"] - sl) * dr <= 0:
                        ex = pos["entry"]
                    trades.append((pos["t"], (ex - pos["entry"]) * dr - sp, "SL" if ex == sl else "TP")); pos = None
                    break
    return pd.DataFrame(trades, columns=["t", "pnl", "res"])


def signals(d, kind, ema=False):
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    A = d.atr.values; chh = d.ch_h.values; n = len(d)
    sess = (chh >= 8) & (chh < 20)
    e20, e50, e200 = d.e20.values, d.e50.values, d.e200.values
    sig = {}; xl = xs = None
    if kind == "ST":
        st = d.st.values
        xl = st == -1; xs = st == 1
        for i in range(210, n - 1):
            if st[i] != st[i - 1] and st[i] != 0 and sess[i] and not (ema and (c[i] - e200[i]) * st[i] <= 0):
                sig[i] = dict(type="market", dir=int(st[i]), price=None, sl=None, tp=None, exp=i + 1, maxb=10 ** 6)
    elif kind == "HA":
        hc, ho, hlo, hhi = d.ha_c.values, d.ha_o.values, d.ha_lo.values, d.ha_hi.values
        bull = hc > ho
        xl = ~bull; xs = bull
        for i in range(210, n - 1):
            if not sess[i] or np.isnan(A[i]):
                continue
            if bull[i] and not bull[i - 1] and hlo[i] >= min(ho[i], hc[i]) - 1e-9 and c[i] > e50[i]:
                sig[i] = dict(type="market", dir=1, price=None, sl=c[i] - 1.5 * A[i], tp=None, exp=i + 1, maxb=10 ** 6)
            elif not bull[i] and bull[i - 1] and hhi[i] <= max(ho[i], hc[i]) + 1e-9 and c[i] < e50[i]:
                sig[i] = dict(type="market", dir=-1, price=None, sl=c[i] + 1.5 * A[i], tp=None, exp=i + 1, maxb=10 ** 6)
    elif kind == "MACD":
        m, s = d.macd.values, d.macd_s.values
        for i in range(210, n - 1):
            if not sess[i] or np.isnan(A[i]):
                continue
            if m[i] > s[i] and m[i - 1] <= s[i - 1] and m[i] < 0 and c[i] > e200[i]:
                dr = 1
            elif m[i] < s[i] and m[i - 1] >= s[i - 1] and m[i] > 0 and c[i] < e200[i]:
                dr = -1
            else:
                continue
            sig[i] = dict(type="market", dir=dr, price=None, sl=c[i] - dr * 1.5 * A[i], tp=c[i] + dr * 2.25 * A[i], exp=i + 1, maxb=24)
    elif kind == "MOM":
        for i in range(210, n - 1):
            if not sess[i] or np.isnan(A[i]):
                continue
            rng = h[i] - l[i]; body = abs(c[i] - o[i])
            if rng <= 0 or body < 1.5 * A[i]:
                continue
            pos_ = (c[i] - l[i]) / rng
            dr = 1 if (c[i] > o[i] and pos_ >= 0.8) else (-1 if (c[i] < o[i] and pos_ <= 0.2) else 0)
            if not dr:
                continue
            sl = (h[i] + l[i]) / 2
            sig[i] = dict(type="market", dir=dr, price=None, sl=sl, tp=None, tp_r=1.0, exp=i + 1, maxb=6)
    elif kind == "IB":
        for i in range(210, n - 1):
            if not sess[i] or np.isnan(A[i]):
                continue
            if not (h[i] < h[i - 1] and l[i] > l[i - 1]):
                continue
            dr = 1 if (c[i] > e50[i] and e50[i] > e50[i - 3]) else (-1 if (c[i] < e50[i] and e50[i] < e50[i - 3]) else 0)
            if not dr:
                continue
            P = h[i - 1] + 0.05 if dr == 1 else l[i - 1] - 0.05
            sl = l[i - 1] if dr == 1 else h[i - 1]
            sig[i] = dict(type="stop", dir=dr, price=P, sl=sl, tp=None, tp_r=1.5, exp=i + 3, maxb=24)
    elif kind == "KC":
        up, dn = e20 + 2 * A, e20 - 2 * A
        xl = c < e20; xs = c > e20
        for i in range(210, n - 1):
            if not sess[i] or np.isnan(A[i]):
                continue
            if c[i] > up[i] and c[i - 1] <= up[i - 1] and c[i] > e200[i]:
                dr = 1
            elif c[i] < dn[i] and c[i - 1] >= dn[i - 1] and c[i] < e200[i]:
                dr = -1
            else:
                continue
            sig[i] = dict(type="market", dir=dr, price=None, sl=c[i] - dr * 1.5 * A[i], tp=None, exp=i + 1, maxb=36)
    elif kind == "RN":
        for i in range(210, n - 1):
            if not sess[i] or np.isnan(A[i]):
                continue
            a = A[i]
            Lb = np.floor(c[i] / 10) * 10                 # level just below the close (buy bounce)
            Ls = np.ceil(c[i] / 10) * 10                  # level just above (sell rejection)
            if l[i] <= Lb and c[i] >= Lb + 0.2 * a and c[i] > o[i] and (l[i - 6:i] > Lb + a).all():
                sig[i] = dict(type="market", dir=1, price=None, sl=Lb - 0.5 * a, tp=None, tp_r=1.5, exp=i + 1, maxb=24)
            elif h[i] >= Ls and c[i] <= Ls - 0.2 * a and c[i] < o[i] and (h[i - 6:i] < Ls - a).all():
                sig[i] = dict(type="market", dir=-1, price=None, sl=Ls + 0.5 * a, tp=None, tp_r=1.5, exp=i + 1, maxb=24)
    return sig, xl, xs


VARIANTS = [("ST", False), ("ST", True), ("HA", False), ("MACD", False), ("MOM", False), ("IB", False), ("KC", False), ("RN", False)]


def report(d, sp, label):
    days = d.ch_day.nunique(); mid_t = d.index[len(d) // 2]
    say(f"\n{label}: {len(d)} candles {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d} ({days} days), spread ${sp}")
    for kind, ema in VARIANTS:
        name = kind + ("+ema200" if ema else "")
        try:
            sig, xl, xs = signals(d, kind, ema)
            tr = run3(d, sig, sp, xl, xs)
        except Exception:
            import traceback; say(f"  {name}: error {traceback.format_exc()[-400:]}"); continue
        if not len(tr):
            say(f"  {name:10s} no trades"); continue
        x = tr.pnl.values; h1 = tr[tr.t < mid_t].pnl.values; h2 = tr[tr.t >= mid_t].pnl.values
        cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
        dayp = tr.groupby(tr.t.dt.tz_convert(CHART).dt.date).pnl.sum()
        say(f"  {name:10s} {len(tr):5d} trades ({len(tr) / days:4.1f}/day) win {np.mean(x > 0) * 100:3.0f}% PF {pf(x):.2f} "
            f"net ${x.sum():+6.0f} halves {pf(h1):.2f}/{pf(h2):.2f} | gross before spread PF {pf(x + sp):.2f} | "
            f"winning days {np.mean(dayp > 0) * 100:.0f}% | max DD ${dd:.0f}")


if __name__ == "__main__":
    for label, loader, sp in (("Deriv XAUUSD 5m", lambda: deriv(300, 30), 0.25),
                              ("Yahoo GC=F 5m", X.yahoo5, 0.30),
                              ("Deriv XAUUSD 1m", lambda: deriv(60, 15), 0.25)):
        try:
            report(prep(loader()), sp, label)
        except Exception as e:
            say(f"{label}: data error {e}")
    os.makedirs("status", exist_ok=True)
    open("status/research.txt", "w").write("Gold scalping round 3 (high frequency)\n" + "\n".join(X.out) + "\n")
