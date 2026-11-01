"""Check of the live setups on the broker's own 6.6-year M5 history (JustMarkets demo, Mar 2020 - Oct 2026).
  1. Gold London breakout with squeeze 0.6 (strategies.london_breakout on M15 built from M5, as live).
  2. NR7 D1 per instrument (OCO at yesterday's high/low, SL other side, exit next day open).
  3. RSI2 H1 per instrument (live EA rules), with and without spread.
Costs: the export's bar spread."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategies as ST
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
pf, f2 = SA.pf, SA.f2

# 1. London breakout on gold
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
m = d.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "s": "spread"})[["open", "high", "low", "close", "spread"]]
m = m.resample("15min", label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last", "spread": "max"}).dropna()
d1 = m.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna(); d1 = d1[d1.index.dayofweek < 5]
tr = np.maximum(d1.high - d1.low, np.maximum(abs(d1.high - d1.close.shift()), abs(d1.low - d1.close.shift())))
datr = tr.rolling(14).mean().shift(1)
t = ST.london_breakout(m)
keep = []
for _, r in t.iterrows():
    day = r.open.normalize(); g = m[(m.index >= day + pd.Timedelta(hours=3)) & (m.index < day + pd.Timedelta(hours=8))]
    a = datr.get(day, np.nan); keep.append(not (a == a) or (g.high.max() - g.low.min()) < 0.6 * a)
for name, x in (("no squeeze", t), ("squeeze 0.6 (live)", t[np.array(keep)])):
    p = x.pnl.values; mon = x.groupby(x.open.dt.strftime("%Y-%m")).pnl.sum(); h = len(x) // 2
    print(f"London breakout gold, {name}: {len(x)} trades {m.index[0].date()}..{m.index[-1].date()}, PF {pf(p):.2f}, "
          f"net ${p.sum():+.0f} per 0.01 lot, halves {pf(p[:h]):.2f}/{pf(p[h:]):.2f}, winning months {(mon > 0).sum()}/{len(mon)}")
    print("   by year: " + ", ".join(f"{y}: {len(g)}t PF {pf(g.pnl.values):.2f} ${g.pnl.sum():+.0f}" for y, g in x.groupby(x.open.dt.year)))

# 2 and 3: NR7 and RSI2 per instrument
for name in ("NR7 D1", "RSI2 H1"):
    print(f"\n{name} per instrument: trades, PF after spread, PF without spread, halves, last 12 months R, net $ per 0.01 lot, by year")
    for s in sorted(meta):
        f = os.path.join(DATA, s + ".csv")
        if not os.path.exists(f):
            continue
        d = SA.load(f, meta[s]["point"]); d = SA.prep(d)
        X = SA.daily(d) if name == "NR7 D1" else SA.hourly(d)
        sig, flat = SA.live_nr7(X) if name == "NR7 D1" else SA.live_rsi2(X)
        tr_ = SA.sim(*(X[c].values for c in ("o", "h", "l", "c", "s")), sig, flat)
        if not tr_:
            continue
        T = pd.DataFrame(tr_, columns=["k", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = X.index[T.k.values]; T["R"] = (T.pnl - T.sp) / T.risk; T["G"] = T.pnl / T.risk
        usd = meta[s]["tick_value"] / meta[s]["tick_size"] * 0.01
        h = len(T) // 2
        l12 = T[T.t >= T.t.max() - pd.Timedelta(days=365)].R.sum()
        yrs = " ".join(f"{y % 100}:{f2(pf(g.R.values))}" for y, g in T.groupby(T.t.dt.year))
        print(f"  {s:7s} {len(T):5d} PF {f2(pf(T.R.values))} gross {f2(pf(T.G.values))} halves {f2(pf(T.R.values[:h]))} "
              f"{f2(pf(T.R.values[h:]))} last12 {l12:+6.1f}R ${((T.pnl - T.sp) * usd).sum():+7.0f} | {yrs}")
