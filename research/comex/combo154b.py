# Round 154d: is the walk-forward model's edge a TIMING artefact? Yahoo GC=F daily closes are the 13:30 ET settlement,
# GLD closes at 16:00 ET, so "GLD up more than GC" already contains gold's 13:30-16:00 move, which the next GC
# settlement-to-settlement return also contains. Re-score with a label that starts at the 16:00 ET hourly close.
import numpy as np, pandas as pd
def daily(k):
    d = pd.read_csv(f'data/tools/{k}_1d.csv'); d.index = pd.to_datetime(d.iloc[:, 0]).dt.tz_localize(None).dt.normalize(); return d.Close.astype(float)
h = pd.read_csv('data/tools/GOLD_1h.csv'); t = pd.to_datetime(h.iloc[:, 0], utc=True).dt.tz_convert('America/New_York')
h.index = t; c = h.Close.astype(float)
c16 = c[t.dt.hour.values == 15]; c16.index = c16.index.tz_localize(None).normalize()   # bar 15:00-16:00 ET -> close at 16:00 ET
c13 = c[t.dt.hour.values == 13]; c13.index = c13.index.tz_localize(None).normalize()   # close at 14:00 ET ~ just after settlement
gc, gld = daily('GOLD'), daily('GLD')
sig = (np.log(gld).diff() - np.log(gc).diff())             # GLD beyond GC = gold's move after settlement
nx_settle = np.log(gc).diff().shift(-1)
nx16 = np.log(c16).diff().shift(-1)                         # 16:00 ET -> next 16:00 ET (starts after GLD's close)
D = pd.DataFrame({'s': sig, 'a': nx_settle, 'b': nx16}).dropna(); D = D[D.index >= '2024-07-15']
pf = lambda p: p[p > 0].sum() / -p[p < 0].sum()
for lab, col in (('next settlement-to-settlement (Yahoo daily, what the model used)', 'a'), ('next 16:00 ET -> 16:00 ET (tradable after GLD closes)', 'b')):
    p = np.sign(D.s) * D[col]
    print(f'{lab}: {len(p)} days, corr {np.corrcoef(D.s, D[col])[0, 1]:+.3f}, follow PF {pf(p):.2f}, hit {np.mean(p > 0):.0%}')
