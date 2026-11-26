# Round 172: the LIVE v2.69 FizyTLS rule on real ticks (owner: "buat martiangle. layer unlimited").
# Signal = round 170b TL + nearest S/R on M15 (swing 10, wait 120). Basket: market 0.01 at the next M15 open,
# every 1.5 ATR(M15) of the signal bar against the last entry adds k x 0.01 (unlimited, no SL), basket TP = whole
# basket +3 x (1.5 ATR x 0.01 lot money); one basket at a time. M1 bars from ticks (bid / ask OHLC): adds fill at the
# level, the TP is checked after the adds of the same minute (conservative), floating marked at the minute's worst.
# $1000 starts every 2nd weekday: blown if equity <= 40% of margin (1:3000) at any minute.
import os, sys, numpy as np, pandas as pd
src = open("tl170.py").read().split('print("mode   n  W')[0]
os.environ["TF"] = "900"; os.environ["CAP"] = "16"
exec(src)
N_ = int(os.environ.get("N", "10")); STEPK = float(os.environ.get("STEPK", "1.5")); TPR = float(os.environ.get("TPR", "3"))
sig = sig170(N_, "tlsr", 120, "near", False)
s, atr = B["s"], B["atr"]; NB = len(s)
bask = []; busy = -1
for (j, d) in sig:
    if j + 1 >= NB: continue
    m = s[j + 1]
    if m <= busy: continue
    step = STEPK * atr[j]; tgt = TPR * step                      # $ at 0.01 lot = $1 per $1
    e = M_ao[m] if d == 1 else M_bo[m]
    ents = [e]; lots = [1]; worst = 0.0; k = m; m0 = m; closed = None
    while k < NM:
        # adds
        while True:
            nxt = ents[-1] - d * step
            hit = (M_al[k] <= nxt) if d == 1 else (M_bh[k] >= nxt)
            if not hit: break
            ents.append(nxt); lots.append(len(lots) + 1)
        L = np.array(lots) * 1.0; E = np.array(ents)
        # worst float this minute
        px_w = M_bl[k] if d == 1 else M_ah[k]
        fl = float((d * (px_w - E) * L).sum()); worst = min(worst, fl)
        tp = (tgt + (L * E).sum()) / L.sum() if d == 1 else ((L * E).sum() - tgt) / L.sum()
        hit = (M_bh[k] >= tp) if d == 1 else (M_al[k] <= tp)
        if hit and k > m0: closed = (k, tgt); break
        if k >= m0 and False: pass
        k += 1
    if closed is None: break
    bask.append(dict(t0=M_t[m0], t1=M_t[closed[0]], d=d, n=len(lots), lot=sum(lots) * 0.01, p=closed[1], worst=worst, price=E.mean()))
    busy = closed[0]
D = pd.DataFrame(bask)
print(f"swing {N_} step {STEPK} ATR TP {TPR}R: {len(D)} baskets, max layers {D.n.max()}, max lot {D.lot.max():.2f}, worst floating ${D.worst.min():.0f}")
for lab, lo, hi in (("last 3 m", A3, E_ if (E_ := M_t[-1] + 1) else 0), ("previous", A6, A3)):
    q = D[(D.t0 >= lo) & (D.t0 < hi)]
    print(f"  {lab}: {len(q)} baskets, win 100%, +${q.p.sum():.0f}, worst floating ${q.worst.min():.0f}, layers p90 {q.n.quantile(.9):.0f} max {q.n.max()}")
print("  layers histogram:", D.n.value_counts().sort_index().to_dict())
print("  10 worst baskets:"); print(D.nsmallest(10, "worst")[["t0", "d", "n", "lot", "worst"]].assign(t0=lambda x: pd.to_datetime(x.t0, unit="ms")).to_string(index=False))
# starts
days = pd.to_datetime(pd.Series(M_t[::1440*2]), unit="ms").dt.normalize().unique()
starts = [d for d in pd.date_range(pd.Timestamp(M_t[0], unit="ms").normalize(), pd.Timestamp(A3, unit="ms"), freq="B")][::2]
for BAL in (1000.0, 5000.0, 10000.0):
  blown = 0
  for st in starts:
      bal = BAL
      for r in D[D.t0 >= st.value // 10**6].itertuples():
          marg = r.lot * r.price / 3000 * 100   # $ margin per lot = price*100 /3000
          if bal + r.worst <= 0.4 * marg: blown += 1; break
          bal += r.p
  print(f"  {BAL:.0f} starts blown: {blown} of {len(starts)}")
