# Round 145: the owner's gold M5 BBMA re-entry after momentum (18 Nov; owner's chart: "1. mid bb bawah ema50 2. ada mom sell
# 3. price naik area ma5/10 high dan price reject area situ. ada 1 candle bear 4. entry lepas candle tu close 5. TP dekat low").
# SELL (BUY mirrored): an M5 close below the bottom BB 20,2 (momentum) while mid BB < EMA 50 opens a setup; within W candles a
# bear candle whose high reaches the LWMA 5/10-of-highs zone (high >= the lower of the two) and closes back below it = rejection;
# entry at the next open; TP = the lowest low since the momentum candle ("the low"), or 1R / 2R; SL above the rejection
# candle's high + spread + 0.1 ATR ("cand"), 1.5 ATR from the entry ("atr"), or none (cut on an opposite momentum close);
# out after 8 h. Setup cancelled by an opposite momentum or a close beyond EMA 50; "once" = first rejection per momentum only.
# One position at a time, no entries 23:45-01:30, broker swap. Random-direction twin with the same SL / TP distances.
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
HM = (T.hour * 60 + T.minute).values
DAY = T.normalize().values
SWAP = {1: -0.71, -1: -0.84}
def nights(a, b): return int((DAY[b] - DAY[a]) / np.timedelta64(1, "D"))

def run(W=24, once=True, sl="cand", tp="low", side="both", rng=None, cancel_ema=True):
    trades = []; reg = 0; mi = 0; ext = 0.0; used = False
    pos = 0; e = st = tg = 0.0; t0 = 0
    for j in range(30, n - 1):
        # ---- manage the open position inside bar j (SL first, conservative)
        if pos != 0:
            out = None
            if pos == -1:
                if st and H[j] + S[j] >= st: out = (e - st, "sl")
                elif tg and L[j] + S[j] <= tg: out = (e - tg, "tp")
            else:
                if st and L[j] <= st: out = (st - e, "sl")
                elif tg and H[j] >= tg: out = (tg - e, "tp")
            if out is None and j - t0 >= 96: out = ((C[j] - e) * pos - (S[j] if pos == -1 else 0), "time")
            if out is None and ((pos == 1 and C[j] < DN[j]) or (pos == -1 and C[j] > UP[j])):
                out = ((C[j] - e) * pos - (S[j] if pos == -1 else 0), "cut")
            if out: trades.append((T[t0], out[0] * USD + nights(t0, j) * SWAP[pos], pos, out[1], drn)); pos = 0
        # ---- setup state from the close of bar j
        if C[j] < DN[j]:
            if mid[j] < E50[j]: reg, mi, ext, used = -1, j, L[j], False
            else: reg = 0
            continue
        if C[j] > UP[j]:
            if mid[j] > E50[j]: reg, mi, ext, used = 1, j, H[j], False
            else: reg = 0
            continue
        if reg == 0: continue
        if j - mi > W or (cancel_ema and ((reg == -1 and C[j] > E50[j]) or (reg == 1 and C[j] < E50[j]))):
            reg = 0; continue
        if reg == -1: ext = min(ext, L[j])
        else: ext = max(ext, H[j])
        if pos != 0 or (once and used): continue
        if side == "sell" and reg == 1: continue
        if side == "buy" and reg == -1: continue
        k = j + 1
        if HM[k] >= 1425 or HM[k] < 90: continue
        if reg == -1:
            zl = min(H5[j], H10[j]); rej = H[j] >= zl and C[j] < O[j] and C[j] < zl
        else:
            zl = max(L5[j], L10[j]); rej = L[j] <= zl and C[j] > O[j] and C[j] > zl
        if not rej: continue
        used = True
        # distances measured for the real (setup) direction
        px = O[k]
        if reg == -1:
            ent = px; slp = H[j] + S[j] + 0.1 * ATR[j]; risk = slp - ent; tpd = ent - (ext + S[k])
        else:
            ent = px + S[k]; slp = L[j] - 0.1 * ATR[j]; risk = ent - slp; tpd = ext - ent
        if sl == "atr": risk = 1.5 * ATR[j]
        if risk <= 0: continue
        if tp == "low": tdist = tpd
        else: tdist = float(tp[0]) * risk
        if tdist <= 0: continue
        drn = reg
        if rng is not None: drn = 1 if rng.random() < 0.5 else -1
        e = px + (S[k] if drn == 1 else 0)
        st = 0.0 if sl == "none" else (e + risk if drn == -1 else e - risk)
        tg = e - tdist if drn == -1 else e + tdist
        pos = drn; t0 = k
    return trades

END = T[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
def st_(r, lo, hi):
    g = [x for x in r if lo <= x[0] < hi]
    if not g: return "   0 trades"
    p = np.array([x[1] for x in g]); w = p[p > 0].sum(); l = -p[p < 0].sum()
    eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    day = pd.Series(p, index=pd.DatetimeIndex([x[0] for x in g]).normalize()).groupby(level=0).sum().min()
    def pfs(sgn):
        q = np.array([x[1] for x in g if x[2] == sgn])
        return min(q[q > 0].sum() / max(-q[q < 0].sum(), 1e-9), 99) if len(q) else 0
    ntp = sum(1 for x in g if x[3] == "tp")
    return (f"{len(p):4d} tr win {100*(p>0).mean():3.0f}% tp {ntp:3d} PF {min(w/max(l,1e-9),99):5.2f} "
            f"(b {pfs(1):4.2f} s {pfs(-1):4.2f}) net {p.sum():+6.0f} DD {dd:+5.0f} wday {day:+4.0f} wtr {p.min():+4.0f}")
def pf(r, lo, hi):
    p = np.array([x[1] for x in r if lo <= x[0] < hi])
    return min(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9), 99) if len(p) else 0
def stress(r, lo, hi):   # 1.5x spread: subtract another half spread per trade (median spread)
    ms = float(np.median(S)) * 0.5 * USD
    p = np.array([x[1] - ms for x in r if lo <= x[0] < hi])
    return min(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9), 99) if len(p) else 0

print(f"{SYM} M5, last 3 months {A3:%d %b}-{END:%d %b} | previous {A6:%d %b}-{A3:%d %b} (0.01 lot, swap in)")
for W in (12, 24, 48):
    for once in (True, False):
        for sl in ("cand", "atr", "none"):
            for tp in ("low", "1R", "2R"):
                if sl == "none" and tp != "low": continue
                r = run(W, once, sl, tp)
                rr = [run(W, once, sl, tp, rng=np.random.default_rng(k)) for k in range(3)]
                lab = f"W{W:2d} {'once' if once else 'many'} SL {sl:4s} TP {tp:3s}"
                print(f"{lab} | {st_(r, A3, END + pd.Timedelta(days=1))} stress {stress(r, A3, END + pd.Timedelta(days=1)):4.2f} | "
                      f"{st_(r, A6, A3)} | random {min(pf(x, A3, END) for x in rr):.2f}-{max(pf(x, A3, END) for x in rr):.2f} / "
                      f"{min(pf(x, A6, A3) for x in rr):.2f}-{max(pf(x, A6, A3) for x in rr):.2f}", flush=True)
r = run(24, True, "cand", "low", cancel_ema=False)
print(f"no EMA cancel W24 once cand low | {st_(r, A3, END + pd.Timedelta(days=1))} | {st_(r, A6, A3)}")
