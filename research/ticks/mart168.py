# Round 168: indicator gates to cut MART blow-ups WITHOUT a cut loss or a layer cap (owner: "cari cara macam mana nak reducekan,
# maybe kena pasang beberapa indikator lagi"): gate NEW baskets by regime (ADX, CHOP, BB width, ATR ratio, EMA 200 distance),
# gate ADDS by momentum (M5 / M15 candle back in favour, RSI not stretched / turning), slower lot schedules; random gates as controls.
# Round 166: the six ways to space MART's layers (owner: "test semua point di atas tadi 1 - 6"):
# 1 fixed $, 2 standard deviation of M5 closes, 3 ADR (round 165), 4 % of price, 5 structure (add only at a new
# confirmed M5 fractal swing beyond the last entry), 6 distance + minimum time between adds.
# Engine mart166.c = mart165.c + tmin (s) + smode (structure adds). S / K / T / G scale with the unit (flex 3).
# $1000, unlimited layers k x 0.01, no SL, 24 h weekdays, swap, stop-out 40% of margin at 1:3000.
import ctypes, sys, numpy as np, pandas as pd
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("S", "K", "Tgt", "A", "T", "G", "Lk", "B0")] + [("mode", ctypes.c_int), ("flex", ctypes.c_int), ("tmin", ctypes.c_double), ("smode", ctypes.c_int), ("lotmode", ctypes.c_int)]
class R(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("net", "worstfl", "maxlots")] + [(k, ctypes.c_int) for k in ("baskets", "wins", "blown", "flips")] + [("blowt", ctypes.c_int64)]
lib = ctypes.CDLL("./mart168.so"); lib.sim.restype = ctypes.c_int
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"]); N = len(t)

def atr_for(sec):
    bk = t // (sec * 1000); st = np.flatnonzero(np.r_[True, bk[1:] != bk[:-1]])
    hi = np.maximum.reduceat(b, st) / 100.0; lo = np.minimum.reduceat(b, st) / 100.0; cl = b[np.r_[st[1:] - 1, N - 1]] / 100.0
    pc = np.r_[cl[0], cl[:-1]]; tr = np.maximum(hi - lo, np.maximum(abs(hi - pc), abs(lo - pc)))
    at = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    at = np.r_[at[0], at[:-1]]
    out = np.empty(N, np.float32)
    for j in range(len(st)): out[st[j]:(st[j + 1] if j + 1 < len(st) else N)] = at[j]
    return out

day = t // 86400000; dst = np.flatnonzero(np.r_[True, day[1:] != day[:-1]])
dhi = np.maximum.reduceat(b, dst) / 100.0; dlo = np.minimum.reduceat(b, dst) / 100.0; drng = dhi - dlo
def adr_for(n):
    m = pd.Series(drng).rolling(n, min_periods=1).mean().values
    m = np.r_[m[0], m[:-1]]                       # completed days only: a day uses the ADR known at its open
    out = np.empty(N, np.float32)
    for j in range(len(dst)): out[dst[j]:(dst[j + 1] if j + 1 < len(dst) else N)] = m[j]
    return out

def bars(sec):
    bk = t // (sec * 1000); st = np.flatnonzero(np.r_[True, bk[1:] != bk[:-1]])
    hi = np.maximum.reduceat(b, st) / 100.0; lo = np.minimum.reduceat(b, st) / 100.0; cl = b[np.r_[st[1:] - 1, N - 1]] / 100.0
    return st, hi, lo, cl
def spread_out(st, v):
    out = np.empty(N, np.float32)
    for j in range(len(st)): out[st[j]:(st[j + 1] if j + 1 < len(st) else N)] = v[j]
    return out
st5, hi5, lo5, cl5 = bars(300)
sd = pd.Series(cl5).rolling(20, min_periods=5).std().bfill().values; sd = np.r_[sd[0], sd[:-1]]
# fractal n 2 on M5: bar j is a swing low if its low is below the 2 bars each side; known from the open of bar j + 3
slo_b = np.zeros(len(st5)); shi_b = np.zeros(len(st5)); cur_lo = 0.0; cur_hi = 0.0
for j in range(len(st5)):
    k = j - 3
    if k >= 2:
        if lo5[k] < lo5[k-1] and lo5[k] < lo5[k-2] and lo5[k] <= lo5[k+1] and lo5[k] <= lo5[k+2]: cur_lo = lo5[k]
        if hi5[k] > hi5[k-1] and hi5[k] > hi5[k-2] and hi5[k] >= hi5[k+1] and hi5[k] >= hi5[k+2]: cur_hi = hi5[k]
    slo_b[j] = cur_lo; shi_b[j] = cur_hi
SLO = spread_out(st5, slo_b); SHI = spread_out(st5, shi_b)
U = {"M5": atr_for(300)}
for k, v in U.items(): print(f"{k}: median ${np.median(v):.2f}, p10 ${np.percentile(v,10):.2f}, p90 ${np.percentile(v,90):.2f}")
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = a3 - pd.Timedelta(days=91)
def idx(ts): return int(np.searchsorted(t, int(pd.Timestamp(ts).value // 10**6)))
def run(i0, i1, u="M5", gn="one", ga="one", gs="one", **kw):
    d = dict(S=3, K=3, Tgt=3, A=3, T=1, G=-1, Lk=3, B0=1000, mode=0, flex=0, tmin=0, smode=0, lotmode=0); d.update(kw); r = R(); at = U[u]
    g1, g2, g3 = G[gn], G[ga], G[gs]
    lib.sim(t.ctypes.data_as(ctypes.c_void_p), b.ctypes.data_as(ctypes.c_void_p), a.ctypes.data_as(ctypes.c_void_p), at.ctypes.data_as(ctypes.c_void_p),
            SLO.ctypes.data_as(ctypes.c_void_p), SHI.ctypes.data_as(ctypes.c_void_p),
            g1.ctypes.data_as(ctypes.c_void_p), g2.ctypes.data_as(ctypes.c_void_p), g3.ctypes.data_as(ctypes.c_void_p),
            ctypes.c_int64(i0), ctypes.c_int64(i1), ctypes.byref(P(**d)), ctypes.byref(r)); return r
starts = [d for d in pd.date_range(a6.normalize(), end.normalize() - pd.Timedelta(days=10), freq="B")][::2]
def row(lab, **kw):
    blown = sum(run(idx(s), N, **kw).blown for s in starts)
    out = []
    for lo, hi in ((a3, end + pd.Timedelta(days=1)), (a6, a3)):
        r = run(idx(lo), min(idx(hi), N), **kw)
        bt = f" BLOWN {pd.Timestamp(r.blowt, unit='ms'):%d %b}" if r.blown else ""
        out.append(f"{r.baskets:5d} bsk win {100*r.wins/max(r.baskets,1):3.0f}% net {r.net:+7.0f} worstFl {r.worstfl:+6.0f} maxLot {r.maxlots/100:4.2f}{bt}")
    print(f"{lab:44s} | starts blown {blown:2d}/{len(starts)} | {out[0]} | prev {out[1]}", flush=True)

print("$1000, unlimited layers k x 0.01, no SL, 24 h weekdays, swap in. TRAIL = live v2.67 exit (arm at basket +$3, "
      "line max(price - 0.5 unit-step, basket +$3), flip stop 0.2 step inside)")

# ---------------- indicator gates (closed bars only: a bar's value is used from the NEXT bar's open)
def ohlc(sec):
    bk = t // (sec * 1000); st = np.flatnonzero(np.r_[True, bk[1:] != bk[:-1]])
    o = b[st] / 100.0; h = np.maximum.reduceat(b, st) / 100.0; l = np.minimum.reduceat(b, st) / 100.0; c = b[np.r_[st[1:] - 1, N - 1]] / 100.0
    return st, o, h, l, c
def to_ticks(st, v):           # v per bar = value at bar CLOSE -> usable from the next bar
    v = np.r_[v[0], v[:-1]]; out = np.empty(N, np.uint8)
    for j in range(len(st)): out[st[j]:(st[j + 1] if j + 1 < len(st) else N)] = v[j]
    return out
def wilder(x, n): return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values
def atr_(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]; return wilder(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc))), n)
def adx_(h, l, c, n=14):
    up = np.r_[0, np.diff(h)]; dn = np.r_[0, -np.diff(l)]
    pdm = np.where((up > dn) & (up > 0), up, 0); mdm = np.where((dn > up) & (dn > 0), dn, 0); at = atr_(h, l, c, n)
    pdi = 100 * wilder(pdm, n) / at; mdi = 100 * wilder(mdm, n) / at; dx = 100 * abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-9)
    return wilder(dx, n)
def rsi_(c, n=14):
    d = np.r_[0, np.diff(c)]; g = wilder(np.maximum(d, 0), n); ls = wilder(np.maximum(-d, 0), n); return 100 - 100 / (1 + g / np.maximum(ls, 1e-9))
G = {"one": np.ones(N, np.uint8)}
st15, o15, h15, l15, c15 = ohlc(900); st5, o5, h5, l5, c5 = ohlc(300); st60, o60, h60, l60, c60 = ohlc(3600)
adx15 = adx_(h15, l15, c15)
G["adx<20"] = to_ticks(st15, adx15 < 20); G["adx<25"] = to_ticks(st15, adx15 < 25)
tr15 = atr_(h15, l15, c15, 1); s14 = pd.Series(tr15).rolling(14).sum().values
rng = pd.Series(h15).rolling(14).max().values - pd.Series(l15).rolling(14).min().values
chop = 100 * np.log10(s14 / np.maximum(rng, 1e-9)) / np.log10(14); chop = np.nan_to_num(chop, nan=50)
G["chop>50"] = to_ticks(st15, chop > 50); G["chop>61.8"] = to_ticks(st15, chop > 61.8)
sd = pd.Series(c15).rolling(20).std().values; bbw = np.nan_to_num(4 * sd); med = pd.Series(bbw).rolling(500, min_periods=50).median().values
G["bbw<med"] = to_ticks(st15, bbw < np.nan_to_num(med, nan=1e9))
a60 = atr_(h60, l60, c60); ar = a60 / pd.Series(a60).rolling(480, min_periods=24).mean().values; ar = np.nan_to_num(ar, nan=1)
G["atrH1<1.2x"] = to_ticks(st60, ar < 1.2); G["atrH1<1.5x"] = to_ticks(st60, ar < 1.5)
e200 = pd.Series(c15).ewm(span=200, adjust=False).mean().values; a15 = atr_(h15, l15, c15)
G["ema200<2atr"] = to_ticks(st15, abs(c15 - e200) < 2 * a15); G["ema200<4atr"] = to_ticks(st15, abs(c15 - e200) < 4 * a15)
G["adx<25&chop>50"] = G["adx<25"] & G["chop>50"]
rs5 = rsi_(c5); rs15 = rsi_(c15)
G["b:M5bull"] = to_ticks(st5, c5 > o5); G["s:M5bear"] = to_ticks(st5, c5 < o5)
G["b:M15bull"] = to_ticks(st15, c15 > o15); G["s:M15bear"] = to_ticks(st15, c15 < o15)
G["b:rsi5>30"] = to_ticks(st5, rs5 > 30); G["s:rsi5<70"] = to_ticks(st5, rs5 < 70)
G["b:rsi15>30"] = to_ticks(st15, rs15 > 30); G["s:rsi15<70"] = to_ticks(st15, rs15 < 70)
G["b:rsi5up"] = to_ticks(st5, np.r_[0, np.diff(rs5)] > 0); G["s:rsi5dn"] = to_ticks(st5, np.r_[0, np.diff(rs5)] < 0)
rng0 = np.random.default_rng(7)
for k in ("rnd60a", "rnd60b"):   # random 1-hour blocks, about 60% allowed (the typical share of the regime gates)
    G[k] = to_ticks(st60, rng0.random(len(st60)) < 0.6)
for k in ("rndAddA", "rndAddB"):  # random M5 bars, 50% allowed
    G[k] = to_ticks(st5, rng0.random(len(st5)) < 0.5)
print("share of time allowed:", ", ".join(f"{k} {G[k].mean():.0%}" for k in G if k != "one"))
L = dict(u="M5", flex=3, S=1, K=1, mode=1, A=3, Lk=3, T=0.5, G=0.2)    # live v2.68
row("LIVE v2.68 (no gate)", **L)
print("--- A: NEW baskets only while the regime gate is open (an open basket keeps adding)")
for g in ("adx<20", "adx<25", "chop>50", "chop>61.8", "bbw<med", "atrH1<1.2x", "atrH1<1.5x", "ema200<2atr", "ema200<4atr", "adx<25&chop>50", "rnd60a", "rnd60b"):
    row(f"new only if {g}", gn=g, **L)
print("--- B: ADD a layer only when momentum agrees (buy basket / sell basket)")
for gb, gs_ in (("b:M5bull", "s:M5bear"), ("b:M15bull", "s:M15bear"), ("b:rsi5>30", "s:rsi5<70"), ("b:rsi15>30", "s:rsi15<70"), ("b:rsi5up", "s:rsi5dn"), ("rndAddA", "rndAddB")):
    row(f"add only if {gb} / {gs_}", ga=gb, gs=gs_, **L)
print("--- C: slower lot schedule (no cap): flat 1,1,1.. / 1,1,2,2,3,3.. / 1,1,1,2,3,4..")
for m, nm in ((1, "flat 0.01"), (2, "1,1,2,2,3,3"), (3, "1,1,1,2,3,4")):
    row(f"lots {nm}", lotmode=m, **L)
    row(f"lots {nm}, TP +$3", u="M5", flex=3, S=1, K=1, lotmode=m)
