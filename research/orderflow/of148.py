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

XM = pd.read_pickle(SC + 'ticks/xau_m1.pkl')
def news_dir(T):
    out = []
    for _, r in T.iterrows():
        a = XM.o.asof(r.t.floor('1min')); b = XM.c.asof(r.tx.floor('1min'))
        mv = b - a
        out.append(int(np.sign(r.net) * np.sign(mv)) if mv != 0 else 0)
    return np.array(out)

g = pd.read_pickle(SC + 'ticks/gold133.pkl')
fl = pd.read_pickle(SC + 'ticks/flip133.pkl')
nw = pd.read_pickle(SC + 'ticks/news140.pkl'); nw['d'] = news_dir(nw); nw = nw[nw.d != 0]
rc = pd.read_pickle(SC + 'rcs133.pkl'); rc = rc[rc['mod'] == 'RCS-gold']
bt = pd.read_pickle(SC + 'btcsmc133.pkl')
GOLD = pd.concat([g[['mod', 't', 'd', 'net']], fl[['mod', 't', 'd', 'net']], nw[['mod', 't', 'd', 'net']],
                  rc[['mod', 't', 'd', 'net']], bt[bt['mod'] == 'SMC-gold'][['mod', 't', 'd', 'net']]])
BTC = bt[bt['mod'] != 'SMC-gold'][['mod', 't', 'd', 'net']]

L0, L1, P0 = pd.Timestamp('2026-08-17'), pd.Timestamp('2026-11-18'), pd.Timestamp('2026-05-17')

def pf(x):
    g_ = x[x > 0].sum(); l = -x[x < 0].sum()
    return g_ / l if l > 0 else (99.0 if g_ > 0 else 0.0)

RULES = []
for W in (5, 15, 30, 60, 240):
    RULES += [(f'delta{W} agrees', f'dz{W}', 'pos'), (f'delta{W} against', f'dz{W}', 'neg'),
              (f'delta{W} strong agree >1', f'dz{W}', 'gt1'), (f'delta{W} not strongly against >-1', f'dz{W}', 'gtm1'),
              (f'activity{W} high >1.5', f'va{W}', 'hiv'), (f'activity{W} low <0.8', f'va{W}', 'lov'),
              (f'div{W}: price against, delta with', f'div{W}', 'pos'), (f'div{W}: price with, delta against', f'div{W}', 'neg')]
for W in (15, 60, 240):
    RULES += [(f'big{W} agrees', f'bg{W}', 'pos'), (f'big{W} against', f'bg{W}', 'neg')]
RULES += [('BROKER range15 high >1.5','bv15','hiv'),('BROKER range60 high >1.5','bv60','hiv')]
RULES += [('cvd day agrees', 'cvdday', 'pos'), ('cvd day against', 'cvdday', 'neg')]

def mask(T, col, kind):
    if col.startswith('div'):
        W = col[3:]; dz = T[f'dz{W}'] * T.d; pz = T[f'pz{W}'] * T.d
        return ((pz < -0.5) & (dz > 0.5)) if kind == 'pos' else ((pz > 0.5) & (dz < -0.5))
    x = T[col] * (T.d if col[:2] in ('dz', 'bg', 'cv') else 1)
    return {'pos': x > 0, 'neg': x < 0, 'gt1': x > 1, 'gtm1': x > -1, 'hiv': x > 1.5, 'lov': x < 0.8}[kind]

out = []
def run(T, F, label):
    T = T.copy(); T['u'] = to_utc(T.t); T = T[T.u.notna()]
    X = F.reindex(T.u.values); X.index = T.index
    T = pd.concat([T, X], axis=1).dropna(subset=['dz60'])
    T['w'] = np.where((T.t >= L0) & (T.t < L1), 'L', np.where((T.t >= P0) & (T.t < L0), 'P', ''))
    T = T[T.w != '']
    # broker-side volatility proxy (no order flow): M1 range activity vs its 1-day mean, past bars only
    rg = (XM.h - XM.l); 
    for W in (15, 60):
        bv = (rg.rolling(W).mean() / rg.rolling(1440, min_periods=300).mean()).shift(1)
        T[f'bv{W}'] = bv.reindex(T.t.dt.floor('1min').values).values
    for mod, M in T.groupby('mod'):
        if PLACEBO:
            M = M.copy(); cols = [c for c in M.columns if c[:2] in ('dz','pz','va','bg','cv','bv')]
            for w in ('L','P'):
                ix = M.index[M.w == w]; M.loc[ix, cols] = M.loc[ix, cols].values[rng.permutation(len(ix))]
        a = M[M.w == 'L'].net.values; b = M[M.w == 'P'].net.values
        print(f'\n== {label} {mod}: base last {len(a)} trades PF {pf(a):.2f} ${a.sum():+.0f} | prev {len(b)} PF {pf(b):.2f} ${b.sum():+.0f}', flush=True)
        for name, col, kind in RULES:
            m = mask(M, col, kind).values
            res = []
            for w in ('L', 'P'):
                ww = (M.w == w).values; x = M.net.values[ww]; k = m[ww]
                if k.sum() < 8 or (~k).sum() < 3: res = None; break
                kept, drop = x[k], x[~k]
                # random masks with the same keep count
                sims = np.array([x[rng.permutation(len(x))[:k.sum()]].sum() for _ in range(200)])
                pct = (sims < kept.sum()).mean()
                res.append((k.sum(), len(x), pf(kept), kept.sum(), pf(drop), drop.sum(), pct))
            if res is None: continue
            (ka, na, pfa, ea, pda, eda, qa), (kb, nb, pfb, eb, pdb, edb, qb) = res
            ok = (pfa >= pf(a) + 0.1) and (pfb >= pf(b) + 0.1) and (eda < 0) and (edb < 0) and qa >= 0.9 and qb >= 0.9
            out.append(dict(mkt=label, mod=mod, rule=name, ka=ka, na=na, pfa=pfa, ea=ea, pda=pda, eda=eda, qa=qa,
                            kb=kb, nb=nb, pfb=pfb, eb=eb, pdb=pdb, edb=edb, qb=qb, base_a=pf(a), base_b=pf(b), ok=ok))
            if ok:
                print(f'  HELPS {name:38s} keep {ka}/{na} PF {pfa:.2f} ${ea:+.0f} drop PF {pda:.2f} ${eda:+.0f} rnd%{qa:.2f} | '
                      f'keep {kb}/{nb} PF {pfb:.2f} ${eb:+.0f} drop PF {pdb:.2f} ${edb:+.0f} rnd%{qb:.2f}', flush=True)

FG = load_flow('min', 250); run(GOLD, FG, 'GOLD'); del FG
FB = load_flow('bmin', 2000); run(BTC, FB, 'BTC')
R = pd.DataFrame(out); R.to_csv(SC + f'of/of148_all{PLACEBO}.csv', index=False)
print('\ncells', len(R), 'HELPS', int(R.ok.sum()))
# chance check: same test on shuffled outcomes within each module/window
print(R.groupby('mod').ok.sum().to_string())
