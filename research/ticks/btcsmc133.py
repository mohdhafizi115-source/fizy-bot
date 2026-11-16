import os, sys
DATA = sys.argv[1]; sys.argv = ["x", DATA]
sys.path.insert(0, "/home/claude/fizy-bot/research")
import numpy as np, pandas as pd
import scalp_all as SA, ind23 as R23, smc102 as SM
meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
rows = []
# ---- BTC FOL and STO on M5
mt = meta["BTCUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s")); T = d.index; N = len(d)
tr = np.maximum(H - L, np.maximum(np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])))
atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
def walk(i, dd, sl, iend):
    e = O[i] + (S[i] if dd == 1 else 0)
    for z in range(i, min(iend, N)):
        if dd == 1 and L[z] <= sl: return z, e, (min(O[z], sl) if z > i else sl)
        if dd == -1 and H[z] + S[z] >= sl: return z, e, (max(O[z] + S[z], sl) if z > i else sl)
    z = min(iend, N - 1); return z, e, (O[z] if dd == 1 else O[z] + S[z])
hm = (T.hour * 60 + T.minute).values
busy = -1
for i in range(20, N - 1):
    if i <= busy: continue
    b = C[i] - O[i]
    if abs(b) < 2.5 * atr[i] or atr[i] < 8 * S[i]: continue
    if hm[i + 1] >= 1425 or hm[i + 1] < 90: continue
    dd = 1 if b > 0 else -1
    sl = (L[i] - 0.3 * atr[i]) if dd == 1 else (H[i] + 0.3 * atr[i])
    z, e, x = walk(i + 1, dd, sl, i + 13); rows.append(("BTC-FOL", "BTCUSD", T[i + 1], T[z], dd, (x - e) * dd * usd)); busy = z
c5 = pd.Series(C, index=T); e20 = c5.ewm(span=20, adjust=False).mean().values
ll = pd.Series(L).rolling(5).min(); hh = pd.Series(H).rolling(5).max()
k = ((pd.Series(C) - ll) / (hh - ll) * 100).rolling(3).mean().values; dd_ = pd.Series(k).rolling(3).mean().values
H4 = d.resample("4h").agg({"c": "last"}).dropna(); tr4 = np.sign(H4.c.ewm(span=20, adjust=False).mean() - H4.c.ewm(span=50, adjust=False).mean())
tr4.index = tr4.index + pd.Timedelta(hours=4); trd = tr4.reindex(T, method="ffill").values
lmin3 = pd.Series(L).rolling(3).min().values; hmax3 = pd.Series(H).rolling(3).max().values
busy = -1
for i in range(60, N - 1):
    if i <= busy or not (7 <= T[i].hour < 19): continue
    up = k[i] > dd_[i] and k[i - 1] <= dd_[i - 1] and min(k[i - 1], dd_[i - 1]) < 20 and C[i] > O[i] and trd[i] > 0 and lmin3[i] <= e20[i]
    dn = k[i] < dd_[i] and k[i - 1] >= dd_[i - 1] and max(k[i - 1], dd_[i - 1]) > 80 and C[i] < O[i] and trd[i] < 0 and hmax3[i] >= e20[i]
    if not (up or dn): continue
    s_ = 1 if up else -1; e0 = O[i + 1] + (S[i + 1] if s_ == 1 else 0)
    z, e, x = walk(i + 1, s_, e0 - s_ * 1.5 * atr[i], i + 49); rows.append(("BTC-STO", "BTCUSD", T[i + 1], T[z], s_, (x - e) * s_ * usd)); busy = z
# ---- SMC: gold M15 n5 OB top TP3R, BTC M20 n3 OTE TP3R, BOS, killzone, weekdays
def smc(sym, pair, n, entry, tag):
    SM.PAIRS = (pair,); SM.BUY_CTRL = False
    A, END = SM.run(sym, meta[sym], SW.get(sym))
    for c_ in ("entry", "tp", "typ"): A[c_] = A[c_].astype(str)
    A = A.sort_values("t", kind="stable")
    kz = ((A.hr >= 9) & (A.hr < 12)) | ((A.hr >= 14) & (A.hr < 17))
    g = SM.busy(A[(A.n == n) & (A.entry == entry) & (A.tp == "3R") & (A.typ == "BOS") & kz & (pd.DatetimeIndex(A.t).dayofweek < 5)])
    for r in g.itertuples(): rows.append((tag, sym, r.t, r.t, r.d, float(r.r) * float(r.risk)))
smc("XAUUSD", (15, 240), 5, "OB top", "SMC-gold")
smc("BTCUSD", (20, 240), 3, "OTE 0.705", "BTC-SMC")
X = pd.DataFrame(rows, columns=["mod", "sym", "t", "tx", "d", "net"])
X.to_pickle(os.path.join(DATA, "..", "btcsmc133.pkl")); print(X.groupby("mod").net.agg(["count", "sum"]))
