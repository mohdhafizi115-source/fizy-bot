"""Round 45 (5 Nov 2026): is it right to lower the spike size k from 3.0 to 2.5, to double the trades?

Round 44 left this open. At k = 2.5 the live rule (gate 8, SL 0.2 ATR, no TP, 45 min) gives 2,230 trades
instead of 1,059, PF 1.34 instead of 1.53, +$1,445 instead of +$1,163, and every year >= 1.09. More
trades and more money, but a lower profit factor. The owner always wants more entries, so the question
deserves a proper answer rather than a preference.

THE DECISIVE TEST comes first, and it is not a plateau sweep. k = 2.5 is a SUPERSET of k = 3.0: every
3-ATR spike is also a 2.5-ATR spike. So the +$1,445 at k = 2.5 already contains the +$1,163 the EA
makes today. What actually matters is whether the bars it ADDS - the band 2.5 <= range/ATR < 3.0 - have
an edge of their own. If that band is profitable, lowering k is free money. If it is break-even or
worse, then the k = 2.5 figure is the k = 3 edge diluted with noise, the higher net is just more
exposure, and lowering k is a mistake however good the headline looks.

So section A measures every spike-size band SEPARATELY, non-overlapping, which also shows whether 3.0 is
a real cliff or an arbitrary line. Then:
  B  the full plateau at whichever k survives A: SL, hold, TP, gate
  C  the joint k x gate grid, because the two interact through the cost
  D  how many signals the one-position-at-a-time rule throws away, by k - if that is large, the trade
     count is capped by the hold, not by k, and lowering k buys less than it appears to
  E  controls: random entries and the UP side at the candidate k
  F  what it would cost: drawdown, worst months, losing streaks, against what is live now

Pass rule: >= 150 trades, PF >= 1.15 after the bar's real spread, both halves >= 1.05, stress (1.5x
spread) >= 1.05, last 12 months positive. 0.01 lot, so every figure is in dollars.
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

    def signals(klo=3.0, khi=None, x=8.0, side=1):
        m = base & (gate >= x) & ((c < o) if side == 1 else (c > o)) & (rng >= klo * atr)
        if khi is not None:
            m &= rng < khi * atr
        return np.where(m)[0]

    def build(idx, sl_atr=0.2, tp_f=None, maxb=45, side=1):
        S = []
        for i in idx:
            sl = (l_[i] - sl_atr * atr[i]) if side == 1 else (h_[i] + sl_atr * atr[i])
            tp = (c[i] + side * tp_f * rng[i]) if tp_f else None
            if (sl - c[i]) * side >= 0 or (tp is not None and (tp - c[i]) * side <= 0):
                continue
            g = dict(k0=i + 1, kind="mkt", dir=side, sl=sl, exp=i + 1, maxb=maxb)
            if tp is not None:
                g["tp"] = tp
            S.append(g)
        return S

    def run(klo=3.0, khi=None, sl_atr=0.2, tp_f=None, maxb=45, x=8.0, side=1, rand=0):
        if rand:
            rg = np.random.default_rng(rand)
            idx = np.where(base & (gate >= x) & (rg.random(n) < 0.0015))[0]
        else:
            idx = signals(klo, khi, x, side)
        S = build(idx, sl_atr, tp_f, maxb, side)
        tr_ = SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat)
        if len(tr_) < 40:
            return None, len(S), len(tr_)
        T = pd.DataFrame(tr_, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T, len(S), len(tr_)

    def line(lab, res, mark=True):
        T = res[0] if isinstance(res, tuple) else res
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

    # ------------------------------------------------------------------ A. the decisive test
    say("\n=== A. THE DECISIVE TEST: each spike-size band on its own, non-overlapping ===")
    say("k = 2.5 is a superset of k = 3.0, so its +$1,445 already contains today's +$1,163. The only")
    say("question that matters is whether the bars it ADDS carry an edge. Each row below is ONE band and")
    say("nothing else, so the bands cannot borrow from each other.")
    say(HDR)
    bands = [(2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 5.0), (5.0, None)]
    for klo, khi in bands:
        lab = f"band {klo} - {khi} ATR" if khi else f"band >= {klo} ATR"
        line(lab, run(klo=klo, khi=khi))
    say("\nthe same bands with the OLD exit (TP 0.75, hold 20m), to show the v1.97 change did not")
    say("create the picture above:")
    say(HDR)
    for klo, khi in bands:
        lab = f"band {klo} - {khi} old exit" if khi else f"band >= {klo} old exit"
        line(lab, run(klo=klo, khi=khi, tp_f=0.75, maxb=20))

    say("\ncumulative, for reference (each row CONTAINS the rows below it):")
    say(HDR)
    for klo in (2.0, 2.5, 3.0, 3.5, 4.0):
        line(f"k >= {klo} (cumulative)", run(klo=klo))

    # ------------------------------------------------------------------ B. plateau at k 2.5
    say("\n=== B. the full plateau at k = 2.5, in case A says the added band is tradable ===")
    say("SL sweep (no TP, hold 45m):")
    say(HDR)
    for s in (0.1, 0.2, 0.3, 0.5, 0.75):
        line(f"k2.5 SL {s} ATR", run(klo=2.5, sl_atr=s))
    say("\nhold sweep (no TP, SL 0.2):")
    say(HDR)
    for m in (20, 30, 45, 60, 90, 120):
        line(f"k2.5 hold {m}m", run(klo=2.5, maxb=m))
    say("\nTP sweep (SL 0.2, hold 45m):")
    say(HDR)
    for t in (0.5, 0.75, 1.0, 1.5, 2.0, None):
        line(f"k2.5 TP {t if t else 'none':>4}", run(klo=2.5, tp_f=t))
    say("\ngate sweep (no TP, SL 0.2, hold 45m) - must stay monotone:")
    say(HDR)
    for x in (4, 6, 8, 10, 12, 16):
        line(f"k2.5 gate >= {x:2d}", run(klo=2.5, x=x))

    # ------------------------------------------------------------------ C. the joint grid
    say("\n=== C. the joint k x gate grid: PF, and net $ / trades underneath ===")
    say("The two interact: a smaller spike needs a cheaper bar to stay worth taking.")
    ks = (2.0, 2.5, 3.0, 3.5, 4.0)
    xs = (6, 8, 10, 12, 16)
    say(f"\n{'PF':>8} " + " ".join(f"{'gate' + str(x):>9}" for x in xs))
    grid = {}
    for k in ks:
        row = []
        for x in xs:
            T, ns, nt = run(klo=k, x=x)
            grid[(k, x)] = (T, ns, nt)
            row.append(pf(T.net.values) if T is not None and len(T) >= 40 else np.nan)
        say(f"k {k:5.1f} " + " ".join(f"{v:9.2f}" for v in row))
    say(f"\n{'net $':>8} " + " ".join(f"{'gate' + str(x):>9}" for x in xs))
    for k in ks:
        say(f"k {k:5.1f} " + " ".join(
            f"{(grid[(k, x)][0].net.sum() if grid[(k, x)][0] is not None else np.nan):+9.0f}" for x in xs))
    say(f"\n{'trades':>8} " + " ".join(f"{'gate' + str(x):>9}" for x in xs))
    for k in ks:
        say(f"k {k:5.1f} " + " ".join(f"{grid[(k, x)][2]:9d}" for x in xs))
    say(f"\n{'last12$':>8} " + " ".join(f"{'gate' + str(x):>9}" for x in xs))
    for k in ks:
        row = []
        for x in xs:
            T = grid[(k, x)][0]
            row.append(T[T.t >= end_t - pd.Timedelta(days=365)].net.sum() if T is not None else np.nan)
        say(f"k {k:5.1f} " + " ".join(f"{v:+9.0f}" for v in row))

    # ------------------------------------------------------------------ D. signals thrown away
    say("\n=== D. how many signals the one-position-at-a-time rule throws away ===")
    say("With a 45-minute hold, a second spike while a trade is open is skipped. If the skip rate is")
    say("high, the trade count is capped by the HOLD, not by k, and lowering k buys less than it looks.")
    say(f"{'k':>6} {'hold':>5} {'signals':>8} {'trades':>7} {'taken':>7}")
    for k in (2.0, 2.5, 3.0):
        for m in (20, 45, 90):
            T, ns, nt = run(klo=k, maxb=m)
            say(f"{k:6.1f} {m:4d}m {ns:8d} {nt:7d} {100 * nt / max(ns, 1):6.1f}%")

    # ------------------------------------------------------------------ E. controls
    say("\n=== E. controls at the candidate settings ===")
    say(HDR)
    for sd in (45, 46, 47):
        line(f"RANDOM seed {sd}, gate8 45m", run(rand=sd), mark=False)
    line("k2.5 UP side (fade SELL)", run(klo=2.5, side=-1), mark=False)
    line("band 2.5-3.0 UP side", run(klo=2.5, khi=3.0, side=-1), mark=False)

    # ------------------------------------------------------------------ F. the cost of the choice
    say("\n=== F. what each choice costs ===")
    for lab, res in (("LIVE v1.97  k3.0, no TP, 45m", run(klo=3.0)),
                     ("CAND        k2.5, no TP, 45m", run(klo=2.5)),
                     ("the added band 2.5-3.0 alone", run(klo=2.5, khi=3.0))):
        T = res[0]
        if T is None:
            continue
        eq = T.net.cumsum().values
        dd_s = eq - np.maximum.accumulate(np.r_[0, eq])[1:]
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        streak, cur = 0, 0
        for v in (T.net.values <= 0).astype(int):
            cur = cur + 1 if v else 0
            streak = max(streak, cur)
        i_lo = int(np.argmin(dd_s))
        peak = np.max(eq[: i_lo + 1])
        rec = np.where(eq[i_lo:] >= peak)[0]
        rec_d = (T.t.iloc[i_lo + rec[0]] - T.t.iloc[i_lo]).days if len(rec) else -1
        say(f"\n{lab}")
        say(f"  net ${T.net.sum():+.0f}, {len(T)} trades, {len(T) / days:.2f} a day, win {100 * (T.net > 0).mean():.1f}%, "
            f"PF {pf(T.net.values):.2f}")
        say(f"  average win ${T.net[T.net > 0].mean():.2f}, average loss ${T.net[T.net <= 0].mean():.2f}, "
            f"biggest loss ${T.net.min():.2f}")
        say(f"  max drawdown ${dd_s.min():.0f}" + (f", recovered after {rec_d} days" if rec_d >= 0 else ", never recovered"))
        say(f"  longest losing run {streak}; months positive {int((mo > 0).sum())}/{len(mo)}")
        say(f"  worst months " + ", ".join(f"{p} ${v:.0f}" for p, v in mo.nsmallest(3).items()))
        say(f"  last 12 months ${T[T.t >= end_t - pd.Timedelta(days=365)].net.sum():+.0f}")

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
