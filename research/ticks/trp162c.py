# Round 162c: the video rule with the day's FIRST entry from an OCO pair (buy stop ask + K / sell stop bid - K at 01:30),
# owner: "first trade kau buat stop atas bawah. mana yang trigger terus guna teknik ni". Engine trp162c.c (start 3 = OCO).
import re
src = open("trp162.py").read().split('print(f"ticks')[0].replace('"./trp162.so"', '"./trp162c.so"')
src = src.replace('[("start", ctypes.c_int), ("seed", ctypes.c_int)]', '[("start", ctypes.c_int), ("seed", ctypes.c_int), ("K", ctypes.c_double)]')
src = src.replace("d = dict(A=1, T=1, G=0.5, X=5, start=0, seed=1)", "d = dict(A=1, T=1, G=0.5, X=5, start=0, seed=1, K=3)")
exec(src)
add = 30
bc = np.ascontiguousarray((b - add // 2).astype(np.int32)); ac = np.ascontiguousarray((a + add - add // 2).astype(np.int32))
def st2(te, p, lo, hi):
    m = (te >= lo) & (te < hi); v = p[m]
    if len(v) == 0: return "no trades"
    dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum()
    return f"{len(v)/max(len(dp),1):5.0f} {100*(v>0).mean():4.0f}% {v[v>0].mean():5.2f} {v[v<=0].mean():6.2f} {pf(v):5.2f} {v.sum():+7.0f} {dp.min():+5.0f} {(dp<0).mean()*100:4.0f}%"
E = end + pd.Timedelta(days=1)
print(f"last 3 months from {a3:%Y-%m-%d} | previous 3 months; 0.01 lot; cols: trades/day win avgWin avgLoss PF net$ worstDay losingDays")
for X, A, T, G in ((5, 1, 1, 0.4), (99, 1, 0.3, 0.12), (99, 2, 0.3, 0.12), (20, 1, 0.3, 0.12), (20, 2, 0.5, 0.2), (10, 2, 0.3, 0.12), (20, 5, 0.3, 0.12), (10, 5, 1, 0.4)):
    for st, K in ((0, 0), (3, 1), (3, 2), (3, 3), (3, 5)):
        lab = f"X{X} act+{A} trail{T} | " + ("market BUY" if st == 0 else f"OCO +-${K}")
        te, p = run(A=A, T=T, G=G, X=X, start=st, K=K); tc, pc = run(b=bc, a=ac, A=A, T=T, G=G, X=X, start=st, K=K)
        print(f"{lab:38s} | {st2(te,p,a3,E)} | {st2(te,p,a6,a3)} | cent {st2(tc,pc,a3,E)}", flush=True)
