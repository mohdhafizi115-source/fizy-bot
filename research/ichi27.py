"""Round 27 (4 Nov 2026): the two Ichimoku rules (live gold Kumo breakout and TK cross) on every exported pair.

Owner, after a +$52.82 Kumo win on gold: "teknik macam ni aku nak. kau apply pada semua pair". Same rules, modes,
costs and broker swaps as research/ind23.py; per instrument and mode, with the usual pass rule (PF 0.10 above RAND).
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R
from goldh1_detail import sim2

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
SW = R.load_swaps()
pf = SA.pf
print("sym     mode rule  trades  PF   half1 half2 stress last12$   net$  swap$  RAND")
for sym in R.SYMS:
    if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")):
        continue
    mt = meta[sym]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d5 = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"]); sw = SW.get(sym)
    for mode in ("H1d", "H1s", "H4s"):
        tf, swing, maxb = R.MODES[mode]
        B = DT.bars(d5, tf); dates = B.date.values
        last = np.r_[dates[1:] != dates[:-1], True]
        flat = np.r_[(pd.Series(B.date).diff().dt.days.values[1:] > 1), True] if swing else \
            (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]] | last
        I = R.ind(B); S = R.signals(B, I, swing, maxb, seed=5)
        arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
        mid, end = B.index[len(B) // 2], B.index[-1]
        out = {}
        for rule in ("KUMO", "TK", "RAND"):
            rows = []
            for (k, dr, pnl, sp, risk, why, kx) in sim2(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat):
                swap = 0.0
                if swing and kx > k and sw:
                    d0, d1 = B.date.values[k], B.date.values[min(kx, len(B) - 1)]
                    if d1 > d0:
                        if 1 <= sw["d3"] <= 5:
                            cnt = sum(3 if x.weekday() == sw["d3"] - 1 else 1 for x in pd.bdate_range(pd.Timestamp(d0), pd.Timestamp(d1) - pd.Timedelta(days=1)))
                        else:
                            cnt = int((pd.Timestamp(d1) - pd.Timestamp(d0)).days)
                        swap = (sw["long"] if dr == 1 else sw["short"]) * mt["point"] * cnt * usd
                rows.append((B.index[k], (pnl - sp) * usd + swap, (pnl - 1.5 * sp) * usd + swap, swap))
            out[rule] = pd.DataFrame(rows, columns=["t", "net", "st", "swap"])
        PR = pf(out["RAND"].net.values)
        for rule in ("KUMO", "TK"):
            x = out[rule]
            if x.empty:
                continue
            P, P1, P2, PS = pf(x.net.values), pf(x[x.t < mid].net.values), pf(x[x.t >= mid].net.values), pf(x.st.values)
            l12 = x[x.t >= end - pd.Timedelta(days=365)].net.sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P - PR >= 0.10
            print(f"{sym:7s} {mode:4s} {rule:5s} {len(x):6d} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {x.net.sum():+6.0f} "
                  f"{x.swap.sum():+6.0f} {SA.f2(PR)} {'PASS' if ok else ''}", flush=True)
