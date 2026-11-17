# Round 143c: the round 143b rule (H4 momentum, CB1 then CSAK) pooled over all 30 symbols of the round 133 export, for a sample size
import os, sys
sys.argv = ["x", sys.argv[1], "XAUUSD"]
src = open("bbma143.py").read().split("for sym in SYMS:")[0]; exec(src)
import numpy as np, pandas as pd
CBS = os.environ.get("CBS", "soft,any").split(",")
TPS = os.environ.get("TPS", "2,none").split(",")
syms = [l.split(",")[0] for l in open(os.path.join(DATA, "meta.txt")) if l.strip() and not l.startswith("#")]
syms = [s for s in syms if s in meta]
cfgs = [(cb, W, h4, en, tp) for cb in CBS for W in (8, 16) for h4 in ("onm6", "onm12", "onmt12", "off")
        for en in ("ztop", "mkt") for tp in TPS]
res = {c: [] for c in cfgs}; rnd = {c: [] for c in cfgs}
END = None
for s in syms:
    try: d, m, usd = build(s)
    except Exception as e: print("skip", s, e); continue
    if END is None: END = m.index[-1]
    for cb in CBS:
        for W in (8, 16):
            sig = signals(m, cb, W)
            for c in cfgs:
                if c[0] != cb or c[1] != W: continue
                res[c] += [(t, p, s) for t, p, _ in simulate(d, m, usd, sig, c[2], c[3], 8, "swing", c[4])]
                rnd[c] += [(t, p, s) for t, p, _ in simulate(d, m, usd, sig, c[2], c[3], 8, "swing", c[4], rng=np.random.default_rng(1))]
A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
def pf(r, lo, hi):
    p = np.array([x[1] for x in r if lo <= x[0] < hi]); g = [x for x in r if lo <= x[0] < hi]
    if len(p) == 0: return "  0"
    gold = sum(x[1] for x in g if x[2] == "XAUUSD")
    return f"{len(p):3d} PF {min(p[p>0].sum()/max(-p[p<0].sum(),1e-9),99):5.2f} net {p.sum():+5.0f} (gold {gold:+4.0f})"
print(f"{len(syms)} symbols, last 3 months {A3:%d %b}-{END:%d %b} / previous; 0.01 lot each, $ pooled")
for c in cfgs:
    print(f"CB1 {c[0]:10s} W{c[1]:2d} H4 {c[2]:6s} {c[3]:4s} TP {c[4]:5s} | {pf(res[c], A3, END + pd.Timedelta(days=1))} | {pf(res[c], A6, A3)} | random dir {pf(rnd[c], A3, END + pd.Timedelta(days=1))} / {pf(rnd[c], A6, A3)}")
