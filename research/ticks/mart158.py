# Round 158: MART with the side from the LAST CLOSED H1 candle(s): net move of the last N closed H1 bars (follow / fade), re-checked every new H1 bar while flat.
# Based on round 156: MART (live v2.57 rest: unlimited layers, step $3, TP +$3, no SL, 24 h weekdays, $1000, no target) with a DAILY BIAS:
# each server day ONE side only, the first entry a stop $3 on that side (or market), re-armed after every TP all day.
# Biases: against yesterday's D1 colour (round 152), the same only when yesterday's body <= $60 (else no new baskets / plain),
# against 2 same-colour days (else plain), always sell / buy, a RANDOM side per day (control, 20 seeds), and live two-sided.
import sys, numpy as np, pandas as pd
D = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 else "xau_m1.pkl")
O, H, L, C, SP = (D[k].values for k in ("o", "h", "l", "c", "spread")); T = D.index
HM = (T.hour * 60 + T.minute).values; DAYK = T.normalize()
dd = D.c.groupby(DAYK).agg(["first", "last"]); dd["o"] = D.o.groupby(DAYK).first()
body = (dd["last"] - dd["o"]).abs().shift(1)
prev2 = np.sign(dd["last"] - dd["o"]).shift(2)
colour = np.sign(dd["last"] - dd["o"]); prevcol = colour.shift(1).reindex(DAYK).values
END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
MRG = 4000 / 3000; SWAP = {1: -0.71, -1: -0.84}

BIAS = {}
def sim(mode, K, lo, hi, S=3.0, Tgt=3.0, Lmax=99, B0=1000.0, bias=None, hside=None):
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



HK = T.floor("h")
h1 = D.groupby(HK).agg(o=("o", "first"), c=("c", "last"))
rng = np.random.default_rng(7)
starts = [d for d in pd.date_range(A6.normalize(), END.normalize() - pd.Timedelta(days=10), freq="B")][::2]
def side_from(N, sgn):
    net = np.sign(h1.c - h1.o.shift(N - 1)) * sgn          # move of the last N H1 bars, from the open of the first to the close of the last
    return net.shift(1).reindex(HK).fillna(0).values      # known only after that hour closed
def nexthit(sig):   # does the NEXT H1 bar close the same way? (the direction's own hit rate)
    s_ = pd.Series(sig, index=HK).groupby(level=0).first(); nx = np.sign(h1.c - h1.o).reindex(s_.index)
    m = s_ != 0; r = []
    for lo, hi in ((A3, END + pd.Timedelta(minutes=1)), (A6, A3)):
        k = m & (s_.index >= lo) & (s_.index < hi); r.append((s_[k] == nx[k]).mean())
    return r
def blown(hs, mode='hbias', K=3):
    return sum(1 for st in starts if sim(mode, K, st, END + pd.Timedelta(minutes=1), hside=hs)[3] is not None)
print(f"$1000 starts every 2nd weekday: {len(starts)}\n")
a = sim('bstop', 3, A3, END + pd.Timedelta(minutes=1)); b = sim('bstop', 3, A6, A3)
print(f"LIVE two-sided stops $3 | baskets {a[0]} / {b[0]} | blown {a[2]} / {b[2]} | starts blown {blown(None, 'bstop') if False else sum(1 for st in starts if sim('bstop', 3, st, END + pd.Timedelta(minutes=1))[3] is not None)}/{len(starts)}", flush=True)
for N in (1, 2, 3, 6, 12, 24):
    for sgn, nm in ((1, 'follow'), (-1, 'fade')):
        if sgn == -1 and N not in (1, 6): continue
        hs = side_from(N, sgn); hr = nexthit(hs)
        a = sim('hbias', 3, A3, END + pd.Timedelta(minutes=1), hside=hs); b = sim('hbias', 3, A6, A3, hside=hs)
        print(f"last {N:2d} H1 {nm:6s} stop $3 | next H1 same way {hr[0]:.1%} / {hr[1]:.1%} | baskets {a[0]} / {b[0]} | blown {a[2]} / {b[2]} | worst float {a[4]:.0f} / {b[4]:.0f} | starts blown {blown(hs)}/{len(starts)}", flush=True)
hs = side_from(1, 1); a = sim('hmkt', 0, A3, END + pd.Timedelta(minutes=1), hside=hs); b = sim('hmkt', 0, A6, A3, hside=hs)
print(f"last  1 H1 follow MARKET  | blown {a[2]} / {b[2]} | starts blown {blown(hs, 'hmkt', 0)}/{len(starts)}", flush=True)
res = []
for sd in range(10):
    rs = pd.Series(rng.choice([-1, 1], len(h1)), index=h1.index).reindex(HK).values
    res.append(blown(rs))
print(f"RANDOM side per H1 bar (10 seeds), stop $3: starts blown median {np.median(res):.0f}, range {min(res)}-{max(res)}: {sorted(res)}")
