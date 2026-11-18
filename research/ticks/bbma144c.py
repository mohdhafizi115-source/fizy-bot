# Round 144c: the round 144 / 144b rules with an ADX(14) filter on the momentum candle (18 Nov; owner: "tambah ADX 14 kalau
# momentum buy lebih garisan 20 dan bb mid berada atas EMA50"): a momentum close counts only when Wilder ADX(14, M5) of that
# bar is above the threshold (and mid BB vs EMA 50 as before). ex 'swing' = round 144 exits (TP next swing, cut on opposite
# momentum); ex 'mom' = round 144b exits (TP on a new momentum close, SL on a close beyond EMA 50).
# Round 144: the owner's gold M5 BBMA pullback rule (18 Nov; owner: "test gold bbma di m5. buy sahaja bila ada mom close top bb
# + mid bb atas ema50 ... instant entry bila price touch ma5/10 low ... TP next resistant ... berterusan sampai cut loss bila ada
# mom sell candle close luar low bb. untuk sell terbalikkan").
# BUY regime: an M5 candle closes above the top BB 20,2 while mid BB > EMA 50 (filter can be switched off).
#   While in it: every time price comes down to the MA5/10 LOW zone (top = max(LWMA5, LWMA10) of the lows of the last closed bar,
#   or the zone middle), enter at that price at once (market, + spread); TP = the nearest unbroken fractal swing high above the
#   entry ("next resistance"); after a TP, wait for the next touch and go again, one position at a time.
#   Cut: an M5 close below the bottom BB (sell momentum) closes the buy at the next open and ends the buy regime.
# SELL mirrored. Optional disaster SL (none / beyond the nearest support - 0.1 ATR / fixed $10). No entries 23:45-01:30 server.
# Broker swap (gold long -$0.71 / short -$0.84 per night at 0.01 lot). Random-direction twin at the same entry bar with the
# mirrored exit rules. Last 3 months and the 3 before, 0.01 lot, $1 per $1 on gold.
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/fizy-bot/research")
import scalp_all as SA
DATA = sys.argv[1]; SYM = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
mt = meta[SYM]; USD = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, SYM + ".csv"), mt["point"])
O, H, L, C, S = (d[k].values for k in ("o", "h", "l", "c", "s"))
T = d.index; n = len(d)
c = d.c; mid = c.rolling(20).mean().values; sd = c.rolling(20).std(ddof=0).values
UP = mid + 2 * sd; DN = mid - 2 * sd
E50 = c.ewm(span=50, adjust=False).mean().values
def lwma(x, k):
    w = np.arange(1, k + 1, dtype=float)
    return x.rolling(k).apply(lambda a: np.dot(a, w) / w.sum(), raw=True).values
L5, L10, H5, H10 = lwma(d.l, 5), lwma(d.l, 10), lwma(d.h, 5), lwma(d.h, 10)
tr = np.maximum(d.h - d.l, np.maximum((d.h - c.shift()).abs(), (d.l - c.shift()).abs()))
ATR = tr.ewm(alpha=1 / 14, adjust=False).mean().values
up_ = d.h.diff(); dn_ = -d.l.diff()
pdm = np.where((up_ > dn_) & (up_ > 0), up_, 0.0); mdm = np.where((dn_ > up_) & (dn_ > 0), dn_, 0.0)
atw = tr.ewm(alpha=1 / 14, adjust=False).mean()
pdi = 100 * pd.Series(pdm, index=d.index).ewm(alpha=1 / 14, adjust=False).mean() / atw
mdi = 100 * pd.Series(mdm, index=d.index).ewm(alpha=1 / 14, adjust=False).mean() / atw
ADX = (100 * (pdi - mdi).abs() / (pdi + mdi)).ewm(alpha=1 / 14, adjust=False).mean().fillna(0).values
HM = (T.hour * 60 + T.minute).values
DAY = T.normalize().values
SWAP = {1: -0.71, -1: -0.84}

def run(nsw=2, zone="top", sl="none", filt=True, side="both", rng=None, adx=0, ex="swing"):
    shs = []; sls = []                       # unbroken swing highs / lows (price)
    reg = 0; pos = 0; e = tp = st = 0.0; t0 = 0; trades = []
    for i in range(30, n):
        # swings confirmed at the close of bar i-1 (pivot p = i-1-nsw)
        p = i - 1 - nsw
        if p - nsw >= 0:
            if H[p] == H[p - nsw:i].max(): shs.append(H[p])
            if L[p] == L[p - nsw:i].min(): sls.append(L[p])
        cl = C[i - 1]
        shs = [x for x in shs if x > cl]; sls = [x for x in sls if x < cl]
        shs = shs[-50:]; sls = sls[-50:]
        mom_up = cl > UP[i - 1]; mom_dn = cl < DN[i - 1]
        # momentum at the close of bar i-1: cut the opposite position at this open, set the regime
        if pos != 0 and ex == "mom" and i - 1 >= t0:
            ema_x = (pos == 1 and cl < E50[i - 1]) or (pos == -1 and cl > E50[i - 1])
            new_m = (pos == 1 and mom_up) or (pos == -1 and mom_dn)
            if ema_x or new_m:
                x = O[i] + (S[i] if pos == -1 else 0)
                trades.append((T[t0], (x - e) * pos * USD + nights(t0, i) * SWAP[pos], pos, "sl" if ema_x else "tp")); pos = 0
        if pos != 0 and ((pos == 1 and mom_dn) or (pos == -1 and mom_up)):
            x = O[i] + (S[i] if pos == -1 else 0)
            trades.append((T[t0], (x - e) * pos * USD + nights(t0, i) * SWAP[pos] * (USD / 1.0), pos, "cut")); pos = 0
        if mom_up: reg = 1 if ((not filt or mid[i - 1] > E50[i - 1]) and ADX[i - 1] > adx) else 0
        if mom_dn: reg = -1 if ((not filt or mid[i - 1] < E50[i - 1]) and ADX[i - 1] > adx) else 0
        # manage the open position inside bar i
        if pos != 0:
            if pos == 1:
                if st and L[i] <= st: trades.append((T[t0], (st - e) * USD + nights(t0, i) * SWAP[1], 1, "sl")); pos = 0
                elif tp and H[i] >= tp: trades.append((T[t0], (tp - e) * USD + nights(t0, i) * SWAP[1], 1, "tp")); pos = 0
            else:
                if st and H[i] + S[i] >= st: trades.append((T[t0], (e - st) * USD + nights(t0, i) * SWAP[-1], -1, "sl")); pos = 0
                elif tp and L[i] + S[i] <= tp: trades.append((T[t0], (e - tp) * USD + nights(t0, i) * SWAP[-1], -1, "tp")); pos = 0
            continue                                     # no re-entry in the bar that closed a trade
        if reg == 0 or (side == "buy" and reg == -1): continue
        if HM[i] >= 1425 or HM[i] < 90: continue
        if reg == 1:
            lvl = max(L5[i - 1], L10[i - 1]) if zone == "top" else 0.5 * (L5[i - 1] + L10[i - 1])
            if cl <= lvl or L[i] > lvl: continue
            px = min(lvl, O[i])                          # touched (or gapped through) the MA5/10 low zone
        else:
            lvl = min(H5[i - 1], H10[i - 1]) if zone == "top" else 0.5 * (H5[i - 1] + H10[i - 1])
            if cl >= lvl or H[i] < lvl: continue
            px = max(lvl, O[i])
        dr = reg
        if rng is not None: dr = 1 if rng.random() < 0.5 else -1
        if dr == 1:
            e = px + S[i]; cand = [x for x in shs if x > e + S[i]]
            if ex == "mom": tp = 0.0
            elif not cand: continue
            else: tp = min(cand)
            sup = [x for x in sls if x < e]
            st = (max(sup) - 0.1 * ATR[i - 1]) if (sl == "swing" and sup) else (e - 10.0 if sl == "10" else 0.0)
        else:
            e = px; cand = [x for x in sls if x < e - S[i]]
            if ex == "mom": tp = 0.0
            elif not cand: continue
            else: tp = max(cand)
            res = [x for x in shs if x > e]
            st = (min(res) + 0.1 * ATR[i - 1]) if (sl == "swing" and res) else (e + 10.0 if sl == "10" else 0.0)
        pos = dr; t0 = i
        # same-bar exit check after the touch (conservative: SL first)
        if pos == 1 and st and L[i] <= st: trades.append((T[t0], (st - e) * USD, 1, "sl")); pos = 0
        elif pos == -1 and st and H[i] + S[i] >= st: trades.append((T[t0], (e - st) * USD, -1, "sl")); pos = 0
    return trades

def nights(a, b): return int((DAY[b] - DAY[a]) / np.timedelta64(1, "D"))

END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
def st_(r, lo, hi):
    g = [x for x in r if lo <= x[0] < hi]
    if not g: return "  0 trades"
    p = np.array([x[1] for x in g]); w = p[p > 0].sum(); l = -p[p < 0].sum()
    eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    day = pd.Series(p, index=pd.DatetimeIndex([x[0] for x in g]).normalize()).groupby(level=0).sum().min()
    nb = sum(1 for x in g if x[2] == 1); cuts = sum(1 for x in g if x[3] == "cut")
    return (f"{len(p):4d} tr (buy {nb:3d}, cut {cuts:3d}) win {100*(p>0).mean():3.0f}% PF {min(w/max(l,1e-9),99):5.2f} "
            f"net {p.sum():+6.0f} DD {dd:+5.0f} wday {day:+4.0f} wtrade {p.min():+5.0f}")
def pf(r, lo, hi):
    p = np.array([x[1] for x in r if lo <= x[0] < hi])
    return min(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9), 99) if len(p) else 0

print(f"{SYM} M5, last 3 months {A3:%d %b}-{END:%d %b} | previous {A6:%d %b}-{A3:%d %b} (0.01 lot, swap in)")
for ex in ("swing", "mom"):
    for side in ("buy", "both"):
        for adx in (0, 20, 25):
            for zone in ("top", "mid"):
                for sl in ("none", "10"):
                    r = run(2, zone, sl, True, side, adx=adx, ex=ex)
                    rr = [run(2, zone, sl, True, side, rng=np.random.default_rng(k), adx=adx, ex=ex) for k in range(3)]
                    lab = f"exit {ex:5s} {side:4s} ADX>{adx:2d} {zone:3s} hardSL {sl:4s}"
                    print(f"{lab} | {st_(r, A3, END + pd.Timedelta(days=1))} | {st_(r, A6, A3)} | random "
                          f"{min(pf(x, A3, END) for x in rr):.2f}-{max(pf(x, A3, END) for x in rr):.2f} / "
                          f"{min(pf(x, A6, A3) for x in rr):.2f}-{max(pf(x, A6, A3) for x in rr):.2f}", flush=True)
