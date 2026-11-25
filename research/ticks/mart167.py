# Round 167: the basket TARGET (owner: "kalau tp tetap dari 3 naik ke 5? atau ada lagi better? sebab ni sen"), engine mart166.
# Round 166: the six ways to space MART's layers (owner: "test semua point di atas tadi 1 - 6"):
# 1 fixed $, 2 standard deviation of M5 closes, 3 ADR (round 165), 4 % of price, 5 structure (add only at a new
# confirmed M5 fractal swing beyond the last entry), 6 distance + minimum time between adds.
# Engine mart166.c = mart165.c + tmin (s) + smode (structure adds). S / K / T / G scale with the unit (flex 3).
# $1000, unlimited layers k x 0.01, no SL, 24 h weekdays, swap, stop-out 40% of margin at 1:3000.
import ctypes, sys, numpy as np, pandas as pd
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("S", "K", "Tgt", "A", "T", "G", "Lk", "B0")] + [("mode", ctypes.c_int), ("flex", ctypes.c_int), ("tmin", ctypes.c_double), ("smode", ctypes.c_int)]
class R(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("net", "worstfl", "maxlots")] + [(k, ctypes.c_int) for k in ("baskets", "wins", "blown", "flips")] + [("blowt", ctypes.c_int64)]
lib = ctypes.CDLL("./mart166.so"); lib.sim.restype = ctypes.c_int
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
U = {"M5": atr_for(300), "ADR14": adr_for(14), "SD": spread_out(st5, sd), "PCT": (b / 100.0 / 100.0).astype(np.float32)}
for k, v in U.items(): print(f"{k}: median ${np.median(v):.2f}, p10 ${np.percentile(v,10):.2f}, p90 ${np.percentile(v,90):.2f}")
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = a3 - pd.Timedelta(days=91)
def idx(ts): return int(np.searchsorted(t, int(pd.Timestamp(ts).value // 10**6)))
def run(i0, i1, u="M5", **kw):
    d = dict(S=3, K=3, Tgt=3, A=3, T=1, G=-1, Lk=3, B0=1000, mode=0, flex=0, tmin=0, smode=0); d.update(kw); r = R(); at = U[u]
    lib.sim(t.ctypes.data_as(ctypes.c_void_p), b.ctypes.data_as(ctypes.c_void_p), a.ctypes.data_as(ctypes.c_void_p), at.ctypes.data_as(ctypes.c_void_p),
            SLO.ctypes.data_as(ctypes.c_void_p), SHI.ctypes.data_as(ctypes.c_void_p), ctypes.c_int64(i0), ctypes.c_int64(i1), ctypes.byref(P(**d)), ctypes.byref(r)); return r
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
print("--- live v2.68 FLEX (1 ATR M5 step / OCO), exit TP +T or the live trail (arm basket > +T, lock +T)")
for T in (1, 2, 3, 5, 8, 10, 15, 20):
    row(f"1 ATR(M5), TP +${T}", u="M5", flex=3, S=1, K=1, Tgt=T)
    row(f"1 ATR(M5), TRAIL arm/lock +${T}", u="M5", flex=3, S=1, K=1, mode=1, A=T, Lk=T, T=0.5, G=0.2)
print("--- fixed $3 step / OCO (v2.57), TP +T")
for T in (1, 3, 5, 10):
    row(f"fixed $3, TP +${T}", S=3, K=3, Tgt=T)
