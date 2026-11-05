"""Round 41: are the M1 spike-fade trades news-driven? Match every live-rule signal against data/calendar.csv."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA, daytrade as DT, ind23 as R
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
CAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "calendar.csv")
pf = SA.pf
meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]
usd = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
B = DT.bars(d, "1min")
o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
n = len(c); dates = B.date.values
flat = (B.hm.values >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
I = R.ind(B); atr = I["atr"]; spr = B.s.values * usd; hm = B.hm.values
ok = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (np.arange(n) >= 300) & (atr >= 8 * spr); ok[-2:] = False
rg = h - l
S, sig_of = [], {}
for i in np.where(ok & (rg >= 3 * atr) & (c < o))[0]:
    sl = l[i] - 0.2 * atr[i]; tp = c[i] + 0.75 * rg[i]
    if sl >= c[i] or tp <= c[i]: continue
    S.append(dict(k0=i + 1, kind="mkt", dir=1, sl=sl, tp=tp, exp=i + 1, maxb=20)); sig_of[i + 1] = i
T = pd.DataFrame(SA.sim(*[B[x].values for x in ("o","h","l","c","s")], sorted(S, key=lambda g: g["k0"]), flat),
                 columns=["kk", "dir", "pnl", "sp", "risk", "why"])
T["t"] = B.index[T.kk.values]; T["net"] = (T.pnl - T.sp) * usd
T["sigt"] = [B.index[sig_of[k]] for k in T.kk]

C = pd.read_csv(CAL, usecols=["time", "impact", "currency", "name"])
hi = C.impact.max()
print(f"calendar: {len(C)} rows, impact scale max = {hi}")
for lab, sub in (("high impact, USD", C[(C.currency == "USD") & (C.impact == hi)]),
                 ("high impact, any currency", C[C.impact == hi])):
    ev = pd.DatetimeIndex(sorted(set(pd.to_datetime(sub.time.values, unit="s").tz_localize("Etc/GMT-2")
                                     .tz_convert("Europe/Athens").tz_localize(None))))
    print(f"\n--- against {len(ev)} {lab} events ---")
    pos = ev.searchsorted(T.sigt.values)
    gap = []
    for p, t in zip(pos, T.sigt.values):
        best = np.inf
        if p < len(ev): best = min(best, abs((ev[p] - t) / np.timedelta64(1, "m")))
        if p > 0: best = min(best, abs((t - ev[p - 1]) / np.timedelta64(1, "m")))
        gap.append(best)
    T["gap"] = gap
    for w in (2, 5, 15, 30, 60):
        m = T.gap <= w
        print(f"  within {w:2d} min of an event: {m.sum():4d} of {len(T)} trades ({100*m.mean():4.1f}%), "
              f"PF {SA.f2(pf(T[m].net.values)).strip():>5s}, net {T[m].net.sum():+7.0f} $ | "
              f"the rest: {(~m).sum():4d}, PF {SA.f2(pf(T[~m].net.values)).strip():>5s}, net {T[~m].net.sum():+7.0f} $")
print("\ntrades by hour (MYT), count and PF:")
myt = T.sigt.dt.tz_localize("Europe/Athens", ambiguous=True, nonexistent="shift_forward").dt.tz_convert("Asia/Kuala_Lumpur")
T["mh"] = myt.dt.hour
for hh in range(24):
    g = T[T.mh == hh]
    if len(g): print(f"  {hh:02d}:00 MYT  {len(g):4d} trades  PF {SA.f2(pf(g.net.values)).strip():>5s}  {g.net.sum():+7.0f} $")
