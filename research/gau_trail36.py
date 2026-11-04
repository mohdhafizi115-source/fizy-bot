"""Round 36 (4 Nov 2026): the auction-scalp trailing exit, with the intrabar bias removed.

Round 35 showed a trailing exit of 0.5 x ATR(M1) at PF 2.09 with a max drawdown of only $33. That number used the
low of the SAME bar to set the trail level before checking that bar's high, which assumes the bar went down before it
went up: intrabar look-ahead. Here the trail level is fixed at the START of each bar from the lows up to the previous
bar, which is what a real stop order would do, and it must sit at least one spread away from the price.
  TRAIL x @m   sell 10:15 London; from London minute m, a buy stop at (lowest low so far + x x ATR(14, M1));
               hard exit 10:45; SL 2 x ATR(14, M5) throughout
  FIXED m      exit at London minute m (no trail), for comparison
Costs: the entry bar's spread, stress 1.5x. 0.01 lot.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
LON, SRV = ZoneInfo("Europe/London"), ZoneInfo("Europe/Athens")
pf = SA.pf
T0 = time.time()


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(c)
    M5 = d.resample("5min", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    p1 = M5.c.shift()
    tr5 = np.maximum(M5.h - M5.l, np.maximum((M5.h - p1).abs(), (M5.l - p1).abs()))
    atr5 = tr5.ewm(alpha=1 / 14, adjust=False).mean().shift(1).reindex(d.index, method="ffill").values
    c1 = d.c.shift()
    tr1 = np.maximum(d.h - d.l, np.maximum((d.h - c1).abs(), (d.l - c1).abs()))
    atr1 = tr1.ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    loc = d.index.tz_localize(SRV, ambiguous=True, nonexistent="shift_forward").tz_convert(LON)
    hm = (loc.hour * 60 + loc.minute).values
    day = pd.Index(loc.date)
    wd = pd.DatetimeIndex(pd.to_datetime(day)).day_of_week
    starts = {}
    for i in np.where((hm == 615) & (wd < 5))[0]:
        starts.setdefault(day[i], i)
    say = lambda s="": print(s, flush=True)
    say(f"XAUUSD M1, {len(starts)} auction days, sell 10:15 London, SL 2 x ATR(M5), hard exit 10:45\n")

    def run(x, start_m):
        res = []
        for dd, k in starts.items():
            if k + 40 >= n:
                continue
            e = o[k]
            sl = e + 2.0 * atr5[k] if np.isfinite(atr5[k]) else np.inf
            lo_prev = np.inf                                   # lowest low up to the PREVIOUS bar
            ex = None
            for q in range(k, n):
                if day[q] != dd:
                    ex = o[q]; break
                trail = np.inf
                if x is not None and hm[q] >= start_m and np.isfinite(lo_prev) and np.isfinite(atr1[q]):
                    trail = max(lo_prev + x * atr1[q], o[q] + sp[q])   # a stop must sit above the current ask
                stop = min(sl, trail)
                if hm[q] >= 645:
                    ex = o[q]; break
                if h[q] >= stop:
                    ex = stop; break
                if x is None and hm[q] >= start_m:
                    ex = o[q]; break
                lo_prev = min(lo_prev, l[q])
            if ex is None:
                continue
            res.append((d.index[k], (e - ex) * usd - sp[k] * usd, sp[k] * usd))
        return pd.DataFrame(res, columns=["t", "net", "sp"])

    say("exit rule               trades  win%   PF  half1 half2 stress last12$   net$  $/trade  maxDD$ mth+   by year")
    jobs = [(x, m, f"trail {x} ATR from {m // 60:02d}:{m % 60:02d}") for m in (615, 625, 630)
            for x in (0.3, 0.5, 0.75, 1.0, 1.5, 2.0)]
    jobs += [(None, m, f"fixed exit {m // 60:02d}:{m % 60:02d}") for m in (630, 631, 632, 634, 635)]
    for x, m, lab in jobs:
        T = run(x, m)
        if len(T) < 100:
            continue
        T["st"] = T.net - 0.5 * T.sp
        mid, end = T.t.iloc[len(T) // 2], T.t.max()
        P, P1, P2, PS = pf(T.net.values), pf(T[T.t < mid].net.values), pf(T[T.t >= mid].net.values), pf(T.st.values)
        l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd_ = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:23s} {len(T):5d} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} "
            f"{T.net.sum():+6.0f} {T.net.mean():+8.3f} {dd_:+7.0f} {(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok else ''}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
