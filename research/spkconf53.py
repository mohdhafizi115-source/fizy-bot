"""Round 53 (6 Nov 2026): plateau and attribution check of the round-52 survivor (wick + RSI < 30).

Live v1.99 on the night of 5 Nov bought four times in six minutes (16:38, 16:39, 16:42, 16:44 server)
while gold fell from 4124 to 4099, and every one hit its stop: -$14 in one evening. The live rule
enters on the spike bar itself, so in a sustained drop it buys every leg down.

The owner sent the classic spike-fade description, which differs exactly where that went wrong:
  1. spike: one or more very large M1 candles
  2. DO NOT enter on the spike. Wait for a confirmation candle with a long rejection wick that fails to
     close beyond the extreme (buyers/sellers exhausted); optionally RSI / Stochastic extreme
  3. SL a little beyond the tip of the wick; TP back at the level from before the spike (mean reversion)
  4. close half at 1:1 and move the stop to breakeven on the rest
  5. bias from a higher timeframe, danger when fading a strong trend

All of it is tested here, both sides, on the broker's M1 gold history:
  W     how many bars after the spike the confirmation may come (1 / 2 / 3 / 5)
  WICK  lower (upper) wick >= 0.5 / 0.6 of the bar's range and the close in the upper (lower) half
  RSI   RSI(14) at the spike below 30 (above 70), on / off
  HTF   only buy when the H1 EMA 50 is rising (sell when falling), on / off
  EXIT  (a) one target at the pre-spike level, (b) half at 1R + breakeven + half at the pre-spike level
  COOL  after a stopped trade, ignore signals for 0 / 15 / 30 minutes
Plus the live v1.99 rule as the benchmark and random entries under the same gate as the control.

A custom simulator handles the partial close: each half pays half the spread, the breakeven move happens
only after 1R has actually traded, and bar paths use the same O-L-H-C / O-H-L-C order as SA.sim.

Also reported for every line: the most trades taken inside any 10 minutes (the waterfall), the longest
losing streak, the worst single day, and max drawdown against a $100 account.

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
HDR = ("variant                                 trades /day win%   PF  half1 half2 stress last12$  net$"
       "  maxDD$ worstday lose-run max/10m  pass")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    del d
    o, h, l, c = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(c)
    hm = B.hm.values
    dates = B.date.values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    flat = (hm >= 1350) | newday | np.r_[newday[1:], True]
    sp = B.s.values.astype(float)
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = np.where(sp > 0, atr / sp, np.nan)
    dlt = np.diff(c, prepend=c[0])
    up_ = pd.Series(np.clip(dlt, 0, None)).ewm(alpha=1 / 14, adjust=False).mean()
    dn_ = pd.Series(np.clip(-dlt, 0, None)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up_ / dn_.replace(0, np.nan))).values         # RSI of the bar, known at its close
    H1 = B.c.resample("1h").last().dropna()
    e50 = H1.ewm(span=50, adjust=False).mean()
    slope = (e50 - e50.shift(1)).shift(1)                                    # last CLOSED H1 bar only
    hslope = slope.reindex(B.index, method="ffill").values
    rng = h - l
    days = B.index.normalize().nunique()
    mid_t, end_t = B.index[n // 2], B.index[-1]
    okb = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (sp > 0) & (np.arange(n) >= 300)
    okb[-8:] = False
    say(f"XAUUSD M1, {n:,} bars, {days} days. Halves split at {mid_t:%Y-%m-%d}. "
        f"Median spread ${np.median(sp) * usd:.3f}.")

    # ------------------------------------------------------------- simulator with partial + breakeven
    def run(sigs, partial):
        """sigs: list of (k_entry, dir, sl, tp, spike_i). One position at a time."""
        res = []
        busy = -1
        last_sl_bar = -10 ** 9
        for k, dr, sl, tp, si, cool in sigs:
            if k <= busy or k >= n - 1:
                continue
            if cool and k - last_sl_bar < cool:
                continue
            e = o[k]
            risk = (e - sl) * dr
            if risk <= 0 or (tp - e) * dr <= 0:
                continue
            p1 = e + dr * risk                                               # the 1:1 level
            halves = [[0.5, p1 if partial else tp, sl], [0.5, tp, sl]] if partial else [[1.0, tp, sl]]
            pnl = 0.0
            q = k
            first = True
            hit_sl = False
            while q < n and halves:
                if not first:
                    if flat[q] or q - k >= 45:
                        for hv in halves:
                            pnl += hv[0] * (o[q] - e) * dr
                        halves = []
                        break
                    # gap through a level at the open
                    keep = []
                    for hv in halves:
                        if (o[q] - hv[2]) * dr <= 0:
                            pnl += hv[0] * (o[q] - e) * dr
                            hit_sl = hit_sl or hv[2] == sl
                        elif (o[q] - hv[1]) * dr >= 0:
                            pnl += hv[0] * (o[q] - e) * dr
                        else:
                            keep.append(hv)
                    if len(keep) < len(halves) and partial and len(keep) == 1 and keep[0][2] == sl:
                        keep[0][2] = e                                       # 1R done: rest to breakeven
                    halves = keep
                    if not halves:
                        break
                path = (o[q], l[q], h[q], c[q]) if c[q] >= o[q] else (o[q], h[q], l[q], c[q])
                for si_ in range(3):
                    x, y = path[si_], path[si_ + 1]
                    if si_ == 0 and first:
                        x = e
                    keep = []
                    took_1r = False
                    for hv in halves:
                        tgt, stp = hv[1], hv[2]
                        if dr == 1:
                            if y < x and y <= stp:
                                pnl += hv[0] * (stp - e); hit_sl = hit_sl or stp == sl; continue
                            if y > x and y >= tgt:
                                pnl += hv[0] * (tgt - e); took_1r = took_1r or tgt == p1; continue
                        else:
                            if y > x and y >= stp:
                                pnl += hv[0] * (e - stp); hit_sl = hit_sl or stp == sl; continue
                            if y < x and y <= tgt:
                                pnl += hv[0] * (e - tgt); took_1r = took_1r or tgt == p1; continue
                        keep.append(hv)
                    if partial and took_1r:
                        for hv in keep:
                            if hv[2] == sl:
                                hv[2] = e
                    halves = keep
                    if not halves:
                        break
                first = False
                q += 1
            if halves:
                for hv in halves:
                    pnl += hv[0] * (c[n - 1] - e) * dr
            res.append((k, dr, pnl, sp[k]))
            busy = q
            if hit_sl and pnl < 0:
                last_sl_bar = q
        if len(res) < 50:
            return None
        T = pd.DataFrame(res, columns=["k", "dir", "pnl", "sp"])
        T["t"] = B.index[T.k.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 50:
            say(f"{lab:39s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        wd = T.groupby(T.t.dt.normalize()).net.sum().min()
        run_, cur = 0, 0
        for v in (T.net.values <= 0):
            cur = cur + 1 if v else 0
            run_ = max(run_, cur)
        tt = T.t.values.astype("datetime64[m]").astype(np.int64)
        m10 = int(max(np.searchsorted(tt, tt + 10, side="left") - np.arange(len(tt)))) if len(tt) else 0
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        say(f"{lab:39s} {len(T):6d} {len(T) / days:4.2f} {100 * (T.net > 0).mean():4.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+6.0f} {dd:+7.0f} {wd:+8.1f} {run_:8d} {m10:7d}"
            f"  {'PASS' if ok and mark else ''}")
        return ok

    # ------------------------------------------------------------- signal builders
    def live(k=2.0, tp_f=0.5):
        out = []
        for i in np.where(okb & (gate >= 8) & (c < o) & (rng >= k * atr))[0]:
            sl = l[i] - 0.2 * atr[i]
            tp = c[i] + tp_f * rng[i]
            out.append((i + 1, 1, sl, tp, i, 0))
        return out

    def conf(side=1, k=2.0, W=3, wk=0.5, rsi_on=False, htf=False, cool=0, include_spike=False, rth=30, nowick=False):
        out = []
        cond = okb & (gate >= 8) & (rng >= k * atr) & ((c < o) if side == 1 else (c > o))
        if rsi_on:
            cond &= (rsi < rth) if side == 1 else (rsi > 100 - rth)
        if htf:
            cond &= (hslope > 0) if side == 1 else (hslope < 0)
        for i in np.where(cond)[0]:
            ext = l[i] if side == 1 else h[i]
            start = i if include_spike else i + 1
            for j in range(start, min(i + W + 1, n - 2)):
                if flat[j]:
                    break
                ext = min(ext, l[j]) if side == 1 else max(ext, h[j])
                r = h[j] - l[j]
                if r <= 0:
                    continue
                if side == 1:
                    wick = min(o[j], c[j]) - l[j]
                    good = wick >= wk * r and c[j] >= (h[j] + l[j]) / 2
                else:
                    wick = h[j] - max(o[j], c[j])
                    good = wick >= wk * r and c[j] <= (h[j] + l[j]) / 2
                if nowick:
                    good = True
                if good:
                    sl = ext - side * 0.1 * atr[i]
                    tp = o[i]                                                # back to where the spike started
                    out.append((j + 1, side, sl, tp, i, cool))
                    break
        return out


    def yrs(T):
        if T is None:
            return ""
        return " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))

    def L(lab, T, mark=True):
        line(lab, T, mark)
        if T is not None and len(T) >= 50:
            say(f"{'':39s} by year {yrs(T)}")

    say("\n=== A. RSI threshold plateau (buy, W3, wick 0.5, single TP) ===")
    say(HDR)
    for r in (20, 25, 30, 35, 40, 50):
        L(f"RSI < {r}", run(conf(1, rsi_on=True, rth=r), partial=False))

    say("\n=== B. is it the WICK or the RSI doing the work? ===")
    say(HDR)
    L("RSI<30 spike, enter next bar, NO wick wait", run(conf(1, rsi_on=True, nowick=True, W=1), partial=False))
    L("RSI<30 spike + wick (W3)", run(conf(1, rsi_on=True), partial=False))
    L("no RSI + wick (W3)", run(conf(1), partial=False), mark=False)

    say("\n=== C. W and wick size under RSI<30 ===")
    say(HDR)
    for W in (1, 2, 3, 5):
        for wk in (0.4, 0.5, 0.6):
            line(f"RSI<30 W{W} wick{wk}", run(conf(1, rsi_on=True, W=W, wk=wk), partial=False))

    say("\n=== D. spike size under RSI<30 (W3 wick 0.5) ===")
    say(HDR)
    for k in (1.5, 2.0, 2.5, 3.0):
        L(f"RSI<30 k{k}", run(conf(1, rsi_on=True, k=k), partial=False))

    say("\n=== E. exits under RSI<30 (W3 wick 0.5) ===")
    say(HDR)
    L("single TP at the pre-spike level", run(conf(1, rsi_on=True), partial=False))
    L("half at 1:1 + rest breakeven", run(conf(1, rsi_on=True), partial=True))
    L("RSI<30 + H1 bias, partial", run(conf(1, rsi_on=True, htf=True), partial=True))
    L("RSI<30 + H1 bias, single", run(conf(1, rsi_on=True, htf=True), partial=False))
    for rr in (25, 35):
        line(f"RSI<{rr} + H1 bias, partial", run(conf(1, rsi_on=True, rth=rr, htf=True), partial=True))

    say("\n=== F. controls ===")
    say(HDR)
    rg = np.random.default_rng(53)
    rnd = []
    m = okb & (gate >= 8) & (rsi < 30) & (rg.random(n) < 0.05)
    for j in np.where(m)[0]:
        rnd.append((j + 1, 1, c[j] - 1.0 * atr[j], c[j] + 1.5 * atr[j], j, 0))
    line("random bar with RSI<30, gate 8", run(rnd, partial=False), mark=False)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
