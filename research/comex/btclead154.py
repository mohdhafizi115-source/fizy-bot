# Round 154b: is "gold follows BTC's London move (09:00-15:30 server) into 15:30-23:30" real?
# Checks: (1) the same on COMEX GC hourly over 2 years by quarter; (2) neighbouring windows; (3) beyond gold's own move;
# (4) random-day control (BTC sign from a random other day).
import numpy as np, pandas as pd, sys
SC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'
rng = np.random.default_rng(4)
def hourly(k):
    d = pd.read_csv(f'data/tools/{k}_1h.csv'); d.index = pd.to_datetime(d.iloc[:, 0], utc=True).dt.tz_localize(None)
    return d.Close.astype(float).dropna()
btc = hourly('BTC'); gc = hourly('GOLD')
def srv(d, m): return (pd.Timestamp(d) + pd.Timedelta(minutes=m)).tz_localize('Europe/Athens', ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
def price_at(s, t):   # last close at or before t (hourly close stamped at the bar start -> close is t+1h; use bar start <= t-1h)
    x = s[s.index <= t - pd.Timedelta(hours=1)]; return x.iloc[-1] if len(x) else np.nan
X = pd.read_pickle(SC + 'ticks/xau_m1.pkl'); X = X[X.index.dayofweek < 5]
mi = X.index.hour * 60 + X.index.minute; dd = X.index.normalize()
def bro_at(m): return X.o[mi >= m].groupby(dd[mi >= m]).first()
days_b = sorted(set(dd))
def run(src, days, a, b, c, e, gold):   # signal = sign(src(b) - src(a)); trade gold from c to e
    rows = []
    for d in days:
        if pd.Timestamp(d).dayofweek >= 5: continue
        s0, s1 = price_at(src, srv(d, a)), price_at(src, srv(d, b))
        if gold == 'broker':
            g0 = bro_at_c.get(d, np.nan); g1 = bro_at_e.get(d, np.nan); own = g0 - bro_at_a.get(d, np.nan)
        else:
            g0, g1 = price_at(gc, srv(d, c)), price_at(gc, srv(d, e)); own = g0 - price_at(gc, srv(d, a))
        if np.isnan([s0, s1, g0, g1, own]).any() or s1 == s0: continue
        rows.append((pd.Timestamp(d), np.sign(s1 - s0), g1 - g0, np.sign(own)))
    return pd.DataFrame(rows, columns=['d', 's', 'mv', 'own']).set_index('d')
def pf(p): g, l = p[p > 0].sum(), -p[p < 0].sum(); return g / l if l else 99
SP = 0.26
print('(1) COMEX GC hourly, BTC 09:00-15:30 server -> gold 15:30-23:30, follow, gross, by quarter')
gdays = pd.date_range(max(btc.index.min(), gc.index.min()).normalize() + pd.Timedelta(days=2), gc.index.max().normalize())
R = run(btc, gdays, 540, 930, 930, 1410, 'gc'); p = R.s * R.mv
print(f'  all {len(p)} days hit {np.mean(p > 0):.0%} PF {pf(p):.2f} net {p.sum():+.0f}')
for q, x in p.groupby(p.index.to_period('Q')): print(f'  {q} {len(x):3d} days hit {np.mean(x > 0):.0%} PF {pf(x):.2f} {x.sum():+6.0f}')
rnd = [pf(rng.permutation(R.s.values) * R.mv.values) for _ in range(500)]
print(f'  random-day control PF median {np.median(rnd):.2f}, 95th {np.quantile(rnd, 0.95):.2f}')
print('  when BTC agrees / disagrees with gold\'s own 09:00-15:30 move:')
for lab, m in (('agree', R.s == R.own), ('disagree', R.s != R.own)):
    x = p[m]; print(f'    {lab:9s} {len(x):3d} days hit {np.mean(x > 0):.0%} PF {pf(x):.2f} {x.sum():+.0f}')
print('\n(2) neighbouring windows on COMEX GC (2 years), follow, gross PF:')
for a, b, c, e in ((480, 930, 930, 1410), (600, 930, 930, 1410), (720, 930, 930, 1410), (540, 840, 840, 1410), (540, 1020, 1020, 1410),
                   (540, 930, 930, 1200), (540, 930, 960, 1410), (90, 540, 540, 1410), (90, 930, 930, 1410), (930, 1200, 1200, 1410)):
    R2 = run(btc, gdays, a, b, c, e, 'gc'); p2 = R2.s * R2.mv
    half = p2.index < p2.index[len(p2) // 2]
    print(f'  BTC {a//60:02d}:{a%60:02d}-{b//60:02d}:{b%60:02d} -> gold {c//60:02d}:{c%60:02d}-{e//60:02d}:{e%60:02d}: {len(p2)} days PF {pf(p2):.2f}, halves {pf(p2[half]):.2f} / {pf(p2[~half]):.2f}')
print('\n(3) broker gold (spread in), BTC 09:00-15:30 -> 15:30-23:30, by month')
bro_at_a, bro_at_c, bro_at_e = bro_at(540).to_dict(), bro_at(930).to_dict(), X.c[mi <= 1410].groupby(dd[mi <= 1410]).last().to_dict()
R3 = run(btc, days_b, 540, 930, 930, 1410, 'broker'); p3 = R3.s * R3.mv - SP
for mth, x in p3.groupby(p3.index.to_period('M')): print(f'  {mth} {len(x):3d} days hit {np.mean(x > 0):.0%} PF {pf(x):.2f} {x.sum():+6.0f}')
print(f'  all {len(p3)} days PF {pf(p3):.2f} {p3.sum():+.0f}, worst day {p3.min():+.0f}')
