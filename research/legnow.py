"""Where is today's M1 gold leg right now? Same online zigzag as FizyLEG.mqh (0.10% on closes, from the
server day start). Prints every leg of today and the current one with its age in candles."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
B = DT.bars(d, "1min")
B = B[B.date == B.date.iloc[-1]]
C = B.c.values.astype(float); T = B.index
pct = 0.001
d_, ext, piv = 0, 0, 0
legs = []
for k in range(1, len(C)):
    c = C[k]
    if d_ == 0:
        if c >= C[piv] * (1 + pct): d_, ext = 1, k
        elif c <= C[piv] * (1 - pct): d_, ext = -1, k
        continue
    if d_ == 1:
        if c > C[ext]: ext = k
        elif c <= C[ext] * (1 - pct): legs.append((piv, ext, 1)); piv, d_, ext = ext, -1, k
    else:
        if c < C[ext]: ext = k
        elif c >= C[ext] * (1 + pct): legs.append((piv, ext, -1)); piv, d_, ext = ext, 1, k
myt = lambda t: (t + np.timedelta64(6, "h")).strftime("%H:%M")
print(f"XAUUSD M1 server day {B.date.iloc[-1]}, last closed bar {T[-1]:%H:%M} server = {myt(T[-1])} MYT, close {C[-1]:.2f}")
for a, b, s in legs:
    print(f"  {'UP  ' if s == 1 else 'DOWN'} {myt(T[a])} -> {myt(T[b])} MYT  {b - a:3d} candles  {C[a]:.2f} -> {C[b]:.2f}")
j = len(C) - 1
if d_ == 0:
    print(f"NOW: no leg confirmed yet today ({j} candles since the day start)")
else:
    print(f"NOW: {'UP' if d_ == 1 else 'DOWN'} leg from {myt(T[piv])} MYT at {C[piv]:.2f}, age {j - piv} candles, "
          f"extreme so far {C[ext]:.2f}; EA fades it at 60 candles")
