import ctypes, numpy as np, pandas as pd, sys
DF = ("D", "lock", "K", "spm", "tgt", "minstep", "be_at", "be_off", "pyr_at", "minbody", "maxbody")
IF = ("timer_ms", "maxn", "cut_ms", "start_ms", "end_ms", "tstop_min", "pyr_max", "re_mode", "cool_min", "d1", "flip_dir", "big_mode", "rnd_pct", "seed")
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in DF] + [(k, ctypes.c_int) for k in IF]
lib = ctypes.CDLL("./ticksim2.so")
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"]); n = len(t)
N = 2_000_000; xt = np.zeros(N, np.int64); xp = np.zeros(N); xe = np.zeros(N, np.int64); xo = np.zeros(N, np.int32)
lib.sim.restype = ctypes.c_int
H = 3600000
BASE = dict(D=4, lock=1, K=3, spm=1.0, tgt=25, minstep=0.10, be_at=0, be_off=0.5, pyr_at=0, minbody=0, maxbody=0, timer_ms=1000, maxn=0,
            cut_ms=0, start_ms=int(1.5 * H), end_ms=int(23.5 * H), tstop_min=0, pyr_max=0, re_mode=0, cool_min=0, d1=1, flip_dir=0, big_mode=0, rnd_pct=0, seed=0)
def run(**kw):
    d = dict(BASE); d.update(kw); p = P(**d); v = ctypes.c_void_p
    m = lib.sim(t.ctypes.data_as(v), b.ctypes.data_as(v), a.ctypes.data_as(v), ctypes.c_int64(n), ctypes.byref(p),
                xt.ctypes.data_as(v), xp.ctypes.data_as(v), xe.ctypes.data_as(v), xo.ctypes.data_as(v))
    return pd.to_datetime(xt[:m], unit="ms"), xp[:m].copy(), pd.to_datetime(xe[:m], unit="ms"), xo[:m].copy()
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
def pf(v):
    g = v[v > 0].sum(); l = -v[v < 0].sum(); return g / l if l > 0 else 99.0
def st(te, p, lo, hi):
    m = (te >= lo) & (te < hi); v = p[m]
    if len(v) == 0: return "      no trades"
    dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min()
    return f"{len(v):5d} {len(v)/max(len(dp),1):4.1f} {100*(v>0).mean():3.0f}% {pf(v):5.2f} {v.sum():+6.0f} {dd:+5.0f} {dp.min():+5.0f} {v.max():+5.0f} {(dp<0).mean()*100:3.0f}%"
def row(lab, **kw):
    te, p, _, _ = run(**kw); ts, ps, _, _ = run(**dict(kw, spm=1.5))
    print(f"{lab:44s} | {st(te, p, a3, end + pd.Timedelta(days=1))} {pf(ps[ts >= a3]):5.2f} | {st(te, p, a6, a3)}", flush=True)
if __name__ == "__main__":
    print(f"last 3 months {a3:%Y-%m-%d} .. {end:%Y-%m-%d} | previous {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}; 0.01 lot; base = FROZEN D $4, lock +$1, K $3, D1 filter, $25 target")
    print(f"{'variant':44s} | {'trd':>5} {'/day':>4} {'win':>4} {'PF':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bigW':>5} {'loseD':>4} {'strs':>5} | previous: trd /day win PF net DD wDay bigW loseD")
    exec(open(sys.argv[1]).read())
