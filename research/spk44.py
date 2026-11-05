"""Round 44 (5 Nov 2026): confirm the one thing round 43 found, before touching the live EA.

Round 43 built six rule families out of round 42's measurements. All six failed (`m1build43.txt`):
CUMFADE 0.88-1.09, ASIAFADE 0.85-0.91 with its London control also failing at 0.92-1.00, LDNMOM
0.81-0.93, BUSYLONG 1.01, NYOPEN 0.83-0.96. The falsification control did its job: a variance ratio
below 1 is NOT a tradable edge, it is a small variance effect that the spread eats.

But the same round found a real improvement to the rule that is already live. Taking the live signal
(one M1 bar falling >= 3 ATR with ATR >= 8 x spread, SL 0.2 ATR below its low) and simply REMOVING the
take profit:

  live now:  TP 0.75 x range, hold 20m   PF 1.37  halves 1.33/1.38  +$675   DD -$87   win 30.0%
  no TP,                      hold 45m   PF 1.53  halves 1.54/1.53  +$1,163 DD -$144  win 20.0%

The holds with a TP are flat (20-90 min: 1.37, 1.38, 1.39, 1.39, 1.39), so the TP is what caps it, not
the hold. Removing it lets the reversion run, which is exactly what round 42 predicted: under the gate
the variance ratio keeps falling out to 60 minutes.

A live rule is not changed on one cell. This round checks whether that is a plateau or a lucky setting:
  A  SL sweep with no TP (the previous SL sweep was done WITH a TP, so it does not carry over)
  B  hold sweep at the best SL
  C  TP sweep - maybe a FAR target beats no target at all
  D  gate sweep - round 42 C says a real cost effect must stay monotone
  E  spike size k sweep
  F  a random control with identical mechanics, and the same rule on the UP side (must fail)
  G  what the change actually costs: drawdown, the worst months, and the losing-streak length, so the
     owner is told the downside and not just the profit
Costs: the entry bar's real spread; stress = 1.5x. 0.01 lot, so every figure is dollars.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
pf = SA.pf
say = lambda s="": print(s, flush=True)
HDR = ("variant                       trades  win%   PF  half1 half2 stress last12$    net$  maxDD$"
       " avg win avg loss mth+   by year")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    del d
    o, h_, l_, c = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(c)
    hm = B.hm.values
    dates = B.date.values
    flat = (hm >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    spr = B.s.values.astype(float)
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h_ - l_, np.maximum(np.abs(h_ - c1), np.abs(l_ - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = np.where(spr > 0, atr / spr, np.nan)
    base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 300)
    base[-3:] = False
    rng = h_ - l_
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    mid_t, end_t = B.index[n // 2], B.index[-1]
    days = B.index.normalize().nunique()
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, {days} days. "
        f"Halves split at {mid_t:%Y-%m-%d}. Median spread ${np.median(spr) * usd:.3f} per 0.01 lot.")

    def run(sl_atr=0.2, tp_f=None, maxb=45, x=8.0, k=3.0, side=1, rand=0):
        if rand:
            rg = np.random.default_rng(rand)
            hit = base & (gate >= x) & (rg.random(n) < 0.0007)
        else:
            hit = base & (gate >= x) & ((c < o) if side == 1 else (c > o)) & (rng >= k * atr)
        S = []
        for i in np.where(hit)[0]:
            sl = (l_[i] - sl_atr * atr[i]) if side == 1 else (h_[i] + sl_atr * atr[i])
            tp = (c[i] + side * tp_f * rng[i]) if tp_f else None
            if (sl - c[i]) * side >= 0 or (tp is not None and (tp - c[i]) * side <= 0):
                continue
            g = dict(k0=i + 1, kind="mkt", dir=side, sl=sl, exp=i + 1, maxb=maxb)
            if tp is not None:
                g["tp"] = tp
            S.append(g)
        tr_ = SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat)
        if len(tr_) < 40:
            return None
        T = pd.DataFrame(tr_, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 40:
            say(f"{lab:29s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        w, ls = T.net[T.net > 0], T.net[T.net <= 0]
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:29s} {len(T):6d} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} "
            f"{SA.f2(PS)} {l12:+7.0f} {T.net.sum():+7.0f} {dd:+7.0f} {w.mean():7.2f} {ls.mean():8.2f} "
            f"{(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok and mark else ''}")
        return ok

    say("\n=== reference: what is live today, and the round 43 candidate ===")
    say(HDR)
    line("LIVE  TP 0.75, hold 20m", run(tp_f=0.75, maxb=20))
    line("CAND  no TP,   hold 45m", run(tp_f=None, maxb=45))

    say("\n=== A. SL sweep, no TP, hold 45m (the old sweep was done WITH a TP) ===")
    say(HDR)
    for s in (0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5):
        line(f"SL {s} ATR below the low", run(sl_atr=s, maxb=45))

    say("\n=== B. hold sweep, no TP, SL 0.2 ATR ===")
    say(HDR)
    for m in (15, 20, 30, 45, 60, 90, 120, 240):
        line(f"hold {m}m", run(maxb=m))

    say("\n=== C. TP sweep: is a FAR target better than none? (SL 0.2, hold 45m) ===")
    say(HDR)
    for t in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, None):
        line(f"TP {t if t else 'none':>4} x the spike range", run(tp_f=t, maxb=45))

    say("\n=== D. gate sweep, no TP, hold 45m - a real cost effect stays MONOTONE ===")
    say(HDR)
    for x in (0, 2, 4, 6, 8, 10, 12, 16, 20):
        line(f"gate >= {x:2d}", run(maxb=45, x=x))

    say("\n=== E. spike size sweep, no TP, hold 45m ===")
    say(HDR)
    for k in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        line(f"spike >= {k} ATR", run(maxb=45, k=k))

    say("\n=== F. controls: random entries and the UP side, identical mechanics ===")
    say(HDR)
    for sd in (44, 45, 46):
        line(f"RANDOM seed {sd}, no TP 45m", run(maxb=45, rand=sd), mark=False)
    line("UP spike, no TP 45m (fade SELL)", run(maxb=45, side=-1), mark=False)

    say("\n=== G. what the change costs: the downside of dropping the take profit ===")
    A = run(tp_f=0.75, maxb=20)
    Bc = run(tp_f=None, maxb=45)
    for lab, T in (("LIVE  TP 0.75 / 20m", A), ("CAND  no TP / 45m", Bc)):
        eq = T.net.cumsum().values
        dd_series = eq - np.maximum.accumulate(np.r_[0, eq])[1:]
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        loss = (T.net.values <= 0).astype(int)
        streak, cur = 0, 0
        for v in loss:
            cur = cur + 1 if v else 0
            streak = max(streak, cur)
        # how long the worst drawdown took to recover, in calendar days
        i_lo = int(np.argmin(dd_series))
        peak = np.max(eq[: i_lo + 1]) if i_lo >= 0 else 0
        rec = np.where(eq[i_lo:] >= peak)[0]
        rec_d = (T.t.iloc[i_lo + rec[0]] - T.t.iloc[i_lo]).days if len(rec) else -1
        say(f"\n{lab}")
        say(f"  net ${T.net.sum():+.0f} over {len(T)} trades, {len(T) / days:.2f} a day, win rate "
            f"{100 * (T.net > 0).mean():.1f}%")
        say(f"  average win ${T.net[T.net > 0].mean():.2f}, average loss ${T.net[T.net <= 0].mean():.2f}, "
            f"biggest win ${T.net.max():.2f}, biggest loss ${T.net.min():.2f}")
        say(f"  max drawdown ${dd_series.min():.0f}" +
            (f", recovered after {rec_d} days" if rec_d >= 0 else ", never fully recovered"))
        say(f"  longest run of losing trades in a row: {streak}")
        say(f"  months positive {int((mo > 0).sum())}/{len(mo)}; worst months " +
            ", ".join(f"{p} ${v:.0f}" for p, v in mo.nsmallest(4).items()))
        say(f"  best months " + ", ".join(f"{p} ${v:.0f}" for p, v in mo.nlargest(3).items()))
        say(f"  last 12 months ${T[T.t >= end_t - pd.Timedelta(days=365)].net.sum():+.0f}")

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
