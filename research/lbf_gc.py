"""London breakout + one indicator filter at a time, on GC=F hourly (2 years). Spread $0.30, swap included."""
import os, sys
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
from lbf import london_f, prepare, FILTERS, COMBOS
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": "60m", "range": "730d"},
                 headers=UA, timeout=60)
res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
g = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")}, index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index]); g = g[~g.index.duplicated()].sort_index()
g["spread"] = 0.30
F = prepare(g)
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
out = [f"London breakout + squeeze + second filter on GC=F hourly {g.index[0]:%Y-%m-%d}..{g.index[-1]:%Y-%m-%d} (all filters start after 60 daily bars)"]
for f in COMBOS:
    tr = london_f(g, f, F, bars_per_hour=1)
    if len(tr) == 0:
        out.append(f"  {f:10s}: no trades"); continue
    h = len(tr) // 2
    mo = tr.groupby(tr.open.dt.to_period("M")).pnl.sum(); eq = tr.pnl.cumsum()
    yrs = tr.groupby(tr.open.dt.year).pnl.sum()
    out.append(f"  {f:10s}: trades {len(tr):3d}, win {np.mean(tr.pnl > 0) * 100:.0f}%, PF {pf(tr.pnl.values):.2f}, net ${tr.pnl.sum():+5.0f}, "
               f"1st half PF {pf(tr.pnl.values[:h]):.2f} / 2nd half PF {pf(tr.pnl.values[h:]):.2f}, winning months {(mo > 0).sum()}/{len(mo)}, "
               f"max DD ${(eq.cummax() - eq).max():.0f}; " + " ".join(f"{y}:{v:+.0f}" for y, v in yrs.items()))
print("\n".join(out))
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("\n".join(out) + "\n")
