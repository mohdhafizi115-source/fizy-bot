# Round 154c: ALL tools together. Walk-forward logistic regression on COMEX gold (GC=F) daily:
# features = yesterday's return sign and size (z) of every tool, gold's own last 1 / 2 / 5 days, GVZ level change,
# gold/silver ratio z, weekday and turn-of-month; label = sign of GC's next close-to-close move.
# Train on all years before, test each year 2023-2026 out of sample. Controls: labels shuffled; always-long.
import numpy as np, pandas as pd
from numpy.linalg import solve
T = ['DXY', 'US10Y', 'TIP', 'GLD', 'GDX', 'SILVER', 'VIX', 'SPX', 'ES', 'EURUSD', 'USDJPY', 'COPPER', 'OIL', 'GVZ', 'IRX', 'FVX', 'N225', 'HSI', 'BTC', 'AUDUSD']
def daily(k):
    d = pd.read_csv(f'data/tools/{k}_1d.csv'); d.index = pd.to_datetime(d.iloc[:, 0]).dt.tz_localize(None).dt.normalize()
    return d.Close.astype(float).dropna()
gc = daily('GOLD'); r = np.log(gc).diff()
F = pd.DataFrame(index=gc.index)
for k in T:
    x = np.log(daily(k).clip(lower=1e-6)).diff().reindex(gc.index).ffill(limit=2)
    F[k] = x / x.rolling(60, min_periods=20).std()
F['g1'] = r / r.rolling(60, min_periods=20).std(); F['g2'] = r.rolling(2).sum() / r.rolling(60).std(); F['g5'] = r.rolling(5).sum() / r.rolling(60).std()
gs = np.log(gc / daily('SILVER').reindex(gc.index).ffill()); F['gsr'] = (gs - gs.rolling(60).mean()) / gs.rolling(60).std()
for wd in range(4): F[f'wd{wd}'] = (gc.index.dayofweek == wd).astype(float)
F['tom'] = (gc.index.day >= 26).astype(float) + (gc.index.day <= 3).astype(float)
import os
if os.environ.get('LABEL16'):   # tradable label: COMEX gold 16:00 ET -> next 16:00 ET (after every US close)
    h = pd.read_csv('data/tools/GOLD_1h.csv'); tt = pd.to_datetime(h.iloc[:, 0], utc=True).dt.tz_convert('America/New_York')
    c16 = pd.Series(h.Close.astype(float).values, index=tt)[tt.dt.hour.values == 15]; c16.index = c16.index.tz_localize(None).normalize()
    y = np.log(c16).diff().shift(-1).reindex(gc.index)
else:
    y = r.shift(-1)
D = F.join(y.rename('y')).dropna()
def fit(Xa, ya, lam=5.0):   # ridge-penalised logistic regression by Newton steps
    Xa = np.c_[np.ones(len(Xa)), Xa]; w = np.zeros(Xa.shape[1]); t = (ya > 0).astype(float)
    for _ in range(25):
        p = 1 / (1 + np.exp(-Xa @ w)); g = Xa.T @ (p - t) + lam * np.r_[0, w[1:]]
        Hm = (Xa * (p * (1 - p))[:, None]).T @ Xa + lam * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= solve(Hm, g)
    return w
def pf(p): g, l = p[p > 0].sum(), -p[p < 0].sum(); return g / l if l else 99
rng = np.random.default_rng(9)
print('Walk-forward, all tools together -> COMEX gold next day (gross, close-to-close)')
print(f'{"test year":9s} | days  hit   PF   | shuffled-label model PF (20 draws) median / 95th | always long PF')
for yr in ((2025, 2026) if os.environ.get('LABEL16') else (2023, 2024, 2025, 2026)):
    tr = D[D.index.year < yr]; te = D[D.index.year == yr]
    mu, sd = tr.iloc[:, :-1].mean(), tr.iloc[:, :-1].std().replace(0, 1)
    Xtr, Xte = ((tr.iloc[:, :-1] - mu) / sd).values, ((te.iloc[:, :-1] - mu) / sd).values
    w = fit(Xtr, tr.y.values); s = np.sign(np.c_[np.ones(len(Xte)), Xte] @ w); p = s * te.y.values
    sims = []
    for _ in range(20):
        w2 = fit(Xtr, rng.permutation(tr.y.values)); s2 = np.sign(np.c_[np.ones(len(Xte)), Xte] @ w2); sims.append(pf(s2 * te.y.values))
    print(f'{yr:9d} | {len(te):4d} {np.mean(p > 0):.0%} {pf(p):5.2f} | {np.median(sims):.2f} / {np.quantile(sims, 0.95):.2f} | {pf(te.y.values):.2f}')
w = fit(((D.iloc[:, :-1] - D.iloc[:, :-1].mean()) / D.iloc[:, :-1].std().replace(0, 1)).values, D.y.values)
print('\nfull-sample weights (largest 8, for reading only):')
for nm, v in sorted(zip(D.columns[:-1], w[1:]), key=lambda z: -abs(z[1]))[:8]: print(f'  {nm:7s} {v:+.3f}')
