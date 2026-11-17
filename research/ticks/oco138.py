# Round 138: BUY STOP / SELL STOP (OCO) strategies on gold M1, simulated on the owner's real ticks
# (fills at the crossing tick, stops / TP / time exits at the real bid / ask). 0.01 lot, $1 move = $1.
import ctypes, numpy as np, pandas as pd, sys
v = ctypes.c_void_p
lib = ctypes.CDLL("./oco138.so"); lib.sim.restype = ctypes.c_int
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"]); n = len(t)
D = pd.read_pickle("xau_m1.pkl"); MS = 60000
O, H, L, C, SP = (D[c].values for c in ("o", "h", "l", "c", "spread"))
TM = D.index.values.astype("datetime64[ms]").astype(np.int64)        # bar start, server ms
hr = D.index.hour.values + D.index.minute.values / 60.0; wd = D.index.dayofweek.values
tr = np.maximum(H - L, np.maximum(abs(H - np.r_[C[0], C[:-1]]), abs(L - np.r_[C[0], C[:-1]])))
ATR = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
END = pd.Timestamp(t[-1], unit="ms"); A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
NB = 400000; ot = np.zeros(NB, np.int64); op = np.zeros(NB); ox = np.zeros(NB, np.int64); od = np.zeros(NB, np.int32)
def sim(tp, buy, sell, sl, tpd, texp, texit):
    o = np.argsort(tp, kind="stable"); A = [np.ascontiguousarray(x[o]) for x in (tp, buy, sell, sl, tpd, texp, texit)]
    A = [A[0].astype(np.int64), A[1].astype(float), A[2].astype(float), A[3].astype(float), A[4].astype(float), A[5].astype(np.int64), A[6].astype(np.int64)]
    m = lib.sim(t.ctypes.data_as(v), b.ctypes.data_as(v), a.ctypes.data_as(v), ctypes.c_int64(n), ctypes.c_int(len(A[0])),
                *[x.ctypes.data_as(v) for x in A], ctypes.c_int(0), ot.ctypes.data_as(v), op.ctypes.data_as(v), ox.ctypes.data_as(v), od.ctypes.data_as(v))
    return pd.Series(op[:m].copy(), index=pd.to_datetime(ot[:m], unit="ms")), od[:m].copy()
def pf(x): g = x[x > 0].sum(); l = -x[x < 0].sum(); return g / l if l > 0 else 99.0
def st(s, lo, hi):
    x = s[(s.index >= lo) & (s.index < hi)]
    if len(x) == 0: return "  no trades".ljust(66)
    d = x.groupby(x.index.normalize()).sum(); eq = d.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min()
    return f"{len(x):5d} {len(x)/max(len(d),1):5.1f}/d win {100*(x>0).mean():3.0f}% PF {pf(x):5.2f} str {pf(x-0.13):4.2f} net {x.sum():+6.0f} worst {d.min():+5.0f} DD {dd:+5.0f}"
RES = []
def row(lab, ev):
    if ev is None or len(ev[0]) == 0: print(f"{lab:46s} no events"); return
    s, d = sim(*ev); x = s[s.index >= A3]; y = s[(s.index >= A6) & (s.index < A3)]
    RES.append((lab, len(x), pf(x), x.sum(), pf(x - 0.13), pf(y), y.sum()))
    print(f"{lab:46s} | {st(s, A3, END + pd.Timedelta(days=1))} | {st(s, A6, A3)}", flush=True)
ok = ((hr >= 1.5) & (hr < 22.5) & (wd < 5))
# ---------- 1. N-bar box breakout (compression), re-placed every minute ----------
def box(N, cx, buf, slm, tpm, hold, h0=1.5, h1=22.5, rnd=False):
    hh = pd.Series(H).rolling(N).max().values; ll = pd.Series(L).rolling(N).min().values; rg = hh - ll
    m = ok & (hr >= h0) & (hr < h1) & np.isfinite(rg) & (rg <= cx * ATR) & (rg > 0)
    if rnd:  # control: same count of minutes picked at random from the allowed window
        idx = np.flatnonzero(ok & np.isfinite(rg) & (rg > 0)); rs = np.random.default_rng(7); i = np.sort(rs.choice(idx, m.sum(), replace=False))
    else: i = np.flatnonzero(m)
    tp = TM[i] + MS; sl = np.maximum(slm * rg[i], 0.5) if slm > 0 else -slm + 0 * rg[i]
    return (tp, hh[i] + buf + SP[i], ll[i] - buf, sl, tpm * sl if tpm > 0 else 0 * sl, tp + MS, tp + hold * MS)
print(f"last 3 months {A3:%Y-%m-%d} .. {END:%Y-%m-%d} | previous {A6:%Y-%m-%d} .. {A3:%Y-%m-%d}; stress = +$0.13 a trade")
print("== 1. BOX: N-bar M1 range <= cx * ATR(M1), OCO at the box high + spread + buf / low - buf, valid 1 min, SL slm x box (neg = fixed $), TP tpm x SL, out after hold min")
for N in (5, 10, 15, 30):
    for cx in (1.5, 2.5, 4.0):
        for slm, tpm in ((1.0, 0), (1.0, 2), (0.5, 2), (-3, 0)):
            row(f"BOX N{N} cx{cx} sl{slm} tp{tpm} 30m", box(N, cx, 0.1, slm, tpm, 30))
for N, cx in ((10, 2.5), (15, 2.5), (30, 4.0)):
    row(f"BOX N{N} cx{cx} sl1 60m", box(N, cx, 0.1, 1.0, 0, 60)); row(f"BOX N{N} cx{cx} sl1 120m", box(N, cx, 0.1, 1.0, 0, 120))
    row(f"BOX N{N} cx{cx} sl1 30m RANDOM", box(N, cx, 0.1, 1.0, 0, 30, rnd=True))
    row(f"BOX N{N} cx{cx} sl1 30m London 10-15", box(N, cx, 0.1, 1.0, 0, 30, 10, 15)); row(f"BOX N{N} cx{cx} sl1 30m NY 15-19", box(N, cx, 0.1, 1.0, 0, 30, 15, 19))
# ---------- 2. Hour-open straddle ----------
def straddle(hh, K, sl, tpm, hold, expm=15, mins=None):
    if mins is None: i = np.flatnonzero((D.index.hour.values == int(hh)) & (D.index.minute.values == int(round((hh % 1) * 60))) & (wd < 5))
    else: i = mins
    tp = TM[i]; o = O[i]
    return (tp, o + K + SP[i], o - K, np.full(len(i), sl, float), np.full(len(i), sl * tpm), tp + expm * MS, tp + hold * MS)
print("== 2. STRADDLE at a fixed server time: OCO open +/- K, SL $sl, TP tpm x SL (0 = none), out after hold min")
for hh in (1.5, 3, 8, 9, 10, 11, 14, 15, 15.5, 16, 16.5, 17, 18, 20):
    for K, sl, tpm, hold in ((1, 3, 0, 30), (2, 4, 0, 60), (3, 5, 2, 120), (2, 3, 2, 30)):
        row(f"STR {hh:5.2f} K{K} sl{sl} tp{tpm} {hold}m", straddle(hh, K, sl, tpm, hold))
# ---------- 3. News straddle (USD high importance) ----------
cal = pd.read_csv("/home/claude/fizy-bot/data/calendar.csv")
cal = cal[(cal.currency == "USD") & (cal.importance == 3)]
utc = pd.to_datetime(cal.time - 7200, unit="s").dt.tz_localize("UTC").dt.tz_convert("Europe/Athens").dt.tz_localize(None)
ev = pd.DatetimeIndex(sorted(set(utc[(utc >= D.index[0]) & (utc <= D.index[-1])])))
print(f"== 3. NEWS: {len(ev)} USD high-importance releases in the tick window; OCO placed 1 min before at the price +/- K, expire 5 min after")
im = D.index.get_indexer(ev - pd.Timedelta(minutes=1)); im = im[im >= 0]
for K, sl, tpm, hold in ((1, 3, 0, 15), (2, 4, 0, 30), (3, 5, 0, 60), (2, 4, 2, 30), (5, 5, 2, 60), (1, 2, 2, 10)):
    tp = TM[im] + 55000; o = C[im]
    row(f"NEWS K{K} sl{sl} tp{tpm} {hold}m", (tp, o + K + SP[im], o - K, np.full(len(im), sl, float), np.full(len(im), sl * tpm), tp + 6 * MS, tp + hold * MS))
    rs = np.random.default_rng(3); fake = rs.choice(np.flatnonzero(ok), len(im), replace=False); tp2 = TM[fake] + 55000; o2 = C[fake]
    row(f"  FAKE times K{K} sl{sl} tp{tpm} {hold}m", (tp2, o2 + K + SP[fake], o2 - K, np.full(len(fake), sl, float), np.full(len(fake), sl * tpm), tp2 + 6 * MS, tp2 + hold * MS))
# ---------- 4. Inside bar on M5 / M15 ----------
def inside(rule, tpm, hold, nexp=3):
    R = D.resample(rule).agg({"o": "first", "h": "max", "l": "min", "c": "last", "spread": "median"}).dropna()
    h, l = R.h.values, R.l.values; ins = (h[1:] < h[:-1]) & (l[1:] > l[:-1])
    i = np.flatnonzero(ins) + 1; idx = R.index[i]; hh = idx.hour + idx.minute / 60
    keep = (hh >= 1.5) & (hh < 22) & (idx.dayofweek < 5); i = i[keep]
    step = pd.Timedelta(rule).value // 10**6; tp = R.index.values[i].astype("datetime64[ms]").astype(np.int64) + step
    mh, ml = h[i - 1], l[i - 1]; rg = mh - ml
    return (tp, mh + R.spread.values[i] + 0.05, ml - 0.05, rg, tpm * rg, tp + nexp * step, tp + hold * MS)
print("== 4. INSIDE BAR: OCO at the mother bar's high / low, SL = mother range, TP tpm x SL, expire 3 bars")
for rule in ("5min", "15min"):
    for tpm, hold in ((1, 60), (2, 120), (0, 60), (0, 240)):
        row(f"INSIDE {rule} tp{tpm} {hold}m", inside(rule, tpm, hold))
pd.DataFrame(RES, columns=["rule", "n3", "pf3", "net3", "str3", "pfprev", "netprev"]).to_csv("oco138_res.csv", index=False)
