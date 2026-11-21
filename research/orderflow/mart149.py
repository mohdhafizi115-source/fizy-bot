# Round 146g: MART with a TWO-SIDED OCO first entry (owner 20 Nov: "buy stop bawah sell stop atas. mana yg trigger delete yang tak
# trigger. floating tambah layer. gap ikut sekarang"). No D1 filter: the side is whichever order fills first. Live v2.56 rest:
# unlimited layers (lin +0.01), step $3, basket TP +$3, no SL, 24 h weekdays, hold overnight, $1000 account, no daily target.
# Modes: live = D1 side, stop $3 + limit $1 same side (v2.55/2.56); bstop = BUY STOP ask+$K / SELL STOP bid-$K;
# blim = BUY LIMIT ask-$K / SELL LIMIT bid+$K. When one M1 bar touches both levels the bar colour decides the order
# (bullish O->L->H->C, bearish O->H->L->C).
import sys, numpy as np, pandas as pd
D = pd.read_pickle("../ticks/xau_m1.pkl")
O, H, L, C, SP = (D[k].values for k in ("o", "h", "l", "c", "spread")); T = D.index
HM = (T.hour * 60 + T.minute).values; DAYK = T.normalize()
dd = D.c.groupby(DAYK).agg(["first", "last"]); dd["o"] = D.o.groupby(DAYK).first()
colour = np.sign(dd["last"] - dd["o"]); prevcol = colour.shift(1).reindex(DAYK).values
END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
MRG = 4000 / 3000; SWAP = {1: -0.71, -1: -0.84}

def sim(mode, K, lo, hi, S=3.0, Tgt=3.0, Lmax=99, B0=1000.0, gate=None, dmode=None, pause=None):
    bal = B0; blown = 0; baskets = []; days = {}; wf = 0.0
    pos = []; d = 0; pend = None; pt = 0; first_blow = None; lastday = None; dside = 0
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
            if gate is not None:
                W, g = gate
                if abs(DZ[W][i]) > g: continue
            if dmode is not None:
                W, g, sgn = dmode
                if W == -5:
                    z = BCV[i]
                elif W == -6:
                    if abs(BCV[i]) < g: continue
                    z = RS[sgn][i] * 9.0; sgn = 1
                elif W == -3:
                    if abs(CV[i]) < g: continue
                    z = RS[sgn][i] * 9.0; sgn = 1
                if W in (-5, -6): pass
                else: z = (RS[int(g)][i] * 9.0) if W == -2 else (DZ[W][i] if W else CV[i])
                if abs(z) < g: continue
                ds = int(np.sign(z)) * sgn
            if mode == "live":
                if dside != 0:
                    pend = ((ask + 3, ask - 1) if dside == 1 else (bid - 3, bid + 1), dside)
            elif mode == "bstop": pend = ((ask + K, bid - K), 0)
            else: pend = ((ask - K, bid + K), 0)
            if dmode is not None:
                pend = ((ask + K, -1e9), 0) if ds == 1 else ((1e9, bid - K), 0); pt = i
        if not pos and pend is not None and dmode is not None and i - pt > 30:
            pend = None; continue
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
                if pause is not None and DZ[pause[0]][i] * d < -pause[1]: break
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


import importlib.util, os
spec = importlib.util.spec_from_file_location("of", "of148_flow.py"); OF = importlib.util.module_from_spec(spec); spec.loader.exec_module(OF)
F = OF.load_flow("min", 250)
U = OF.to_utc(T)
FX = F.reindex(U); 
DZ = {W: np.nan_to_num(FX[f"dz{W}"].values) for W in (15, 60, 240)}
CV = np.nan_to_num(FX["cvdday"].values)
# broker tick-rule CVD (no outside data): uptick +1 / downtick -1 per tick, summed since 00:00 UTC, z-scored like the Binance CVD
_td = pd.read_pickle('tickdelta.pkl').d.reindex(T).fillna(0.0)
_tdu = pd.Series(_td.values, index=U)
_sd = _tdu.rolling(1440, min_periods=300).std()
_dy = U.floor('D'); _cs = _tdu.groupby(_dy).cumsum(); _nn = _tdu.groupby(_dy).cumcount() + 1
BCV = np.nan_to_num((_cs / (_sd * np.sqrt(_nn))).shift(1).values)
print('corr broker CVD z vs Binance CVD z', np.corrcoef(BCV[300:], CV[300:])[0,1], 'sign agree', np.mean(np.sign(BCV[300:])==np.sign(CV[300:])), flush=True)
RS = {sd: np.where(np.random.default_rng(sd).random(len(T)) < 0.5, -1.0, 1.0) for sd in range(1, 21)}

starts = [d for d in pd.date_range(A6.normalize(), END.normalize() - pd.Timedelta(days=10), freq="B")][::2]
starts = [s_ for s_ in starts if s_ >= pd.Timestamp("2026-05-04")]
def row(lab, **kw):
    a = sim("bstop", 3, A3, END + pd.Timedelta(minutes=1), **kw); b = sim("bstop", 3, max(A6, pd.Timestamp("2026-05-04")), A3, **kw)
    nb = sum(1 for s_ in starts if sim("bstop", 3, s_, END + pd.Timedelta(minutes=1), **kw)[3] is not None)
    print(f"{lab:40s} | last {a[0]} baskets blown {a[2]} float {a[4]:.0f} | prev {b[0]} blown {b[2]} float {b[4]:.0f} | $1000 starts blown {nb}/{len(starts)}", flush=True)

for g in (1.0, 1.5, 1.75, 2.0, 2.5):
    row(f"BROKER tick CVD follow |z|>={g}", dmode=(-5, g, 1))
for g in (1.5, 2.0):
    row(f"BROKER tick CVD fade |z|>={g}", dmode=(-5, g, -1))
for sd in range(1, 11):
    row(f"RANDOM side, same broker-CVD|z|>=1.5 gate, seed {sd}", dmode=(-6, 1.5, sd))
