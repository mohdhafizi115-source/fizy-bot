import ctypes, numpy as np, pandas as pd
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("A", "T", "G", "X")] + [("start", ctypes.c_int), ("seed", ctypes.c_int)]
lib = ctypes.CDLL("./trp162.so"); lib.sim.restype = ctypes.c_int
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"]); n = len(t)
xt = np.zeros(8_000_000, np.int64); xp = np.zeros(8_000_000)
def run(b=b, a=a, **kw):
    d = dict(A=1, T=1, G=0.5, X=5, start=0, seed=1); d.update(kw)
    m = lib.sim(t.ctypes.data_as(ctypes.c_void_p), b.ctypes.data_as(ctypes.c_void_p), a.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int64(n), ctypes.byref(P(**d)), xt.ctypes.data_as(ctypes.c_void_p), xp.ctypes.data_as(ctypes.c_void_p))
    return pd.to_datetime(xt[:m], unit="ms"), xp[:m].copy()
# stress: widen the spread by 50% around the mid
mid2 = (a.astype(np.int64) + b) ; sp = a - b
bs = np.ascontiguousarray(((mid2 - (sp * 1.5).astype(np.int64)) // 2).astype(np.int32)); as_ = np.ascontiguousarray(((mid2 + (sp * 1.5).astype(np.int64)) // 2).astype(np.int32))
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
def pf(v):
    g = v[v > 0].sum(); l = -v[v < 0].sum(); return g / l if l > 0 else 99.0
def st(te, p, lo, hi):
    m = (te >= lo) & (te < hi); v = p[m]
    if len(v) == 0: return "no trades"
    dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min()
    return f"{len(v):6d} {len(v)/max(len(dp),1):4.0f} {100*(v>0).mean():3.0f}% {pf(v):5.2f} {v.sum():+7.0f} {dd:+6.0f} {dp.min():+5.0f} {(dp<0).mean()*100:3.0f}%"
print(f"ticks {n:,} {pd.Timestamp(t[0],unit='ms')} .. {end}; last 3 months from {a3:%Y-%m-%d}, previous from {a6:%Y-%m-%d}; 0.01 lot")
print(f"{'variant':34s} | trades /day win  PF   net$    DD  wDay loseD strs | previous 3 months")
def row(lab, **kw):
    te, p = run(**kw); ts, ps = run(b=bs, a=as_, **kw)
    print(f"{lab:34s} | {st(te,p,a3,end+pd.Timedelta(days=1))} {pf(ps[ts>=a3]):5.2f} | {st(te,p,a6,a3)}", flush=True)
for X in (3, 5, 99):
    for A, T, G in ((1, 1, 0.5), (1, 0.5, 0.2), (1, 2, 0.5), (1, 3, 0.5), (2, 2, 0.5), (1, 1, 0.3), (1, 1, 0.8)):
        row(f"X{X} act+{A} trail{T} gap{G}", A=A, T=T, G=G, X=X)
print("controls (X5 act+1 trail1 gap0.5): start SELL / random")
row("start SELL", X=5, start=1)
for s in (1, 2, 3): row(f"start random seed{s}", X=5, start=2, seed=s)
