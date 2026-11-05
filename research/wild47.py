"""Round 47 (5 Nov 2026): the wildest M1 gold scalper still untried. Seven angles never tested.

"ciptakan aku lagi ea scalping yang paling gila di m1. m1 ya, aku tak nak tf lain."

Round 46 proved there is NO edge in predicting the next minute's return from a bar's own features: a
saturated model trained on 3.3 years and applied honestly to the next 3.3 has exactly zero gross edge
before costs. But that is a precise claim about ONE thing - the unconditional next-minute return. It
does not touch conditional EVENTS, which is what the live spike fade is and why that one works.

So the question is whether any event on M1 is left. These seven have genuinely never been tested, and
the first is the one worth being excited about, because it is only testable at all because the broker's
export carries the spread of every single bar.

  A  SPREAD-SHOCK SCALP. When the spread itself blows out, the broker has pulled liquidity. Prints
     made into a thin book are the ones most likely to be wrong. Nothing in 46 rounds has looked at
     this. Measured first, then traded: fade the move made during the shock, once the spread is back.
  B  SPIKE CLUSTERS. Is the second spike inside a cluster better or worse than an isolated one? The
     live rule treats them all alike.
  C  RE-ENTRY AFTER A STOP. The spike fade loses 80% of the time for small amounts. If a stop means
     the reversion simply started lower, re-entering once should be free money; if it means the move
     was real, it should be a disaster. Either answer is useful.
  D  MINUTE-OF-N MICROSTRUCTURE. Does gold overshoot at the 5, 15 and 60-minute boundaries where
     algorithms and bar-close systems act? Descriptive, then the spike fade split by the signal bar's
     position inside the 5 / 15 / 60-minute block.
  E  TICK-VOLUME SPIKE, with the cost gate. Round 16 tested volume spikes on M5 before the cost gate
     existed; on M1 and gated it is untested.
  F  THE UP SIDE, with a trend filter. Round 42 found up spikes CONTINUE, but only in the second half,
     which was called a bull-market artefact. This tests that claim directly by trading the up side
     only when the daily trend is DOWN. If it is really a trend effect it should work there.
  G  VOLATILITY-REGIME SPLIT of the live rule, to see whether the EA should scale its own aggression.

Plus the live v1.98 rule as the benchmark and random entries under the same gate as the control.

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
HDR = ("variant                           trades /day  win%   PF  half1 half2 stress last12$    net$"
       "  maxDD$ mth+   by year")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    vol = d.v.resample("1min", label="left", closed="left").sum().reindex(B.index).values
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
    base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 1500)
    base[-3:] = False
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    days = B.index.normalize().nunique()
    mid_t, end_t = B.index[n // 2], B.index[-1]
    nxt = np.r_[(o[2:] - o[1:-1]) * usd, np.nan, np.nan]
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, {days} days. "
        f"Halves split at {mid_t:%Y-%m-%d}. Median spread ${np.median(spr) * usd:.3f} per 0.01 lot.")

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
            say(f"{lab:33s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:33s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+7.0f} {dd:+7.0f} {(mo > 0).sum():2d}/{len(mo)}  {yr}"
            f"{'  PASS' if ok and mark else ''}")
        return ok

    def fade(idx, side=1, sl_atr=0.2, maxb=45, ref="bar"):
        """fade the signal bar: BUY below a down bar (side 1) or SELL above an up bar (side -1)"""
        S = []
        for i in idx:
            sl = (l_[i] - sl_atr * atr[i]) if side == 1 else (h_[i] + sl_atr * atr[i])
            if (sl - c[i]) * side >= 0:
                continue
            S.append(dict(k0=i + 1, kind="mkt", dir=side, sl=sl, exp=i + 1, maxb=maxb))
        return go(S)

    say("\n=== benchmark: the live v1.98 rule, and the control ===")
    say(HDR)
    live = base & (gate >= 8) & (c < o) & (rng >= 2.5 * atr)
    line("LIVE v1.98 (k2.5 gate8 45m)", fade(np.where(live)[0]))
    rg0 = np.random.default_rng(47)
    line("RANDOM under gate8", fade(np.where(base & (gate >= 8) & (rg0.random(n) < 0.0015))[0]), mark=False)

    # ---------------------------------------------------------------- A. spread shock
    say("\n=== A. SPREAD-SHOCK SCALP: trade what happens when the broker pulls liquidity ===")
    sp_med = pd.Series(spr).rolling(1440, min_periods=200).median().shift(1).values
    shock = np.where(sp_med > 0, spr / sp_med, np.nan)          # the spread now, in multiples of its own daily median
    say(f"Spread relative to its own 1-day rolling median: p50 {np.nanpercentile(shock[base], 50):.2f}, "
        f"p90 {np.nanpercentile(shock[base], 90):.2f}, p99 {np.nanpercentile(shock[base], 99):.2f}, "
        f"max {np.nanmax(shock[base]):.1f}")
    say("\nFirst, measured: after a bar whose spread is >= x times its own median, where does price go?")
    say("(mean move of the close over the next h minutes, in $ per 0.01 lot, signed so + means the")
    say("shock bar's move REVERSED; the cost to take it is the spread at the time)")
    say(f"\n{'shock':>12} {'dir':>5} {'n':>7} {'1m':>7} {'5m':>7} {'15m':>7} {'30m':>7} {'45m':>7} {'cost then':>10}")
    for lo, hi, lab in ((2, 3, "2 - 3x"), (3, 5, "3 - 5x"), (5, 10, "5 - 10x"), (10, 1e9, ">= 10x")):
        for sd, dlab in ((1, "down"), (-1, "up")):
            m = base & (shock >= lo) & (shock < hi) & ((c < o) if sd == 1 else (c > o))
            if m.sum() < 80:
                continue
            row = []
            for hh in (1, 5, 15, 30, 45):
                j = np.arange(n) + hh
                ok = m & (j < n) & ~newday[np.minimum(j, n - 1)]
                jj = j[ok]
                row.append(np.nanmean((c[jj] - c[ok]) * usd * sd) if ok.sum() > 30 else np.nan)
            say(f"{lab:>12} {dlab:>5} {m.sum():7d} " + " ".join(f"{x:7.3f}" for x in row) +
                f" {np.nanmean(spr[m]) * usd:10.3f}")
    say("\nTraded. SL 0.2 ATR beyond the shock bar's extreme, no TP, 45 min:")
    say(HDR)
    for lo in (2, 3, 5):
        for sd, dlab in ((1, "fade DOWN (buy)"), (-1, "fade UP (sell)")):
            m = base & (shock >= lo) & ((c < o) if sd == 1 else (c > o)) & (rng >= 1.0 * atr)
            line(f"shock>={lo}x {dlab}", fade(np.where(m)[0], side=sd))
    say("\nand with the cost gate as well (the spread must still be small vs ATR):")
    say(HDR)
    for lo in (2, 3):
        for x in (4, 8):
            m = base & (shock >= lo) & (gate >= x) & (c < o) & (rng >= 1.0 * atr)
            line(f"shock>={lo}x gate>={x} fade DOWN", fade(np.where(m)[0]))
    say("\nthe reverse question - does the LIVE rule do better or worse on a wide-spread bar?")
    say(HDR)
    for lo, hi, lab in ((0, 1.2, "spread < 1.2x median"), (1.2, 2.0, "1.2 - 2x"), (2.0, 1e9, ">= 2x")):
        m = live & (shock >= lo) & (shock < hi)
        line(f"LIVE, {lab}", fade(np.where(m)[0]))

    # ---------------------------------------------------------------- B. clusters
    say("\n=== B. SPIKE CLUSTERS: is the second spike of a cluster better or worse? ===")
    sig_i = np.where(live)[0]
    prev = np.full(n, -10 ** 9)
    last = -10 ** 9
    for i in range(n):                                                      # minutes since the previous signal
        prev[i] = last
        if live[i]:
            last = i
    since = np.arange(n) - prev
    say(HDR)
    for lo, hi, lab in ((0, 10, "within 10 min of the last"), (10, 30, "10 - 30 min"),
                        (30, 120, "30 - 120 min"), (120, 10 ** 9, "isolated, > 2 h")):
        m = live & (since >= lo) & (since < hi)
        line(f"{lab}", fade(np.where(m)[0]))

    # ---------------------------------------------------------------- C. re-entry after a stop
    say("\n=== C. RE-ENTRY AFTER A STOP: if the stop just means the reversion started lower ===")
    say("Take the live rule. Whenever it is stopped out, buy again at the next bar's open, once, with")
    say("the stop 0.2 ATR under the new low. If reversion is real this should be free; if the move was")
    say("real it should be a disaster. Both answers are worth having.")
    T0_ = fade(sig_i)
    S2 = []
    if T0_ is not None:
        stopped = T0_[T0_.why == "SL"]
        for kk in stopped.kk.values:
            # the bar the stop happened on is not recorded, so re-enter one bar after the entry window ends
            i = int(kk)
            for q in range(i, min(i + 46, n - 2)):
                if l_[q] <= (l_[i - 1] - 0.2 * atr[i - 1]):
                    j = q + 1
                    if j >= n - 1 or flat[j] or not np.isfinite(atr[j]):
                        break
                    sl = l_[q] - 0.2 * atr[q]
                    if sl < c[q]:
                        S2.append(dict(k0=j, kind="mkt", dir=1, sl=sl, exp=j, maxb=45))
                    break
    say(HDR)
    line("re-entries only", go(S2))
    line("live + re-entries combined", go([dict(k0=i + 1, kind="mkt", dir=1, sl=l_[i] - 0.2 * atr[i],
                                                exp=i + 1, maxb=45) for i in sig_i
                                           if l_[i] - 0.2 * atr[i] < c[i]] + S2))

    # ---------------------------------------------------------------- D. minute-of-N
    say("\n=== D. MINUTE-OF-N MICROSTRUCTURE: do the 5 / 15 / 60-minute boundaries matter? ===")
    say("mean next-minute move and mean |move| by the bar's position inside each block, in $:")
    for N in (5, 15, 60):
        pos = hm % N
        say(f"\n  block of {N} minutes:")
        say("    position " + " ".join(f"{p:>8}" for p in range(min(N, 15))))
        mn, ab = [], []
        for p in range(min(N, 15)):
            m = base & (pos == p) & np.isfinite(nxt)
            mn.append(np.nanmean(nxt[m]))
            ab.append(np.nanmean(np.abs(nxt[m])))
        say("    mean     " + " ".join(f"{x:+8.4f}" for x in mn))
        say("    mean |.| " + " ".join(f"{x:8.4f}" for x in ab))
    say("\nthe live rule split by where the signal bar sits in each block:")
    say(HDR)
    for N in (5, 15, 60):
        for grp, lab in (([0], "first minute of the block"), (list(range(1, N - 1)), "middle"),
                         ([N - 1], "last minute of the block")):
            m = live & np.isin(hm % N, grp)
            line(f"block {N}: {lab}", fade(np.where(m)[0]))

    # ---------------------------------------------------------------- E. tick volume
    say("\n=== E. TICK-VOLUME SPIKE, gated (round 16 tested volume on M5, before the gate existed) ===")
    vm = pd.Series(vol).rolling(60, min_periods=30).mean().shift(1).values
    vr = np.where(vm > 0, vol / vm, np.nan)
    say(f"tick volume relative to its own 60-bar mean: p50 {np.nanpercentile(vr[base], 50):.2f}, "
        f"p95 {np.nanpercentile(vr[base], 95):.2f}, p99 {np.nanpercentile(vr[base], 99):.2f}")
    say(HDR)
    for k in (3, 5, 8):
        for x in (0, 8):
            for sd, dlab in ((1, "fade DOWN"), (-1, "fade UP")):
                m = base & (vr >= k) & (gate >= x) & ((c < o) if sd == 1 else (c > o))
                line(f"vol>={k}x gate>={x} {dlab}", fade(np.where(m)[0], side=sd))
    say("\nvolume spike ON TOP of the live signal (does it pick the better spikes?):")
    say(HDR)
    for lo, hi, lab in ((0, 2, "vol < 2x"), (2, 4, "2 - 4x"), (4, 1e9, ">= 4x")):
        m = live & (vr >= lo) & (vr < hi)
        line(f"LIVE, {lab}", fade(np.where(m)[0]))

    # ---------------------------------------------------------------- F. the up side, trend-filtered
    say("\n=== F. THE UP SIDE with a daily trend filter ===")
    say("Round 42 found up spikes CONTINUE, but only in the second half, and called it a bull-market")
    say("artefact. If that is right, fading up spikes should work when the DAILY trend is down.")
    D = B.c.resample("1D").last().dropna()
    dtr = (D - D.shift(20)).reindex(B.index.normalize()).values                 # 20-day change, known at the open
    say(HDR)
    upsig = base & (gate >= 8) & (c > o) & (rng >= 2.5 * atr)
    line("fade UP, all days", fade(np.where(upsig)[0], side=-1), mark=False)
    line("fade UP, 20-day trend DOWN", fade(np.where(upsig & (dtr < 0))[0], side=-1))
    line("fade UP, 20-day trend UP", fade(np.where(upsig & (dtr > 0))[0], side=-1), mark=False)
    line("LIVE buy, 20-day trend DOWN", fade(np.where(live & (dtr < 0))[0]))
    line("LIVE buy, 20-day trend UP", fade(np.where(live & (dtr > 0))[0]))

    # ---------------------------------------------------------------- G. regime split
    say("\n=== G. the live rule by volatility regime, to see if the EA should scale its own size ===")
    a100 = pd.Series(tr).ewm(alpha=1 / 100, adjust=False).mean().shift(1).values
    ratio = np.where(a100 > 0, atr / a100, np.nan)
    say(HDR)
    for lo, hi, lab in ((0, 0.8, "ATR14/ATR100 < 0.8"), (0.8, 1.2, "0.8 - 1.2"),
                        (1.2, 2.0, "1.2 - 2.0"), (2.0, 1e9, ">= 2.0")):
        line(f"LIVE, {lab}", fade(np.where(live & (ratio >= lo) & (ratio < hi))[0]))
    say("\nand by the gate band the signal arrived in:")
    say(HDR)
    for lo, hi, lab in ((8, 10, "gate 8 - 10"), (10, 14, "10 - 14"), (14, 20, "14 - 20"), (20, 1e9, ">= 20")):
        line(f"LIVE, {lab}", fade(np.where(live & (gate >= lo) & (gate < hi))[0]))

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
