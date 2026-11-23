# Round 163: live MART + the video's trailing exit (owner: "kita gabungkan dengan teknik mart. kau calculate dekat mana
# nak letak stop bila sedang floating"). Engine mart163.c, real ticks, $1000 starts every 2nd weekday (blown count).
import ctypes, sys, numpy as np, pandas as pd
class P(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("S", "K", "Tgt", "A", "T", "G", "Lk", "B0")] + [("mode", ctypes.c_int)]
class R(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("net", "worstfl", "maxlots")] + [(k, ctypes.c_int) for k in ("baskets", "wins", "blown", "flips")] + [("blowt", ctypes.c_int64)]
lib = ctypes.CDLL("./mart163.so"); lib.sim.restype = ctypes.c_int
z = np.load("xau.npz"); t = np.ascontiguousarray(z["t"]); b = np.ascontiguousarray(z["b"]); a = np.ascontiguousarray(z["a"])
end = pd.Timestamp(t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = a3 - pd.Timedelta(days=91)
def idx(ts): return int(np.searchsorted(t, int(pd.Timestamp(ts).value // 10**6)))
def run(i0, i1, **kw):
    d = dict(S=3, K=3, Tgt=3, A=3, T=1, G=-1, Lk=1, B0=1000, mode=0); d.update(kw); r = R()
    lib.sim(t.ctypes.data_as(ctypes.c_void_p), b.ctypes.data_as(ctypes.c_void_p), a.ctypes.data_as(ctypes.c_void_p),
            ctypes.c_int64(i0), ctypes.c_int64(i1), ctypes.byref(P(**d)), ctypes.byref(r)); return r
starts = [d for d in pd.date_range(a6.normalize(), end.normalize() - pd.Timedelta(days=10), freq="B")][::2]
N = len(t)
def row(lab, **kw):
    blown = sum(run(idx(s), N, **kw).blown for s in starts)
    out = []
    for lo, hi in ((a3, end + pd.Timedelta(days=1)), (a6, a3)):
        r = run(idx(lo), min(idx(hi), N), **kw)
        bt = f" BLOWN {pd.Timestamp(r.blowt, unit='ms'):%d %b}" if r.blown else ""
        out.append(f"{r.baskets:5d} bsk win {100*r.wins/max(r.baskets,1):3.0f}% net {r.net:+7.0f} worstFl {r.worstfl:+6.0f} maxLot {r.maxlots/100:4.2f}{bt}")
    print(f"{lab:40s} | starts blown {blown:2d}/{len(starts)} | {out[0]} | prev {out[1]}", flush=True)
print(f"ticks to {end}; last 3 months from {a3:%Y-%m-%d}; $1000, step $3, OCO +-$3, unlimited layers, no SL, 24 h weekdays, swap in")
cells = [l.split("|") for l in sys.argv[1:]] if len(sys.argv) > 1 else None
row("LIVE: basket TP +$3", mode=0)
for A, T, G, Lk in ((3, 1, -1, 1), (3, 1, 0.5, 1), (5, 2, -1, 3), (5, 2, 0.5, 3), (10, 3, -1, 5), (10, 3, 1, 5), (3, 0.5, 0.2, 1), (5, 1, 0.5, 3)):
    row(f"TRAIL arm +${A} trail ${T} lock +${Lk} " + (f"flip ${G}" if G >= 0 else "no flip"), mode=1, A=A, T=T, G=G, Lk=Lk)
