"""Gold-only follow-up tests (GC=F, Yahoo):
  A. Session holds (one trade a day, spread $0.30 per trade): long 01:00->10:00 broker (Asian session,
     before London), long 01:00->04:00, short 15:00->22:00 (US session). 2 years of hourly data.
  B. Daily Donchian trend following on gold since 2004 with several lookbacks, long+short and long-only,
     with an estimated swap (long -0.0177% / short -0.021% of price per night, triple Wednesday)."""
import os, sys, time
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
out = []
def say(s=""):
    print(s, flush=True); out.append(s)

def yahoo(interval, **p):
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/GC=F", params={"interval": interval, **p},
                     headers=UA, timeout=60)
    res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                      index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
    return df[(df.high >= df.low) & (df.close > 0)]

def stats(p, label):
    p = p.dropna()
    if len(p) == 0:
        say(f"  {label}: no trades"); return
    eq = p.cumsum(); dd = (eq.cummax() - eq).max()
    h = len(p) // 2
    pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
    yrs = p.groupby(p.index.year).sum()
    say(f"  {label}: days {len(p)}, net ${p.sum():+.0f} per 0.01 lot, avg ${p.mean():+.2f}, win {np.mean(p > 0) * 100:.0f}%, "
        f"PF {pf(p):.2f}, max DD ${dd:.0f}, 1st half ${p.iloc[:h].sum():+.0f} / 2nd half ${p.iloc[h:].sum():+.0f}; "
        + " ".join(f"{y}:{v:+.0f}" for y, v in yrs.items()))

try:
    g = yahoo("60m", range="730d")
    g.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in g.index])
    say(f"A. GOLD SESSION HOLDS (GC=F hourly {g.index[0]:%Y-%m-%d}..{g.index[-1]:%Y-%m-%d}, broker time, spread $0.30)")
    buyhold = g.close.iloc[-1] - g.open.iloc[0]
    say(f"  (buy and hold over the period: ${buyhold:+.0f})")
    day = g.index.normalize()
    for label, a, b, dr in (("long 01->10", 1, 10, 1), ("long 01->04", 1, 4, 1), ("long 09->10", 9, 10, 1),
                            ("short 15->22", 15, 22, -1), ("long 10->22 (rest of day)", 10, 22, 1)):
        x = g[(g.index.hour >= a) & (g.index.hour < b)]
        d = x.groupby(x.index.normalize()).agg(o=("open", "first"), c=("close", "last"), n=("open", "size"))
        d = d[d.n >= (b - a) - 1]
        p = (d.c - d.o) * dr - 0.30
        p.index = pd.DatetimeIndex(p.index)
        stats(p, label)
except Exception as e:
    say(f"  error {e}")

say()
try:
    d = yahoo("1d", period1=1072915200, period2=int(time.time()))
    d.index = d.index.tz_convert(None).normalize(); d = d[~d.index.duplicated()]
    say(f"B. GOLD DAILY DONCHIAN (GC=F {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d}), R = 2 x ATR20, spread $0.30, est. swap")
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - d.close.shift()), abs(d.low - d.close.shift())))
    a = tr.rolling(20).mean().shift()
    o, h, l, c = d.open.values, d.high.values, d.low.values, d.close.values
    for n_in, n_out in ((20, 10), (55, 20), (100, 50)):
        for longonly in (False, True):
            hi_in, lo_in = d.high.rolling(n_in).max().shift(), d.low.rolling(n_in).min().shift()
            hi_out, lo_out = d.high.rolling(n_out).max().shift(), d.low.rolling(n_out).min().shift()
            pos, R, Rs, ts = None, [], [], []
            for i in range(n_in + 5, len(d) - 1):
                if pos is not None:
                    dr = pos["dr"]; ex = None
                    if (dr == 1 and l[i] <= pos["sl"]) or (dr == -1 and h[i] >= pos["sl"]):
                        ex = o[i] if ((dr == 1 and o[i] < pos["sl"]) or (dr == -1 and o[i] > pos["sl"])) else pos["sl"]
                    elif (dr == 1 and c[i] < lo_out.iloc[i]) or (dr == -1 and c[i] > hi_out.iloc[i]):
                        ex = o[i + 1]
                    if ex is not None:
                        nights = np.busday_count(pos["t"].date(), d.index[i].date()) + 2 * ((d.index[i] - pos["t"]).days // 7)
                        swap = nights * pos["e"] * (0.000177 if dr == 1 else 0.00021)
                        R.append(((ex - pos["e"]) * dr - 0.30) / pos["r"]); Rs.append(((ex - pos["e"]) * dr - 0.30 - swap) / pos["r"])
                        ts.append(pos["t"]); pos = None
                        continue
                if pos is None and not np.isnan(a.iloc[i]):
                    dr = 1 if c[i] > hi_in.iloc[i] else (-1 if (c[i] < lo_in.iloc[i] and not longonly) else 0)
                    if dr:
                        e = o[i + 1]; r = 2 * a.iloc[i]
                        pos = dict(dr=dr, e=e, sl=e - dr * r, r=r, t=d.index[i + 1])
            R, Rs = np.array(R), np.array(Rs); ts = pd.DatetimeIndex(ts)
            pf = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
            rec = Rs[ts >= "2015-01-01"]; old = Rs[ts < "2015-01-01"]
            say(f"  {n_in}/{n_out} {'long only ' if longonly else 'long+short'}: trades {len(R)}, win {np.mean(R > 0) * 100:.0f}%, "
                f"{R.sum():+.1f}R (PF {pf(R):.2f}), after swap {Rs.sum():+.1f}R (PF {pf(Rs):.2f}); "
                f"2004-2014 {old.sum():+.1f}R, 2015-2026 {rec.sum():+.1f}R")
except Exception as e:
    import traceback; say("  error " + traceback.format_exc()[-800:])

os.makedirs("status", exist_ok=True)
with open("status/research.txt", "w") as f:
    f.write("Gold follow-up tests\n" + "\n".join(out) + "\n")
