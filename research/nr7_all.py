"""NR7 breakout per instrument (all 28 FX pairs, gold, BTC), hold 1 day and hold 3 days: PF, R, halves, last 3 years."""
import os, sys
import numpy as np, pandas as pd
src = open(os.path.join(os.path.dirname(__file__), "nr7.py")).read().split("for n in (\"XAUUSD\"")[0]
ns = {"__file__": os.path.join(os.path.dirname(__file__), "nr7.py")}; exec(src, ns)
say, yahoo, nr_trades, ALL = ns["say"], ns["yahoo"], ns["nr_trades"], ns["ALL"]
pfh = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
rows = []
for n in ALL:
    try:
        d = yahoo(n, "1d")
    except Exception as e:
        say(f"{n}: data error {e}"); continue
    for hold in (1, 3):
        r = nr_trades(d, n, hold=hold)
        if not r:
            continue
        s = pd.Series([R for _, R in r], index=[t for t, _ in r])
        mid = s.index[len(s) // 2]
        l3 = s[s.index >= pd.Timestamp("2023-11-01", tz="UTC")]
        rows.append(dict(inst=n, hold=hold, n=len(s), pf=pfh(s), R=s.sum(), h1=pfh(s[s.index < mid]), h2=pfh(s[s.index >= mid]),
                         l3=l3.sum(), l3pf=pfh(l3), first=s.index[0].year))
df = pd.DataFrame(rows)
for hold in (1, 3):
    g = df[df.hold == hold].sort_values("pf", ascending=False)
    ok = g[(g.h1 > 1) & (g.h2 > 1) & (g.l3 > 0)]
    say(f"\nNR7 hold {hold} day(s): {len(g)} instruments, PF > 1 in {np.mean(g.pf > 1) * 100:.0f}%, both halves > 1 and last 3 years > 0 in {len(ok)}: {', '.join(ok.inst)}")
    for r in g.itertuples():
        say(f"  {r.inst:7s} from {r.first} {r.n:4d}t PF {r.pf:.2f} {r.R:+6.1f}R halves {r.h1:.2f}/{r.h2:.2f} last 3y {r.l3:+5.1f}R PF {r.l3pf:.2f}")
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("NR7 breakout per instrument\n" + "\n".join(ns["out"]) + "\n")
