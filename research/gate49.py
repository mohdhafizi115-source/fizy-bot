"""Round 49 (5 Nov 2026): lower the cost gate from 8 to 6? The band test, then the plateau.

Round 48's menu showed exactly one configuration with 2 or more trades a day that passes the pass
rule: k 2.5 with the gate at 6 instead of 8. It gives 2.22 trades a day against the live 1.31 - 70%
more - at PF 1.21 instead of 1.34 and $190 a year instead of $216.

Gate 6 is a SUPERSET of gate 8, exactly like k 2.5 was a superset of k 3.0 in round 45, so its
headline already contains what the live rule makes and a sweep cannot settle it. The decisive test is
the same: measure each gate band ON ITS OWN, non-overlapping, so no band can borrow another's profit.
If the 6-8 band pays for itself, lowering the gate is justified; if not, it is only more exposure.

Then the plateau at gate 6 (SL, hold, k) and the controls.

Pass rule: >= 150 trades, PF >= 1.15 after spread, both halves >= 1.05, stress >= 1.05, last 12 months
positive. 0.01 lot, so every figure is in dollars.
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
HDR = ("variant                        trades /day  win%   PF  half1 half2 stress last12$   net$  $/yr"
       "  maxDD$ mth+   by year")


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
    newday = np.r_[True, dates[1:] != dates[:-1]]
    flat = (hm >= 1350) | newday | np.r_[newday[1:], True]
    spr = B.s.values.astype(float)
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h_ - l_, np.maximum(np.abs(h_ - c1), np.abs(l_ - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = np.where(spr > 0, atr / spr, np.nan)
    rng = h_ - l_
    base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 300)
    base[-3:] = False
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    days = B.index.normalize().nunique()
    yrs = days / 255.0
    mid_t, end_t = B.index[n // 2], B.index[-1]
    say(f"XAUUSD M1, {n:,} bars, {days} days ({yrs:.1f} years). Halves split at {mid_t:%Y-%m-%d}.")

    def run(k=2.5, glo=8.0, ghi=None, sl_atr=0.2, tp_f=None, maxb=45, rand=0):
        if rand:
            rg = np.random.default_rng(rand)
            m = base & (gate >= glo) & (rg.random(n) < 0.0025)
            if ghi is not None:
                m &= gate < ghi
        else:
            m = base & (gate >= glo) & (c < o) & (rng >= k * atr)
            if ghi is not None:
                m &= gate < ghi
        S = []
        for i in np.where(m)[0]:
            sl = l_[i] - sl_atr * atr[i]
            tp = c[i] + tp_f * rng[i] if tp_f else None
            if sl >= c[i] or (tp is not None and tp <= c[i]):
                continue
            g = dict(k0=i + 1, kind="mkt", dir=1, sl=sl, exp=i + 1, maxb=maxb)
            if tp is not None:
                g["tp"] = tp
            S.append(g)
        if len(S) < 60:
            return None
        tr_ = SA.sim(*arr, S, flat)
        if len(tr_) < 50:
            return None
        T = pd.DataFrame(tr_, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 50:
            say(f"{lab:30s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:30s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+6.0f} {T.net.sum() / yrs:+5.0f} {dd:+7.0f} "
            f"{(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok and mark else ''}")
        return ok

    say("\n=== THE DECISIVE TEST: each gate band on its own, non-overlapping (k 2.5, no TP, 45 min) ===")
    say("Gate 6 contains gate 8, so its headline already holds the live profit. Only the band it ADDS")
    say("- signals where the gate is between 6 and 8 - decides whether lowering it is justified.")
    say(HDR)
    for lo, hi, lab in ((4, 6, "gate 4 - 6"), (6, 8, "gate 6 - 8  <- what it adds"),
                        (8, 10, "gate 8 - 10"), (10, 14, "gate 10 - 14"), (14, 20, "gate 14 - 20"),
                        (20, None, "gate >= 20")):
        line(f"band {lab}", run(glo=lo, ghi=hi))

    say("\ncumulative, for reference (each row CONTAINS the rows below):")
    say(HDR)
    for lo in (4, 6, 8, 10, 12):
        line(f"gate >= {lo} (cumulative)", run(glo=lo))

    say("\n=== the plateau at gate 6, in case the band pays ===")
    say(HDR)
    for s in (0.1, 0.2, 0.3, 0.5):
        line(f"gate6 SL {s} ATR", run(glo=6, sl_atr=s))
    say("")
    for m in (20, 30, 45, 60, 90):
        line(f"gate6 hold {m}m", run(glo=6, maxb=m))
    say("")
    for k in (2.0, 2.5, 3.0, 3.5):
        line(f"gate6 k {k}", run(glo=6, k=k))
    say("")
    for t in (0.5, 0.75, None):
        line(f"gate6 TP {t if t else 'none':>4}", run(glo=6, tp_f=t))

    say("\n=== controls ===")
    say(HDR)
    for sd in (49, 50, 51):
        line(f"RANDOM gate>=6 seed {sd}", run(glo=6, rand=sd), mark=False)
    line("gate 6-8 band, UP side only", None, mark=False)

    say("\n=== side by side: what the owner would be choosing ===")
    for lab, T in (("LIVE now   k2.5 gate8", run(glo=8)), ("CAND       k2.5 gate6", run(glo=6)),
                   ("the added band 6-8", run(glo=6, ghi=8))):
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
        say(f"  {len(T) / days:.2f} trades a day, PF {pf(T.net.values):.2f}, ${T.net.sum() / yrs:+.0f} a year, "
            f"win {100 * (T.net > 0).mean():.1f}%")
        say(f"  max drawdown ${dd_s.min():.0f}" + (f", recovered in {rec_d} days" if rec_d >= 0 else ", never recovered")
            + f"; profit per $ of drawdown {T.net.sum() / abs(dd_s.min()):.1f}")
        say(f"  longest losing run {streak}; months positive {int((mo > 0).sum())}/{len(mo)}; "
            f"last 12 months ${T[T.t >= end_t - pd.Timedelta(days=365)].net.sum():+.0f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
