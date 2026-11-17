# Round 140 (part 2): news straddle trades (08:30 NY USD/CAD + 02:00 NY EUR/GBP release days, K $2, SL $3, 15 min) as a trade list
import sys; sys.argv = ["x"]
exec(open("oco139b.py").read().split('print(f"last 3 months')[0])
tt = sorted(set(slot(["USD", "CAD"], "08:30")[0]) | set(slot(["EUR", "GBP"], "02:00")[0]))
ev = mk(tt, 2, 3, 15); o = np.argsort(ev[0], kind="stable"); A = [np.ascontiguousarray(x[o]) for x in ev]
A = [A[0].astype(np.int64), A[1].astype(float), A[2].astype(float), A[3].astype(float), A[4].astype(float), A[5].astype(np.int64), A[6].astype(np.int64)]
m = lib.sim(t.ctypes.data_as(v), b.ctypes.data_as(v), a.ctypes.data_as(v), ctypes.c_int64(n), ctypes.c_int(len(A[0])), *[x.ctypes.data_as(v) for x in A], ctypes.c_int(0), ot.ctypes.data_as(v), op.ctypes.data_as(v), ox.ctypes.data_as(v), od.ctypes.data_as(v))
Zn = pd.DataFrame({"t": pd.to_datetime(ot[:m], unit="ms"), "tx": pd.to_datetime(ox[:m], unit="ms"), "net": op[:m].copy(), "mod": "NEWS", "sym": "XAUUSD"})
Zn.to_pickle("news140.pkl"); print(len(Zn), Zn.net.sum())
