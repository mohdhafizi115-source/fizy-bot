# Round 165: MART with the layer step / OCO distance from the ADR (average daily range of the last N
# completed server days, high - low of the bid), instead of the M5 ATR (owner: "kau uji no 3 dulu").
# Engine mart165.c = mart164.c with flex 3: S / K / T / G scale with the unit, the trail arm A and lock Lk stay in $.
# $1000, unlimited layers k x 0.01, no SL, 24 h weekdays, swap, stop-out 40% of margin at 1:3000.
import ctypes, sys, numpy as np, pandas as pd
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("S", "K", "Tgt", "A", "T", "G", "Lk", "B0")] + [("mode", ctypes.c_int), ("flex", ctypes.c_int)]
class R(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("net", "worstfl", "maxlots")] + [(k, ctypes.c_int) for k in ("baskets", "wins", "blown", "flips")] + [("blowt", ctypes.c_int64)]
lib = ctypes.CDLL("./mart165.so"); lib.sim.restype = ctypes.c_int
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

U = {"M5": atr_for(300), "ADR5": adr_for(5), "ADR14": adr_for(14), "ADR20": adr_for(20)}
for k, v in U.items(): print(f"{k}: median ${np.median(v):.2f}, p10 ${np.percentile(v,10):.2f}, p90 ${np.percentile(v,90):.2f}")
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = a3 - pd.Timedelta(days=91)
def idx(ts): return int(np.searchsorted(t, int(pd.Timestamp(ts).value // 10**6)))
def run(i0, i1, u="M5", **kw):
    d = dict(S=3, K=3, Tgt=3, A=3, T=1, G=-1, Lk=3, B0=1000, mode=0, flex=0); d.update(kw); r = R(); at = U[u]
    lib.sim(t.ctypes.data_as(ctypes.c_void_p), b.ctypes.data_as(ctypes.c_void_p), a.ctypes.data_as(ctypes.c_void_p), at.ctypes.data_as(ctypes.c_void_p),
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
row("LIVE v2.57 fixed $3, TP +$3", mode=0)
row("LIVE v2.68 FLEX: 1 ATR(M5), TRAIL", u="M5", flex=3, mode=1, S=1, K=1, A=3, T=0.5, G=0.2, Lk=3)
row("1 ATR(M5), TP +$3", u="M5", flex=3, mode=0, S=1, K=1)
for u in ("ADR14", "ADR5", "ADR20"):
    fs = (0.03, 0.05, 0.075, 0.1, 0.15, 0.2) if u == "ADR14" else (0.05, 0.1)
    for f in fs:
        row(f"{u} x {f}, TP +$3", u=u, flex=3, mode=0, S=f, K=f)
        row(f"{u} x {f}, TRAIL", u=u, flex=3, mode=1, S=f, K=f, A=3, T=0.5 * f, G=0.2 * f, Lk=3)
