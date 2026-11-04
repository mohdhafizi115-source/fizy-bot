"""Round 29 (4 Nov 2026): gold Kumo and TK on M5 and M15 (owner: "buat kan pada gold m1, m5, m15"; M1 is round 25).
Same rules as ind23.py. Day = signals 01:30-21:00, flat 23:00, no swap; swing = held up to 48 hours (576 M5 / 192 M15
bars), closed before the weekend, broker swap counted. Usual pass rule, PF 0.10 above RAND."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R
from goldh1_detail import sim2

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
sw = R.load_swaps()["XAUUSD"]
d5 = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
pf = SA.pf
print("tf   mode  rule  trades /day  win%   PF  half1 half2 stress last12$   net$  swap$  RAND")
for tf, nb in (("5min", 576), ("15min", 192)):
    B = DT.bars(d5, tf); dates = B.date.values; days = B.index.normalize().nunique()
    I = R.ind(B); arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    mid, end = B.index[len(B) // 2], B.index[-1]
    for swing in (False, True):
        flat = np.r_[(pd.Series(B.date).diff().dt.days.values[1:] > 1), True] if swing else \
            (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
        S = R.signals(B, I, swing, nb if swing else 10 ** 6, seed=9)
        out = {}
        for rule in ("KUMO", "TK", "RAND"):
            rows = []
            for (k, dr, pnl, sp, risk, why, kx) in sim2(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat):
                swap = 0.0
                if swing and kx > k:
                    d0, d1 = B.date.values[k], B.date.values[min(kx, len(B) - 1)]
                    if d1 > d0:
                        cnt = sum(3 if x.weekday() == sw["d3"] - 1 else 1 for x in pd.bdate_range(pd.Timestamp(d0), pd.Timestamp(d1) - pd.Timedelta(days=1)))
                        swap = (sw["long"] if dr == 1 else sw["short"]) * mt["point"] * cnt * usd
                rows.append((B.index[k], (pnl - sp) * usd + swap, (pnl - 1.5 * sp) * usd + swap, swap))
            out[rule] = pd.DataFrame(rows, columns=["t", "net", "st", "swap"])
        PR = pf(out["RAND"].net.values)
        for rule in ("KUMO", "TK"):
            x = out[rule]
            P, P1, P2, PS = pf(x.net.values), pf(x[x.t < mid].net.values), pf(x[x.t >= mid].net.values), pf(x.st.values)
            l12 = x[x.t >= end - pd.Timedelta(days=365)].net.sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P - PR >= 0.10
            print(f"{tf:5s} {'swing' if swing else 'day':5s} {rule:5s} {len(x):6d} {len(x) / days:4.1f} {100 * (x.net > 0).mean():5.1f} {SA.f2(P)} "
                  f"{SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {x.net.sum():+7.0f} {x.swap.sum():+6.0f} {SA.f2(PR)} {'PASS' if ok else ''}", flush=True)
