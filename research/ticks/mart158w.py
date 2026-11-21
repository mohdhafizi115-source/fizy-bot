# Round 158w: WEEKLY timeframe. (A) COMEX GC weekly bars 2000-2026: does next week go the same way as the last 1 / 2 / 4 weeks?
# (B) MART (live v2.57 rest) with the side from the last 1 / 2 / 4 closed broker weeks, follow / fade, vs a random side per week.
import os, sys, numpy as np, pandas as pd
from multiprocessing import Pool
here = os.path.dirname(os.path.abspath(__file__))
g = pd.read_csv(os.path.join(here, "../../data/comex/yahoo_gc_1d.csv"), index_col=0, parse_dates=True)
g.index = pd.to_datetime(g.index, utc=True).tz_localize(None)
c = g[[k for k in g.columns if k.lower() == "close"][0]].astype(float); o = g[[k for k in g.columns if k.lower() == "open"][0]].astype(float)
w = pd.DataFrame({"o": o.resample("W-FRI").first(), "c": c.resample("W-FRI").last()}).dropna()
def wk_hits():
    nx = np.sign(w.c - w.o)
    print("A) COMEX GC weekly: next week the same way as the last N weeks (follow); fade = 1 - that")
    for N in (1, 2, 4):
        s = np.sign(w.c - w.o.shift(N - 1)).shift(1)
        for lo, hi in (("2000", "2009"), ("2010", "2019"), ("2020", "2024"), ("2025", "2026")):
            k = (s != 0) & s.notna() & (w.index >= lo) & (w.index < str(int(hi) + 1))
            print(f"  N {N} {lo}-{hi}: follow hit {(s[k] == nx[k]).mean():.1%} on {k.sum()} weeks | up weeks {(nx[k] > 0).mean():.1%}")
import mart158b as M
END = M.END
WK = M.T.to_period("W-SUN").start_time    # broker weeks (Mon-Sun, server time)
b = M.D.groupby(WK).agg(o=("o", "first"), c=("c", "last"))
def side(N, sg):
    return (np.sign(b.c - b.o.shift(N - 1)) * sg).shift(1).reindex(WK).fillna(0).values
def job(a):
    nm, hs = a
    nb = sum(1 for st in M.starts if M.sim('hbias', 3, st, END + pd.Timedelta(minutes=1), hside=hs)[3] is not None)
    return f"  {nm:22s} | starts blown {nb}/{len(M.starts)}"
if __name__ == "__main__":
    wk_hits()
    print(f"\nB) MART with a weekly side (broker weeks: {len(b)}), live two-sided pair = 26 / 63")
    J = [(f"last {N} W {'follow' if sg == 1 else 'fade'}", side(N, sg)) for N in (1, 2, 4) for sg in (1, -1)]
    u = b.index
    for sd in range(6):
        r = np.random.default_rng(sd).choice([-1, 1], len(u)); J.append((f"RANDOM week seed {sd}", pd.Series(r, index=u).reindex(WK).values))
    with Pool(2) as p:
        for r in p.imap(job, J): print(r, flush=True)
