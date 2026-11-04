"""Round 31 (4 Nov 2026): gold M1 rules judged on TWO WEEKS (owner: "buat 2 minggu"; round 31 used one week). Was: "aku nak yang profit
seminggu"). Same 53 M1 variants + 10 random rules as round 22 (m1month22.build). Shows the last week's winners, then
tests the owner's method out of sample: every week trade the rule(s) that made the most the week before."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import m1month22 as M

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt")); m = meta["XAUUSD"]; usd = m["tick_value"] / m["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "XAUUSD.csv"), m["point"])
dates = d.index.normalize().values; hm = d.index.hour.values * 60 + d.index.minute.values
flat = (hm >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
V = M.build(d)
arr = [d[x].values for x in ("o", "h", "l", "c", "s")]
rows = []
for nm, S in V.items():
    for (k, dr, pnl, sp, risk, why) in SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat):
        rows.append((nm, k, (pnl - sp) * usd))
T = pd.DataFrame(rows, columns=["rule", "k", "net"]); T["t"] = d.index[T.k.values]; T["wk"] = (T.t.dt.to_period("W-SAT").apply(lambda p: p.ordinal) // 2) * 2
_w2s = {}
rules = list(V); real = [r for r in rules if not r.startswith("RAND")]
wk = T.groupby(["rule", "wk"]).net.sum().unstack(fill_value=0.0)
cnt = T.groupby(["rule", "wk"]).net.count().unstack(fill_value=0)
weeks = list(wk.columns)
last = weeks[-1]
label = lambda w: f"{pd.Period(ordinal=int(w), freq='W-SAT').start_time:%Y-%m-%d} + 2 weeks"
t14 = T.t.max() - pd.Timedelta(days=14)
L = T[T.t >= t14].groupby("rule").net.agg(["count", "sum"]).sort_values("sum", ascending=False)
full = T.groupby("rule").net.sum()
print(f"LAST 14 DAYS ({t14:%Y-%m-%d} - {T.t.max():%Y-%m-%d}): top 10 of {len(rules)} rules (RAND_x = random entries), $ per 0.01 lot")
for r, x in L.head(10).iterrows():
    pos = (wk.loc[r] > 0).mean() * 100
    print(f"  {r:28s} {int(x['count']):4d} trades {x['sum']:+8.2f} $ | 2020-2026 {full[r]:+8.0f} $, 2-week periods positive {pos:.0f}%")
print(f"profitable in the last 14 days: {sum(L.loc[r, 'sum'] > 0 for r in real if r in L.index)} of {len(real)} real rules, "
      f"{sum(L.loc[r, 'sum'] > 0 for r in rules if r.startswith('RAND') and r in L.index)} of 10 random")
print("\nTHE '2 WEEKS' METHOD out of sample: every 2 weeks trade the rule that made the most in the 2 weeks before (>= 20 trades)")
for top_n in (1, 3):
    res = []
    for j in range(1, len(weeks)):
        p, q = weeks[j - 1], weeks[j]
        cand = [r for r in real if cnt.loc[r, p] >= 20]
        if not cand:
            continue
        best = sorted(cand, key=lambda r: wk.loc[r, p], reverse=True)[:top_n]
        res.append((q, np.mean([wk.loc[r, q] for r in best])))
    R = pd.Series(dict(res))
    print(f"  best {top_n}: {len(R)} periods, net {R.sum():+.0f} $, periods positive {(R > 0).sum()}/{len(R)} ({100 * (R > 0).mean():.0f}%), "
          f"last 6 periods (12 weeks) {R.iloc[-6:].sum():+.0f} $, by year " + " ".join(f"{y}:{R[[pd.Period(ordinal=int(x), freq="W-SAT").start_time.year == y for x in R.index]].sum():+.0f}" for y in range(2020, 2027)))
a = b = c_ = e = 0
for r in real:
    for j in range(1, len(weeks)):
        p, q = weeks[j - 1], weeks[j]
        if cnt.loc[r, p] < 20 or cnt.loc[r, q] < 20:
            continue
        if wk.loc[r, p] > 0:
            a += 1; b += wk.loc[r, q] > 0
        else:
            c_ += 1; e += wk.loc[r, q] > 0
print(f"\nafter profitable 2 weeks a rule is profitable the next 2 weeks {100 * b / max(a, 1):.0f}% of the time ({a} cases); after losing 2 weeks {100 * e / max(c_, 1):.0f}%")
