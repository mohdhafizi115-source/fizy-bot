"""Round 40: how often the live M1 spike fade (FizySPK) actually trades, and three real examples to explain it."""
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
ok = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (np.arange(n) >= 300) & (atr >= 8 * spr)
ok[-2:] = False
rg = h - l
S, info = [], {}
for i in np.where(ok & (rg >= 3 * atr) & (c < o))[0]:
    sl = l[i] - 0.2 * atr[i]; tp = c[i] + 0.75 * rg[i]
    if sl >= c[i] or tp <= c[i]: continue
    S.append(dict(k0=i + 1, kind="mkt", dir=1, sl=sl, tp=tp, exp=i + 1, maxb=20))
    info[i + 1] = (i, sl, tp)
T = pd.DataFrame(SA.sim(*[B[x].values for x in ("o","h","l","c","s")], sorted(S, key=lambda g: g["k0"]), flat),
                 columns=["kk", "dir", "pnl", "sp", "risk", "why"])
T["t"] = B.index[T.kk.values]; T["net"] = (T.pnl - T.sp) * usd
print(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}\n")
print("year  trades  per trading day   net $ (0.01 lot)   PF")
for y, g in T.groupby(T.t.dt.year):
    dd = B[B.index.year == y].index.normalize().nunique()
    print(f"{y}  {len(g):5d}   {len(g)/dd:5.2f}            {g.net.sum():+8.0f}   {SA.f2(pf(g.net.values))}")
print("\nlast 12 months, trades per month:")
m12 = T[T.t >= T.t.max() - pd.Timedelta(days=365)]
for p, g in m12.groupby(m12.t.dt.to_period("M")):
    print(f"  {p}  {len(g):3d} trades  {g.net.sum():+7.2f} $")
print(f"\nrecent rate: {len(m12)} trades in 12 months = {len(m12)/12:.1f} a month = about 1 every {365/max(len(m12),1):.1f} days")
print(f"hold: median {np.median((T.kk.values - np.array([info[k][0] for k in T.kk])) ):.0f} min from signal to entry bar; "
      f"exits " + ", ".join(f"{k} {v}" for k, v in T.why.value_counts().items()))
print("\nthree real examples (the biggest win, a typical loss, and the most recent trade):")
T["ix"] = [info[k][0] for k in T.kk]
for lab, row in (("biggest win", T.loc[T.net.idxmax()]), ("typical loss", T[(T.net < 0)].iloc[len(T[T.net < 0]) // 2]), ("most recent", T.iloc[-1])):
    i = int(row.ix); k = int(row.kk)
    sl, tp = info[k][1], info[k][2]
    myt = B.index[i].tz_localize("Europe/Athens", ambiguous=True, nonexistent="shift_forward").tz_convert("Asia/Kuala_Lumpur")
    print(f"\n  {lab} — {myt:%a %d %b %Y %H:%M} MYT (broker {B.index[i]:%H:%M})")
    print(f"    the M1 candle: open {o[i]:.2f} high {h[i]:.2f} low {l[i]:.2f} close {c[i]:.2f}  -> it fell ${o[i]-c[i]:.2f}, range ${rg[i]:.2f}")
    print(f"    ATR(M1) was ${atr[i]:.2f} and the spread ${spr[i]:.2f}, so ATR = {atr[i]/spr[i]:.0f}x the spread (gate needs 8x)")
    print(f"    range {rg[i]/atr[i]:.1f}x ATR (needs 3x) -> BUY at {o[k]:.2f}, SL {sl:.2f} (risk ${o[k]-sl:.2f}), TP {tp:.2f} (reward ${tp-o[k]:.2f})")
    print(f"    result: {row.why} after {int(row.kk) and ''}{'' } -> {row.net:+.2f} $")
