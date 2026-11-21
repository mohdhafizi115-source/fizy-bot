# Round 159: (A) weekday / hour direction bias on broker gold; (B) MART live v2.57 (two-sided $3 stops, unlimited, step $3, TP +$3,
# no SL, 24 h, $1000) with a PAUSE gate: no new basket (pending deleted while flat) on a trend day, a volatility burst or around USD news,
# against random gates that pause the same share of time.
# Round 158b: round 158 on EVERY timeframe (M1-D1). Side = net move of the last N closed bars of TF, re-checked on every new bar while flat.
# Round 158: MART with the side from the LAST CLOSED H1 candle(s): net move of the last N closed H1 bars (follow / fade), re-checked every new H1 bar while flat.
# Based on round 156: MART (live v2.57 rest: unlimited layers, step $3, TP +$3, no SL, 24 h weekdays, $1000, no target) with a DAILY BIAS:
# each server day ONE side only, the first entry a stop $3 on that side (or market), re-armed after every TP all day.
# Biases: against yesterday's D1 colour (round 152), the same only when yesterday's body <= $60 (else no new baskets / plain),
# against 2 same-colour days (else plain), always sell / buy, a RANDOM side per day (control, 20 seeds), and live two-sided.
import sys, numpy as np, pandas as pd
D = pd.read_pickle("xau_m1.pkl")
O, H, L, C, SP = (D[k].values for k in ("o", "h", "l", "c", "spread")); T = D.index
HM = (T.hour * 60 + T.minute).values; DAYK = T.normalize()
dd = D.c.groupby(DAYK).agg(["first", "last"]); dd["o"] = D.o.groupby(DAYK).first()
body = (dd["last"] - dd["o"]).abs().shift(1)
prev2 = np.sign(dd["last"] - dd["o"]).shift(2)
colour = np.sign(dd["last"] - dd["o"]); prevcol = colour.shift(1).reindex(DAYK).values
END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
MRG = 4000 / 3000; SWAP = {1: -0.71, -1: -0.84}

BIAS = {}
def sim(mode, K, lo, hi, S=3.0, Tgt=3.0, Lmax=99, B0=1000.0, bias=None, hside=None, gate=None):
    bal = B0; blown = 0; baskets = []; days = {}; wf = 0.0
    pos = []; d = 0; pend = None; first_blow = None; lastday = None; dside = 0
    idx = np.flatnonzero((T >= lo) & (T < hi))
    for i in idx:
        day = DAYK[i]; sp = SP[i]
        if day != lastday:
            if pos and lastday is not None: bal += sum(l for l, e in pos) * SWAP[d]
            lastday = day
            dside = int(prevcol[i]) if not np.isnan(prevcol[i]) else 0
            if mode in ("live", "bias", "bmkt") and not pos: pend = None
            if bias is not None: dside = int(bias.get(day, 0))
        if gate is not None and not pos and not gate[i]:
            pend = None; continue
        if hside is not None and not pos:
            hs_ = int(hside[i])
            if pend is None or pend[1] != hs_:
                ask = C[i - 1] + sp; bid = C[i - 1]
                pend = (((ask + K, -1e9) if hs_ == 1 else (1e9, bid - K)), hs_) if hs_ != 0 else None
                if pend is not None and mode == 'hmkt': d = hs_; pos = [(1, ask if d == 1 else bid)]; pend = None
            if pend is None and not pos: continue
        if not pos and pend is None:
            ask = C[i - 1] + sp; bid = C[i - 1]
            if mode == "live":
                if dside != 0:
                    pend = ((ask + 3, ask - 1) if dside == 1 else (bid - 3, bid + 1), dside)
            elif mode == "bstop": pend = ((ask + K, bid - K), 0)
            elif mode == "bias":
                if dside == 1: pend = ((ask + K, -1e9), 0)
                elif dside == -1: pend = ((1e9, bid - K), 0)
            elif mode == "bmkt":
                if dside != 0: d = dside; pos = [(1, ask if d == 1 else bid)]
            else: pend = ((ask - K, bid + K), 0)
        if not pos and pend is not None:
            (p1, p2), side = pend; bull = C[i] >= O[i]; fill = None
            if mode == "live":
                if side == 1:
                    hs = H[i] + sp >= p1; hl = L[i] + sp <= p2
                    if hs and hl: fill = (1, min(p2, O[i] + sp)) if bull else (1, max(p1, O[i] + sp))
                    elif hs: fill = (1, max(p1, O[i] + sp))
                    elif hl: fill = (1, min(p2, O[i] + sp))
                else:
                    hs = L[i] <= p1; hl = H[i] >= p2
                    if hs and hl: fill = (-1, max(p2, O[i])) if not bull else (-1, min(p1, O[i]))
                    elif hs: fill = (-1, min(p1, O[i]))
                    elif hl: fill = (-1, max(p2, O[i]))
            elif mode in ("bstop", "bias", "hbias"):
                hb = H[i] + sp >= p1; hsl = L[i] <= p2
                if hb and hsl: fill = (-1, min(p2, O[i])) if bull else (1, max(p1, O[i] + sp))
                elif hb: fill = (1, max(p1, O[i] + sp))
                elif hsl: fill = (-1, min(p2, O[i]))
            else:
                hb = L[i] + sp <= p1; hsl = H[i] >= p2
                if hb and hsl: fill = (1, min(p1, O[i] + sp)) if bull else (-1, max(p2, O[i]))
                elif hb: fill = (1, min(p1, O[i] + sp))
                elif hsl: fill = (-1, max(p2, O[i]))
            if fill: d = fill[0]; pos = [(1, fill[1])]; pend = None
        if pos:
            while len(pos) < Lmax:
                le = pos[-1][1]; lvl = le - S if d == 1 else le + S
                hit = (L[i] + sp <= lvl) if d == 1 else (H[i] + sp >= lvl)
                if not hit: break
                pos.append((len(pos) + 1, lvl))
            nl = sum(l for l, e in pos)
            adv = L[i] if d == 1 else H[i] + sp
            fl = sum(l * (adv - e) * d for l, e in pos); wf = min(wf, fl)
            if bal + fl <= 0.4 * nl * MRG:
                loss = -bal; days[day] = days.get(day, 0) + loss; baskets.append(loss); blown += 1
                if first_blow is None: first_blow = day
                bal = B0; pos = []; pend = None; continue
            tp = (Tgt + sum(l * e for l, e in pos)) / nl if d == 1 else (sum(l * e for l, e in pos) - Tgt) / nl
            fav = H[i] if d == 1 else L[i] + sp
            if (d == 1 and fav >= tp) or (d == -1 and fav <= tp):
                pnl = sum(l * (tp - e) * d for l, e in pos); bal += pnl
                days[day] = days.get(day, 0) + pnl; baskets.append(pnl); pos = []
    return len(baskets), sum(baskets), blown, first_blow, wf




import os
from multiprocessing import Pool
here = os.path.dirname(os.path.abspath(__file__))
starts = [d for d in pd.date_range(A6.normalize(), END.normalize() - pd.Timedelta(days=10), freq="B")][::2]
# ---------- A) direction by weekday / hour ----------
def partA():
    print("A) broker gold, share of UP by weekday (day 01:30 -> 23:30 server) and by H1 hour; last 3 months / previous 3")
    hm = HM
    o130 = D.o[(hm >= 90)].groupby(DAYK[hm >= 90]).first(); c2330 = D.c[(hm < 1410)].groupby(DAYK[hm < 1410]).last()
    r = (c2330 - o130).dropna()
    for lo, hi, nm in ((A3, END + pd.Timedelta(minutes=1), "last"), (A6, A3, "prev")):
        k = r[(r.index >= lo) & (r.index < hi)]
        print(f"  {nm}: " + "  ".join(f"{['Mon','Tue','Wed','Thu','Fri'][w]} {(k[k.index.weekday == w] > 0).mean():.0%} ({(k.index.weekday == w).sum()})" for w in range(5)) + f"  | all {(k > 0).mean():.0%}")
    HK = T.floor("h"); h = D.groupby(HK).agg(o=("o", "first"), c=("c", "last")); up = (h.c > h.o)
    rows = []
    for hr in range(24):
        a = up[(up.index.hour == hr) & (up.index >= A3)]; b = up[(up.index.hour == hr) & (up.index >= A6) & (up.index < A3)]
        rows.append((hr, a.mean(), b.mean(), len(a)))
    print("  hour: up% last / prev (n)")
    for hr, a, b, n in rows:
        flag = " <- same side >=58% both" if (a >= .58 and b >= .58) or (a <= .42 and b <= .42) else ""
        print(f"   {hr:02d}h {a:.0%} / {b:.0%} ({n}){flag}")
# ---------- B) gates ----------
hm = HM
dayopen = D.o.where(hm >= 90).groupby(DAYK).transform("first").values
d1 = D.groupby(DAYK).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
tr = pd.concat([d1.h - d1.l, (d1.h - d1.c.shift()).abs(), (d1.l - d1.c.shift()).abs()], axis=1).max(axis=1)
atrd = tr.rolling(14).mean().shift(1).reindex(DAYK).values
rng = pd.Series(H - L, index=T)
r60 = rng.rolling(60).mean().shift(1).values; r1440 = rng.rolling(1440).mean().shift(1).values
cal = pd.read_csv(os.path.join(here, "../../data/calendar.csv")) if os.path.exists(os.path.join(here, "../../data/calendar.csv")) else pd.read_csv("../data/calendar.csv")
cal = cal[(cal.currency == "USD") & (cal.importance == 3)]
ct = pd.to_datetime(cal.time, unit="s").dt.tz_localize("Etc/GMT-2").dt.tz_convert("Europe/Athens").dt.tz_localize(None)
news = np.zeros(len(T), bool); tv = T.values
for t in ct.drop_duplicates():
    a = np.searchsorted(tv, np.datetime64(t - pd.Timedelta(minutes=30))); b = np.searchsorted(tv, np.datetime64(t + pd.Timedelta(minutes=60)))
    news[a:b] = True
G = {}
for k in (0.5, 0.75, 1.0):
    G[f"trend day: pause once |price - 01:30 open| > {k} ATR(D1)"] = ~(np.abs(C - np.nan_to_num(dayopen, nan=C)) > k * np.nan_to_num(atrd, nan=1e9))
for k in (1.5, 2.0, 3.0):
    G[f"vol burst: pause while 60-min range > {k}x the 24 h mean"] = ~(np.nan_to_num(r60) > k * np.nan_to_num(r1440, nan=1e9))
G["news: pause USD high-impact -30 / +60 min"] = ~news
def randgate(frac, seed):
    blk = T.floor("h"); u = pd.Index(blk).unique(); r = np.random.default_rng(seed).random(len(u)) >= frac
    return pd.Series(r, index=u).reindex(blk).values
def job(a):
    nm, g = a
    nb = sum(1 for st in starts if sim('bstop', 3, st, END + pd.Timedelta(minutes=1), gate=g)[3] is not None)
    x = sim('bstop', 3, A3, END + pd.Timedelta(minutes=1), gate=g); y = sim('bstop', 3, A6, A3, gate=g)
    paused = 1 - np.mean(g[T >= A6]) if g is not None else 0
    return f"  {nm:62s} | paused {paused:5.1%} | baskets {x[0]} / {y[0]} | starts blown {nb}/{len(starts)}"
if __name__ == "__main__":
    partA()
    print("\nB) MART live (two-sided $3 stops, unlimited, TP +$3, no SL, 24 h, $1000): $1000 starts blown of", len(starts))
    J = [("LIVE (no pause)", None)] + list(G.items())
    for fr in (0.1, 0.25, 0.4):
        for sd in range(4): J.append((f"RANDOM 1-hour pauses {fr:.0%} seed {sd}", randgate(fr, sd)))
    with Pool(2) as p:
        for r in p.imap(job, J): print(r, flush=True)
