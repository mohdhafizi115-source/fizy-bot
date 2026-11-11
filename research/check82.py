"""Check 82 (11 Nov 2026): the owner saw no LEG trade today. Replays the live entry rules on the latest broker M1 bars
and lists, day by day, every LEG signal (0.10% wick zigzag, leg 20 candles old, fade) and whether the v2.14 filter
(the leg's peak / trough >= $5 beyond EMA 50) let it through; also counts spike-fade and Keltner signals."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
B = DT.bars(d, "1min")
B = B[B.index >= B.index[-1] - pd.Timedelta(days=9)]
O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c")); sp = B.s.values.astype(float)
n = len(C); hm = B.hm.values; day = B.date.values; newd = np.r_[True, day[1:] != day[:-1]]; T = B.index
EV = pd.Series(C).ewm(span=50, adjust=False).mean().values
print(f"XAUUSD M1 {T[0]} .. {T[-1]} (server time), {n} bars")
pct, N = 0.0010, 20
rows = []
d_ = 0; ext = piv = lo0 = hi0 = 0; fired = False
for k in range(n):
    if newd[k]:
        d_, ext, piv, fired = 0, k, k, False; lo0 = hi0 = k; continue
    if d_ == 0:
        if L[k] < L[lo0]: lo0 = k
        if H[k] > H[hi0]: hi0 = k
        if H[k] >= L[lo0] * (1 + pct): d_, piv, ext, fired = 1, lo0, k, False
        elif L[k] <= H[hi0] * (1 - pct): d_, piv, ext, fired = -1, hi0, k, False
        continue
    if d_ == 1:
        if H[k] > H[ext]: ext = k
        elif L[k] <= H[ext] * (1 - pct): piv, d_, ext, fired = ext, -1, k, False; continue
    else:
        if L[k] < L[ext]: ext = k
        elif H[k] >= L[ext] * (1 + pct): piv, d_, ext, fired = ext, 1, k, False; continue
    if not fired and k - piv >= N:
        fired = True
        ref = H[ext] if d_ == 1 else L[ext]
        dist = ref - EV[k] if d_ == 1 else EV[k] - ref
        inhours = 90 <= hm[k] < 1320
        rows.append((T[k], "SELL" if d_ == 1 else "BUY", round(dist, 2), inhours, inhours and dist >= 5.0))
R = pd.DataFrame(rows, columns=["t", "fade", "peak_dist_to_ema50", "in_hours", "would_enter"])
R["day"] = R.t.dt.date
print("\nLEG signals per server day (leg 20 candles old): all / in 01:30-22:00 / passing the $5 peak-trough filter")
print(R.groupby("day").agg(signals=("t", "size"), in_hours=("in_hours", "sum"), would_enter=("would_enter", "sum")).to_string())
last = R.day.max()
print(f"\nevery LEG signal on {last} (server time; MYT = +6 h):")
print(R[R.day == last].to_string(index=False))
# spike fade and Keltner signal counts
c1 = np.r_[C[0], C[:-1]]
tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values; a1 = np.r_[np.nan, atr[:-1]]
gate = a1 / np.where(sp > 0, sp, np.nan); ok = (hm >= 90) & (hm < 1320)
spk = (H - L >= 2.0 * a1) & (C < O) & (gate >= 8) & ok
e20 = pd.Series(C).ewm(span=20, adjust=False).mean().values; lo = e20 - 3 * atr
klt = np.r_[False, (C < lo)[:-1]] & (C >= lo) & (gate >= 8) & ok
G = pd.DataFrame({"spike": spk, "keltner": klt, "gate>=8 bars": (gate >= 8) & ok, "median gate": gate}, index=T)
print("\nper server day: spike-fade signals, Keltner signals, bars with ATR >= 8x spread, median ATR/spread")
print(G.groupby(G.index.date).agg({"spike": "sum", "keltner": "sum", "gate>=8 bars": "sum", "median gate": "median"}).round(1).to_string())
