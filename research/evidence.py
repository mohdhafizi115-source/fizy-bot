"""Tests of the strategies with the best published evidence, on long Yahoo data (runs in GitHub Actions).
  1. Gold hour-of-day profile on GC=F hourly (2 years), broker time (New York + 7)
  2. Daily trend following, per instrument: Donchian 55-day breakout, exit on the 20-day opposite
     channel, initial stop 2 x ATR20, next-day open entries; result in R (1R = 2 x ATR at entry)
  3. Time-series momentum portfolio (Moskowitz / Ooi / Pedersen style): each month, long or short every
     market by the sign of its 12-month return, sized to equal volatility; yearly returns
  4. Gold month-of-year returns on GC=F daily
Spread costs: 1 pip forex / $0.30 gold per trade; swap NOT included (matters for multi-week holds)."""
import os, sys, time
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}


def yahoo(name, interval, rng):
    ysym = "GC=F" if name.startswith("XAU") else name + "=X"
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}",
                     params={"interval": interval, "range": rng}, headers=UA, timeout=60)
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
                      index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
    return df[(df.high >= df.low) & (df.close > 0)]


out = []
def say(s=""):
    print(s, flush=True); out.append(s)

# ---------------------------------------------------------------- 1. gold hour of day
say("1. GOLD HOUR-OF-DAY (GC=F hourly, 2 years, broker time = New York + 7), average $ move per hour")
try:
    g = yahoo("XAUUSD", "60m", "730d")
    g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index])
    g["ret"] = g.close - g.open
    g["hr"] = g.index.hour
    mid = g.index[len(g) // 2]
    rows = []
    for hr, x in g.groupby("hr"):
        a, b = x[x.index < mid].ret, x[x.index >= mid].ret
        t = x.ret.mean() / (x.ret.std() / np.sqrt(len(x)))
        rows.append(f"  {hr:02d}:00  mean {x.ret.mean():+6.2f}  t {t:+5.2f}  n {len(x):4d}  | 1st half {a.mean():+6.2f}  2nd half {b.mean():+6.2f}")
    for r in rows:
        say(r)
    say(f"  period {g.index[0]:%Y-%m-%d} .. {g.index[-1]:%Y-%m-%d}")
except Exception as e:
    say(f"  error {e}")

# ---------------------------------------------------------------- daily data
daily = {}
errs = []
for name in S.symbol_list():
    d = None
    for rng in ("max", "20y", "10y"):
        try:
            d = yahoo(name, "1d", rng); break
        except Exception as e:
            errs.append(f"{name} {rng}: {str(e)[:120]}"); time.sleep(2)
    try:
        if d is None:
            continue
        d.index = d.index.tz_convert(None).normalize()
        d = d[~d.index.duplicated()]
        d = d[d.index >= "2004-01-01"]
        if len(d) > 1000:
            daily[name] = d
        else:
            errs.append(f"{name}: only {len(d)} daily candles")
    except Exception as e:
        errs.append(f"{name}: {str(e)[:120]}")
    time.sleep(1.0)
say()
say(f"daily data: {len(daily)} markets" + (f", from {min(x.index[0] for x in daily.values()):%Y-%m-%d}" if daily else ""))
for e_ in errs[:15]:
    say("  data note: " + e_)


def atr(d, n=20):
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - d.close.shift()), abs(d.low - d.close.shift())))
    return tr.rolling(n).mean()


def cost_of(name):
    return 0.30 if name.startswith("XAU") else (0.01 if "JPY" in name else 0.0001)

import traceback
try:
    # ---------------------------------------------------------------- 2. Donchian 55/20
    say()
    say("2. DAILY DONCHIAN 55/20 TREND FOLLOWING (per trade, R = 2 x ATR20; spread included, swap not)")
    allt = []
    for name, d in daily.items():
        hi55, lo55 = d.high.rolling(55).max().shift(), d.low.rolling(55).min().shift()
        hi20, lo20 = d.high.rolling(20).max().shift(), d.low.rolling(20).min().shift()
        a = atr(d).shift()
        o, h, l, c = d.open.values, d.high.values, d.low.values, d.close.values
        pos = None; cst = cost_of(name)
        for i in range(60, len(d) - 1):
            if pos is not None:
                dr = pos["dr"]
                # stop first (conservative), then channel exit at the next open
                if (dr == 1 and l[i] <= pos["sl"]) or (dr == -1 and h[i] >= pos["sl"]):
                    px = pos["sl"] if not ((dr == 1 and o[i] < pos["sl"]) or (dr == -1 and o[i] > pos["sl"])) else o[i]
                    allt.append((name, pos["t"], ((px - pos["e"]) * dr - cst) / pos["r"])); pos = None
                elif (dr == 1 and c[i] < lo20.iloc[i]) or (dr == -1 and c[i] > hi20.iloc[i]):
                    px = o[i + 1]
                    allt.append((name, pos["t"], ((px - pos["e"]) * dr - cst) / pos["r"])); pos = None
                    continue
            if pos is None and not np.isnan(a.iloc[i]):
                dr = 1 if c[i] > hi55.iloc[i] else (-1 if c[i] < lo55.iloc[i] else 0)
                if dr:
                    e = o[i + 1]; r = 2 * a.iloc[i]
                    pos = dict(dr=dr, e=e, sl=e - dr * r, r=r, t=d.index[i + 1])
    T = pd.DataFrame(allt, columns=["sym", "t", "R"])
    if len(T):
        def pf(x):
            return x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
        fx = T[~T.sym.str.startswith("XAU")]
        say(f"  ALL: trades {len(T)}, win {np.mean(T.R > 0) * 100:.0f}%, total {T.R.sum():+.0f}R, PF {pf(T.R):.2f}, "
            f"avg {T.R.mean():+.3f}R/trade, forex pairs positive {(fx.groupby('sym').R.sum() > 0).mean() * 100:.0f}%")
        yr = T.groupby(T.t.dt.year).R.agg(["count", "sum"])
        say("  by year (R): " + "  ".join(f"{y}:{s:+.0f}" for y, s in yr["sum"].items()))
        for per, x in (("2004-2014", T[T.t < "2015-01-01"]), ("2015-2020", T[(T.t >= "2015-01-01") & (T.t < "2021-01-01")]),
                       ("2021-2026", T[T.t >= "2021-01-01"])):
            say(f"  {per}: trades {len(x)}, total {x.R.sum():+.0f}R, PF {pf(x.R):.2f}")
        g = T[T.sym.str.startswith("XAU")]
        say(f"  GOLD only: trades {len(g)}, total {g.R.sum():+.1f}R, PF {pf(g.R):.2f}; since 2021: {g[g.t >= '2021-01-01'].R.sum():+.1f}R "
            f"PF {pf(g[g.t >= '2021-01-01'].R):.2f}")
        per_sym = T.groupby("sym").R.agg(["count", "sum"]).sort_values("sum")
        say("  per market (R): " + ", ".join(f"{s} {v:+.0f}" for s, v in per_sym["sum"].items()))

    # ---------------------------------------------------------------- 3. TSMOM portfolio
    say()
    say("3. TIME-SERIES MOMENTUM PORTFOLIO (monthly, sign of 12-month return, equal volatility, 10% vol target per market)")
    try:
        px = pd.DataFrame({n: d.close for n, d in daily.items()}).sort_index().ffill()
        mret = px.resample("ME").last().pct_change()
        vol = px.pct_change().rolling(60).std().resample("ME").last() * np.sqrt(252)
        sig = np.sign(px.resample("ME").last().pct_change(12))
        w = (sig * (0.10 / vol)).clip(-3, 3)
        pret = (w.shift(1) * mret)
        turnover_cost = (w.diff().abs() * 0.0002).shift(0)          # ~2 bp per unit traded
        port = (pret - turnover_cost).mean(axis=1).dropna()
        port = port[port.index >= "2005-12-31"]
        ann = port.groupby(port.index.year).apply(lambda r: (1 + r).prod() - 1) * 100
        sh = port.mean() / port.std() * np.sqrt(12)
        say(f"  {port.index[0]:%Y-%m}..{port.index[-1]:%Y-%m}: annual mean {port.mean() * 12 * 100:+.1f}%, vol {port.std() * np.sqrt(12) * 100:.1f}%, Sharpe {sh:.2f}")
        say("  by year (%): " + "  ".join(f"{y}:{v:+.1f}" for y, v in ann.items()))
        eq = (1 + port).cumprod(); dd = (eq / eq.cummax() - 1).min() * 100
        say(f"  max drawdown {dd:.1f}%; positive years {int((ann > 0).sum())}/{len(ann)}")
    except Exception as e:
        say(f"  error {e}")

    # ---------------------------------------------------------------- 4. gold months
    say()
    say("4. GOLD MONTH-OF-YEAR (GC=F daily, average monthly return %)")
    try:
        gd = daily["XAUUSD"].close.resample("ME").last().pct_change().dropna() * 100
        mm = gd.groupby(gd.index.month).agg(["mean", "count"])
        pos = gd.groupby(gd.index.month).apply(lambda x: (x > 0).mean() * 100)
        say("  " + "  ".join(f"{m}:{r:+.1f}% ({p:.0f}% up)" for m, r, p in zip(mm.index, mm["mean"], pos)))
    except Exception as e:
        say(f"  error {e}")
except Exception:
    say('ERROR ' + traceback.format_exc()[-1500:])

os.makedirs("status", exist_ok=True)
with open("status/research.txt", "w") as f:
    f.write("Evidence-based strategy tests (Yahoo data)\n" + "\n".join(out) + "\n")
