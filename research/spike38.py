"""Round 38 (5 Nov 2026): detail and robustness of the one M1 rule that has ever passed.

Round 37 found that fading a big M1 spike passes once it is only taken when the move dwarfs the cost:
  signal   an M1 bar whose range >= k x ATR(14, M1 up to the previous bar), body in either direction
  filter   ATR(14, M1) >= x times that bar's spread   <- this is what turns a loser into a winner
  trade    fade the bar at the next open, SL 0.2 ATR beyond its extreme, TP half the bar's range back, out after h min
With k = 3, x = 8, h = 15 it scored PF 1.16 over 1,732 trades (about 1 a day) against 0.90 for random entries under
the same filter. Before building anything, grid the parameters: a real edge should be a plateau, not one cell.
Also split by side, by year, and against a random control under the same filter.
Costs: the entry bar's real spread; stress = 1.5x. 0.01 lot, so PF and net are in dollars.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
pf = SA.pf


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    dates = B.date.values
    flat = (B.hm.values >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    I = R.ind(B)
    atr = I["atr"]
    spr = B.s.values * usd
    hm = B.hm.values
    base_ok = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (np.arange(n) >= 300)
    base_ok[-2:] = False
    rg = h - l
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    days = B.index.normalize().nunique()
    mid_t, end = B.index[len(B) // 2], B.index[-1]
    say = lambda s="": print(s, flush=True)
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {len(B):,} bars, {days} days")

    def run(k, x, tp_mode, maxb, side=0, rand=False, seed=38):
        ok = base_ok & (atr >= x * spr)
        if rand:
            rg_ = np.random.default_rng(seed)
            idx = np.where(ok & (rg_.random(n) < 0.02))[0]
        else:
            idx = np.where(ok & (rg >= k * atr) & (c != o))[0]
        S = []
        for i in idx:
            if rand:
                dr = 1 if rg_.random() < 0.5 else -1
            else:
                dr = -1 if c[i] > o[i] else 1
                if side and dr != side:
                    continue
            sl = (h[i] + 0.2 * atr[i]) if dr == -1 else (l[i] - 0.2 * atr[i])
            g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=maxb)
            if tp_mode == "half":
                g["tp"] = c[i] + dr * 0.5 * rg[i]
            elif tp_mode == "0.75":
                g["tp"] = c[i] + dr * 0.75 * rg[i]
            else:
                g["tp_r"] = float(tp_mode[:-1])
            if (sl - c[i]) * dr >= 0 or ("tp" in g and (g["tp"] - c[i]) * dr <= 0):
                continue
            S.append(g)
        tr = SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat)
        T = pd.DataFrame(tr, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        if T.empty:
            return None
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 50:
            say(f"{lab:26s} {0 if T is None else len(T):6d} (too few)"); return None
        P = pf(T.net.values)
        P1, P2 = pf(T[T.t < mid_t].net.values), pf(T[T.t >= mid_t].net.values)
        PS = pf(T.st.values)
        l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:26s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} "
            f"{SA.f2(PS)} {l12:+7.0f} {T.net.sum():+7.0f} {dd:+7.0f} {(mo > 0).sum():2d}/{len(mo)}  {yr}"
            f"{'  PASS' if ok and mark else ''}")
        return ok

    say("\n=== A. the cell found in round 37, and random entries under the same filter ===")
    say("variant                    trades /day  win%   PF  half1 half2 stress last12$    net$  maxDD$ mth+   by year")
    line("k3 x8 half 15m", run(3, 8, "half", 15))
    line("RANDOM under ATRx>=8", run(3, 8, "half", 15, rand=True), mark=False)
    line("k3 x8 half 15m, fade UP only", run(3, 8, "half", 15, side=-1))
    line("k3 x8 half 15m, fade DOWN only", run(3, 8, "half", 15, side=1))

    say("\n=== B. volatility filter sweep (k = 3, TP half, 15 min) ===")
    say("variant                    trades /day  win%   PF  half1 half2 stress last12$    net$  maxDD$ mth+   by year")
    for x in (0, 4, 5, 6, 7, 8, 9, 10, 12, 15):
        line(f"ATR >= {x:2d} x spread", run(3, x, "half", 15))

    say("\n=== C. spike size sweep (ATRx >= 8, TP half, 15 min) ===")
    say("variant                    trades /day  win%   PF  half1 half2 stress last12$    net$  maxDD$ mth+   by year")
    for k in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        line(f"spike >= {k} ATR", run(k, 8, "half", 15))

    say("\n=== D. target and hold sweep (k = 3, ATRx >= 8) ===")
    say("variant                    trades /day  win%   PF  half1 half2 stress last12$    net$  maxDD$ mth+   by year")
    for tp in ("half", "0.75", "1.0R", "2.0R"):
        for mb in (10, 15, 20, 30):
            line(f"TP {tp}, hold {mb} min", run(3, 8, tp, mb))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
