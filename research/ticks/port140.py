# Round 140: the MOST TRADES a $100 account can carry without a stop-out. Pool = every tested module that makes money in
# both 3-month windows (live modules from round 133, FLIP lanes with the D1-body filter, news straddles). Greedy: add the
# module with the most trades while the 6-month max drawdown (marked every minute, any start date) stays above the cap.
import numpy as np, pandas as pd
src = open("port133.py").read().split("def show")[0]
src = src.replace('G = pd.concat([pd.read_pickle("gold133.pkl"), pd.read_pickle("flip133.pkl")])', 'G = pd.concat([pd.read_pickle("gold133.pkl"), pd.read_pickle("flip133.pkl"), pd.read_pickle("lanes140.pkl")])')
src = src.replace('Z = pd.concat([pd.read_pickle("../rcs133.pkl"), pd.read_pickle("../btcsmc133.pkl")])', 'Z = pd.concat([pd.read_pickle("../rcs133.pkl"), pd.read_pickle("../btcsmc133.pkl"), pd.read_pickle("news140.pkl")])')
exec(src)
hi = end + pd.Timedelta(minutes=1)
ALLM = sorted(set(G["mod"]) | set(Z["mod"]))
def nets(m):
    g = pd.concat([G[G["mod"] == m][["tx", "net"]], Z[Z["mod"] == m][["tx", "net"]]]); g.tx = pd.to_datetime(g.tx)
    x = g[g.tx >= a3].net; y = g[(g.tx >= a6) & (g.tx < a3)].net
    pf = lambda s: s[s > 0].sum() / max(-s[s < 0].sum(), 1e-9)
    return len(g[g.tx >= a6]), x.sum(), y.sum(), pf(x), pf(y)
print("pool (6 months 18 May - 16 Nov): trades, net last 3 m / previous 3 m, PF, 6-month max DD alone")
pool = []
for m in ALLM:
    k, n3, np3, p3, pp = nets(m); r = curve([m], a6, hi)
    ok = n3 > 0 and np3 > 0 and p3 >= 1.15 and pp >= 1.15
    print(f"  {m:9s} {k:5d} trades  {n3:+6.0f} / {np3:+6.0f}  PF {p3:4.2f} / {pp:4.2f}  DD {r['dd']:+5.0f}  {'POOL' if ok else '-'}")
    if ok: pool.append(m)
lane = lambda m: m[:6] if m.startswith("FLIP-") else m
def survive(mods):
    """$100 started at 00:00 server of every weekday from 18 May; stopped out?"""
    days = pd.DatetimeIndex(sorted(set(T[(T >= a6)].normalize()))); days = days[days.dayofweek < 5]
    bl = 0
    for d0 in days[:-5]:
        r = curve(mods, d0, hi); bl += r["stop"] != "-"
    return bl, len(days) - 5
for cap in (-60, -80, -95):
    cur = []; print(f"\nGREEDY on TRADES, 6-month max DD must stay above ${cap}:")
    while True:
        best = None
        for m in pool:
            if m in cur or any(lane(m) == lane(c) for c in cur): continue
            r = curve(cur + [m], a6, hi)
            if r["dd"] >= cap and (best is None or r["n"] > best[1]["n"]): best = (m, r)
        if best is None: break
        cur.append(best[0]); r = best[1]
        print(f"  + {best[0]:9s} -> {r['n']:5d} trades ({r['n']/130:4.1f} a day), net {r['net']:+6.0f}, maxDD {r['dd']:+5.0f}, worst day {r['worst']:+5.0f}")
    r3 = curve(cur, a3, hi); r0 = curve(cur, a6, a3); bl, nd = survive(cur)
    print(f"  SET {cur}\n  last 3 m {r3['n']} trades net {r3['net']:+.0f} DD {r3['dd']:+.0f} | prev 3 m {r0['n']} trades net {r0['net']:+.0f} DD {r0['dd']:+.0f} | $100 started on each of {nd} weekdays: stopped out {bl}")
