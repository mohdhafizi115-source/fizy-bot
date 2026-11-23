# Round 164: MART with FLEXIBLE distances (owner: "jangan tetapkan sl dan stop. kau adjust la jadi flexible"):
# the OCO distance, the layer step, the trail arm / distance and the opposite stop scale with the live ATR(14)
# of closed M5 or H1 bars (Wilder), recomputed on every tick. Engine mart164.c (= mart163.c with flex).
import ctypes, sys, numpy as np, pandas as pd
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("S", "K", "Tgt", "A", "T", "G", "Lk", "B0")] + [("mode", ctypes.c_int), ("flex", ctypes.c_int)]
class R(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("net", "worstfl", "maxlots")] + [(k, ctypes.c_int) for k in ("baskets", "wins", "blown", "flips")] + [("blowt", ctypes.c_int64)]
lib = ctypes.CDLL("./mart164.so"); lib.sim.restype = ctypes.c_int
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"]); N = len(t)
def atr_for(sec):
    bk = t // (sec * 1000); st = np.flatnonzero(np.r_[True, bk[1:] != bk[:-1]])
    hi = np.maximum.reduceat(b, st) / 100.0; lo = np.minimum.reduceat(b, st) / 100.0; cl = b[np.r_[st[1:] - 1, N - 1]] / 100.0
    pc = np.r_[cl[0], cl[:-1]]; tr = np.maximum(hi - lo, np.maximum(abs(hi - pc), abs(lo - pc)))
    at = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    at = np.r_[at[0], at[:-1]]   # closed bars only: a bar uses the ATR known at its open
    out = np.empty(N, np.float32)
    for j in range(len(st)): out[st[j]:(st[j + 1] if j + 1 < len(st) else N)] = at[j]
    return out
ATR = {"M5": atr_for(300), "H1": atr_for(3600)}
for k, v in ATR.items(): print(f"ATR {k}: median ${np.median(v):.2f}, p10 ${np.percentile(v,10):.2f}, p90 ${np.percentile(v,90):.2f}")
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = a3 - pd.Timedelta(days=91)
def idx(ts): return int(np.searchsorted(t, int(pd.Timestamp(ts).value // 10**6)))
def run(i0, i1, tf="M5", **kw):
    d = dict(S=3, K=3, Tgt=3, A=3, T=1, G=-1, Lk=1, B0=1000, mode=0, flex=0); d.update(kw); r = R(); at = ATR[tf]
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
    print(f"{lab:46s} | starts blown {blown:2d}/{len(starts)} | {out[0]} | prev {out[1]}", flush=True)
print(f"$1000, unlimited layers k x 0.01, no SL, 24 h weekdays, swap in; distances x ATR(14) of closed bars")
DONE = int(sys.argv[1]) if len(sys.argv) > 1 else 0   # rows already printed (resume)
_n = [0]
_row = row
def row(lab, **kw):
    _n[0] += 1
    if _n[0] > DONE: _row(lab, **kw)
row("LIVE fixed $3 / TP +$3", mode=0)
for tf in ("M5", "H1"):
    ks = (1, 1.5, 2, 3, 4) if tf == "M5" else (0.3, 0.5, 0.75, 1)
    for k in ks:
        row(f"{tf} step=OCO={k} ATR, TP +$3", tf=tf, flex=1, mode=0, S=k, K=k)
        row(f"{tf} step=OCO={k} ATR, TP +{k} ATR $", tf=tf, flex=2, mode=0, S=k, K=k, Tgt=k)
        row(f"{tf} step=OCO={k} ATR, trail arm {k} / {k/2} ATR, flip {k/5:.2f}", tf=tf, flex=1, mode=1, S=k, K=k, A=k, T=k / 2, G=k / 5, Lk=1)
