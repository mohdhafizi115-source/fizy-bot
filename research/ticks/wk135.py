import sys; sys.argv=["x"]
exec(open("flip133.py").read().split("L = {")[0])
for lab, kw in (("A", {}), ("A + skip after D1 body > $60", dict(maxbody=60)), ("A + 1 entry after big day", dict(maxbody=60, big_mode=3, big_maxn=1))):
    X = run3(**kw); s = pd.Series(X.net.values, index=X.tx)
    d = s.groupby(s.index.normalize()).sum(); w = s.groupby(s.index.to_period("W")).sum(); m = s.groupby(s.index.to_period("M")).sum()
    eq = d.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min()
    print(f"{lab:30s} trades {len(X)} win {100*(X.net>0).mean():.0f}% | days + {100*(d>0).mean():.0f}% (worst {d.min():+.0f}) | weeks + {(w>0).sum()}/{len(w)} (worst {w.min():+.0f}) | months + {(m>0).sum()}/{len(m)} (worst {m.min():+.0f}) | net {s.sum():+.0f} DD {dd:+.0f}")
    print("   months:", " ".join(f"{p}:{v:+.0f}" for p, v in m.items()))
