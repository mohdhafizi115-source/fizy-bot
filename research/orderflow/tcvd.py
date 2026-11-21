# broker tick-rule delta per server minute -> pickle
import numpy as np, pandas as pd
z = np.load('../ticks/xau.npz'); t = z['t']; m = (z['b'].astype(np.int64) + z['a']) 
d = np.diff(m, prepend=m[0]); s = np.sign(d)
# zero change: carry previous sign
idx = np.where(s != 0, np.arange(len(s)), 0); np.maximum.accumulate(idx, out=idx); s = s[idx]
mins = t // 60000
u, inv = np.unique(mins, return_inverse=True)
dl = np.bincount(inv, weights=s); n = np.bincount(inv)
S = pd.DataFrame({'d': dl, 'n': n}, index=pd.to_datetime(u * 60, unit='s'))
S.to_pickle('tickdelta.pkl'); print(S.head(), len(S), S.d.describe())
