"""Round 48 (5 Nov 2026): the owner's actual complaint, taken seriously.

"sepanjang market sedang berjalan dan berlalu naik turun hampir 100 pip, apa ea sekarang buat?
perati je? ... aku nak scalping, untung makan sikit-sikit ... 1 hari aku tunggu trade langsung tak
ada, kalau ada pun 1 2 je. apa scalping macam tu."

He is right about the symptom: 1.31 trades a day is not a scalper, and gold moves $10+ a day while the
EA waits. Two things have never been tried in the form he is describing.

  A  SCALP THE RANGE, not the spike. He is describing buying low and selling high inside the day's
     own range. Tested as the position of price inside (i) the day's range so far, (ii) the last 60
     and 240 bars (Donchian position) - buy the bottom band, sell the top band, gated by cost, small
     targets. Round 43 tested a z-score against a moving average inside one session; the position
     inside a REALISED range is a different thing and has never been run on M1.
  B  SMALL PROFITS OFTEN, which is what he keeps asking for. The live rule wins 17% of the time and
     waits 45 minutes. A near target turns the same signal into something that wins far more often
     with a much smaller drawdown, and makes less money. That is a preference, not an error, so this
     prints the win rate, months positive and drawdown next to the profit so he can choose.
  C  THE MENU. Every configuration that produces 2 or more trades a day, whether or not it passes the
     pass rule, with net per year and drawdown, so the choice is his and not hidden behind a
     threshold.

Pass rule for reference: >= 150 trades, PF >= 1.15 after spread, both halves >= 1.05, stress >= 1.05,
last 12 months positive. 0.01 lot, so every figure is in dollars.
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
HDR = ("variant                       trades /day  win%   PF  half1 half2 stress  net$  $/yr  maxDD$"
       " mth+   by year")


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
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, {days} days "
        f"({yrs:.1f} years). Median spread ${np.median(spr) * usd:.3f} per 0.01 lot.")
    # the day's range SO FAR, known at each bar's close
    dgrp = pd.Series(np.arange(n)).groupby(dates)
    dh = pd.Series(h_).groupby(dates).cummax().shift(1).values
    dl = pd.Series(l_).groupby(dates).cummin().shift(1).values
    dpos = np.where(dh > dl, (c - dl) / (dh - dl), np.nan)          # 0 = at the day's low, 1 = at its high
    say(f"Average daily range so far by midday: ${np.nanmean((dh - dl)[hm == 720]):.1f}, "
        f"full day ${np.nanmean((dh - dl)[hm == 1319]):.1f} - the owner is right that there is movement.")

    def go(S):
        if len(S) < 60:
            return None
        tr_ = SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat)
        if len(tr_) < 50:
            return None
        T = pd.DataFrame(tr_, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 50:
            say(f"{lab:29s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:29s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {T.net.sum():+6.0f} {T.net.sum() / yrs:+5.0f} {dd:+7.0f} "
            f"{(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok and mark else ''}")
        return ok

    def mk(idx, side, sl_atr, tp_atr=None, tp_f=None, maxb=30):
        S = []
        for i in idx:
            sl = c[i] - side * sl_atr * atr[i]
            tp = None
            if tp_atr:
                tp = c[i] + side * tp_atr * atr[i]
            elif tp_f:
                tp = c[i] + side * tp_f * rng[i]
            if (sl - c[i]) * side >= 0 or (tp is not None and (tp - c[i]) * side <= 0):
                continue
            g = dict(k0=i + 1, kind="mkt", dir=side, sl=sl, exp=i + 1, maxb=maxb)
            if tp is not None:
                g["tp"] = tp
            S.append(g)
        return go(S)

    # ------------------------------------------------------------------ A. scalp the range
    say("\n=== A. SCALP THE RANGE: buy the bottom of the day's range, sell the top ===")
    say("Position of the close inside the day's range so far (0 = at the low, 1 = at the high).")
    say("SL 1 ATR, TP 1 ATR, out after 30 min, gated by cost.")
    say(HDR)
    for band in (0.10, 0.20, 0.30):
        for x in (4, 8):
            lo = base & (gate >= x) & np.isfinite(dpos) & (dpos <= band) & (dh - dl > 2 * atr)
            hi = base & (gate >= x) & np.isfinite(dpos) & (dpos >= 1 - band) & (dh - dl > 2 * atr)
            line(f"buy bottom {band:.0%} gate{x}", mk(np.where(lo)[0], 1, 1.0, tp_atr=1.0))
            line(f"sell top {band:.0%} gate{x}", mk(np.where(hi)[0], -1, 1.0, tp_atr=1.0))
    say("\nsame but only after the day has already moved (range > 4 ATR), which is the owner's")
    say("'market moved 100 pips and the EA just watched' case:")
    say(HDR)
    for band in (0.10, 0.20):
        lo = base & (gate >= 8) & np.isfinite(dpos) & (dpos <= band) & (dh - dl > 4 * atr)
        hi = base & (gate >= 8) & np.isfinite(dpos) & (dpos >= 1 - band) & (dh - dl > 4 * atr)
        line(f"buy bottom {band:.0%}, range>4ATR", mk(np.where(lo)[0], 1, 1.0, tp_atr=1.0))
        line(f"sell top {band:.0%}, range>4ATR", mk(np.where(hi)[0], -1, 1.0, tp_atr=1.0))

    say("\n=== A2. the same idea against a ROLLING range (Donchian position), not the day's ===")
    say(HDR)
    for w in (60, 240):
        hh = pd.Series(h_).rolling(w).max().shift(1).values
        ll = pd.Series(l_).rolling(w).min().shift(1).values
        pos = np.where(hh > ll, (c - ll) / (hh - ll), np.nan)
        for band in (0.05, 0.15):
            lo = base & (gate >= 8) & np.isfinite(pos) & (pos <= band)
            hi = base & (gate >= 8) & np.isfinite(pos) & (pos >= 1 - band)
            line(f"{w}-bar: buy bottom {band:.0%}", mk(np.where(lo)[0], 1, 1.0, tp_atr=1.0))
            line(f"{w}-bar: sell top {band:.0%}", mk(np.where(hi)[0], -1, 1.0, tp_atr=1.0))
    rg0 = np.random.default_rng(48)
    say("")
    line("RANDOM, gate8, SL1 TP1 30m", mk(np.where(base & (gate >= 8) & (rg0.random(n) < 0.002))[0],
                                          1, 1.0, tp_atr=1.0), mark=False)

    # ------------------------------------------------------------------ B. small profits often
    say("\n=== B. SMALL PROFITS OFTEN: the same live signal, with a near target ===")
    say("'untung makan sikit-sikit'. Same entries as live v1.98, but a close take profit. This trades")
    say("the SAME number of times; what changes is how often it wins and how deep it drawdowns.")
    say(HDR)
    for k in (2.5, 2.0):
        live = base & (gate >= 8) & (c < o) & (rng >= k * atr)
        idx = np.where(live)[0]
        for tp_f, maxb in ((0.25, 20), (0.35, 20), (0.5, 20), (0.5, 45), (0.75, 45), (None, 45)):
            S = []
            for i in idx:
                sl = l_[i] - 0.2 * atr[i]
                tp = c[i] + tp_f * rng[i] if tp_f else None
                if sl >= c[i] or (tp is not None and tp <= c[i]):
                    continue
                g = dict(k0=i + 1, kind="mkt", dir=1, sl=sl, exp=i + 1, maxb=maxb)
                if tp is not None:
                    g["tp"] = tp
                S.append(g)
            line(f"k{k} TP {tp_f if tp_f else 'none':>4} hold {maxb}m", go(S))

    # ------------------------------------------------------------------ C. the menu
    say("\n=== C. THE MENU: every setting giving 2+ trades a day, pass or not, so the choice is his ===")
    say("Columns to compare: trades a day, PF, net per YEAR at 0.01 lot, max drawdown, win rate,")
    say("and what share of months were positive. 'pass' is the project's rule, not a verdict on")
    say("whether it is worth trading.")
    say(f"\n{'config':>34} {'/day':>6} {'PF':>6} {'$/yr':>7} {'maxDD$':>8} {'win%':>6} {'mth+':>7} {'h1':>6} {'pass':>5}")
    rows = []
    for k in (3.0, 2.5, 2.0, 1.5, 1.0):
        for x in (12, 8, 6, 4):
            for tp_f, maxb, elab in ((None, 45, "no TP 45m"), (0.5, 20, "TP 0.5x 20m")):
                hit = base & (gate >= x) & (c < o) & (rng >= k * atr)
                idx = np.where(hit)[0]
                if len(idx) < 300:
                    continue
                S = []
                for i in idx:
                    sl = l_[i] - 0.2 * atr[i]
                    tp = c[i] + tp_f * rng[i] if tp_f else None
                    if sl >= c[i] or (tp is not None and tp <= c[i]):
                        continue
                    g = dict(k0=i + 1, kind="mkt", dir=1, sl=sl, exp=i + 1, maxb=maxb)
                    if tp is not None:
                        g["tp"] = tp
                    S.append(g)
                T = go(S)
                if T is None or len(T) / days < 2.0:
                    continue
                P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
                P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
                l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
                eq = T.net.cumsum().values
                dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
                mo = T.groupby(T.t.dt.to_period("M")).net.sum()
                ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
                rows.append((len(T) / days, f"k{k} gate{x} {elab}", P, T.net.sum() / yrs, dd,
                             100 * (T.net > 0).mean(), (mo > 0).sum(), len(mo), P1, ok))
    for r in sorted(rows, key=lambda z: -z[0]):
        say(f"{r[1]:>34} {r[0]:6.2f} {SA.f2(r[2]):>6} {r[3]:+7.0f} {r[4]:+8.0f} {r[5]:6.1f} "
            f"{str(r[6]) + '/' + str(r[7]):>7} {SA.f2(r[8]):>6} {'PASS' if r[9] else '':>5}")
    say("\nfor reference, what is live now:")
    liveT = None
    hit = base & (gate >= 8) & (c < o) & (rng >= 2.5 * atr)
    S = [dict(k0=i + 1, kind="mkt", dir=1, sl=l_[i] - 0.2 * atr[i], exp=i + 1, maxb=45)
         for i in np.where(hit)[0] if l_[i] - 0.2 * atr[i] < c[i]]
    liveT = go(S)
    if liveT is not None:
        eq = liveT.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = liveT.groupby(liveT.t.dt.to_period("M")).net.sum()
        say(f"{'LIVE v1.98 k2.5 gate8 no TP 45m':>34} {len(liveT) / days:6.2f} {SA.f2(pf(liveT.net.values)):>6} "
            f"{liveT.net.sum() / yrs:+7.0f} {dd:+8.0f} {100 * (liveT.net > 0).mean():6.1f} "
            f"{str((mo > 0).sum()) + '/' + str(len(mo)):>7}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
