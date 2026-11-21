import numpy as np, pandas as pd, glob
exec(open('cvd150b.py').read().split("Bx = pd.read_csv")[0])
Bx = pd.read_csv('../m5_133/BTCUSD.csv'); Bx.index = to_utc(pd.DatetimeIndex(pd.to_datetime(Bx.t, unit='s'))); Bx = Bx[Bx.index.notna()]; Bx = Bx[~Bx.index.duplicated()]
px = Bx.c.resample('1min').last().ffill()
db = binance('bmin').reindex(px.index).fillna(0.)
cvd = (db.rolling(1440).sum() / (db.rolling(1440, min_periods=300).std() * np.sqrt(1440))).shift(1)
rs = px.diff().rolling(1440, min_periods=300).std()
mom = (px.diff(1440) / (rs * np.sqrt(1440))).shift(1)
fwd = px.shift(-720) - px
L0 = px.index[-1] - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
s = px.index.minute % 15 == 0
print('corr(cvd1440 z, price 24h z) all', round(cvd[s].corr(mom[s]), 3))
for nm, a, b in (('L', L0, px.index[-1]), ('P', P0, L0)):
    m = s & (px.index >= a) & (px.index < b) & cvd.notna() & mom.notna() & fwd.notna()
    c, p, f = cvd[m], mom[m], fwd[m]
    # residual of cvd after price momentum
    beta = np.polyfit(p, c, 1); res = c - np.polyval(beta, p)
    print(nm, 'IC cvd', round(np.corrcoef(c, f)[0,1], 3), 'IC mom', round(np.corrcoef(p, f)[0,1], 3), 'IC cvd|mom resid', round(np.corrcoef(res, f)[0,1], 3),
          'corr cvd/mom', round(np.corrcoef(c, p)[0,1], 3))
