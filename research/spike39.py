"""Round 39 (5 Nov 2026): the exact M1 spike-fade configuration to build, confirmed.

From round 38: spike >= 3 x ATR(14, M1), only when ATR >= 8 x that bar's spread, TP 0.75 x the spike's range, hold
20 min, SL 0.2 ATR beyond the spike's extreme. TP 0.75 beat TP half (1.22 vs 1.16) and was flat over holds of 10-30
min. Fading DOWN spikes (buying a sharp drop) was much stronger than fading up spikes. This confirms the final cell,
splits it by side and by year, and checks the stop and the spread cap.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA, daytrade as DT, ind23 as R
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
pf = SA.pf
meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]
usd = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
B = DT.bars(d, "1min")
o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
n = len(c); dates = B.date.values
flat = (B.hm.values >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
I = R.ind(B); atr = I["atr"]; spr = B.s.values * usd; hm = B.hm.values
base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (np.arange(n) >= 300); base[-2:] = False
rg = h - l; arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
days = B.index.normalize().nunique(); mid_t, end = B.index[len(B) // 2], B.index[-1]

def run(side=0, slk=0.2, maxb=20, tpf=0.75, x=8, k=3, maxspr=None):
    ok = base & (atr >= x * spr)
    if maxspr: ok = ok & (spr <= maxspr)
    S = []
    for i in np.where(ok & (rg >= k * atr) & (c != o))[0]:
        dr = -1 if c[i] > o[i] else 1
        if side and dr != side: continue
        sl = (h[i] + slk * atr[i]) if dr == -1 else (l[i] - slk * atr[i])
        tp = c[i] + dr * tpf * rg[i]
        if (sl - c[i]) * dr >= 0 or (tp - c[i]) * dr <= 0: continue
        S.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, tp=tp, exp=i + 1, maxb=maxb))
    T = pd.DataFrame(SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat), columns=["kk", "dir", "pnl", "sp", "risk", "why"])
    if T.empty: return None
    T["t"] = B.index[T.kk.values]; T["net"] = (T.pnl - T.sp) * usd; T["st"] = (T.pnl - 1.5 * T.sp) * usd
    T["risk$"] = T.risk * usd
    return T

def line(lab, T):
    if T is None or len(T) < 50: print(f"{lab:30s} too few", flush=True); return
    P, P1, P2 = pf(T.net.values), pf(T[T.t < mid_t].net.values), pf(T[T.t >= mid_t].net.values)
    PS = pf(T.st.values); l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
    eq = T.net.cumsum().values; dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    mo = T.groupby(T.t.dt.to_period("M")).net.sum()
    ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
    yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
    print(f"{lab:30s} {len(T):5d} {len(T)/days:5.2f} {100*(T.net>0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
          f"{l12:+7.0f} {T.net.sum():+7.0f} {dd:+7.0f} {(mo>0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok else ''}", flush=True)

print(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {days} days\n")
print("variant                        trades /day  win%   PF  half1 half2 stress last12$    net$  maxDD$ mth+   by year")
line("both sides (TP 0.75, 20m)", run())
line("BUY after a down spike only", run(side=1))
line("SELL after an up spike only", run(side=-1))
print()
for slk in (0.1, 0.2, 0.3, 0.5):
    line(f"BUY only, SL {slk} ATR beyond", run(side=1, slk=slk))
print()
for mb in (10, 15, 20, 30, 45):
    line(f"BUY only, hold {mb} min", run(side=1, maxb=mb))
print()
for ms in (0.25, 0.30, 0.40, None):
    line(f"BUY only, spread cap ${ms}" if ms else "BUY only, no spread cap", run(side=1, maxspr=ms))
T = run(side=1)
print(f"\nBUY-only detail: median risk ${T['risk$'].median():.2f}, median spread ${(T.sp*usd).median():.2f}, "
      f"avg win ${T.net[T.net>0].mean():.2f}, avg loss ${T.net[T.net<=0].mean():.2f}, exits " +
      ", ".join(f"{k} {v}" for k, v in T.why.value_counts().items()))
print("by hour (server): " + " ".join(f"{hh:02d}h {SA.f2(pf(T[T.t.dt.hour==hh].net.values)).strip()}({(T.t.dt.hour==hh).sum()})"
      for hh in sorted(T.t.dt.hour.unique()) if (T.t.dt.hour==hh).sum() >= 40))
