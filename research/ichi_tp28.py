"""Round 28 (4 Nov 2026): gold Kumo (swing) and TK (day trade) with a take profit added.

The owner closed a Kumo winner by hand because the module has no TP. Same rules and broker swap as ind23.py, plus a TP
at 1 / 1.5 / 2 / 3 / 4 R or 2 / 3 ATR (the normal exit still applies if it comes first)."""
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
print("rule  TP        trades  win%   PF  half1 half2 last12$   net$  avg win  avg loss  maxDD$")
for rule, mode in (("KUMO", "H1s"), ("TK", "H1d")):
    tf, swing, maxb = R.MODES[mode]
    B = DT.bars(d5, tf); dates = B.date.values
    flat = np.r_[(pd.Series(B.date).diff().dt.days.values[1:] > 1), True] if swing else \
        (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    I = R.ind(B); base = R.signals(B, I, swing, maxb, seed=5)[rule]
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    A = I["atr"]; mid, end = B.index[len(B) // 2], B.index[-1]
    for lab in ("none", "1R", "1.5R", "2R", "3R", "4R", "2ATR", "3ATR"):
        S = []
        for g in base:
            g = dict(g); i = g["k0"] - 1
            if lab.endswith("ATR"):
                g["tp"] = B.c.values[i] + g["dir"] * float(lab[:-3]) * A[i]
            elif lab != "none":
                g["tp_r"] = float(lab[:-1])
            S.append(g)
        rows = []
        for (k, dr, pnl, sp, risk, why, kx) in sim2(*arr, sorted(S, key=lambda g: g["k0"]), flat):
            swap = 0.0
            if swing and kx > k:
                d0, d1 = B.date.values[k], B.date.values[min(kx, len(B) - 1)]
                if d1 > d0:
                    cnt = sum(3 if x.weekday() == sw["d3"] - 1 else 1 for x in pd.bdate_range(pd.Timestamp(d0), pd.Timestamp(d1) - pd.Timedelta(days=1)))
                    swap = (sw["long"] if dr == 1 else sw["short"]) * mt["point"] * cnt * usd
            rows.append((B.index[k], (pnl - sp) * usd + swap))
        T = pd.DataFrame(rows, columns=["t", "net"])
        eq = T.net.cumsum().values; dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        print(f"{rule:5s} {lab:8s} {len(T):6d} {100 * (T.net > 0).mean():5.1f} {SA.f2(pf(T.net.values))} {SA.f2(pf(T[T.t < mid].net.values))} "
              f"{SA.f2(pf(T[T.t >= mid].net.values))} {T[T.t >= end - pd.Timedelta(days=365)].net.sum():+7.0f} {T.net.sum():+6.0f} "
              f"{T.net[T.net > 0].mean():8.2f} {T.net[T.net <= 0].mean():9.2f} {dd:+7.0f}", flush=True)
