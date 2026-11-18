# Round 146: FLIP v2.47 entries with NO stop loss and a MARTINGALE basket (18 Nov; owner: "buang sl dan tambahkan martiangle. TP kena
# adjust bila dah tambah lot, cara adjust pastikan ada profit"). Gold M1 bars from the owner's real ticks (xau_m1.pkl, bid OHLC
# + spread), server time. Direction against yesterday's D1 colour (doji = no trade). From 01:30 a stop order $3 from the price on
# the allowed side opens a basket; every further $S against the last entry adds a position with the next lot of the schedule
# (x2 / x1.5 / +0.01, up to Lmax levels); the basket TP is moved after every add to the price where the WHOLE basket nets +$T;
# after a TP a new stop $3 away re-arms (entries 01:30-23:00). At 23:30 either close everything or hold overnight (swap charged).
# $100 account, 1:3000 (0.01 lot = $1.33 margin), stop-out at equity <= 40% of margin: the account is lost, refilled with $100 next day.
# Bars processed conservatively: adverse extreme first (adds, stop-out), then the favourable extreme (TP).
import sys, numpy as np, pandas as pd
D = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 else "xau_m1.pkl")
O, H, L, C, SP = (D[k].values for k in ("o", "h", "l", "c", "spread")); T = D.index
HM = (T.hour * 60 + T.minute).values; DAYK = T.normalize()
dd = D.c.groupby(DAYK).agg(["first", "last"]); dd["o"] = D.o.groupby(DAYK).first()
colour = np.sign(dd["last"] - dd["o"]); prevcol = colour.shift(1).reindex(DAYK).values   # yesterday's D1 colour
END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
MRG = 4000 / 3000; SWAP = {1: -0.71, -1: -0.84}

def lots_of(sched, k):
    if sched == "x2": return 2 ** k
    if sched == "x1.5": return [1, 2, 3, 5, 8, 12, 18, 27, 41, 62, 93, 140][k]
    return k + 1

def sim(S, Tgt, sched, Lmax, overnight, lo, hi):
    bal = 100.0; refill = 0; blown = 0; baskets = []; days = {}
    pos = []; d = 0; pend = None; maxlot = 0; first_blow = None; lastday = None
    idx = np.flatnonzero((T >= lo) & (T < hi))
    for i in idx:
        day = DAYK[i]; hm = HM[i]; sp = SP[i]
        if day != lastday:
            if pos and lastday is not None: bal += sum(l for l, e in pos) * SWAP[d]   # overnight swap
            lastday = day; pend = None
            if not pos:
                d = int(prevcol[i]) if not np.isnan(prevcol[i]) else 0
        if not pos and pend is None and d != 0 and 90 <= hm < 1380:
            pend = (C[i - 1] + sp + 3) if d == 1 else (C[i - 1] - 3)          # buy stop (ask) / sell stop (bid)
        # fill a pending stop
        if not pos and pend is not None and 90 <= hm < 1380:
            if d == 1 and H[i] + sp >= pend: pos = [(1, max(pend, O[i] + sp))]; pend = None
            elif d == -1 and L[i] <= pend: pos = [(1, min(pend, O[i]))]; pend = None
        if pos:
            # adverse extreme: adds, then equity check
            while len(pos) < Lmax:
                le = pos[-1][1]; lvl = le - S if d == 1 else le + S
                hit = (L[i] + sp <= lvl) if d == 1 else (H[i] <= lvl)
                if not hit: break
                pos.append((lots_of(sched, len(pos)), lvl))
            nl = sum(l for l, e in pos); maxlot = max(maxlot, nl)
            adv = L[i] if d == 1 else H[i] + sp
            fl = sum(l * (adv - e) * d for l, e in pos)
            if bal + fl <= 0.4 * nl * MRG:
                loss = -bal; bal = 0.0
                days[day] = days.get(day, 0) + loss; baskets.append(loss); blown += 1
                if first_blow is None: first_blow = day
                bal = 100.0; refill += 100; pos = []; pend = None; d = 0; continue
            # TP of the whole basket at +$Tgt
            tp = (Tgt + sum(l * e for l, e in pos) * d) / nl * d if d == 1 else (sum(l * e for l, e in pos) - Tgt) / nl
            if d == 1: tp = (Tgt + sum(l * e for l, e in pos)) / nl
            fav = H[i] if d == 1 else L[i] + sp
            if (d == 1 and fav >= tp) or (d == -1 and fav <= tp):
                pnl = sum(l * (tp - e) * d for l, e in pos); bal += pnl
                days[day] = days.get(day, 0) + pnl; baskets.append(pnl); pos = []
                continue
            # 23:30 close (if not holding overnight)
            if hm >= 1410 and not overnight:
                px = C[i] if d == 1 else C[i] + sp
                pnl = sum(l * (px - e) * d for l, e in pos); bal += pnl
                days[day] = days.get(day, 0) + pnl; baskets.append(pnl); pos = []
        if not pos and hm >= 1410: pend = None
    if pos:   # mark the last open basket to market
        px = C[idx[-1]] if d == 1 else C[idx[-1]] + SP[idx[-1]]
        baskets.append(sum(l * (px - e) * d for l, e in pos))
    b = np.array(baskets) if baskets else np.zeros(1)
    net = (bal - 100) - refill + 100 * 0 + (refill - 100 * blown) * 0
    net = sum(baskets)
    wday = min(days.values()) if days else 0
    return len(b), 100 * (b > 0).mean(), net, blown, wday, maxlot, first_blow

print(f"FLIP v2.47 entries, NO SL, martingale basket, TP = whole basket +$T | last 3 months {A3:%d %b}-{END:%d %b} | previous {A6:%d %b}-{A3:%d %b}")
print("cols: baskets, win% (baskets closed in profit), net $ incl. blown accounts, $100 accounts blown, worst day, max lots (x0.01), first blow-up")
for overnight in (False, True):
    for sched in ("x2", "x1.5", "lin"):
        for S in (2, 3, 5, 8):
            for Tgt in (1, 3):
                for Lmax in (6, 10):
                    a = sim(S, Tgt, sched, Lmax, overnight, A3, END + pd.Timedelta(minutes=1))
                    b = sim(S, Tgt, sched, Lmax, overnight, A6, A3)
                    f = lambda r: (f"{r[0]:4d} win {r[1]:3.0f}% net {r[2]:+7.0f} blown {r[3]:3d} wday {r[4]:+6.0f} maxlot {r[5]:4d} "
                                   f"1st {r[6].strftime('%d %b') if r[6] is not None else '-':>6s}")
                    print(f"{'hold' if overnight else '2330'} {sched:4s} step ${S} TP+${Tgt} max{Lmax:2d} | {f(a)} | {f(b)}", flush=True)

# survival: a fresh $100 account started at 00:00 server on every 2nd weekday from 18 May, run to the end of the data
print("\nsurvival of a $100 account (no refill), started on every 2nd weekday 18 May - 6 Nov, run to 16 Nov")
starts = [d for d in pd.date_range(A6.normalize(), END.normalize() - pd.Timedelta(days=10), freq="B")][::2]
for cell in [(3, 3, "x1.5", 6, True), (3, 3, "lin", 6, True), (3, 3, "x1.5", 6, False), (2, 3, "lin", 6, True), (5, 1, "x1.5", 6, True)]:
    S, Tg, sc, Lm, ov = cell; life = []; nb = 0
    for s in starts:
        r = sim(S, Tg, sc, Lm, ov, s, END + pd.Timedelta(minutes=1))
        if r[6] is not None: nb += 1; life.append((r[6] - s).days)
    med = np.median(life) if life else float("nan")
    print(f"{'hold' if ov else '2330'} {sc:4s} step ${S} TP+${Tg} max{Lm} | {nb} of {len(starts)} starts blown ({100*nb/len(starts):.0f}%), "
          f"median {med:.0f} days to blow-up, within 7 days {sum(1 for x in life if x <= 7)}, within 30 days {sum(1 for x in life if x <= 30)}", flush=True)
