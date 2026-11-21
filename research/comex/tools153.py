# Round 153: do the usual 'direction tools' (DXY, US 10Y yield, TIP, GLD, GDX, silver, VIX, S&P 500, ES, EURUSD,
# USDJPY, copper, oil) tell gold's direction for the day?
# A) broker gold, last 3 months / the 3 before: tool's last daily return (known before 01:30 server) -> gold 01:30 -> 23:30;
#    tool's 01:30-09:00 move -> gold 09:00 -> 23:30; tool's 09:00-15:30 move -> gold 15:30 -> 23:30. Follow and fade, spread in,
#    500 random-side draws.  B) the daily rule on COMEX gold (GC=F) close-to-close over 5 years, year by year.
import numpy as np, pandas as pd, sys
SC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/'
import os
TOOLS = os.environ.get('TOOLS', 'DXY,US10Y,TIP,GLD,GDX,SILVER,VIX,SPX,ES,EURUSD,USDJPY,COPPER,OIL').split(',')
rng = np.random.default_rng(2)
def daily(k):
    d = pd.read_csv(f'data/tools/{k}_1d.csv'); d.index = pd.to_datetime(d.iloc[:, 0]).dt.tz_localize(None).dt.normalize()
    if len(d) < 100:   # e.g. CNH: build daily closes from the hourly series (UTC day)
        h = hourly(k); return h.groupby(h.index.normalize()).last()
    return d.Close.astype(float).dropna()
def hourly(k):
    d = pd.read_csv(f'data/tools/{k}_1h.csv'); d.index = pd.to_datetime(d.iloc[:, 0], utc=True).dt.tz_localize(None)
    return d.Close.astype(float).dropna()
X = pd.read_pickle(SC + 'ticks/xau_m1.pkl'); X = X[X.index.dayofweek < 5]
mi = X.index.hour * 60 + X.index.minute; day = X.index.normalize()
at = lambda m: X.o[mi >= m].groupby(day[mi >= m]).first()
end = X.c[mi <= 1410].groupby(day[mi <= 1410]).last()
G = pd.DataFrame({'e130': at(90), 'e900': at(540), 'e1530': at(930), 'x': end}).dropna()
srv2utc = lambda d, m: (pd.Timestamp(d) + pd.Timedelta(minutes=m)).tz_localize('Europe/Athens').tz_convert('UTC').tz_localize(None)
L0 = G.index[-1] - pd.Timedelta(days=91); P0 = L0 - pd.Timedelta(days=91)
SP = 0.26
def sc(side, mv, msk):
    s = side[msk]; m = mv[msk]; ok = s != 0; s, m = s[ok], m[ok]
    p = s * m - SP; g, l = p[p > 0].sum(), -p[p < 0].sum()
    rnd = [(rng.choice([-1, 1], len(s)) * m.values - SP).sum() for _ in range(500)]
    return len(s), (p > 0).mean(), (g / l if l else 99), p.sum(), np.mean(np.array(rnd) < p.sum())
fmt = lambda r: f'{r[0]:3d} hit {r[1]:.0%} PF {r[2]:4.2f} {r[3]:+6.0f} rnd {r[4]:.0%}'
wl = (G.index >= L0); wp = (G.index >= P0) & (G.index < L0)
print(f'broker gold days {len(G)}; last 3 months {wl.sum()} / previous {wp.sum()} days; 0.01 lot, spread ${SP}\n')
print('A) tool signal -> broker gold, FOLLOW = gold the tool\'s way, FADE = the other way  |  last 3 months  |  previous 3 months')
nflag = 0; ncell = 0
for k in TOOLS:
    dc = daily(k); dr = np.sign(dc.diff())
    h = hourly(k)
    sig = {}
    # yesterday's daily return, the latest close strictly before today's 01:30 server
    sig['yday'] = (pd.Series([dr[dr.index < d].iloc[-1] if (dr.index < d).any() else 0 for d in G.index], index=G.index), 'e130')
    def hmove(m0, m1):
        out = []
        for d in G.index:
            a, b = srv2utc(d, m0), srv2utc(d, m1)
            s = h[(h.index >= a) & (h.index <= b)]
            out.append(np.sign(s.iloc[-1] - s.iloc[0]) if len(s) >= 2 else 0)
        return pd.Series(out, index=G.index)
    sig['asia'] = (hmove(90, 540), 'e900'); sig['lon'] = (hmove(540, 930), 'e1530')
    inverse = k in ('DXY', 'US10Y', 'VIX', 'USDJPY', 'IRX', 'FVX', 'CNH')   # tools that usually move against gold: FOLLOW means gold the other way
    for nm, (s, e) in sig.items():
        if (s != 0).sum() < 40: continue
        mv = G.x - G[e]
        for lab, sgn in (('FOLLOW', -1 if inverse else 1), ('FADE', 1 if inverse else -1)):
            a = sc(s * sgn, mv, wl); b = sc(s * sgn, mv, wp); ncell += 1
            ok = a[2] >= 1.15 and b[2] >= 1.15 and a[4] >= 0.9 and b[4] >= 0.9 and a[0] >= 30 and b[0] >= 30; nflag += ok
            print(f'{k:7s} {nm:5s} {lab:6s} | {fmt(a)} | {fmt(b)}{"  <== holds" if ok else ""}', flush=True)
print(f'\ncells {ncell}, hold in both windows {nflag}\n')
print('B) COMEX gold (GC=F) next day close-to-close, by year: FOLLOW the tool\'s previous day (gold-way sign), PF per year 2022 / 2023 / 2024 / 2025 / 2026')
gc = daily('GOLD'); gr = gc.diff().shift(-1)   # tomorrow's GC move, indexed by today
for k in TOOLS:
    dc = daily(k); s = np.sign(dc.diff()).reindex(gc.index)
    if k in ('DXY', 'US10Y', 'VIX', 'USDJPY', 'IRX', 'FVX', 'CNH'): s = -s
    p = (s * gr).dropna(); yrs = []
    for y in (2022, 2023, 2024, 2025, 2026):
        q = p[p.index.year == y]; g, l = q[q > 0].sum(), -q[q < 0].sum(); yrs.append(g / l if l else 0)
    allg, alll = p[p > 0].sum(), -p[p < 0].sum()
    print(f'{k:7s} days {len(p):4d} PF all {allg / alll:4.2f} | ' + ' / '.join(f'{v:4.2f}' for v in yrs))
p = (-np.sign(gc.diff()).reindex(gc.index) * gr).dropna(); yrs = []
for y in (2022, 2023, 2024, 2025, 2026):
    q = p[p.index.year == y]; yrs.append(q[q > 0].sum() / -q[q < 0].sum())
print(f'{"(ref) AGAINST gold\'s own previous day":38s} PF ' + ' / '.join(f'{v:4.2f}' for v in yrs))
