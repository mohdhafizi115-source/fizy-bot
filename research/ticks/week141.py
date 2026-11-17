# Round 141: the round 140 sets with the owner's WEEKLY RESET: every Monday 00:00 server the account is $100 again
# (profit withdrawn), run to Sunday; stop-out = equity <= 40% of margin. Gold trades marked every minute.
import numpy as np, pandas as pd
src = open("port140.py").read().split("hi = end")[0]; exec(src)
hi = end + pd.Timedelta(minutes=1)
SETS = {"cap60 (5 modules)": ["BTC-STO", "GAU", "NEWS", "BTC-SMC", "SMC-gold"],
        "cap80 (6 modules, offered)": ["BTC-STO", "GAU", "NEWS", "BTC-SMC", "SMC-gold", "RCS-gold"],
        "cap95 (with KUMO)": ["BTC-STO", "GAU", "NEWS", "KUMO", "BTC-SMC", "RCS-gold"],
        "live FLIP 4 lanes, for comparison": ["FLIP-A", "FLIP-B", "FLIP-C", "FLIP-D"],
        "FLIP lane A alone": ["FLIP-A"]}
mons = pd.date_range(pd.Timestamp("2026-05-04"), end, freq="W-MON")
for lab, mods in SETS.items():
    rows = []
    for m0 in mons:
        m1 = min(m0 + pd.Timedelta(days=7), hi); r = curve(mods, m0, m1)
        rows.append((m0, r["net"], r["minEq"], r["stop"], r["n"]))
    R = pd.DataFrame(rows, columns=["week", "net", "minEq", "stop", "n"])
    so = (R.stop != "-").sum()
    print(f"\n{lab}: {len(R)} weeks, stopped out {so}, weeks in profit {(R.net > 0).sum()}, withdrawn total {R.net.clip(lower=0).sum():+.0f}, "
          f"losing weeks {(R.net < 0).sum()} (refill {-R.net.clip(upper=0).sum():.0f}), avg trades/week {R.n.mean():.0f}, lowest equity in any week ${R.minEq.min():.0f}")
    print("   week net:", " ".join(f"{w:%d%b}:{v:+.0f}" for w, v in zip(R.week, R.net)))
    print("   lowest equity each week:", " ".join(f"{v:.0f}" for v in R.minEq))
