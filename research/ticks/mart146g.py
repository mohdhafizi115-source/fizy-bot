# Round 146g: MART with a TWO-SIDED OCO first entry (owner 20 Nov: "buy stop bawah sell stop atas. mana yg trigger delete yang tak
# trigger. floating tambah layer. gap ikut sekarang"). No D1 filter: the side is whichever order fills first. Live v2.56 rest:
# unlimited layers (lin +0.01), step $3, basket TP +$3, no SL, 24 h weekdays, hold overnight, $1000 account, no daily target.
# Modes: live = D1 side, stop $3 + limit $1 same side (v2.55/2.56); bstop = BUY STOP ask+$K / SELL STOP bid-$K;
# blim = BUY LIMIT ask-$K / SELL LIMIT bid+$K. When one M1 bar touches both levels the bar colour decides the order
# (bullish O->L->H->C, bearish O->H->L->C).
import sys, numpy as np, pandas as pd
D = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 else "xau_m1.pkl")
O, H, L, C, SP = (D[k].values for k in ("o", "h", "l", "c", "spread")); T = D.index
HM = (T.hour * 60 + T.minute).values; DAYK = T.normalize()
dd = D.c.groupby(DAYK).agg(["first", "last"]); dd["o"] = D.o.groupby(DAYK).first()
colour = np.sign(dd["last"] - dd["o"]); prevcol = colour.shift(1).reindex(DAYK).values
END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
MRG = 4000 / 3000; SWAP = {1: -0.71, -1: -0.84}

def sim(mode, K, lo, hi, S=3.0, Tgt=3.0, Lmax=99, B0=1000.0):
    bal = B0; blown = 0; baskets = []; days = {}; wf = 0.0
    pos = []; d = 0; pend = None; first_blow = None; lastday = None; dside = 0
    idx = np.flatnonzero((T >= lo) & (T < hi))
    for i in idx:
        day = DAYK[i]; sp = SP[i]
        if day != lastday:
            if pos and lastday is not None: bal += sum(l for l, e in pos) * SWAP[d]
            lastday = day
            dside = int(prevcol[i]) if not np.isnan(prevcol[i]) else 0
            if mode == "live" and not pos: pend = None
        if not pos and pend is None:
            ask = C[i - 1] + sp; bid = C[i - 1]
            if mode == "live":
                if dside != 0:
                    pend = ((ask + 3, ask - 1) if dside == 1 else (bid - 3, bid + 1), dside)
            elif mode == "bstop": pend = ((ask + K, bid - K), 0)
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
            elif mode == "bstop":
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

starts = [d for d in pd.date_range(A6.normalize(), END.normalize() - pd.Timedelta(days=10), freq="B")][::2]
for mode, K in (("live", 0), ("bstop", 3), ("bstop", 1), ("blim", 1), ("blim", 3)):
    a = sim(mode, K, A3, END + pd.Timedelta(minutes=1)); b = sim(mode, K, A6, A3)
    nb = sum(1 for s in starts if sim(mode, K, s, END + pd.Timedelta(minutes=1))[3] is not None)
    print(f"{mode:5s} K ${K} | last {a[0]} baskets net {a[1]:+.0f} blown {a[2]} 1st {a[3]} worst float {a[4]:.0f} | "
          f"prev {b[0]} net {b[1]:+.0f} blown {b[2]} float {b[4]:.0f} | $1000 starts blown {nb}/{len(starts)}", flush=True)
