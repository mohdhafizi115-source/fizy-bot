# Round 162b: the video rule tuned for WIN RATE (owner: "aku bukan nak tengok pf, tapi aku nak win rate").
# Same engine as trp162; adds the cent-account spread (XAUUSD.c ~ $0.56 vs .m $0.26: +$0.30 widened around the mid).
exec(open("trp162.py").read().split("print(f\"ticks")[0])
add = 30  # cents of price
bc = np.ascontiguousarray((b - add // 2).astype(np.int32)); ac = np.ascontiguousarray((a + add - add // 2).astype(np.int32))
def st2(te, p, lo, hi):
    m = (te >= lo) & (te < hi); v = p[m]
    dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum()
    return f"{len(v)/max(len(dp),1):5.0f} {100*(v>0).mean():4.0f}% {v[v>0].mean() if (v>0).any() else 0:5.2f} {v[v<=0].mean() if (v<=0).any() else 0:6.2f} {v.sum():+7.0f} {dp.min():+5.0f} {(dp<0).mean()*100:4.0f}%"
print(f"last 3 months from {a3:%Y-%m-%d}; 0.01 lot; cols: trades/day win avgWin avgLoss net$ worstDay losingDays")
print(f"{'variant':30s} | {'XAUUSD.m spread $0.26':^44s} | {'cent XAUUSD.c spread ~$0.56':^44s}")
res = []
for X in (5, 10, 20, 99):
    for A in (0.5, 1, 2, 3, 5):
        for T in (0.3, 0.5, 1, 2):
            if T >= A + 0.01 and A < 1: continue
            G = min(0.5, T * 0.4)
            te, p = run(A=A, T=T, G=G, X=X); tc, pc = run(b=bc, a=ac, A=A, T=T, G=G, X=X)
            m = te >= a3; mc = tc >= a3
            res.append((100*(p[m]>0).mean(), f"X{X} act+{A} trail{T} gap{G:.2f}", te, p, tc, pc))
res.sort(key=lambda r: -r[0])
for w, lab, te, p, tc, pc in res:
    print(f"{lab:30s} | {st2(te,p,a3,end+pd.Timedelta(days=1))} | {st2(tc,pc,a3,end+pd.Timedelta(days=1))}", flush=True)
