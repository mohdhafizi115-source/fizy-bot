"""Round 34 (4 Nov 2026): M1 entry and exit timing for the live LBMA pre-auction gold sell.

Round 33 scanned every minute of the day on M1 and found no new time window (0 survivors, while a shuffled control
gave 22), but it did show that M1 timing improves the one window that works. This round grids that properly, with
the live module's own stop (2 x ATR(14) on M5, as FizyGAU.mqh uses), so the baseline really is what runs now.

  Entry   MKT        sell at the 10:15 London open (live)
          GRN<n>     wait up to n minutes for an M1 bar that closes up, sell at the next open (sell into a bounce)
          GRN2<n>    the same but the bar must also close above the previous close
          BNC<x>     wait up to 15 min for the price to come back x x ATR(M1) above the 10:15 open
  Exit    10:30 (live) / 10:32 / 10:35 / 10:40 London, or the day's end if earlier
  Stop    none, 2 x ATR(M5) (live), 3 x ATR(M5)
Costs: the entry bar's spread, stress = 1.5x. 0.01 lot, so PF and net are in dollars. Pass rule as usual.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
LON, SRV = ZoneInfo("Europe/London"), ZoneInfo("Europe/Athens")
T0 = time.time()
pf = SA.pf


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(c)
    # ATR(14) Wilder on M5, as the live module uses, mapped back to every M1 bar
    M5 = d.resample("5min", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    p1 = M5.c.shift()
    tr5 = np.maximum(M5.h - M5.l, np.maximum((M5.h - p1).abs(), (M5.l - p1).abs()))
    a5 = tr5.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    atr5 = a5.reindex(d.index, method="ffill").values
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
    days = d.index.normalize().nunique()
    say = lambda s="": print(s, flush=True)
    say(f"XAUUSD M1 {d.index[0]:%Y-%m-%d} .. {d.index[-1]:%Y-%m-%d}, {len(starts)} auction days")
    say("\nentry    exit   stop        trades  win%   PF  half1 half2 stress last12$   net$  $/trade  maxDD$ mth+   by year")

    ENTRIES = [("MKT", None), ("GRN5", 5), ("GRN10", 10), ("GRN15", 15), ("GRN2_10", -10), ("BNC0.5", 0.5), ("BNC1", 1.0)]
    rows = []
    for ename, earg in ENTRIES:
        for exit_m in (630, 632, 635, 640):
            for slk in (0.0, 2.0, 3.0):
                res = []
                for dd, k in starts.items():
                    if k + 30 >= n:
                        continue
                    ent = None
                    if ename == "MKT":
                        ent = k
                    elif ename.startswith("GRN2"):
                        for q in range(k, k + abs(earg)):
                            if c[q] > o[q] and c[q] > c[q - 1]:
                                ent = q + 1; break
                    elif ename.startswith("GRN"):
                        for q in range(k, k + int(earg)):
                            if c[q] > o[q]:
                                ent = q + 1; break
                    else:
                        if not np.isfinite(atr1[k]):
                            continue
                        lvl = o[k] + earg * atr1[k]
                        for q in range(k, k + 15):
                            if h[q] >= lvl:
                                ent = q + 1; break
                    if ent is None or ent + 1 >= n or day[ent] != dd or hm[ent] >= exit_m:
                        continue
                    e = o[ent]
                    sl = e + slk * atr5[ent] if (slk > 0 and np.isfinite(atr5[ent])) else np.inf
                    ex = None
                    for q in range(ent, n):
                        if hm[q] >= exit_m or day[q] != dd:
                            ex = o[q]; break
                        if h[q] >= sl:
                            ex = sl; break
                    if ex is None:
                        continue
                    res.append((d.index[ent], (e - ex) * usd - sp[ent] * usd, sp[ent] * usd))
                if len(res) < 100:
                    continue
                T = pd.DataFrame(res, columns=["t", "net", "sp"])
                T["st"] = T.net - 0.5 * T.sp                      # stress: 1.5x the spread (0.5 more than already charged)
                mid, end = T.t.iloc[len(T) // 2], T.t.max()
                P, P1, P2 = pf(T.net.values), pf(T[T.t < mid].net.values), pf(T[T.t >= mid].net.values)
                PS = pf(T.st.values)
                l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
                eq = T.net.cumsum().values
                dd_ = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
                mo = T.groupby(T.t.dt.to_period("M")).net.sum()
                ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
                yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
                lab = f"{ename:8s} {exit_m // 60:02d}:{exit_m % 60:02d}  {'none ' if slk == 0 else f'{slk:.0f}xATR5'}"
                rows.append((ok, P, lab, len(T), T))
                say(f"{lab:21s} {len(T):6d} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
                    f"{l12:+7.0f} {T.net.sum():+6.0f} {T.net.mean():+8.3f} {dd_:+7.0f} {(mo > 0).sum():2d}/{len(mo)}  {yr}"
                    f"{'  PASS' if ok else ''}")
    npass = sum(1 for r in rows if r[0])
    say(f"\n{npass} of {len(rows)} entry / exit / stop combinations pass")
    best = sorted([r for r in rows if r[0]], key=lambda r: -r[1])[:3]
    for _, P, lab, ntr, T in best:
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        say(f"  {lab}: PF {P:.2f}, {ntr} trades, worst month {mo.min():+.0f} $, best {mo.max():+.0f} $, "
            f"worst trade {T.net.min():+.2f} $, best {T.net.max():+.2f} $")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
