"""Deriv XAUUSD lows around the London breakout TP on 30 Oct 2026 (TP 3927.40)."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
out = []
for g in (300, 900):
    d = S.fetch_deriv("XAUUSD", need=700, max_pages=2, granularity=g)
    d.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in d.index])
    x = d[(d.index >= "2026-10-30 14:30") & (d.index < "2026-10-30 17:00")]
    out.append(f"granularity {g}: lowest low {x.low.min():.2f} at {x.low.idxmin()}")
    out += [f"  {t:%H:%M} o {r.open:.2f} h {r.high:.2f} l {r.low:.2f} c {r.close:.2f}" for t, r in x.iterrows() if r.low < 3932]
os.makedirs("status", exist_ok=True); open("status/research.txt", "w").write("\n".join(out) + "\n"); print("\n".join(out))
