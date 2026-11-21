# Round 157: the public "daily forecast" that everyone reads — TradingView's Technicals rating (the same family as
# Investing.com's technical summary): Strong Buy / Buy / Neutral / Sell / Strong Sell from 15 moving averages + 11 oscillators.
# Rebuilt from TradingView's published rules on DAILY bars; does it call the NEXT day's direction?
# A) COMEX gold (Yahoo GC=F daily), 5 years, rating at the close of day t -> sign of close t+1 vs close t, by year.
# B) broker gold, last 3 months / the 3 before: rating from the last COMPLETED D1 bar -> 01:30 -> 23:30 server.
import numpy as np, pandas as pd, sys
SC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'
def rating(o, h, l, c):
    s = {}
    for n in (10, 20, 30, 50, 100, 200):
        s[f'sma{n}'] = np.sign(c - c.rolling(n).mean()); s[f'ema{n}'] = np.sign(c - c.ewm(span=n, adjust=False).mean())
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2; kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    spanA = ((tenkan + kijun) / 2); spanB = (h.rolling(52).max() + l.rolling(52).min()) / 2
    s['ichi'] = np.where((spanA > spanB) & (c > spanA) & (kijun > spanA) & (tenkan > kijun), 1, np.where((spanA < spanB) & (c < spanA) & (kijun < spanA) & (tenkan < kijun), -1, 0))
    vw = c.rolling(20).mean()  # no real volume on spot gold: VWMA approximated by SMA
    s['vwma'] = np.sign(c - vw)
    w = np.arange(1, 10); wma = lambda x, n: x.rolling(n).apply(lambda a: np.dot(a, np.arange(1, n + 1)) / np.arange(1, n + 1).sum(), raw=True)
    hma = wma(2 * wma(c, 4) - wma(c, 9), 3); s['hma'] = np.sign(c - hma)
    MA = pd.DataFrame(s, index=c.index).mean(axis=1)
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)
    k = 100 * (c - l.rolling(14).min()) / (h.rolling(14).max() - l.rolling(14).min()); k = k.rolling(3).mean(); dd = k.rolling(3).mean()
    tp = (h + l + c) / 3; cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda a: np.abs(a - a.mean()).mean(), raw=True))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    pdm = (h.diff()).where((h.diff() > -l.diff()) & (h.diff() > 0), 0); mdm = (-l.diff()).where((-l.diff() > h.diff()) & (-l.diff() > 0), 0)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean(); pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr; mdi = 100 * mdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    adx = (100 * (pdi - mdi).abs() / (pdi + mdi)).ewm(alpha=1 / 14, adjust=False).mean()
    mid = (h + l) / 2; ao = mid.rolling(5).mean() - mid.rolling(34).mean()
    mom = c - c.shift(10)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); sig = macd.ewm(span=9, adjust=False).mean()
    rmin, rmax = rsi.rolling(14).min(), rsi.rolling(14).max(); srsi = 100 * (rsi - rmin) / (rmax - rmin); sk = srsi.rolling(3).mean(); sd = sk.rolling(3).mean()
    wr = -100 * (h.rolling(14).max() - c) / (h.rolling(14).max() - l.rolling(14).min())
    ema13 = c.ewm(span=13, adjust=False).mean(); bull, bear = h - ema13, l - ema13
    bp1 = c.diff(); bp = c - pd.concat([l, c.shift()], axis=1).min(axis=1)
    uo = 100 * (4 * bp.rolling(7).sum() / tr.rolling(7).sum() + 2 * bp.rolling(14).sum() / tr.rolling(14).sum() + bp.rolling(28).sum() / tr.rolling(28).sum()) / 7
    up_trend = c.ewm(span=50, adjust=False).mean() < c
    O = {}
    O['rsi'] = np.where((rsi < 30) & (rsi > rsi.shift()), 1, np.where((rsi > 70) & (rsi < rsi.shift()), -1, 0))
    O['stoch'] = np.where((k < 20) & (dd < 20) & (k > dd), 1, np.where((k > 80) & (dd > 80) & (k < dd), -1, 0))
    O['cci'] = np.where((cci < -100) & (cci > cci.shift()), 1, np.where((cci > 100) & (cci < cci.shift()), -1, 0))
    O['adx'] = np.where((adx > 20) & (pdi.shift() < mdi.shift()) & (pdi > mdi), 1, np.where((adx > 20) & (pdi.shift() > mdi.shift()) & (pdi < mdi), -1, 0))
    O['ao'] = np.where(((ao > 0) & (ao.shift() < 0)) | ((ao > 0) & (ao > ao.shift()) & (ao.shift() < ao.shift(2))), 1, np.where(((ao < 0) & (ao.shift() > 0)) | ((ao < 0) & (ao < ao.shift()) & (ao.shift() > ao.shift(2))), -1, 0))
    O['mom'] = np.where(mom > mom.shift(), 1, np.where(mom < mom.shift(), -1, 0))
    O['macd'] = np.where(macd > sig, 1, np.where(macd < sig, -1, 0))
    O['srsi'] = np.where(~up_trend & (sk < 20) & (sd < 20) & (sk > sd), 1, np.where(up_trend & (sk > 80) & (sd > 80) & (sk < sd), -1, 0))
    O['wr'] = np.where((wr < -80) & (wr > wr.shift()), 1, np.where((wr > -20) & (wr < wr.shift()), -1, 0))
    O['bbp'] = np.where(up_trend & (bear < 0) & (bear > bear.shift()), 1, np.where(~up_trend & (bull > 0) & (bull < bull.shift()), -1, 0))
    O['uo'] = np.where(uo > 70, 1, np.where(uo < 30, -1, 0))
    OS = pd.DataFrame(O, index=c.index).mean(axis=1)
    return (MA + OS) / 2, MA, OS
lab = lambda r: np.where(r > 0.5, 'STRONG BUY', np.where(r > 0.1, 'BUY', np.where(r >= -0.1, 'NEUTRAL', np.where(r >= -0.5, 'SELL', 'STRONG SELL'))))
g = pd.read_csv('data/tools/GOLD_1d.csv'); g.index = pd.to_datetime(g.iloc[:, 0]).dt.tz_localize(None); g = g[['Open', 'High', 'Low', 'Close']].astype(float).dropna()
R, MA, OS = rating(g.Open, g.High, g.Low, g.Close)
nx = np.sign(g.Close.shift(-1) - g.Close)
D = pd.DataFrame({'r': R, 'ma': MA, 'os': OS, 'nx': nx}).dropna(); D = D[D.index >= '2022-01-01']
print('A) COMEX gold daily (GC=F), rating at the close -> next day up or down (hit rate = rating side right)\n')
for nm, col in (('Summary', 'r'), ('Moving averages', 'ma'), ('Oscillators', 'os')):
    print(f'{nm}:')
    L = lab(D[col])
    for b in ('STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'):
        m = L == b; side = 1 if 'BUY' in b else -1 if 'SELL' in b else 0
        yrs = ' '.join(f'{y}:{(np.mean(D.nx[m & (D.index.year == y)] == side) if side else np.mean(D.nx[m & (D.index.year == y)] > 0)):.0%}' for y in range(2022, 2027))
        hit = np.mean(D.nx[m] == side) if side else np.mean(D.nx[m] > 0)
        print(f'  {b:11s} days {m.sum():4d}  {"hit" if side else "up%"} {hit:.1%}  | {yrs}')
base = np.mean(D.nx > 0); print(f'  base rate: gold up on {base:.1%} of days\n')
# B) broker gold, rating from completed D1 bars (server days built from M1)
X = pd.read_pickle(SC + 'ticks/xau_m1.pkl'); X = X[X.index.dayofweek < 5]
dd_ = X.groupby(X.index.normalize()).agg(o=('o', 'first'), h=('h', 'max'), l=('l', 'min'), c=('c', 'last'))
# prepend GC daily history (shifted to the broker level) so 200-day averages exist from May
gpre = g[g.index < dd_.index[0]].copy(); off = dd_.o.iloc[0] - g.Close[g.index < dd_.index[0]].iloc[-1]
pre = pd.DataFrame({'o': gpre.Open + off, 'h': gpre.High + off, 'l': gpre.Low + off, 'c': gpre.Close + off})
full = pd.concat([pre, dd_]); Rb, _, _ = rating(full.o, full.h, full.l, full.c); Rb = Rb.shift(1).reindex(dd_.index)
mi = X.index.hour * 60 + X.index.minute; day = X.index.normalize()
e = X.o[mi >= 90].groupby(day[mi >= 90]).first(); x = X.c[mi <= 1410].groupby(day[mi <= 1410]).last()
B = pd.DataFrame({'r': Rb, 'mv': x - e}).dropna(); L0 = B.index[-1] - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
print('B) broker gold, yesterday\'s completed D1 rating -> 01:30-23:30 server today')
for w, a, b_ in (('last 3 months', L0, B.index[-1] + pd.Timedelta(days=1)), ('previous 3 months', P0, L0)):
    s = B[(B.index >= a) & (B.index < b_)]; Ls = lab(s.r); out = []
    for bb in ('STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'):
        m = Ls == bb; side = 1 if 'BUY' in bb else -1 if 'SELL' in bb else 0
        out.append(f'{bb} {m.sum()}d ' + (f'hit {np.mean(np.sign(s.mv[m]) == side):.0%}' if side and m.sum() else ''))
    print(f'  {w}: ' + ' | '.join(out))
