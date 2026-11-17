import numpy as np, pandas as pd
D = pd.read_pickle("xau_m1.pkl"); T = D.index; C = D.c.values; SP = D.spread.values; N = len(T)
G = pd.read_pickle("flip133.pkl")
MG = 4000 / 3000
def path(mods):
    g = G[G["mod"].isin(mods)]
    a = T.searchsorted(g.t.values); b = T.searchsorted(g.tx.values)
    cl = np.zeros(N + 1); nl = np.zeros(N + 1); ns = np.zeros(N + 1); el = np.zeros(N + 1); es = np.zeros(N + 1)
    np.add.at(cl, b, g.net.values)
    L = g.d.values == 1
    np.add.at(nl, a[L], 1); np.add.at(nl, b[L], -1); np.add.at(el, a[L], g.e.values[L]); np.add.at(el, b[L], -g.e.values[L])
    np.add.at(ns, a[~L], 1); np.add.at(ns, b[~L], -1); np.add.at(es, a[~L], g.e.values[~L]); np.add.at(es, b[~L], -g.e.values[~L])
    c = lambda v: np.cumsum(v[:N])
    n_open = c(nl) + c(ns)
    P = c(cl) + c(nl) * C - c(el) + c(es) - c(ns) * (C + SP)
    return P, n_open
def survive(mods, cap=100):
    P, no = path(mods)
    days = T.normalize(); starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])
    starts = [i for i in starts if T[i].dayofweek < 5]
    res = []
    for i in starts:
        eq = cap + P[i:] - P[i]
        bad = np.flatnonzero(eq <= 0.4 * MG * no[i:])
        if len(bad): res.append(((T[i + bad[0]] - T[i]).days + (T[i + bad[0]] - T[i]).seconds / 86400, True))
        else: res.append(((T[-1] - T[i]).days, False))
    r = pd.DataFrame(res, columns=["days", "blown"]); r["start"] = [T[i] for i in starts]
    return r
for lab, mods in (("FLIP 4 lanes (live v2.48)", ["FLIP-A", "FLIP-B", "FLIP-C", "FLIP-D"]), ("FLIP lane A only", ["FLIP-A"]), ("FLIP A+B", ["FLIP-A", "FLIP-B"])):
    for cap in (100, 200, 300):
        r = survive(mods, cap); b = r[r.blown]
        fast = b.days.quantile([0.1, 0.25, 0.5]).round(1).tolist() if len(b) else []
        print(f"{lab:26s} ${cap}: starts {len(r)}, stopped out {len(b)} ({100*len(b)/len(r):.0f}%), days to stop-out min/10%/25%/median {b.days.min() if len(b) else '-'} / {fast}, "
              f"blown within 7 days {100*(r.blown & (r.days<=7)).mean():.0f}%, within 30 {100*(r.blown & (r.days<=30)).mean():.0f}%")
        if cap == 100 and lab.startswith("FLIP 4"):
            r.to_csv("surv134_4lanes.csv", index=False)
