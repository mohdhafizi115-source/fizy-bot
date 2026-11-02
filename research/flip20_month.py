"""Dump the round 20 REJ trades of the last month with the M15 candles around them, as JSON, for a chart page.

Same rules and data as research/flip20.py (rule REJ). Output: one JSON object on stdout with
  bars:   [t (server time, unix s), o, h, l, c] for the M15 candles from 2 days before the month to the end
  trades: signal / entry / exit bar times, side, level, entry, SL, TP, target source, exit price, reason, net $ (0.01 lot)
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import flip20 as F
from goldh1_detail import sim2

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    m = meta[F.SYM]
    usd = m["tick_value"] / m["tick_size"] * 0.01 if m["tick_size"] > 0 else 1.0
    d5 = SA.load(os.path.join(DATA, F.SYM + ".csv"), m["point"])
    B = DT.bars(d5, "15min")
    flat = F.flat_mask(B)
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    end = B.index[-1]
    t1m = end - pd.Timedelta(days=31)
    S = F.signals(B, **F.VARIANTS["REJ"])
    info = {g["k0"]: g for g in S}
    tr = sim2(*arr, sorted(S, key=lambda g: g["k0"]), flat)
    ts = (B.index.values.astype("datetime64[s]").astype(np.int64)).tolist()
    trades = []
    for k, dr, pnl, sp, risk, why, kx in tr:
        if B.index[k] < t1m:
            continue
        g = info[k]
        e = arr[0][k]
        tp = g.get("tp", e + dr * 2.0 * risk)
        trades.append(dict(sig=ts[g["sig"]], ent=ts[k], ext=ts[min(kx, len(ts) - 1)], side="BUY" if dr == 1 else "SELL",
                           level=round(g["lvl"], 2), entry=round(e, 2), sl=round(g["sl"], 2), tp=round(tp, 2), src=g["src"],
                           exit=round(e + dr * pnl, 2), why=why, usd=round((pnl - sp) * usd, 2), spread=round(sp * usd, 2)))
    a = int(np.searchsorted(B.index.values, (t1m - pd.Timedelta(days=2)).to_datetime64()))
    bars = [[ts[i], round(arr[0][i], 2), round(arr[1][i], 2), round(arr[2][i], 2), round(arr[3][i], 2)] for i in range(a, len(B))]
    print(json.dumps(dict(sym=F.SYM, end=ts[-1], bars=bars, trades=trades), separators=(",", ":")))


if __name__ == "__main__":
    main()
