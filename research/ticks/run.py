import ctypes, numpy as np, pandas as pd, sys
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("D", "lock", "be", "T", "k", "step", "K", "tgt", "minstep", "spm")] + \
               [(k, ctypes.c_int) for k in ("mode", "timer_ms", "d1", "reset_min")]
lib = ctypes.CDLL("./ticksim.so")
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"]); n = len(t)
xt = np.zeros(2_000_000, np.int64); xp = np.zeros(2_000_000)
lib.sim.restype = ctypes.c_int
def run(**kw):
    d = dict(D=5, lock=1, be=0.5, T=1, k=2, step=0.5, K=3, tgt=25, minstep=0.10, spm=1.0, mode=1, timer_ms=1000, d1=1, reset_min=0); d.update(kw)
    p = P(**d)
    m = lib.sim(t.ctypes.data_as(ctypes.c_void_p), b.ctypes.data_as(ctypes.c_void_p), a.ctypes.data_as(ctypes.c_void_p),
                ctypes.c_int64(n), ctypes.byref(p), xt.ctypes.data_as(ctypes.c_void_p), xp.ctypes.data_as(ctypes.c_void_p))
    return pd.to_datetime(xt[:m], unit="ms"), xp[:m].copy()
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
def pf(v):
    g = v[v > 0].sum(); l = -v[v < 0].sum(); return g / l if l > 0 else 99.0
def st(te, p, lo, hi):
    m = (te >= lo) & (te < hi); v = p[m]
    if len(v) == 0: return "      no trades"
    dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min()
    return f"{len(v):5d} {len(v)/max(len(dp),1):4.0f} {100*(v>0).mean():3.0f}% {pf(v):5.2f} {v.sum():+6.0f} {dd:+5.0f} {dp.min():+5.0f} {v.max():+5.0f} {(dp<0).mean()*100:3.0f}%"
def row(lab, **kw):
    te, p = run(**kw); ts, ps = run(spm=1.5, **kw)
    ms = (ts >= a3)
    print(f"{lab:44s} | {st(te, p, a3, end + pd.Timedelta(days=1))} {pf(ps[ms]):5.2f} | {st(te, p, a6, a3)}", flush=True)
if __name__ == "__main__":
    sp = (a - b) / 100.0
    print(f"ticks {n:,}  {pd.Timestamp(t[0], unit='ms')} .. {end}  spread median ${np.median(sp):.2f} mean ${sp.mean():.2f} p95 ${np.percentile(sp,95):.2f}")
    print(f"last 3 months {a3:%Y-%m-%d} .. {end:%Y-%m-%d} | previous {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}; 0.01 lot, $25 target, D1 filter unless noted, EA timer 1 s")
    print(f"{'variant':44s} | {'trd':>5} {'/day':>4} {'win':>4} {'PF':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bigW':>5} {'loseD':>4} {'strs':>5} | previous: trd /day win PF net DD wDay bigW loseD")
    exec(open(sys.argv[1]).read())
