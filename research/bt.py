"""Bar-based backtester on M15 gold data (broker time). Lot 0.01 -> $1 per $1 move.
Costs: spread from the export (points * 0.01) on entry, swap per night held (buy -0.71, sell -0.84,
triple on Wednesday night). Intrabar path: bull bar O-L-H-C, bear bar O-H-L-C."""
import numpy as np, pandas as pd

CSV = "/mnt/user-data/attachments/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/9fdc8808-XAUUSD.m_M15_202601020100_202610232345"
SPLIT = pd.Timestamp("2026-06-01")


def load():
    df = pd.read_csv(CSV, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df.index = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df["spread"] = df["spread"] * 0.01
    return df[["open", "high", "low", "close", "spread"]]


def resample(m, rule):
    return m.resample(rule, label="left", closed="left", origin="start_day").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "spread": "max"}).dropna()


def atr(d, n=14):
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - d.close.shift()), abs(d.low - d.close.shift())))
    return tr.rolling(n).mean()


class Pos:
    def __init__(s, t, dr, entry, sl, tp, risk, tag=""):
        s.t, s.dr, s.entry, s.sl, s.tp, s.risk, s.tag = t, dr, entry, sl, tp, risk, tag
        s.be_done = False


def swap_cost(t0, t1, dr):
    """nights held between t0 and t1 (rollover at 00:00 broker), Wednesday triple"""
    days = pd.date_range(t0.normalize() + pd.Timedelta(days=1), t1.normalize(), freq="D")
    n = sum(3 if d.dayofweek == 3 else (1 if d.dayofweek < 5 else 0) for d in days)  # rollover into Thu = Wed night
    return n * (0.71 if dr == 1 else 0.84)


def metrics(tr, label=""):
    if len(tr) == 0 or "pnl" not in tr:
        return dict(n=0, win=0, pf=0, net=0, dd=0, avgR=0)
    p = tr.pnl.values
    eq = np.cumsum(p); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    return dict(n=len(p), win=round((p > 0).mean() * 100, 1), pf=round(gp / gl, 2) if gl else 99,
                net=round(p.sum(), 1), dd=round(dd, 1), avgR=round(tr.R.mean(), 2))


def report(name, tr):
    if len(tr) == 0:
        print(f"{name:42s} no trades"); return None
    a = metrics(tr); A = metrics(tr[tr.open < SPLIT]); B = metrics(tr[tr.open >= SPLIT])
    print(f"{name:42s} n={a['n']:4d} win={a['win']:5.1f}% PF={a['pf']:5.2f} net=${a['net']:8.1f} dd=${a['dd']:7.1f} "
          f"avgR={a['avgR']:5.2f} | Jan-May PF {A['pf']:5.2f} ${A['net']:7.1f} | Jun-Oct PF {B['pf']:5.2f} ${B['net']:7.1f}")
    return a, A, B
