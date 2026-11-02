"""Detail of the 3 Ducks rule (research/webscalp.py) on gold: why it does not pass. In $ and in R, by year, halves,
drawdown, win rate, trades a day, and against random entries."""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import webscalp as WS

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    sym = "XAUUSD"
    d = SA.load(os.path.join(DATA, sym + ".csv"), meta[sym]["point"])
    dates = d.index.normalize().values
    flat = ((d.index.hour * 60 + d.index.minute) >= 1380) | np.r_[True, dates[1:] != dates[:-1]]
    S = WS.build(d, sym)
    arr = [d[x].values for x in ("o", "h", "l", "c", "s")]
    days = len(np.unique(dates))
    for rule in ("DUCKS", "RAND"):
        res = SA.sim(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat)
        T = pd.DataFrame(res, columns=["k", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = d.index[T.k.values]
        net = (T.pnl - T.sp).values                 # $ per 0.01 lot (gold: $1 per $1 move)
        R = net / T.risk.values
        mid, end = d.index[len(d) // 2], d.index[-1]
        h = (T.t >= mid).values
        l12 = (T.t >= end - pd.Timedelta(days=365)).values
        eq = np.cumsum(net)
        dd = (eq - np.maximum.accumulate(eq)).min()
        wins, losses = net[net > 0], net[net <= 0]
        print(f"\n{rule} on {sym}: {len(T)} trades ({len(T) / days:.2f} a day), win rate {100 * (net > 0).mean():.1f}%")
        print(f"  $ per 0.01 lot: total {net.sum():+.0f}, per trade {net.mean():+.3f}, average win {wins.mean():+.2f}, "
              f"average loss {losses.mean():+.2f}, spread paid {T.sp.sum():.0f}, gross before spread {T.pnl.sum():+.0f}")
        print(f"  PF in $: all {SA.f2(SA.pf(net))}, half 1 {SA.f2(SA.pf(net[~h]))}, half 2 {SA.f2(SA.pf(net[h]))}, "
              f"stress 1.5x spread {SA.f2(SA.pf((T.pnl - 1.5 * T.sp).values))}, last 12 months {net[l12].sum():+.0f}")
        print(f"  PF in R (each trade sized to its stop, as the pass rule uses): {SA.f2(SA.pf(R))}, halves {SA.f2(SA.pf(R[~h]))} / {SA.f2(SA.pf(R[h]))}")
        print(f"  max drawdown ${dd:.0f}; exits: " + ", ".join(f"{k} {v}" for k, v in T.why.value_counts().items()))
        by = pd.Series(net, index=T.t).groupby(T.t.dt.year).agg(["count", "sum"])
        print("  by year: " + " | ".join(f"{y}: {int(r['count'])} trades {r['sum']:+.0f}$ PF {SA.f2(SA.pf(net[(T.t.dt.year == y).values]))}"
                                          for y, r in by.iterrows()))
        side = pd.Series(net).groupby(T.dir.values).agg(["count", "sum"])
        print("  by side: " + ", ".join(f"{'BUY' if k == 1 else 'SELL'} {int(r['count'])} trades {r['sum']:+.0f}$" for k, r in side.iterrows()))


if __name__ == "__main__":
    main()
