"""VSA signals on GC=F hourly with REAL futures volume (2 years). Spread $0.30, JustMarkets-style swap."""
import os, sys
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
from vsa import vsa
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": "60m", "range": "730d"},
                 headers=UA, timeout=60)
res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
g = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                 index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
g = g.rename(columns={"volume": "vol"})
g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index]); g = g[~g.index.duplicated()].sort_index()
g["spread"] = 0.30
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
out = [f"VSA on GC=F hourly with real volume {g.index[0]:%Y-%m-%d}..{g.index[-1]:%Y-%m-%d} (bars with volume: {(g.vol > 0).mean() * 100:.0f}%)"]
for tf in ("1h", "4h"):
    for kinds in (("NS",), ("TST",), ("SV",), ("NS", "TST", "SV")):
        for rr in (1.5, 2.0):
            tr = vsa(g, tf=tf, kinds=kinds, rr=rr)
            if len(tr) == 0:
                out.append(f"  {tf} {'+'.join(kinds):10s} {rr}R: no trades"); continue
            h = len(tr) // 2
            out.append(f"  {tf} {'+'.join(kinds):10s} {rr}R: trades {len(tr)}, win {np.mean(tr.pnl > 0) * 100:.0f}%, net ${tr.pnl.sum():+.0f}, "
                       f"PF {pf(tr.pnl.values):.2f}, {tr.R.sum():+.1f}R, 1st half PF {pf(tr.pnl.values[:h]):.2f} / 2nd half PF {pf(tr.pnl.values[h:]):.2f}")
print("\n".join(out))
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("\n".join(out) + "\n")
