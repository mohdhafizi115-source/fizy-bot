"""London breakout on every pair (Yahoo H1, 2 years, broker time = New York + 7).
Same mechanics as the gold rules: Asian range 03:00-08:00, OCO stops at 08:00 one pip beyond, SL at the
other side of the range (capped), TP 2.5R, BE 1.5R, close 21:00.
Two settings:
  gold  = the gold filters unchanged (range 0.30-1.60% of price, SL cap 0.6%)
  fx    = forex-sized filters (range 0.10-0.80% of price, SL cap 0.4%)
each with and without the squeeze filter (range < 0.6 x daily ATR14). Spread 1 pip forex, swap ignored."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
import strategies as ST
from ms_forex_data import yahoo_h1
ST.swap_cost = lambda t0, t1, dr: 0.0


def lb(m, pip, fmin, fmax, cap, squeeze, r0=3, r1=8, tp_r=2.5, be_r=1.5, close_h=21):
    d1 = m.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d1 = d1[d1.index.dayofweek < 5]
    tr = np.maximum(d1.high - d1.low, np.maximum(abs(d1.high - d1.close.shift()), abs(d1.low - d1.close.shift())))
    datr = tr.rolling(14).mean().shift(1)            # known before the day starts
    sig = {}
    for day, gg in m.groupby(m.index.normalize()):
        rg = gg[(gg.index.hour >= r0) & (gg.index.hour < r1)]
        if len(rg) < (r1 - r0) - 1:
            continue
        hi, lo = rg.high.max(), rg.low.min()
        mid = (hi + lo) / 2; width = (hi - lo) / mid * 100
        if width < fmin or width > fmax:
            continue
        a = datr.get(day, np.nan)
        if np.isnan(a):
            continue
        if squeeze and (hi - lo) >= 0.6 * a:
            continue
        t = day + pd.Timedelta(hours=r1)
        if t not in m.index:
            continue
        exp = day + pd.Timedelta(hours=close_h)
        capd = mid * cap / 100; buf = pip
        sl_b = max(lo, hi + buf - capd); sl_s = min(hi, lo - buf + capd)
        rb = hi + buf - sl_b; rs = sl_s - (lo - buf)
        sig[t] = [dict(type="stop", dir=1, price=hi + buf, sl=sl_b, tp=hi + buf + tp_r * rb, expire=exp, be_at=be_r, be_off=pip, close_at=exp, tag="LB"),
                  dict(type="stop", dir=-1, price=lo - buf, sl=sl_s, tp=lo - buf - tp_r * rs, expire=exp, be_at=be_r, be_off=pip, close_at=exp, tag="LB")]
    return ST.run_bars(m, sig, lambda pos, t, n: "close" if pos.close_at is not None and t >= pos.close_at else None)


SETS = {"gold filters": dict(fmin=0.30, fmax=1.60, cap=0.6, squeeze=False),
        "gold+squeeze": dict(fmin=0.30, fmax=1.60, cap=0.6, squeeze=True),
        "fx filters": dict(fmin=0.10, fmax=0.80, cap=0.4, squeeze=False),
        "fx+squeeze": dict(fmin=0.10, fmax=0.80, cap=0.4, squeeze=True)}
pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
out, allr = [], {k: [] for k in SETS}
for name in S.symbol_list():
    S.set_symbol(name)
    try:
        df = yahoo_h1(name)
    except Exception as e:
        out.append(f"{name}: data error {e}"); continue
    df.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in df.index]); df = df[~df.index.duplicated()].sort_index()
    df["spread"] = S.CUR["spread"] if not name.startswith("XAU") else 0.30
    pip = S.CUR["pip"] if not name.startswith("XAU") else 0.10
    line = f"{name:7s} |"
    for k, kw in SETS.items():
        tr = lb(df, pip, **kw)
        if len(tr) == 0:
            line += f" {k}: n=0 |"; continue
        r = tr.R.values; h = len(r) // 2
        allr[k] += [(name, t.open, t.R) for t in tr.itertuples()]
        line += f" {k}: n={len(r)} R={r.sum():+.1f} PF={pf(r):.2f} ({pf(r[:h]):.2f}/{pf(r[h:]):.2f}) |"
    out.append(line); print(line, flush=True)
summ = []
for k, rows in allr.items():
    d = pd.DataFrame(rows, columns=["sym", "open", "R"])
    fx = d[~d.sym.str.startswith("XAU")]
    gbp = fx[fx.sym.str.contains("GBP")]
    per = fx.groupby("sym").R.sum()
    summ.append(f"{k}: forex trades {len(fx)}, total {fx.R.sum():+.1f}R, PF {pf(fx.R.values):.2f}, pairs positive {(per > 0).mean() * 100:.0f}% | "
                f"GBP pairs: trades {len(gbp)}, {gbp.R.sum():+.1f}R, PF {pf(gbp.R.values):.2f}")
os.makedirs("status", exist_ok=True)
with open("status/research.txt", "w") as f:
    f.write("London breakout on all pairs, Yahoo H1 2 years (R per trade; halves PF in brackets)\n" + "\n".join(summ) + "\n\n" + "\n".join(out) + "\n")
print("\n".join(summ))
