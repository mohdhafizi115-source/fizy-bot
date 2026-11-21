# Round 152: which DAILY BIAS (buy or sell for the day) holds on broker gold?
# Each rule decides a side at a fixed time; the score is the broker move from that time to 23:30 server, in $ per 0.01 lot
# (= $ move), minus the spread. Last 3 months / the 3 before; random-side control (500 draws).
import numpy as np, pandas as pd, sys
SC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'
X = pd.read_pickle(SC + 'ticks/xau_m1.pkl'); X = X[X.index.dayofweek < 5]
mi = X.index.hour * 60 + X.index.minute; day = X.index.normalize()
def at(minute):   # first price at/after minute of each server day
    s = X.o[mi >= minute]; return s.groupby(day[mi >= minute]).first()
def last_before(minute):
    s = X.c[mi <= minute]; return s.groupby(day[mi <= minute]).last()
D = pd.DataFrame({'o130': at(90), 'o400': at(240), 'o900': at(540), 'o1530': at(930), 'c2330': last_before(1410)})
d1 = X.groupby(day).agg(o=('o', 'first'), h=('h', 'max'), l=('l', 'min'), c=('c', 'last'))
D = D.join(d1).dropna()
D['pcol'] = np.sign(D.c - D.o).shift(1); D['pbody'] = (D.c - D.o).abs().shift(1)
D['p2col'] = np.sign(D.c - D.o).shift(2)
D['ema20'] = D.c.ewm(span=20).mean().shift(1); D['emaslope'] = np.sign(D.ema20.diff())
D['pclose'] = D.c.shift(1); D['gap'] = np.sign(D.o130 - D.pclose)
D['wk'] = D.index.to_period('W'); wk = D.groupby('wk').agg(wo=('o', 'first'), wc=('c', 'last'))
D['pwcol'] = D.wk.map(np.sign(wk.wc - wk.wo).shift(1))
D['pmid'] = ((D.h + D.l) / 2).shift(1); D['vs_mid'] = np.sign(D.o130 - D.pmid)
D['asia'] = np.sign(D.o900 - D.o130); D['early'] = np.sign(D.o400 - D.o130); D['lon'] = np.sign(D.o1530 - D.o900)
SPREAD = 0.26
rules = {  # name: (side series, entry column)
    'AGAINST yesterday colour (live D1 filter)': (-D.pcol, 'o130'),
    'WITH yesterday colour': (D.pcol, 'o130'),
    'AGAINST yesterday, body <= $60': ((-D.pcol).where(D.pbody <= 60, 0), 'o130'),
    'AGAINST yesterday, body > $60': ((-D.pcol).where(D.pbody > 60, 0), 'o130'),
    'AGAINST 2 same-colour days': ((-D.pcol).where(D.pcol == D.p2col, 0), 'o130'),
    'AGAINST last week colour': (-D.pwcol, 'o130'),
    'WITH D1 EMA20 slope': (D.emaslope, 'o130'),
    'AGAINST D1 EMA20 slope': (-D.emaslope, 'o130'),
    'WITH overnight gap': (D.gap, 'o130'),
    'AGAINST overnight gap': (-D.gap, 'o130'),
    'open above yesterday mid -> buy': (D.vs_mid, 'o130'),
    'open above yesterday mid -> sell': (-D.vs_mid, 'o130'),
    'WITH 01:30-04:00 move (from 04:00)': (D.early, 'o400'),
    'AGAINST 01:30-04:00 move (from 04:00)': (-D.early, 'o400'),
    'WITH Asia 01:30-09:00 (from 09:00)': (D.asia, 'o900'),
    'AGAINST Asia 01:30-09:00 (from 09:00)': (-D.asia, 'o900'),
    'WITH London 09:00-15:30 (from 15:30)': (D.lon, 'o1530'),
    'AGAINST London 09:00-15:30 (from 15:30)': (-D.lon, 'o1530'),
    'always BUY': (pd.Series(1, index=D.index), 'o130'),
    'always SELL': (pd.Series(-1, index=D.index), 'o130'),
}
L0 = D.index[-1] - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
rng = np.random.default_rng(1)
def score(side, entry, w0, w1):
    m = (D.index >= w0) & (D.index <= w1) & side.notna() & (side != 0)
    s = side[m]; mv = (D.c2330 - D[entry])[m]; p = s * mv - SPREAD
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    rnd = []
    for _ in range(500):
        rs = rng.choice([-1, 1], len(s)); rp = rs * mv.values - SPREAD; rnd.append(rp.sum())
    pct = np.mean(np.array(rnd) < p.sum())
    return len(s), (p > 0).mean(), g / l if l else 99, p.sum(), p.min(), pct
print(f'days {len(D)} ({D.index[0].date()} .. {D.index[-1].date()}); hold to 23:30 server, 0.01 lot, spread ${SPREAD}\n')
print(f'{"rule":42s} | last 3 months: days  hit   PF     net   worst  beats-random | prev 3 months: days  hit   PF     net   worst  beats-random')
for nm, (side, e) in rules.items():
    a = score(side, e, L0, D.index[-1]); b = score(side, e, P0, L0 - pd.Timedelta(days=1))
    f = lambda r: f'{r[0]:4d} {r[1]:.0%} {r[2]:5.2f} {r[3]:+7.0f} {r[4]:+6.0f}   {r[5]:.0%}'
    ok = a[2] >= 1.15 and b[2] >= 1.15 and a[5] >= 0.9 and b[5] >= 0.9
    print(f'{nm:42s} | {f(a)} | {f(b)}{"  <== holds" if ok else ""}')
