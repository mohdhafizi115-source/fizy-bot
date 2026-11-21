# Round 151: does COMEX gold futures (GC=F, Yahoo) VOLUME predict the broker's gold move?
# Hourly features known at the close of the COMEX hour; forward = broker mid move from the next hour's open.
# Control: the feature shifted by a whole number of days (3..40), keeps its bias and daily pattern.
import numpy as np, pandas as pd, sys
rng = np.random.default_rng(3)
SC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'
h = pd.read_csv('data/comex/yahoo_gc_1h.csv'); h.index = pd.to_datetime(h.Datetime, utc=True).dt.tz_localize(None); h = h[~h.index.duplicated()]
h = h[h.Volume > 0]
hour = h.index.hour
# volume surprise: vs the median of the same UTC hour over the previous 20 sessions
h['vz'] = np.log(h.Volume) - np.log(h.Volume).groupby(hour).transform(lambda s: s.shift(1).rolling(20, min_periods=10).median())
h['ret'] = np.log(h.Close / h.Open)
rs = h.ret.rolling(500, min_periods=100).std().shift(1)
h['rz'] = h.ret / rs
F = pd.DataFrame(index=h.index)
F['vol_surprise'] = h.vz                                   # big volume -> bigger move? (sign-free, test |fwd|)
F['vol_x_dir'] = h.vz.clip(lower=0) * np.sign(h.ret)      # follow a high-volume hour
F['ret_hi_vol'] = h.rz.where(h.vz > 0.5)                   # hour return only when volume is high
F['ret_lo_vol'] = h.rz.where(h.vz < -0.5)                  # ... when volume is low
for W in (4, 8, 24):                                       # volume-weighted direction over W hours
    F[f'vwdir{W}'] = (h.ret * h.Volume).rolling(W).sum() / (h.Volume.rolling(W).sum() * rs)
    F[f'pvdiv{W}'] = np.sign(h.ret.rolling(W).sum()) * -h.vz.rolling(W).mean()   # price move on falling volume
X = pd.read_pickle(SC + 'ticks/xau_m1.pkl')
u = X.index.tz_localize('Europe/Athens', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC').tz_localize(None)
X = X[~u.isna()]; X.index = u[~u.isna()]; X = X[~X.index.duplicated()]
px = X.c; spread = X.spread.median()
L0 = px.index[-1] - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
t0 = F.index + pd.Timedelta(hours=1)                     # feature known at the end of the hour
p_at = lambda t: px.reindex(px.index.union(t)).ffill().reindex(t).values
p0 = p_at(t0)
print(f'COMEX GC hourly bars {len(h)} ({h.index.min()} .. {h.index.max()}), broker spread ~{spread:.2f}\n')
nflag = 0; ncell = 0
for H in (1, 4, 12, 24):
    fwd = pd.Series(p_at(t0 + pd.Timedelta(hours=H)) - p0, index=F.index)
    for c in F.columns:
        out = []
        for w0, w1 in ((L0, px.index[-1]), (P0, L0)):
            target = fwd.abs() if c == 'vol_surprise' else fwd
            m = (F.index >= w0) & (F.index < w1 - pd.Timedelta(hours=H)) & F[c].notna().values & target.notna().values
            z = F[c].values[m]; r = target.values[m]
            if m.sum() < 60: out = None; break
            ic = np.corrcoef(z, r)[0, 1]
            sims = []
            for k in rng.integers(3, 41, 40):
                zs = np.roll(F[c].values, int(k) * 23)[m]; ok = ~np.isnan(zs)
                sims.append(np.corrcoef(zs[ok], r[ok])[0, 1] if ok.sum() > 30 else 0.0)
            sims = np.nan_to_num(np.array(sims))
            q = np.quantile(z, [0.2, 0.8]); top = r[z >= q[1]].mean(); bot = r[z <= q[0]].mean()
            out.append((ic, np.mean(np.abs(sims) >= abs(ic)), top, bot, m.sum()))
        if out is None: continue
        ncell += 1
        (a, pa, ta, ba, na), (b, pb, tb, bb, nb) = out
        # sparse features (ret_hi/lo_vol) make the shifted control overlap too few rows, so also ask |t| >= 2 in both windows
        flag = np.sign(a) == np.sign(b) and pa <= 0.1 and pb <= 0.1 and abs(a) * np.sqrt(na) >= 2 and abs(b) * np.sqrt(nb) >= 2
        nflag += flag
        print(f'{c:13s} H{H:3d} | last n{na:5d} IC {a:+.3f} p {pa:.2f} top20% {ta:+6.2f} bot20% {ba:+6.2f} | '
              f'prev n{nb:5d} IC {b:+.3f} p {pb:.2f} {tb:+6.2f} {bb:+6.2f}{"  <==" if flag else ""}', flush=True)
print(f'\ncells {ncell}, flagged (same sign, p <= 0.1 in both windows) {nflag}')
# daily: COMEX day volume vs its 20-day mean, with the day's direction -> broker next day (01:30 -> 23:30 server)
d = pd.read_csv('data/comex/yahoo_gc_1d.csv'); d.index = pd.to_datetime(d.Date); d = d[d.Volume > 0]
d['vr'] = np.log(d.Volume / d.Volume.rolling(20).mean().shift(1)); d['dir'] = np.sign(d.Close - d.Open)
Xs = pd.read_pickle(SC + 'ticks/xau_m1.pkl'); day = Xs.index.normalize()
o = Xs.o[(Xs.index.hour * 60 + Xs.index.minute) >= 90].groupby(day[(Xs.index.hour * 60 + Xs.index.minute) >= 90]).first()
cl = Xs.c[(Xs.index.hour * 60 + Xs.index.minute) <= 1410].groupby(day[(Xs.index.hour * 60 + Xs.index.minute) <= 1410]).last()
nd = (cl - o).dropna()
print('\n=== DAILY: COMEX volume ratio x direction -> broker NEXT day 01:30-23:30 ($ per 0.01 lot = $ move)')
rows = []
for t, r in d.iterrows():
    nx = nd.index[nd.index > t]
    if len(nx) == 0 or np.isnan(r.vr): continue
    rows.append((t, r.vr, r.dir, nd[nx[0]]))
D = pd.DataFrame(rows, columns=['t', 'vr', 'dir', 'nx']).set_index('t')
for lab, w0, w1 in (('last', L0, px.index[-1]), ('prev', P0, L0)):
    s = D[(D.index >= w0) & (D.index < w1)]
    for nm, msk in (('high vol (vr>0.3)', s.vr > 0.3), ('normal', s.vr.abs() <= 0.3), ('low vol (vr<-0.3)', s.vr < -0.3)):
        x = s[msk]; f = (x.nx * x.dir)
        print(f'{lab} {nm:18s} days {len(x):3d}  next day WITH today: mean {f.mean():+6.2f}  hit {np.mean(f > 0) if len(x) else 0:.2f}')

# is the volume -> next-hour size effect more than the broker's own volatility clustering?
fwd = pd.Series(p_at(t0 + pd.Timedelta(hours=1)) - p0, index=F.index).abs()
own = pd.Series(p0 - p_at(F.index), index=F.index).abs()          # broker's own move in the same hour
print('\n=== vol_surprise vs the broker\'s own last-hour |move| -> next-hour |move|')
for lab, w0, w1 in (('last', L0, px.index[-1]), ('prev', P0, L0)):
    m = (F.index >= w0) & (F.index < w1) & F.vol_surprise.notna().values & fwd.notna().values & own.notna().values
    y, a, b = fwd.values[m], F.vol_surprise.values[m], own.values[m]
    A = np.c_[np.ones(m.sum()), b]; ry = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]; ra = a - A @ np.linalg.lstsq(A, a, rcond=None)[0]
    print(f'{lab}: corr(own,|next|) {np.corrcoef(b, y)[0,1]:+.3f}  corr(vol,|next|) {np.corrcoef(a, y)[0,1]:+.3f}  partial corr(vol,|next| | own) {np.corrcoef(ra, ry)[0,1]:+.3f}')
