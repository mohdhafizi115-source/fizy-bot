# Round 147: Binance XAUUSDT order flow (aggressor side) -> trade broker XAUUSD M1
import pandas as pd, numpy as np, glob
rng = np.random.default_rng(7)
B = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob('bmin/*.pkl'))])
B.index = pd.to_datetime(B.index * 60, unit='s')
B = B[~B.index.duplicated()]
X = pd.read_csv('../m5_133/BTCUSD.csv'); X.index = pd.to_datetime(X.t, unit='s'); X['spread'] = X.s * 0.01
B = B.resample('5min').agg({'o':'first','h':'max','l':'min','c':'last','bu':'sum','su':'sum','n':'sum', **{c:'sum' for c in B.columns if c[:2] in ('bb','sb')}}).dropna(subset=['c'])
xu = X.index.tz_localize('Europe/Athens', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC').tz_localize(None)
X = X[~xu.isna()].copy(); X.index = xu[~xu.isna()]; X = X[~X.index.duplicated()]
srv_min = (X.index + (X.index.tz_localize('UTC').tz_convert('Europe/Athens').tz_localize(None) - X.index)).hour * 60 \
          + X.index.minute  # not used for tz, recomputed below
srv = X.index.tz_localize('UTC').tz_convert('Europe/Athens')
X['sm'] = srv.hour * 60 + srv.minute
D = B.reindex(X.index)  # binance minute aligned to broker bar (same UTC minute)
D = D.fillna({c: 0. for c in D.columns if c not in 'ohlc'})
d = (D.bu - D.su).values; v = (D.bu + D.su).values
sd = pd.Series(d).rolling(288, min_periods=60).std().shift(1).values
vm = pd.Series(v).rolling(288, min_periods=60).mean().shift(1).values
dz = d / sd
rngb = (D.h - D.l).values; atrb = pd.Series(rngb).rolling(48, min_periods=20).mean().shift(1).values
bodyb = (D.c - D.o).values
o = X.o.values; c = X.c.values; sp = X.spread.values; sm = X.sm.values
idx = X.index
N = len(X)
# minute gaps: entry must be the next bar 1 minute later
nxt_ok = np.r_[(np.diff(idx.values).astype('timedelta64[m]').astype(int) == 5), False]
okt = (sm >= 90) & (sm <= 23 * 60 + 30)  # skip rollover

L0, L1 = pd.Timestamp('2026-08-17'), pd.Timestamp('2026-11-18')
P0 = pd.Timestamp('2026-05-17')

def run(sig, H):
    """sig: array of +1/-1/0 at bar t (closed). enter open t+1, exit open t+1+H. one at a time."""
    res = []; busy = -1
    for t in np.flatnonzero(sig):
        if t <= busy or t + 1 + H >= N or not nxt_ok[t] or not okt[t]: continue
        e, x = t + 1, t + 1 + H
        if (idx[x] - idx[e]).total_seconds() > (5*H + 30) * 60: continue
        s = sig[t]
        pnl = ((o[x] - o[e]) * s - sp[e]) * 0.01
        res.append((idx[e], s, pnl, (o[x] - o[e]) * 0.01)); busy = x
    return pd.DataFrame(res, columns=['t', 's', 'p', 'mv'])

def st(r):
    if len(r) == 0: return '0'
    g = r.p[r.p > 0].sum(); l = -r.p[r.p < 0].sum()
    pf = g / l if l > 0 else 99
    day = r.groupby(r.t.dt.date).p.sum()
    eq = r.p.cumsum(); dd = (eq - eq.cummax()).min()
    return f'{len(r):4d} PF {pf:4.2f} ${r.p.sum():+7.0f} DD {dd:+5.0f} wd {day.min():+4.0f}'

def rnd(r):
    if len(r) == 0: return 'n/a'
    pfs = []
    for k in range(5):
        s = rng.choice([-1, 1], len(r)); p = r.mv * s - (r.mv * r.s - r.p)
        g = p[p > 0].sum(); l = -p[p < 0].sum(); pfs.append(g / l if l else 99)
    return f'{min(pfs):.2f}-{max(pfs):.2f}'

def show(name, sig):
    for H in (1, 3, 6, 12):
        for flip, lab in ((1, 'follow'), (-1, 'fade')):
            r = run(sig * flip, H)
            a = r[(r.t >= L0) & (r.t < L1)]; b = r[(r.t >= P0) & (r.t < L0)]
            print(f'{name:34s} {lab:6s} H{H:2d} | last {st(a)} rnd {rnd(a)} | prev {st(b)} rnd {rnd(b)}', flush=True)

print('bars', N, 'binance minutes matched', np.isfinite(D.c.values).sum())
# A: big taker orders (same-ms aggregate) net side
for k in (250, 1000, 2000, 5000):
    nb = (D[f'bb{k}'] - D[f'sb{k}']).values
    for mult in (1, 2):
        thr = k * 1e3 * mult
        sig = np.where(nb >= thr, 1, np.where(nb <= -thr, -1, 0))
        show(f'A big>={k}k net>={thr/1e3:.0f}k', sig)
# B: delta z extreme
for z in (3, 4, 5):
    sig = np.where(dz >= z, 1, np.where(dz <= -z, -1, 0))
    show(f'B delta z>={z}', sig)
# C: absorption: big delta but binance body small (sign = aggressor side; fade = against aggressors)
for z in (2.5, 3, 4):
    for bf in (0.2, 0.4):
        ab = (np.abs(dz) >= z) & (np.abs(bodyb) <= bf * atrb) & (v >= 2 * vm)
        sig = np.where(ab, np.sign(d), 0).astype(int)
        show(f'C absorb z>={z} body<={bf}atr', sig)
# C2: price moved one way, delta the other (divergent bar) -> follow the delta
for z in (2, 3):
    dv = (np.abs(dz) >= z) & (np.sign(bodyb) == -np.sign(d)) & (np.abs(bodyb) >= 0.3 * atrb)
    show(f'C2 divergent bar z>={z} (sign=delta)', np.where(dv, np.sign(d), 0).astype(int))
# D: 30-min CVD vs 30-min price
for W in (3, 6, 12):
    cd = pd.Series(d).rolling(W).sum().values
    cds = pd.Series(d).rolling(288, min_periods=60).std().shift(1).values * np.sqrt(W)
    pm = pd.Series(D.c.values).diff(W).values
    pms = pd.Series(D.c.values).diff().rolling(288, min_periods=60).std().shift(1).values * np.sqrt(W)
    for z in (1.5, 2.5):
        dv = (np.abs(cd / cds) >= z) & (np.sign(pm) == -np.sign(cd)) & (np.abs(pm / pms) >= 1)
        show(f'D cvd{W} z>={z} vs price (sign=cvd)', np.where(dv, np.sign(cd), 0).astype(int))
