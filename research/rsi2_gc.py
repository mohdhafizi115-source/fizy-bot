"""H1 RSI(2) pullback on GC=F hourly, 2 years: with the 200-SMA trend, buy RSI2 < 10 (sell > 90), stop
k x ATR14, exit when the H1 close crosses the 5-SMA. Spread $0.30, JustMarkets-style swap."""
import os, sys
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
from strategies import rsi2
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": "60m", "range": "730d"}, headers=UA, timeout=60)
res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
g = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")}, index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index]); g = g[~g.index.duplicated()].sort_index(); g["spread"] = 0.30
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
out = [f"H1 RSI(2) pullback on GC=F hourly {g.index[0]:%Y-%m-%d}..{g.index[-1]:%Y-%m-%d}"]
for th in ((10, 90), (5, 95)):
    for sl in (2.0, 3.0):
        tr = rsi2(g, tf="1h", lo_th=th[0], hi_th=th[1], atr_sl=sl)
        h = len(tr) // 2; mo = tr.groupby(tr.open.dt.to_period("M")).pnl.sum(); eq = tr.pnl.cumsum()
        yrs = tr.groupby(tr.open.dt.year).pnl.sum()
        out.append(f"  RSI {th[0]}/{th[1]}, SL {sl} ATR: trades {len(tr)}, win {np.mean(tr.pnl > 0) * 100:.0f}%, PF $ {pf(tr.pnl.values):.2f}, "
                   f"net ${tr.pnl.sum():+.0f}, PF R {pf(tr.R.values):.2f}, halves PF {pf(tr.pnl.values[:h]):.2f}/{pf(tr.pnl.values[h:]):.2f}, "
                   f"winning months {(mo > 0).sum()}/{len(mo)}, max DD ${(eq.cummax() - eq).max():.0f}; " + " ".join(f"{y}:{v:+.0f}" for y, v in yrs.items()))
print("\n".join(out)); os.makedirs("status", exist_ok=True); open("status/research.txt", "w").write("\n".join(out) + "\n")
