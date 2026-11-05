"""Round 43 (5 Nov 2026): build M1 gold rules ONLY from what round 42 measured.

Round 42 (`research/status/m1char42.txt`) measured gold's M1 behaviour instead of guessing rules. Six
things came out of it, and every rule below is traceable to one of them. Nothing here is borrowed from a
website or an indicator book; that approach already failed in rounds 21, 25, 26 and 30.

  M1  the cost gate is REAL and usable in advance. corr(ATR/spread now, the next 20 minutes' range)
      = 0.692 and corr(ATR now, ATR in 20 min) = 0.945, and range/spread rises monotonically with the
      gate (11 -> 24 -> 33 -> 45 -> 66 -> 135). Both halves agree. So every rule here is gated, and
      every family gets a gate sweep: a real cost effect is monotone in the gate.
  M2  gold M1 mean-reverts, but WHERE depends on the session. Variance ratio by session:
      Asia 01:30-09:00  0.82 at every horizon (the strongest, flattest reversion found)
      London 09:00-15:30  1.02-1.06  -> the only session that TRENDS
      NY overlap 15:30-19:00  0.95 at 1m falling to 0.86 at 60m
      and under the live gate (>=8) the reversion BUILDS with the horizon: 0.96 at 1m -> 0.845 at 60m.
  M3  only the DOWN side fades. After a 3 ATR shock with the gate on, a down bar is bought back
      (+$1.20 over 20 min); an up bar keeps going. The up side is unstable across halves (+0.25/-1.04),
      which is the bull-market signature, so it is not traded.
  M4  after a 3 ATR down shock with the gate on there is room for a stop and a target: median MFE
      $6.49 against median MAE $5.24 over 20 min, and 86.5% reach 1 ATR the right way.
  M5  streaks and quiet-then-expansion are statistically real but economically dead: mean moves of
      $0.05-$0.16 against a $0.19 spread. Only the "busy" regime (ATR14/ATR100 >= 1.6) clears it,
      +$0.228 over 30 min with t 4.7, so that one gets a test.
  M6  gold does NOT respect round numbers on M1. The real $1/$5/$10 grid gave -$0.005 and a grid
      shifted by half a step gave +$0.006, with |t| < 1.2 on both. Dead, not tested further.

Rules, each with the measurement it comes from:
  CUMFADE  (M2, M3) the live spike fade needs ONE bar of 3 ATR. Since the reversion builds over 15-60
           minutes under the gate, fade a CUMULATIVE drop of k x ATR over the last w bars instead.
           This is the main candidate: it should fire far more often for the same reason.
  ASIAFADE (M2) z-score fade inside the Asia session, where the variance ratio is 0.82.
  LDNFADE  (M2) the SAME rule in London, as a falsification control: London trends, so it must fail.
           If ASIAFADE and LDNFADE both pass, the session finding is not what is driving it.
  LDNMOM   (M2) momentum in London only, the mirror image: an N-bar breakout in the break direction.
  SPKHOLD  (M2) the live spike fade with longer holds and a closed-bar trailing stop, because the
           reversion keeps building to 60 minutes under the gate while the EA exits at 20.
  BUSYLONG (M5) long only while ATR14/ATR100 >= 1.6.
  NYOPEN   (M1, and round 42 H: 15:30 is the most explosive minute of the day, the next 30 minutes
           range $9.57) an OCO on the 15:15-15:30 range, gated.
  RAND     random entries under the same gate, the control every round must have.

Pass rule: >= 150 trades, PF >= 1.15 after the bar's real spread, both halves >= 1.05, stress
(1.5x spread) >= 1.05, last 12 months positive. 0.01 lot, so every figure is in dollars.
Trailing stops are set from CLOSED bars only (the round 35 lesson: using the same bar's low to set the
trail before checking its high gave a fake PF 2.09).
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

ASIA = (90, 540)        # server minutes
LONDON = (540, 930)
NY = (930, 1140)


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
    spr = B.s.values.astype(float)                             # price units
    spr_d = spr * usd
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h_ - l_, np.maximum(np.abs(h_ - c1), np.abs(l_ - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    atr100 = pd.Series(tr).ewm(alpha=1 / 100, adjust=False).mean().shift(1).values
    gate = np.where(spr > 0, (atr * usd) / spr_d, np.nan)
    base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 300)
    base[-3:] = False
    days = B.index.normalize().nunique()
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    mid_t, end_t = B.index[n // 2], B.index[-1]
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, {days} days. "
        f"Halves split at {mid_t:%Y-%m-%d}. Median spread ${np.median(spr_d):.3f} per 0.01 lot.")

    hdr = ("variant                          trades /day  win%   PF  half1 half2 stress last12$    net$"
           "  maxDD$ mth+   by year")

    def run(sigs):
        if len(sigs) < 60:
            return None
        tr_ = SA.sim(*arr, sorted(sigs, key=lambda g: g["k0"]), flat)
        if len(tr_) < 50:
            return None
        T = pd.DataFrame(tr_, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 50:
            say(f"{lab:32s} {0 if T is None else len(T):6d} (too few)")
            return None
        P = pf(T.net.values)
        P1, P2 = pf(T[T.t < mid_t].net.values), pf(T[T.t >= mid_t].net.values)
        PS = pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:32s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+7.0f} {dd:+7.0f} {(mo > 0).sum():2d}/{len(mo)}  {yr}"
            f"{'  PASS' if ok and mark else ''}")
        return ok

    def sess(lo, hi):
        return (hm >= lo) & (hm < hi)

    # ---------------------------------------------------------------- CUMFADE
    say("\n=== CUMFADE: fade a cumulative drop of k x ATR over the last w bars (from M2 + M3) ===")
    say("The live spike fade needs one bar of 3 ATR, which is rare. Round 42 showed the reversion under")
    say("the gate builds over 15-60 minutes, not within one bar, so the drop is measured over a window.")
    say("BUY only (M3). SL = the window's low - 0.2 ATR. TP = tp x the drop. Session filter from M2.")
    say(hdr)

    roll_lo, roll_hi = {}, {}

    def extremes(w):
        if w not in roll_lo:
            roll_lo[w] = pd.Series(l_).rolling(w).min().shift(1).values
            roll_hi[w] = pd.Series(h_).rolling(w).max().shift(1).values
        return roll_lo[w], roll_hi[w]

    def cumfade(w, k, x, tp_f, maxb, where=None, side=1):
        lo_w, hi_w = extremes(w)
        ref = np.r_[np.full(w, np.nan), c[:-w]]                 # the close w bars ago
        drop = (ref - c) * side                                 # + = it moved against the fade by this much
        ok = base & (gate >= x) & np.isfinite(lo_w) & np.isfinite(hi_w) & np.isfinite(ref) & (drop >= k * atr)
        if where is not None:
            ok &= where
        S = []
        for i in np.where(ok)[0]:
            sl = (lo_w[i] - 0.2 * atr[i]) if side == 1 else (hi_w[i] + 0.2 * atr[i])
            tp = (c[i] + side * tp_f * drop[i]) if tp_f else None
            if (sl - c[i]) * side >= 0 or (tp is not None and (tp - c[i]) * side <= 0):
                continue
            g = dict(k0=i + 1, kind="mkt", dir=side, sl=sl, exp=i + 1, maxb=maxb)
            if tp is not None:
                g["tp"] = tp
            S.append(g)
        return run(S)

    def randctl(x, maxb, rate=0.004, seed=43, where=None):
        """random entries under the same gate, with an ATR stop and target of the same shape"""
        rg = np.random.default_rng(seed)
        ok = base & (gate >= x) & (rg.random(n) < rate)
        if where is not None:
            ok &= where
        S = []
        for i in np.where(ok)[0]:
            dr = 1 if rg.random() < 0.5 else -1
            S.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c[i] - dr * 1.5 * atr[i], tp_r=1.0,
                          exp=i + 1, maxb=maxb))
        return run(S)

    best = None
    for w in (5, 10, 15, 30):
        for k in (1.5, 2.0, 3.0):
            T = cumfade(w, k, 8, 0.5, 30)
            r = line(f"w{w} drop{k} gate8 TP.5 30m", T)
            if r:
                best = best or (w, k)
    say("")
    line("RANDOM, gate>=8, 30m", randctl(8, 30), mark=False)
    line("RANDOM, gate>=8, 60m", randctl(8, 60, seed=44), mark=False)

    say("\nCUMFADE target and hold sweep (w 10, drop 2 ATR, gate 8):")
    say(hdr)
    for tp_f in (0.3, 0.5, 0.75, 1.0, None):
        for maxb in (15, 30, 60):
            line(f"TP {tp_f if tp_f else 'none':>4} hold {maxb}m", cumfade(10, 2.0, 8, tp_f, maxb))

    say("\nCUMFADE gate sweep (w 10, drop 2 ATR, TP 0.5, 30m) - a real cost effect is MONOTONE:")
    say(hdr)
    for x in (0, 4, 6, 8, 10, 12, 16):
        line(f"gate >= {x:2d}", cumfade(10, 2.0, x, 0.5, 30))

    say("\nCUMFADE by session (w 10, drop 2 ATR, gate 8, TP 0.5, 30m). M2 says Asia reverts, London trends:")
    say(hdr)
    for lab, wh in (("Asia 01:30-09:00", sess(*ASIA)), ("London 09:00-15:30", sess(*LONDON)),
                    ("NY 15:30-19:00", sess(*NY)), ("late 19:00-22:00", (hm >= 1140) & (hm < 1320))):
        line(f"{lab}", cumfade(10, 2.0, 8, 0.5, 30, where=wh))
    say("mirror check - fade a cumulative RISE (M3 says the up side should not work):")
    line("fade cumulative RISE, all day", cumfade(10, 2.0, 8, 0.5, 30, side=-1))

    # ---------------------------------------------------------------- ASIAFADE / LDNFADE / LDNMOM
    say("\n=== ASIAFADE / LDNFADE: z-score fade, Asia against London (from M2) ===")
    say("z = (close - SMA(w)) / SD(w). Fade |z| >= zk, gated, SL 1.5 ATR, TP back at the SMA.")
    say("London is the FALSIFICATION control: its variance ratio is above 1, so this rule must fail there.")
    say("If it passes in both, the session finding is not what is driving the result.")
    say(hdr)

    def zfade(w, zk, x, where, maxb, side=0, mom=False):
        sma = pd.Series(c).rolling(w).mean().shift(1).values
        sd = pd.Series(c).rolling(w).std(ddof=0).shift(1).values
        z = np.where(sd > 0, (c - sma) / sd, np.nan)
        S = []
        hit = base & (gate >= x) & where & np.isfinite(z) & (np.abs(z) >= zk)
        for i in np.where(hit)[0]:
            dr = int(np.sign(z[i])) * (1 if mom else -1)        # fade, or follow when mom
            if dr == 0 or (side and dr != side):
                continue
            sl = c[i] - dr * 1.5 * atr[i]
            tp = sma[i] if not mom else c[i] + dr * 1.5 * atr[i] * 2
            if (tp - c[i]) * dr <= 0:
                continue
            S.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, tp=tp, exp=i + 1, maxb=maxb))
        return run(S)

    for w in (20, 60):
        for zk in (2.0, 2.5, 3.0):
            line(f"ASIA  z{zk} w{w} gate8 60m", zfade(w, zk, 8, sess(*ASIA), 60))
    say("")
    for w in (20, 60):
        for zk in (2.0, 2.5, 3.0):
            line(f"LDN   z{zk} w{w} gate8 60m (control)", zfade(w, zk, 8, sess(*LONDON), 60), mark=False)
    say("")
    line("ASIA  z2.5 w20 gate8, BUY only", zfade(20, 2.5, 8, sess(*ASIA), 60, side=1))
    line("ASIA  z2.5 w20 gate8, SELL only", zfade(20, 2.5, 8, sess(*ASIA), 60, side=-1))
    say("\nAsia gate sweep (z 2.5, w 20, 60m):")
    say(hdr)
    for x in (0, 4, 6, 8, 12):
        line(f"ASIA z2.5 gate >= {x:2d}", zfade(20, 2.5, x, sess(*ASIA), 60))

    say("\n=== LDNMOM: follow the move in London, the only trending session (from M2) ===")
    say(hdr)
    for w in (20, 60):
        for zk in (2.0, 2.5):
            line(f"LDN follow z{zk} w{w} gate8 60m", zfade(w, zk, 8, sess(*LONDON), 60, mom=True))

    def brk(w, x, where, maxb, tpr):
        hh = pd.Series(h_).rolling(w).max().shift(1).values
        ll = pd.Series(l_).rolling(w).min().shift(1).values
        S = []
        hit = base & (gate >= x) & where & np.isfinite(hh) & np.isfinite(ll)
        up = hit & (c > hh)
        dn = hit & (c < ll)
        for i in np.where(up)[0]:
            S.append(dict(k0=i + 1, kind="mkt", dir=1, sl=c[i] - 1.5 * atr[i], tp_r=tpr, exp=i + 1, maxb=maxb))
        for i in np.where(dn)[0]:
            S.append(dict(k0=i + 1, kind="mkt", dir=-1, sl=c[i] + 1.5 * atr[i], tp_r=tpr, exp=i + 1, maxb=maxb))
        return run(S)

    for w in (20, 60):
        for tpr in (1.0, 2.0):
            line(f"LDN {w}-bar break TP{tpr}R 60m", brk(w, 8, sess(*LONDON), 60, tpr))
    line("ASIA 20-bar break TP2R 60m (control)", brk(20, 8, sess(*ASIA), 60, 2.0), mark=False)

    # ---------------------------------------------------------------- SPKHOLD
    say("\n=== SPKHOLD: the live spike fade, held longer, and with a closed-bar trailing stop (from M2) ===")
    say("Round 42 found the reversion under the gate keeps building to 60 minutes (VR 0.96 at 1m -> 0.845")
    say("at 60m) while the live EA exits at 20. Live settings: one bar >= 3 ATR down, gate 8, SL 0.2 ATR")
    say("below its low, TP 0.75 x its range.")
    say(hdr)

    def spike(maxb, tp_f=0.75, x=8.0, k=3.0, trail=None):
        rng = h_ - l_
        hit = base & (gate >= x) & (c < o) & (rng >= k * atr)
        idx = np.where(hit)[0]
        if trail is None:
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
            return run(S)
        # trailing variant, simulated here because sim has no trailing stop.
        # The trail level is frozen at the START of each bar from CLOSED bars only (round 35 lesson).
        res, busy = [], -1
        for i in idx:
            e_k = i + 1
            if e_k <= busy or e_k >= n - 1:
                continue
            e = o[e_k]
            sl = l_[i] - 0.2 * atr[i]
            if sl >= e:
                continue
            hi_prev = -np.inf
            best = sl                                           # the stop only ever tightens upward
            ex, k_ = None, e_k
            for q in range(e_k, min(e_k + maxb + 1, n)):
                if hi_prev > -np.inf and np.isfinite(atr[q]):
                    cand = hi_prev - trail * atr[q]
                    cand = min(cand, o[q] - spr[q])             # a buy's stop must sit below the bid
                    if cand > best:
                        best = cand
                stop = best
                if flat[q] or q - e_k >= maxb:
                    ex, k_ = o[q], q; break
                if l_[q] <= stop:
                    ex, k_ = min(stop, o[q]), q; break
                hi_prev = h_[q] if hi_prev == -np.inf else max(hi_prev, h_[q])
            if ex is None:
                continue
            res.append((e_k, 1, ex - e, spr[e_k], e - sl, "trail"))
            busy = k_
        if len(res) < 50:
            return None
        T = pd.DataFrame(res, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.kk.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    for maxb in (20, 30, 45, 60, 90):
        line(f"LIVE signal, hold {maxb}m", spike(maxb))
    say("")
    for maxb in (20, 30, 45, 60):
        line(f"LIVE signal, no TP, hold {maxb}m", spike(maxb, tp_f=None))
    say("")
    for tl in (0.5, 1.0, 1.5, 2.0):
        for maxb in (30, 60):
            line(f"trail {tl} ATR, cap {maxb}m", spike(maxb, trail=tl))

    # ---------------------------------------------------------------- BUSYLONG, NYOPEN
    say("\n=== BUSYLONG: long while ATR14/ATR100 >= r (from M5: +$0.228 over 30 min, t 4.7) ===")
    say(hdr)
    ratio = np.where(atr100 > 0, atr / atr100, np.nan)
    for r_ in (1.4, 1.6, 2.0):
        for maxb in (30, 60):
            hit = base & (gate >= 8) & np.isfinite(ratio) & (ratio >= r_)
            S = [dict(k0=i + 1, kind="mkt", dir=1, sl=c[i] - 1.5 * atr[i], tp_r=1.5, exp=i + 1, maxb=maxb)
                 for i in np.where(hit)[0]]
            line(f"ratio >= {r_} gate8 {maxb}m", run(S))

    say("\n=== NYOPEN: OCO on the 15:15-15:30 range at the New York open, gated (round 42 H) ===")
    say("15:30 server is the most explosive minute of the day: mean 1-minute move $2.07 and a $9.57 range")
    say("over the next 30 minutes.")
    say(hdr)
    for pre in (15, 30):
        for tpr in (1.0, 2.0):
            S = []
            for i in np.where(base & (hm == 930))[0]:
                a, b = i - pre, i
                if a < 0:
                    continue
                hi, lo = h_[a:b].max(), l_[a:b].min()
                if not (np.isfinite(hi) and np.isfinite(lo)) or hi <= lo or gate[i] < 8:
                    continue
                S.append(dict(k0=i, kind="oco", P=hi, P2=lo, sl=lo, sl2=hi, tp_r=tpr, exp=i + 60,
                              maxb=120, end=min(i + 200, n - 1)))
            line(f"pre-range {pre}m TP{tpr}R", run(S))

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
