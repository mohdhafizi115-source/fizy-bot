"""How long can one gold M1 trend leg get? 0.10% zigzag on wicks (as live FizyLEG), reset each server day."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
B = DT.bars(d, "1min"); H, L = B.h.values.astype(float), B.l.values.astype(float)
day = B.date.values; newd = np.r_[True, day[1:] != day[:-1]]; T = B.index
pct = 0.001; out = []
d_ = ext = piv = lo0 = hi0 = 0
for k in range(len(H)):
    if newd[k]: d_, ext, piv, lo0, hi0 = 0, k, k, k, k; continue
    if d_ == 0:
        if L[k] < L[lo0]: lo0 = k
        if H[k] > H[hi0]: hi0 = k
        if H[k] >= L[lo0] * (1 + pct): d_, piv, ext = 1, lo0, k
        elif L[k] <= H[hi0] * (1 - pct): d_, piv, ext = -1, hi0, k
        continue
    if d_ == 1:
        if H[k] > H[ext]: ext = k
        elif L[k] <= H[ext] * (1 - pct): out.append((piv, ext, 1)); piv, d_, ext = ext, -1, k
    else:
        if L[k] < L[ext]: ext = k
        elif H[k] >= L[ext] * (1 + pct): out.append((piv, ext, -1)); piv, d_, ext = ext, 1, k
a = np.array(out); ln = a[:, 1] - a[:, 0]
yr = T.year.values[a[:, 0]]
for s, lab in ((1, "UP (buy) legs"), (-1, "DOWN (sell) legs")):
    m = a[:, 2] == s; x = ln[m]
    i = np.argmax(np.where(m, ln, -1))
    print(f"{lab}: n={m.sum()}, mean {x.mean():.1f}, median {np.median(x):.0f}, p90 {np.percentile(x, 90):.0f}, "
          f"p99 {np.percentile(x, 99):.0f}, max {x.max()} candles (from {T[a[i, 0]]:%Y-%m-%d %H:%M} server)")
    for y in (2024, 2025, 2026):
        xy = ln[m & (yr == y)]
        print(f"   {y}: mean {xy.mean():.1f}, median {np.median(xy):.0f}, p99 {np.percentile(xy, 99):.0f}, max {xy.max()}")
