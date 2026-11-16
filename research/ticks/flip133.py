import ctypes, numpy as np, pandas as pd, sys
sys.argv = ["x"]; src = open("run2.py").read().split('if __name__ == "__main__":')[0]
src = src.replace('ctypes.CDLL("./ticksim2.so")', 'ctypes.CDLL("./ticksim2b.so")')
exec(src)
xq = np.zeros(N)
def run3(**kw):
    d = dict(BASE); d.update(kw); p = P(**d); v = ctypes.c_void_p
    m = lib.sim(t.ctypes.data_as(v), b.ctypes.data_as(v), a.ctypes.data_as(v), ctypes.c_int64(n), ctypes.byref(p),
                xt.ctypes.data_as(v), xp.ctypes.data_as(v), xe.ctypes.data_as(v), xo.ctypes.data_as(v), xq.ctypes.data_as(v))
    q = xq[:m].copy()
    return pd.DataFrame({"t": pd.to_datetime(xe[:m], unit="ms"), "tx": pd.to_datetime(xt[:m], unit="ms"), "d": np.sign(q).astype(int), "e": np.abs(q), "net": xp[:m].copy()})
L = {"FLIP-A": dict(), "FLIP-B": dict(D=6, K=5), "FLIP-C": dict(D=5, K=8), "FLIP-D": dict(start_ms=8 * H)}
X = pd.concat([run3(**kw).assign(mod=k) for k, kw in L.items()]); X["sym"] = "XAUUSD"
X.to_pickle("flip133.pkl"); print(X.groupby("mod").net.agg(["count", "sum"]))
