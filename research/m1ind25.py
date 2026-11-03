"""Round 25 (4 Nov 2026): the round 23 indicator systems on gold M1 (the owner wanted M1, not H1).

Same 14 rules as research/ind23.py (MACD, EMA 20/50, Supertrend, PSAR, ADX/DI, RSI 30/70 and 50, Stochastic, BB mean
reversion, CCI, Heikin Ashi, Williams %R, Ichimoku TK, Aroon) + random entries, on XAUUSD M1 from the broker
(run 41663561048), day trades: signals 01:30-21:00 server, flat 23:00, at most 60 bars, SL / TP as in round 23.
Costs: bar spread, stress 1.5x, 0.01 lot. Usual pass rule, PF 0.10 above RAND.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
mt = meta["XAUUSD"]
usd = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
B = DT.bars(d, "1min")
dates = B.date.values
flat = (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
print(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {len(B):,} bars", flush=True)
I = R.ind(B)
S = R.signals(B, I, False, 60, seed=11)
print(f"indicators + signals in {time.time() - T0:.0f} s", flush=True)
arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
mid, end, days = B.index[len(B) // 2], B.index[-1], B.index.normalize().nunique()
res = {}
for rule in R.RULES:
    tr = SA.sim(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat)
    T = pd.DataFrame(tr, columns=["k", "dir", "pnl", "sp", "risk", "why"])
    T["t"] = B.index[T.k.values]; T["net"] = (T.pnl - T.sp) * usd; T["st"] = (T.pnl - 1.5 * T.sp) * usd; T["raw"] = T.pnl * usd
    res[rule] = T
pf = SA.pf
PR = pf(res["RAND"].net.values)
t1 = end - pd.Timedelta(days=31)
print("\nrule      trades /day  win%   PF  half1 half2 stress last12$    net$  rawPF | last month: trades  PF   net$")
for rule, T in res.items():
    if T.empty:
        print(f"{rule:9s} no trades"); continue
    P, P1, P2, PS = pf(T.net.values), pf(T[T.t < mid].net.values), pf(T[T.t >= mid].net.values), pf(T.st.values)
    l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
    ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P - PR >= 0.10
    M = T[T.t >= t1]
    print(f"{rule:9s} {len(T):6d} {len(T) / days:5.1f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
          f"{l12:+7.0f} {T.net.sum():+8.0f} {SA.f2(pf(T.raw.values))} | {len(M):6d} {SA.f2(pf(M.net.values))} {M.net.sum():+7.0f} "
          f"{'PASS' if ok and rule != 'RAND' else ''}")
print(f"\ndone in {time.time() - T0:.0f} s")
