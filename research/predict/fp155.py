# Round 155: can ANY combination of tools call the next $3 move (+$3 or -$3 first, within 4 h) with a high win rate?
# This is exactly MART's question: a basket opened on the right side closes at +$3 without adding a layer.
# Features known before minute t: broker gold (momentum, EMA distance, RSI, range, spread, hour, weekday), broker tick-rule CVD,
# Binance XAUUSDT order flow (delta, CVD, big takers, activity), Binance BTCUSDT returns and delta.
# Gradient boosting trained on one 3-month window, tested on the other (both ways). Win rate by confidence slice,
# against: 50%, always-the-training-majority-side, and the same model trained on shuffled labels.
import numpy as np, pandas as pd, glob, sys
from sklearn.ensemble import HistGradientBoostingClassifier
SC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'
import os
K, HOR, STEP = float(os.environ.get("K", 3)), int(os.environ.get("HOR", 240)), int(os.environ.get("STEP", 5))
X = pd.read_pickle(SC + 'ticks/xau_m1.pkl')
u = X.index.tz_localize('Europe/Athens', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC').tz_localize(None)
X = X[~u.isna()]; X.index = u[~u.isna()]; X = X[~X.index.duplicated()].sort_index()
o, h, l, c = X.o.values, X.h.values, X.l.values, X.c.values; N = len(X)
# label: first passage of +K / -K from the bar's open within HOR bars (bars spanning both -> dropped)
lab = np.full(N, np.nan); idx = np.arange(0, N - HOR, STEP)
for i in idx:
    p = o[i]; up = np.flatnonzero(h[i:i + HOR] >= p + K); dn = np.flatnonzero(l[i:i + HOR] <= p - K)
    a = up[0] if len(up) else 10**9; b = dn[0] if len(dn) else 10**9
    if a == b: continue
    lab[i] = 1.0 if a < b else 0.0
F = pd.DataFrame(index=X.index)
cs = X.c; atr = (X.h - X.l).rolling(60).mean()
for W in (1, 5, 15, 60, 240): F[f'r{W}'] = (cs.shift(1) - cs.shift(1 + W)) / atr.shift(1)
for W in (50, 200, 1000): F[f'ema{W}'] = (cs.shift(1) - cs.shift(1).ewm(span=W).mean()) / atr.shift(1)
d = cs.diff(); up_ = d.clip(lower=0).ewm(alpha=1 / 14).mean(); dn_ = (-d.clip(upper=0)).ewm(alpha=1 / 14).mean()
F['rsi'] = (100 - 100 / (1 + up_ / dn_)).shift(1)
F['atr'] = atr.shift(1); F['atrr'] = (atr / atr.rolling(1440).mean()).shift(1); F['spr'] = X.spread.shift(1)
F['hour'] = X.index.hour + X.index.minute / 60; F['wd'] = X.index.dayofweek
dayo = cs.groupby(X.index.normalize()).transform('first'); F['fromopen'] = (cs.shift(1) - dayo) / atr.shift(1)
hi = X.h.groupby(X.index.normalize()).cummax().shift(1); lo = X.l.groupby(X.index.normalize()).cummin().shift(1)
F['posday'] = (cs.shift(1) - lo) / (hi - lo + 1e-9)
td = pd.read_pickle(SC + 'of/tickdelta.pkl'); tu = td.index.tz_localize('Europe/Athens', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC').tz_localize(None)
td = td[~tu.isna()]; td.index = tu[~tu.isna()]; td = td[~td.index.duplicated()].d.reindex(X.index).fillna(0)
for W in (5, 15, 60, 240): F[f'tcvd{W}'] = (td.rolling(W).sum() / (td.rolling(1440, min_periods=300).std() * np.sqrt(W))).shift(1)
def binance(dn):
    B = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(SC + 'of/' + dn + '/*.pkl'))]); B.index = pd.to_datetime(B.index * 60, unit='s')
    return B[~B.index.duplicated()].sort_index()
B = binance('min').reindex(X.index); dl = (B.bu - B.su).fillna(0); vol = (B.bu + B.su).fillna(0)
sd = dl.rolling(1440, min_periods=300).std()
for W in (1, 5, 15, 60, 240): F[f'bd{W}'] = (dl.rolling(W).sum() / (sd * np.sqrt(W))).shift(1)
F['bcvd'] = (dl.groupby(X.index.normalize()).cumsum() / (sd * np.sqrt(dl.groupby(X.index.normalize()).cumcount() + 1))).shift(1)
for W in (15, 60): F[f'bact{W}'] = (vol.rolling(W).mean() / vol.rolling(1440, min_periods=300).mean()).shift(1)
for k in (250, 1000):
    nb = (B[f'bb{k}'] - B[f'sb{k}']).fillna(0); F[f'big{k}_60'] = nb.rolling(60).sum().shift(1) / 1e6
Bb = binance('bmin').reindex(X.index); bc = Bb.c.ffill(); bdl = (Bb.bu - Bb.su).fillna(0)
for W in (5, 15, 60, 240): F[f'btc{W}'] = (np.log(bc).diff(W)).shift(1) / np.log(bc).diff().rolling(1440, min_periods=300).std().shift(1) / np.sqrt(W)
F['btcd60'] = (bdl.rolling(60).sum() / (bdl.rolling(1440, min_periods=300).std() * np.sqrt(60))).shift(1)
F['y'] = lab
S = F[F.y.notna()].dropna()
srv = S.index.tz_localize('UTC').tz_convert('Europe/Athens').tz_localize(None)
mm = srv.hour * 60 + srv.minute; S = S[(mm >= 90) & (mm <= 1425) & (srv.dayofweek < 5)]
end = S.index[-1]; L0 = end - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
Lw, Pw = S[S.index >= L0], S[(S.index >= P0) & (S.index < L0)]
cols = [c_ for c_ in S.columns if c_ != 'y']
print(f'samples every {STEP} min, label = +${K:.0f} before -${K:.0f} within {HOR} min; features {len(cols)}')
print(f'last 3 months {len(Lw)} samples, up-first {Lw.y.mean():.1%} | previous 3 months {len(Pw)}, up-first {Pw.y.mean():.1%}\n')
rng = np.random.default_rng(0)
def slices(p, y):
    conf = np.abs(p - 0.5); side = (p > 0.5).astype(float); hit = (side == y)
    out = [f'all {hit.mean():.1%}']
    for q in (0.5, 0.2, 0.1, 0.05, 0.01):
        m = conf >= np.quantile(conf, 1 - q); out.append(f'top{int(q * 100)}% {hit[m].mean():.1%} (n {m.sum()})')
    return ' | '.join(out)
for tr_nm, tr, te_nm, te in (('previous', Pw, 'last', Lw), ('last', Lw, 'previous', Pw)):
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0)
    m.fit(tr[cols].values, tr.y.values); p = m.predict_proba(te[cols].values)[:, 1]
    maj = float(tr.y.mean() > 0.5)
    print(f'train {tr_nm} -> test {te_nm}: always the training majority side {np.mean(te.y.values == maj):.1%}')
    print('  MODEL     ' + slices(p, te.y.values))
    for s in range(3):
        m2 = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0)
        m2.fit(tr[cols].values, rng.permutation(tr.y.values)); p2 = m2.predict_proba(te[cols].values)[:, 1]
        print(f'  SHUFFLED{s} ' + slices(p2, te.y.values))
    # which single features matter: hit rate of each feature's top / bottom decile, sign learnt on the training window
    res = []
    for c_ in cols:
        a, b = tr[c_].values, te[c_].values
        qa = np.quantile(a, [0.1, 0.9]); sgn_hi = np.mean(tr.y.values[a >= qa[1]]) - np.mean(tr.y.values[a <= qa[0]])
        qb = np.quantile(b, [0.1, 0.9]); yb = te.y.values
        hit = np.r_[(yb[b >= qb[1]] == (sgn_hi > 0)), (yb[b <= qb[0]] == (sgn_hi < 0))].mean()
        res.append((hit, c_))
    res.sort(reverse=True)
    print('  best single features (outer deciles, side learnt on train): ' + ', '.join(f'{c_} {hh:.1%}' for hh, c_ in res[:6]) + '\n')
