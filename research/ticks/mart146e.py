import pandas as pd, numpy as np
src=open("/home/claude/fizy-bot/research/ticks/mart146.py").read()
src=src[:src.index('print(f"FLIP v2.47')]
src=src.replace("def sim(S, Tgt, sched, Lmax, overnight, lo, hi):\n    bal = 100.0","def sim(S, Tgt, sched, Lmax, overnight, lo, hi, B0=1000.0, DT=1e9, ENT='stop', K=3.0):\n    bal = B0; global WF; WF=[]")
src=src.replace("bal = 100.0; refill += 100;","bal = B0; refill += B0;")
src=src.replace("if not pos and pend is None and d != 0 and 90 <= hm < 1380:","if not pos and pend is None and d != 0 and 90 <= hm < 1380 and days.get(day, 0) < DT:")
old_p="            pend = (C[i - 1] + sp + 3) if d == 1 else (C[i - 1] - 3)          # buy stop (ask) / sell stop (bid)"
assert old_p in src
src=src.replace(old_p,"            pend = ((C[i-1]+sp+K) if d == 1 else (C[i-1]-K)) if ENT=='stop' else ((((C[i-1]+sp+3),(C[i-1]+sp-1)) if d==1 else ((C[i-1]-3),(C[i-1]+1))) if ENT=='oco' else ((C[i-1]+sp-K) if d == 1 else (C[i-1]+K)))")
old_f="""            if d == 1 and H[i] + sp >= pend: pos = [(1, max(pend, O[i] + sp))]; pend = None
            elif d == -1 and L[i] <= pend: pos = [(1, min(pend, O[i]))]; pend = None"""
assert old_f in src
src=src.replace(old_f,"""            if ENT=='oco':
                ps, pl = pend
                if d == 1:
                    hs = H[i] + sp >= ps; hl = L[i] + sp <= pl
                    if hs and hl: pos = [(1, min(pl, O[i]+sp) if O[i] < C[i] else max(ps, O[i]+sp))]; pend = None
                    elif hs: pos = [(1, max(ps, O[i] + sp))]; pend = None
                    elif hl: pos = [(1, min(pl, O[i] + sp))]; pend = None
                else:
                    hs = L[i] <= ps; hl = H[i] >= pl
                    if hs and hl: pos = [(1, max(pl, O[i]) if O[i] > C[i] else min(ps, O[i]))]; pend = None
                    elif hs: pos = [(1, min(ps, O[i]))]; pend = None
                    elif hl: pos = [(1, max(pl, O[i]))]; pend = None
            elif ENT=='stop':
                if d == 1 and H[i] + sp >= pend: pos = [(1, max(pend, O[i] + sp))]; pend = None
                elif d == -1 and L[i] <= pend: pos = [(1, min(pend, O[i]))]; pend = None
            else:
                if d == 1 and L[i] + sp <= pend: pos = [(1, min(pend, O[i] + sp))]; pend = None
                elif d == -1 and H[i] >= pend: pos = [(1, max(pend, O[i]))]; pend = None""")
src=src.replace("            if bal + fl <= 0.4 * nl * MRG:","            WF.append(fl)\n            if bal + fl <= 0.4 * nl * MRG:")
exec(src)
starts = [d for d in pd.date_range(A6.normalize(), END.normalize() - pd.Timedelta(days=10), freq="B")][::2]
for Lm in (10,):
  for ent,K in (("oco",0),):
    a=sim(3,3,"lin",Lm,True,A3,END+pd.Timedelta(minutes=1),ENT=ent,K=K); wa=min(WF) if WF else 0
    b=sim(3,3,"lin",Lm,True,A6,A3,ENT=ent,K=K); wb=min(WF) if WF else 0
    nb=0
    for s in starts:
        r=sim(3,3,"lin",Lm,True,s,END+pd.Timedelta(minutes=1),ENT=ent,K=K)
        if r[6] is not None: nb+=1
    print(f"max{Lm} {ent} ${K} | last {a[0]} baskets net {a[2]:+.0f} blown {a[3]} 1st {a[6]} worst float {wa:.0f} | prev {b[0]} net {b[2]:+.0f} blown {b[3]} float {wb:.0f} | $1000 starts blown {nb}/{len(starts)}", flush=True)
