# Round 150: does CVD (Binance gold / BTC perp, broker tick CVD) predict the broker's forward return?
# Control: the feature series circularly shifted by a random whole number of days (keeps its bias, autocorrelation
# and daily pattern, breaks the alignment with future prices).
import numpy as np, pandas as pd, glob, sys
rng = np.random.default_rng(5)
def binance(d):
    B = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(d + '/*.pkl'))]); B.index = pd.to_datetime(B.index * 60, unit='s')
    B = B[~B.index.duplicated()].sort_index(); full = pd.date_range(B.index[0], B.index[-1], freq='1min')
    return (B.bu - B.su).reindex(full).fillna(0.)
def to_utc(ix):
    u = ix.tz_localize('Europe/Athens', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC').tz_localize(None); return u
def feats(d):
    sd = d.rolling(1440, min_periods=300).std()
    F = {}
    for W in (15, 60, 240, 720, 1440): F[f'cvd{W}'] = d.rolling(W).sum() / (sd * np.sqrt(W))
    for nm, h, m in (('day', 0, 0), ('london', 7, 0), ('ny', 13, 30)):
        anchor = (d.index - pd.Timedelta(hours=h, minutes=m)).floor('D')
        cs = d.groupby(anchor).cumsum(); n = d.groupby(anchor).cumcount() + 1
        F[f'anch_{nm}'] = cs / (sd * np.sqrt(n))
    return pd.DataFrame(F).shift(1)   # known at the open of the minute
def run(label, d, px, spread):
    F = feats(d).reindex(px.index)
    Hs = (15, 60, 240, 720)
    fwd = {H: (px.shift(-H) - px) for H in Hs}
    L0 = px.index[-1] - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
    win = np.where(px.index >= L0, 'L', np.where(px.index >= P0, 'P', ''))
    # sample every 15 minutes to limit overlap
    samp = (px.index.minute % 15 == 0) & (win != '')
    print(f'\n=== {label}: spread ~{spread:.2f}, sample {samp.sum()} points', flush=True)
    for c in F.columns:
        for H in Hs:
            out = []
            for w in ('L', 'P'):
                m = samp & (win == w) & F[c].notna().values & fwd[H].notna().values
                z = F[c].values[m]; r = fwd[H].values[m]
                ic = np.corrcoef(z, r)[0, 1]
                hi = r[z >= 1.5].mean() if (z >= 1.5).sum() > 30 else np.nan
                lo = r[z <= -1.5].mean() if (z <= -1.5).sum() > 30 else np.nan
                edge = np.nanmean([hi, -lo]) if not (np.isnan(hi) and np.isnan(lo)) else np.nan  # follow the flow, $ per 0.01 lot*100
                # control: shift the feature by k days (k = 3..40), 30 draws
                sims = []
                zz_all = F[c].values
                for k in rng.integers(3, 41, 30):
                    zs = np.roll(zz_all, int(k) * 1440)[m]
                    sims.append(np.corrcoef(zs, r)[0, 1])
                sims = np.array(sims)
                out.append((ic, np.mean(np.abs(sims) >= abs(ic)), hi, lo, edge))
            (a, pa, ha, la, ea), (b, pb, hb, lb, eb) = out
            flag = ' <==' if (np.sign(a) == np.sign(b) and pa <= 0.1 and pb <= 0.1) else ''
            print(f'{c:12s} H{H:4d} | last IC {a:+.3f} p {pa:.2f} z>=1.5 {ha:+6.2f} z<=-1.5 {la:+6.2f} | prev IC {b:+.3f} p {pb:.2f} {hb:+6.2f} {lb:+6.2f}{flag}', flush=True)
X = pd.read_pickle('../ticks/xau_m1.pkl'); X.index = to_utc(X.index); X = X[X.index.notna()]; X = X[~X.index.duplicated()]
gold_px = X.c
dg = binance('min')
run('GOLD vs Binance XAUUSDT CVD', dg, gold_px, X.spread.median())
td = pd.read_pickle('tickdelta.pkl'); td.index = to_utc(td.index); td = td[td.index.notna()]; td = td[~td.index.duplicated()]
tdd = td.d.reindex(pd.date_range(td.index[0], td.index[-1], freq='1min')).fillna(0.)
run('GOLD vs BROKER tick CVD', tdd, gold_px, X.spread.median())
Bx = pd.read_csv('../m5_133/BTCUSD.csv'); Bx.index = to_utc(pd.to_datetime(Bx.t, unit='s')); Bx = Bx[Bx.index.notna()]; Bx = Bx[~Bx.index.duplicated()]
btc_px = Bx.c.resample('1min').last().ffill()
db = binance('bmin')
run('BTC vs Binance BTCUSDT CVD', db, btc_px, (Bx.s * 0.01).median())
