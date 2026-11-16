import sys, numpy as np, pandas as pd, subprocess
Z = sys.argv[1]; out = sys.argv[2]
p = subprocess.Popen(["unzip", "-p", Z], stdout=subprocess.PIPE)
T = []; B = []; A = []; lb = np.nan; la = np.nan; n = 0
for ch in pd.read_csv(p.stdout, sep="\t", usecols=[0, 1, 2, 3], names=["d", "t", "b", "a"], header=0,
                      dtype={"d": str, "t": str, "b": "float64", "a": "float64"}, chunksize=4_000_000):
    ts = pd.to_datetime(ch.d + " " + ch.t, format="%Y.%m.%d %H:%M:%S.%f").values.astype("datetime64[ms]").astype(np.int64)
    b = ch.b.values.copy(); a = ch.a.values.copy()
    if np.isnan(b[0]): b[0] = lb
    if np.isnan(a[0]): a[0] = la
    b = pd.Series(b).ffill().values; a = pd.Series(a).ffill().values
    lb = b[-1]; la = a[-1]
    T.append(ts); B.append(np.round(b * 100).astype(np.int32)); A.append(np.round(a * 100).astype(np.int32))
    n += len(ts); print(n, pd.Timestamp(ts[-1], unit="ms"), flush=True)
np.savez(out, t=np.concatenate(T), b=np.concatenate(B), a=np.concatenate(A))
