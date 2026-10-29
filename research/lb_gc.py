"""London breakout (same rules as the live alerts) on GC=F hourly, 2 years, to check it outside the
10-month JustMarkets sample. Hourly bars: intrabar path O-L-H-C / O-H-L-C, spread $0.30, swap estimated."""
import os, sys
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
import strategies as ST
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": "60m", "range": "730d"},
                 headers=UA, timeout=60)
res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
g = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")}, index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index]); g = g[~g.index.duplicated()].sort_index()
g["spread"] = 0.30
def london_h(m, r0=3, r1=8, tp_r=2.5, be_r=1.5, close_h=21, fmin=0.30, fmax=1.60, cap=0.6, buf=0.10):
    sig = {}
    for day, gg in m.groupby(m.index.normalize()):
        rg = gg[(gg.index.hour >= r0) & (gg.index.hour < r1)]
        if len(rg) < (r1 - r0) - 1:
            continue
        hi, lo = rg.high.max(), rg.low.min()
        mid = (hi + lo) / 2; width = (hi - lo) / mid * 100
        if width < fmin or width > fmax:
            continue
        t = day + pd.Timedelta(hours=r1)
        if t not in m.index:
            continue
        exp = day + pd.Timedelta(hours=close_h)
        capd = mid * cap / 100
        sl_b = max(lo, hi + buf - capd); sl_s = min(hi, lo - buf + capd)
        rb = hi + buf - sl_b; rs = sl_s - (lo - buf)
        sig[t] = [dict(type="stop", dir=1, price=hi + buf, sl=sl_b, tp=hi + buf + tp_r * rb, expire=exp, be_at=be_r, close_at=exp, tag="LB"),
                  dict(type="stop", dir=-1, price=lo - buf, sl=sl_s, tp=lo - buf - tp_r * rs, expire=exp, be_at=be_r, close_at=exp, tag="LB")]
    return ST.run_bars(m, sig, lambda pos, t, n: "close" if pos.close_at is not None and t >= pos.close_at else None)

out = [f"London breakout on GC=F hourly {g.index[0]:%Y-%m-%d}..{g.index[-1]:%Y-%m-%d} (spread $0.30, est. swap)"]
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
for label, kw in (("base 03-08, TP 2.5R, BE 1.5R", {}), ("range 02-08", dict(r0=2)), ("TP 2R", dict(tp_r=2.0)),
                  ("no BE", dict(be_r=None)), ("close 18:00", dict(close_h=18))):
    tr = london_h(g, **kw)
    if len(tr) == 0:
        out.append(f"  {label}: no trades"); continue
    h = len(tr) // 2
    yrs = tr.groupby(tr.open.dt.year).pnl.sum()
    mo = tr.groupby(tr.open.dt.to_period("M")).pnl.sum()
    out.append(f"  {label}: trades {len(tr)}, win {np.mean(tr.pnl > 0) * 100:.0f}%, net ${tr.pnl.sum():+.0f} per 0.01 lot, PF {pf(tr.pnl.values):.2f}, "
               f"{tr.R.sum():+.1f}R, 1st half PF {pf(tr.pnl.values[:h]):.2f} / 2nd half PF {pf(tr.pnl.values[h:]):.2f}, "
               f"losing months {int((mo < 0).sum())}/{len(mo)}; " + " ".join(f"{y}:{v:+.0f}" for y, v in yrs.items()))
print("\n".join(out))
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("\n".join(out) + "\n")
