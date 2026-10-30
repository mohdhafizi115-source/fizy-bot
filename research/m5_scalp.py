"""Gold M5 scalping candidates (rules fixed in advance), tested on:
  - Yahoo GC=F 5-minute bars (last 60 days)
  - Deriv frxXAUUSD 5-minute bars (paged back as far as the API allows)
Spread $0.30 (GC=F) / $0.25 (Deriv) per trade, swap ignored (intraday). Broker time = New York + 7.
Session filter for every setup: entries only 08:00-20:00 broker (London + New York).
  A  EMA pullback: EMA 9 > 21 > 50; the candle dips to EMA 21 and closes bullish above EMA 9 -> buy next open;
     SL below the candle low - 0.1 ATR; TP 1.5R; exit after 12 candles (1 hour). Sell mirrored.
  B  RSI(2) pullback: close above EMA 200 and RSI(2) < 10 -> buy; SL 2 ATR; exit when the close crosses the SMA 5
     (max 24 candles). Sell mirrored.
  C  1-hour breakout with trend: close above the highest high of the last 12 candles while EMA 50 rises
     -> buy next open; SL 1 ATR; TP 1.5R; exit after 12 candles. Sell mirrored."""
import os, sys, time, json
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
import strategies as ST
ST.swap_cost = lambda t0, t1, dr: 0.0
from strategies import run_bars, first_bar
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
out = []
def say(x=""):
    print(x, flush=True); out.append(x)

def yahoo5():
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": "5m", "range": "60d"}, headers=UA, timeout=60)
    res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
    g = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")}, index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
    g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index]); return g[~g.index.duplicated()].sort_index()

def deriv5(pages=40):
    got = {}; end = "latest"
    for p in range(pages):
        js = S._deriv_call({"ticks_history": "frxXAUUSD", "style": "candles", "granularity": 300, "count": 5000, "end": end})
        if js.get("error"):
            say(f"  deriv page {p}: {js['error'].get('message')}"); break
        rows = js.get("candles") or []
        new = [r for r in rows if int(r["epoch"]) not in got]
        for r in rows: got[int(r["epoch"])] = r
        if not rows or not new: break
        end = min(int(r["epoch"]) for r in rows) - 1
        time.sleep(1.0)
    df = pd.DataFrame([got[e] for e in sorted(got)])
    df.index = pd.to_datetime(df["epoch"].astype(int), unit="s", utc=True)
    df = df[["open", "high", "low", "close"]].astype(float)
    df.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in df.index]); return df

def atr(d, n=14):
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - d.close.shift()), abs(d.low - d.close.shift())))
    return tr.rolling(n).mean()

def setups(d, kind):
    c_s = d.close
    A_ = atr(d).values; hr = d.index.hour
    sess = (hr >= 8) & (hr < 20)
    c, o, h, l = (d[x].values for x in ("close", "open", "high", "low"))
    e9, e21, e50, e200 = (c_s.ewm(span=n, adjust=False).mean().values for n in (9, 21, 50, 200))
    dl = c_s.diff(); up = dl.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = (100 - 100 / (1 + up / dn)).values; sma5 = c_s.rolling(5).mean().values
    sig = {}
    for i in range(210, len(d) - 1):
        a = A_[i]
        if not sess[i] or np.isnan(a):
            continue
        dr = 0; tp = None
        if kind == "A":
            if e9[i] > e21[i] > e50[i] and l[i] <= e21[i] and c[i] > o[i] and c[i] > e9[i]:
                dr = 1; sl = l[i] - 0.1 * a
            elif e9[i] < e21[i] < e50[i] and h[i] >= e21[i] and c[i] < o[i] and c[i] < e9[i]:
                dr = -1; sl = h[i] + 0.1 * a
            if dr:
                risk = (c[i] - sl) * dr; tp = c[i] + dr * 1.5 * risk
        elif kind == "B":
            if c[i] > e200[i] and rsi2[i] < 10:
                dr = 1
            elif c[i] < e200[i] and rsi2[i] > 90:
                dr = -1
            if dr:
                sl = c[i] - dr * 2 * a; risk = 2 * a
        elif kind == "C":
            hh, ll = h[i - 12:i].max(), l[i - 12:i].min()
            if c[i] > hh and e50[i] > e50[i - 3]:
                dr = 1
            elif c[i] < ll and e50[i] < e50[i - 3]:
                dr = -1
            if dr:
                sl = c[i] - dr * a; risk = a; tp = c[i] + dr * 1.5 * risk
        if not dr or risk <= 0:
            continue
        sig[d.index[i + 1]] = [dict(type="market", dir=dr, price=None, sl=sl, tp=tp, tag=kind)]
    pos_n = {}
    def manage(pos, t, n):
        k = pos_n.setdefault(id(pos), n)
        i = n - 1
        if kind == "B" and i >= 0 and ((pos.dr == 1 and c[i] > sma5[i]) or (pos.dr == -1 and c[i] < sma5[i])):
            return "close"
        if n - k >= (24 if kind == "B" else 12):
            return "close"
        return None
    return run_bars(d, sig, manage)


pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
for src, loader, spread in (("Yahoo GC=F 5m", yahoo5, 0.30), ("Deriv XAUUSD 5m", deriv5, 0.25)):
    try:
        d = loader(); d["spread"] = spread
    except Exception as e:
        say(f"{src}: data error {e}"); continue
    days = d.index.normalize().nunique()
    say(f"{src}: {len(d)} candles, {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d} ({days} days)")
    for kind, name in (("A", "EMA 9/21/50 pullback, TP 1.5R"), ("B", "RSI(2) + EMA 200, exit SMA 5"), ("C", "1h breakout + EMA 50 slope, TP 1.5R")):
        tr = run = setups(d, kind)
        if len(tr) == 0:
            say(f"  {kind} {name}: no trades"); continue
        h = len(tr) // 2; dd_ = tr.pnl.cumsum(); dd = (dd_.cummax() - dd_).max()
        day = tr.groupby(tr.open.dt.normalize()).pnl.sum()
        say(f"  {kind} {name}: trades {len(tr)} ({len(tr) / days:.1f}/day), win {np.mean(tr.pnl > 0) * 100:.0f}%, PF {pf(tr.pnl.values):.2f}, "
            f"net ${tr.pnl.sum():+.0f} per 0.01 lot, halves PF {pf(tr.pnl.values[:h]):.2f}/{pf(tr.pnl.values[h:]):.2f}, "
            f"winning days {np.mean(day > 0) * 100:.0f}%, max DD ${dd:.0f}")
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("Gold M5 scalping candidates\n" + "\n".join(out) + "\n")
