# Round 136: the FLIP lanes as ONE basket, closed on the basket's own day P&L (realised + floating, marked every minute).
# Rules per server day: target T (close all at +T, stop for the day), loss cap S (close all at -S, stop), trail (once the
# basket reached +A, close if it gives back to max(lock L, peak - R)). No lot changes. Exits at the M1 close mark (optimistic by up to 1 min).
import numpy as np, pandas as pd, sys
exec(open("surv134.py").read().split("def survive")[0])
days = T.normalize(); starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]]); ends = np.r_[starts[1:], N]
CUT = pd.Timestamp("2026-08-16")
def run(mods, Tg=None, S=None, A=None, L=None, R=None):
    P, no = path(mods); out = []
    for i, j in zip(starts, ends):
        if T[i].dayofweek >= 5: continue
        p = P[i:j] - (P[i - 1] if i else 0.0); res = p[-1]; pk = -1e9; arm = False
        for k in range(len(p)):
            v = p[k]; pk = max(pk, v)
            if Tg is not None and v >= Tg: res = v; break
            if S is not None and v <= -S: res = v; break
            if A is not None:
                if pk >= A: arm = True
                if arm and v <= max(L, pk - R): res = v; break
        out.append((T[i], res))
    return pd.Series(dict(out))
def rep(lab, d):
    for w, x in (("last3", d[d.index >= CUT]), ("prev3", d[(d.index < CUT) & (d.index >= CUT - pd.Timedelta(days=92))])):
        eq = x.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min(); m = x.groupby(x.index.to_period("M")).sum()
        g = x[x > 0].sum(); l = -x[x < 0].sum()
        print(f"{lab:44s} {w} days {len(x)} +{100*(x>0).mean():.0f}% PFd {g/max(l,1e-9):.2f} net {x.sum():+.0f} worst {x.min():+.0f} DD {dd:+.0f} months+ {(m>0).sum()}/{len(m)}", flush=True)
sets = {"4 lanes": ["FLIP-A", "FLIP-B", "FLIP-C", "FLIP-D"], "A": ["FLIP-A"], "A+B": ["FLIP-A", "FLIP-B"]}
for sn, mods in sets.items():
    rep(f"{sn} plain", run(mods))
    for Tg in (10, 15, 25, 40, 60): rep(f"{sn} target {Tg}", run(mods, Tg=Tg))
    for S in (10, 20, 30, 50): rep(f"{sn} losscap {S}", run(mods, S=S))
    for Tg, S in ((25, 20), (40, 30), (60, 30), (25, 10)): rep(f"{sn} target {Tg} cap {S}", run(mods, Tg=Tg, S=S))
    for A, L, R in ((10, 2, 10), (15, 5, 10), (20, 5, 15), (30, 10, 20), (10, 0, 5), (50, 20, 25)): rep(f"{sn} trail arm {A} lock {L} give {R}", run(mods, A=A, L=L, R=R))
    for A, L, R, S in ((15, 5, 10, 30), (20, 5, 15, 30), (30, 10, 20, 40)): rep(f"{sn} trail {A}/{L}/{R} cap {S}", run(mods, A=A, L=L, R=R, S=S))
