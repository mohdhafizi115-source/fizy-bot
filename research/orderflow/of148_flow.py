# Round 148: Binance order flow as a FILTER on every module's real trade list.
# Features use only Binance minutes that closed BEFORE the entry minute.
import pandas as pd, numpy as np, glob
import os
PLACEBO = int(os.environ.get('PLACEBO','0'))
rng = np.random.default_rng(11 + PLACEBO)
SC = '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'

def load_flow(d, big):
    B = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(SC + 'of/' + d + '/*.pkl'))])
    B.index = pd.to_datetime(B.index * 60, unit='s'); B = B[~B.index.duplicated()].sort_index()
    full = pd.date_range(B.index[0], B.index[-1], freq='1min')
    B = B.reindex(full)
    for c in B.columns:
        if c not in ('o', 'h', 'l', 'c'): B[c] = B[c].fillna(0.)
    B['c'] = B.c.ffill()
    B['d'] = B.bu - B.su; B['v'] = B.bu + B.su
    B['nb'] = B[f'bb{big}'] - B[f'sb{big}']
    sd1 = B.d.rolling(1440, min_periods=300).std()
    vm = B.v.rolling(1440, min_periods=300).mean()
    rs = B.c.diff().rolling(1440, min_periods=300).std()
    F = pd.DataFrame(index=B.index)
    for W in (5, 15, 30, 60, 240):
        F[f'dz{W}'] = B.d.rolling(W).sum() / (sd1 * np.sqrt(W))
        F[f'pz{W}'] = B.c.diff(W) / (rs * np.sqrt(W))
        F[f'va{W}'] = B.v.rolling(W).mean() / vm
    for W in (15, 60, 240):
        F[f'bg{W}'] = B.nb.rolling(W).sum()
    day = B.index.floor('D')
    F['cvdday'] = B.d.groupby(day).cumsum() / (sd1 * np.sqrt(B.groupby(day).cumcount() + 1))
    return F.shift(1)  # value at minute m = info up to the close of minute m-1

def to_utc(t):
    t = pd.DatetimeIndex(t).floor('1min')
    u = t.tz_localize('Europe/Athens', ambiguous='NaT', nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    return u

