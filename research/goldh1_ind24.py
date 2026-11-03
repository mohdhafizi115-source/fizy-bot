"""Round 24 (4 Nov 2026): detail check of the gold H1 indicator day trades that passed round 23 (TK cross, EMA 20/50).

Round 23 passes on XAUUSD H1 day trades (flat 23:00, no swap): TK (Ichimoku Tenkan / Kijun cross with the close beyond
the cloud, exit on the opposite cross, SL 2 ATR) PF 1.50, and EMA 20/50 cross PF 1.23. Before building, check:
  sides       buys and sells apart (gold rose from $1,600 to $4,000 in the data)
  neighbours  other Ichimoku periods (7/22/44, 12/30/60), no cloud filter, SL 1.5 / 3 ATR, signals 08:00-20:00 only,
              EMA 10/30 and 30/80
  overlap     share of days with a live gold module trade (Kumo H1 cloud breakout, re-checked with the broker swap)
  drawdown    worst peak-to-trough at 0.01 lot, months positive
Same data and costs as round 23 (bar spread; day trades have no swap).
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R
from goldh1_detail import sim2

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def mid(h, l, m):
    return (pd.Series(h).rolling(m).max().values + pd.Series(l).rolling(m).min().values) / 2


def variants(B, I):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    hm = B.hm.values
    A = I["atr"]
    base_ok = (hm >= 90) & (hm < 1260) & np.isfinite(A) & np.isfinite(I["e200"]) & (np.arange(n) >= 220)
    base_ok[-2:] = False
    V = {}

    def run(name, bu, bd, slm, xl, xs, ok=base_ok):
        S = []
        for i in np.where(ok & bu)[0]:
            S.append(dict(k0=i + 1, kind="mkt", dir=1, sl=c[i] - slm * A[i], exp=i + 1, maxb=24, xl=xl, xs=xs))
        for i in np.where(ok & bd)[0]:
            S.append(dict(k0=i + 1, kind="mkt", dir=-1, sl=c[i] + slm * A[i], exp=i + 1, maxb=24, xl=xl, xs=xs))
        V[name] = S

    cu = R.cross_up
    for (a, b, s_), lab in (((9, 26, 52), "TK 9/26/52"), ((7, 22, 44), "TK 7/22/44"), ((12, 30, 60), "TK 12/30/60")):
        ten, kij = mid(h, l, a), mid(h, l, b)
        sa = np.r_[np.full(b, np.nan), ((ten + kij) / 2)[:-b]]
        sb = np.r_[np.full(b, np.nan), mid(h, l, s_)[:-b]]
        top, bot = np.fmax(sa, sb), np.fmin(sa, sb)
        tu, td = cu(ten, kij), cu(kij, ten)
        run(lab, tu & (c > top), td & (c < bot), 2, td, tu)
        if lab == "TK 9/26/52":
            run("TK buys only", tu & (c > top), np.zeros(n, bool), 2, td, tu)
            run("TK sells only", np.zeros(n, bool), td & (c < bot), 2, td, tu)
            run("TK no cloud filter", tu, td, 2, td, tu)
            run("TK SL 1.5 ATR", tu & (c > top), td & (c < bot), 1.5, td, tu)
            run("TK SL 3 ATR", tu & (c > top), td & (c < bot), 3, td, tu)
            run("TK 08:00-20:00", tu & (c > top), td & (c < bot), 2, td, tu, ok=base_ok & (hm >= 480) & (hm < 1200))
    for f, s_ in ((20, 50), (10, 30), (30, 80)):
        ef = pd.Series(c).ewm(span=f, adjust=False).mean().values
        es = pd.Series(c).ewm(span=s_, adjust=False).mean().values
        eu, ed = cu(ef, es), cu(es, ef)
        run(f"EMA {f}/{s_}", eu, ed, 2, ed, eu)
        if f == 20:
            run("EMA 20/50 buys only", eu, np.zeros(n, bool), 2, ed, eu)
            run("EMA 20/50 sells only", np.zeros(n, bool), ed, 2, ed, eu)
    rg = np.random.default_rng(3)
    S = []
    for i in np.where(base_ok & (rg.random(n) < 1 / 24))[0]:
        dr = 1 if rg.random() < 0.5 else -1
        S.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c[i] - dr * 1.5 * A[i], exp=i + 1, maxb=24, tp_r=2.0))
    V["RAND"] = S
    return V


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d5 = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d5, "1h")
    dates = B.date.values
    flat = (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    I = R.ind(B)
    V = variants(B, I)
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    mid_t, end = B.index[len(B) // 2], B.index[-1]
    say(f"XAUUSD H1 {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, day trades flat 23:00 server, costs = bar spread, 0.01 lot")
    say("variant               trades /day  win%   PF  half1 half2 stress last12$   net$  maxDD$ months+   by year")
    res = {}
    for nm, S in V.items():
        tr = sim2(*arr, sorted(S, key=lambda g: g["k0"]), flat)
        T = pd.DataFrame(tr, columns=["k", "dir", "pnl", "sp", "risk", "why", "kx"])
        T["t"] = B.index[T.k.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        res[nm] = T
        if T.empty:
            continue
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        x = T
        yr = " ".join(f"{y % 100}:{SA.f2(SA.pf(x[x.t.dt.year == y].net.values)).strip()}" for y in sorted(x.t.dt.year.unique()))
        say(f"{nm:21s} {len(x):6d} {len(x) / B.index.normalize().nunique():4.2f} {100 * (x.net > 0).mean():5.1f} {SA.f2(SA.pf(x.net.values))} "
            f"{SA.f2(SA.pf(x[x.t < mid_t].net.values))} {SA.f2(SA.pf(x[x.t >= mid_t].net.values))} {SA.f2(SA.pf(x.st.values))} "
            f"{x[x.t >= end - pd.Timedelta(days=365)].net.sum():+7.0f} {x.net.sum():+6.0f} {dd:+7.0f} {(mo > 0).sum():3d}/{len(mo)}   {yr}")
    T = res["TK 9/26/52"]
    say(f"\nTK 9/26/52 exits: " + ", ".join(f"{k} {v}" for k, v in T.why.value_counts().items()) +
        f"; average hold {np.mean(T.kx - T.k):.1f} H1 bars; average win ${T.net[T.net > 0].mean():.2f}, average loss ${T.net[T.net <= 0].mean():.2f}")
    # overlap with the live Kumo module (swing version, as live)
    S = R.signals(B, I, True, 48, seed=1)["KUMO"]
    gap = np.r_[(pd.Series(B.date).diff().dt.days.values[1:] > 1), True]
    K = pd.DataFrame(sim2(*arr, sorted(S, key=lambda g: g["k0"]), gap), columns=["k", "dir", "pnl", "sp", "risk", "why", "kx"])
    kd = set(B.index[K.k.values].normalize())
    td = pd.Series(B.index[T.k.values].normalize())
    say(f"days with a TK trade that also had a new Kumo trade: {100 * td.isin(kd).mean():.0f}%")
    dT = T.groupby(B.index[T.k.values].normalize()).apply(lambda x: ((x.pnl - x.sp) * usd).sum())
    dK = K.groupby(B.index[K.k.values].normalize()).apply(lambda x: ((x.pnl - x.sp) * usd).sum())
    j = pd.concat([dT, dK], axis=1).fillna(0)
    say(f"daily P&L correlation TK vs Kumo: {j.corr().iloc[0, 1]:.2f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
