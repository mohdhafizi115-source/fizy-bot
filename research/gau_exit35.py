"""Round 35 (4 Nov 2026): fine sweep of the exit minute for the LBMA pre-auction gold sell, plus M1 exit rules.

Round 34 found that M1 entry tricks add nothing but holding past 10:30 London does: exit 10:32 gave PF 1.69 against
1.50 at the live 10:30. Before changing the live module, check that 10:32 is a plateau and not one lucky minute, and
test exits that react to the M1 price instead of a fixed clock:
  FIXED m    exit at London minute m (10:28 .. 10:45)
  M1UP n     after 10:30, exit at the next open after the first M1 bar that closes up (cap: London minute n)
  M1UP2 n    the same but two up closes in a row
  TRAIL x    after 10:30, exit when the price comes back x x ATR(M1) above the running low (cap 10:45)
All sell at 10:15 London, SL 2 x ATR(14, M5) as the live module. Costs: the entry bar's spread, stress 1.5x.
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
    say(f"XAUUSD M1, {len(starts)} auction days, sell 10:15 London, SL 2 x ATR(M5)\n")

    def run(kind, arg):
        res = []
        for dd, k in starts.items():
            if k + 40 >= n:
                continue
            e = o[k]
            sl = e + 2.0 * atr5[k] if np.isfinite(atr5[k]) else np.inf
            ex, run_lo = None, np.inf
            for q in range(k, n):
                if day[q] != dd:
                    ex = o[q]; break
                if h[q] >= sl:
                    ex = sl; break
                if kind == "FIXED":
                    if hm[q] >= arg:
                        ex = o[q]; break
                else:
                    cap = 645 if kind == "TRAIL" else arg
                    if hm[q] >= cap:
                        ex = o[q]; break
                    if hm[q] >= 630:
                        if kind == "M1UP" and c[q] > o[q]:
                            ex = o[min(q + 1, n - 1)]; break
                        if kind == "M1UP2" and c[q] > o[q] and c[q - 1] > o[q - 1]:
                            ex = o[min(q + 1, n - 1)]; break
                        if kind == "TRAIL":
                            run_lo = min(run_lo, l[q])
                            if np.isfinite(atr1[q]) and h[q] >= run_lo + arg * atr1[q]:
                                ex = run_lo + arg * atr1[q]; break
            if ex is None:
                continue
            res.append((d.index[k], (e - ex) * usd - sp[k] * usd, sp[k] * usd))
        return pd.DataFrame(res, columns=["t", "net", "sp"])

    say("exit rule       trades  win%   PF  half1 half2 stress last12$   net$  $/trade  maxDD$ mth+   by year")
    out = []
    jobs = [("FIXED", m, f"{m // 60:02d}:{m % 60:02d}") for m in range(628, 646)]
    jobs += [("M1UP", cap, f"M1 up close, cap {cap // 60:02d}:{cap % 60:02d}") for cap in (635, 640, 645)]
    jobs += [("M1UP2", cap, f"2 up closes, cap {cap // 60:02d}:{cap % 60:02d}") for cap in (640, 645)]
    jobs += [("TRAIL", x, f"trail {x} x ATR(M1)") for x in (0.5, 1.0, 1.5)]
    for kind, arg, lab in jobs:
        T = run(kind, arg)
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
        say(f"{lab:16s} {len(T):5d} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} "
            f"{T.net.sum():+6.0f} {T.net.mean():+8.3f} {dd_:+7.0f} {(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok else ''}")
        out.append((lab, P, ok, T))
    fx = [(lab, P) for lab, P, ok, T in out if ":" in lab and "cap" not in lab and "trail" not in lab]
    say("\nexit-minute shape: " + "  ".join(f"{lab} {P:.2f}" for lab, P in fx))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
