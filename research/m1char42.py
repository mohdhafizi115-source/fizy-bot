"""Round 42 (5 Nov 2026): MEASURE how gold really behaves on M1. No trading rules in this script.

The owner asked for an M1 gold scalper designed from gold's own behaviour ("aku nak kau cipta sendiri
scalping di m1 pada gold. ikut perangai gold"), not another borrowed system.

Why measure first. Rounds 21, 25, 26, 30 guessed 130+ M1 rules from indicators and from the web: every
one lost. Round 33 scanned every entry minute of the day x every hold and found 0 survivors against 22
in a shuffled control. The ONE thing that has ever worked on M1 (round 37) did not come from a rule at
all, it came from a property of the data: an M1 edge only survives when the move dwarfs the cost. So
guessing more rules is the approach that has already failed seven times. This round measures the
behaviour; round 43 builds only on what is actually here.

What is measured, all on the broker's own M1 gold history:
  A  variance ratio and autocorrelation by horizon, volatility regime and session - is gold M1
     mean-reverting or trending, at which horizon, and is the move bigger than the spread there
  B  the conditional path after a k x ATR shock, both sides, h = 1..60 min: mean move, t, and the
     MFE / MAE that decide whether a stop and a target can even be placed
  C  volatility clustering - whether the cost gate (ATR >= x * spread) predicts the NEXT 20 minutes,
     which is what makes it usable in advance rather than in hindsight
  D  streaks: after n consecutive up or down minutes
  E  contraction then expansion: after an unusually quiet stretch
  F  the hour-of-day profile of ATR, spread, the gate, and the signed drift
  G  micro round numbers ($1 / $5 / $10) - gold is widely claimed to respect them
  H  the first minutes after the session opens

Rules of the measurement:
  - everything in DOLLARS per 0.01 lot, so every number can be compared with the spread it must beat
  - every headline number is split first half / second half of the history: a property that is not in
    both halves is not a property, it is a period
  - forward bars are matched by EXACT clock time (ts + h minutes), so weekend and session gaps never
    leak into a horizon
  - the 23:45-01:30 server rollover is dropped: the bid is distorted there
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)
HOR = (1, 2, 3, 5, 10, 15, 20, 30, 45, 60)


def tstat(x):
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return np.nan
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def fwd_index(ts, h):
    """j[i] = index of the bar exactly h minutes after bar i, or -1 when that bar does not exist"""
    j = np.searchsorted(ts, ts + 60 * h)
    ok = j < len(ts)
    j2 = np.where(ok, j, 0)
    ok &= ts[j2] == ts + 60 * h
    return np.where(ok, j2, -1)


def fwd_ext(h, hi, lo):
    """highest high and lowest low over the NEXT h bars (bar i+1 .. i+h), by bar count"""
    mx = pd.Series(hi).rolling(h).max().shift(-h).values
    mn = pd.Series(lo).rolling(h).min().shift(-h).values
    return mx, mn


def halves(v, mask, mid):
    """mean of v over mask, split first / second half"""
    a = v[mask & (np.arange(len(v)) < mid)]
    b = v[mask & (np.arange(len(v)) >= mid)]
    return (np.nanmean(a) if len(a) else np.nan), (np.nanmean(b) if len(b) else np.nan), len(a), len(b)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01          # price difference -> $ per 0.01 lot
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    del d
    hm = B.hm.values
    keep = ~((hm >= 1425) | (hm < 90))                        # drop the 23:45-01:30 rollover
    B = B[keep]
    o, h_, l_, c = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(c)
    ts = B.index.values.astype("datetime64[s]").astype(np.int64)
    hm = B.hm.values
    spr = B.s.values.astype(float) * usd                      # $ per 0.01 lot
    # Wilder ATR(14) on M1, shifted: known at the close of bar i, so usable from bar i+1
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h_ - l_, np.maximum(np.abs(h_ - c1), np.abs(l_ - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    atr_d = atr * usd
    gate = np.where(spr > 0, atr_d / spr, np.nan)             # ATR in multiples of the spread
    r1 = np.r_[np.nan, np.diff(c)] * usd                      # one-minute return in $
    mid = n // 2
    t_mid, t_end = B.index[mid], B.index[-1]
    base = np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 300)
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars after dropping the rollover, "
        f"{B.index.normalize().nunique()} days. Halves split at {t_mid:%Y-%m-%d}.")
    say(f"$ per 0.01 lot per $1 of price = {usd:.2f}. Spread: median ${np.median(spr):.3f}, "
        f"p10 ${np.percentile(spr, 10):.3f}, p90 ${np.percentile(spr, 90):.3f}. "
        f"ATR(14,M1): median ${np.nanmedian(atr_d):.3f}. Gate ATR/spread: median {np.nanmedian(gate):.1f}, "
        f"p10 {np.nanpercentile(gate, 10):.1f}, p90 {np.nanpercentile(gate, 90):.1f}")

    # ---------------------------------------------------------------- A. trend or reversion, by horizon
    say("\n=== A. Is gold M1 trending or mean-reverting? ===")
    say("Variance ratio VR(h) = Var(h-minute move) / (h x Var(1-minute move)). VR > 1 trending, < 1 reverting.")
    say("'move $' is the standard deviation of the h-minute move in dollars per 0.01 lot; compare it with the")
    say("median spread above - a reverting horizon is only tradable where the move is far bigger than the cost.")
    v1 = np.nanvar(r1[base])
    say(f"\n{'horizon':>8} {'VR':>6} {'VR h1':>6} {'VR h2':>6} {'lag1 ac':>8} {'move $':>7} {'move/spread':>11} {'n':>9}")
    for hh in HOR:
        j = fwd_index(ts, hh)
        ok = base & (j >= 0)
        mv = np.full(n, np.nan)
        mv[ok] = (c[j[ok]] - c[ok]) * usd
        vr = np.nanvar(mv[ok]) / (hh * v1)
        ok1 = ok & (np.arange(n) < mid)
        ok2 = ok & (np.arange(n) >= mid)
        vr1 = np.nanvar(mv[ok1]) / (hh * np.nanvar(r1[ok1]))
        vr2 = np.nanvar(mv[ok2]) / (hh * np.nanvar(r1[ok2]))
        # lag-1 autocorrelation of NON-overlapping h-minute moves
        idx = np.where(ok)[0][::hh]
        x = mv[idx]
        x = x[np.isfinite(x)]
        ac = np.corrcoef(x[:-1], x[1:])[0, 1] if len(x) > 50 else np.nan
        sd = np.nanstd(mv[ok])
        say(f"{hh:6d}m  {vr:6.3f} {vr1:6.3f} {vr2:6.3f} {ac:8.3f} {sd:7.2f} {sd / np.median(spr):11.1f} {ok.sum():9d}")

    say("\nSame variance ratio, split by the volatility regime the bar is in (gate = ATR / spread):")
    q = np.nanpercentile(gate[base], [33, 67])
    regs = [("quiet   gate<%.0f" % q[0], gate < q[0]), ("mid", (gate >= q[0]) & (gate < q[1])),
            ("busy    gate>%.0f" % q[1], gate >= q[1]), ("gate>=8 (the live gate)", gate >= 8)]
    say(f"{'regime':>24} " + " ".join(f"{hh:>6}m" for hh in (1, 5, 15, 30, 60)) + f" {'n':>9}")
    for lab, m in regs:
        row = []
        mm = base & m
        vl = np.nanvar(r1[mm])
        for hh in (1, 5, 15, 30, 60):
            j = fwd_index(ts, hh)
            ok = mm & (j >= 0)
            mv = (c[j[ok]] - c[ok]) * usd
            row.append(np.nanvar(mv) / (hh * vl) if len(mv) > 100 else np.nan)
        say(f"{lab:>24} " + " ".join(f"{x:7.3f}" for x in row) + f" {mm.sum():9d}")

    say("\nSame, split by session (server time = Europe/Athens):")
    sess = [("Asia      01:30-09:00", (hm >= 90) & (hm < 540)), ("London    09:00-15:30", (hm >= 540) & (hm < 930)),
            ("NY overlap 15:30-19:00", (hm >= 930) & (hm < 1140)), ("late NY   19:00-23:45", (hm >= 1140))]
    say(f"{'session':>24} " + " ".join(f"{hh:>6}m" for hh in (1, 5, 15, 30, 60)) + f" {'n':>9} {'med spr':>8} {'med ATR':>8}")
    for lab, m in sess:
        row = []
        mm = base & m
        vl = np.nanvar(r1[mm])
        for hh in (1, 5, 15, 30, 60):
            j = fwd_index(ts, hh)
            ok = mm & (j >= 0)
            mv = (c[j[ok]] - c[ok]) * usd
            row.append(np.nanvar(mv) / (hh * vl) if len(mv) > 100 else np.nan)
        say(f"{lab:>24} " + " ".join(f"{x:7.3f}" for x in row) +
            f" {mm.sum():9d} {np.median(spr[mm]):8.3f} {np.nanmedian(atr_d[mm]):8.3f}")

    # ---------------------------------------------------------------- B. the path after a shock
    say("\n=== B. What happens after a shock of k x ATR? ===")
    say("For every bar whose range >= k x ATR(14,M1) and which closed DOWN (or UP), the average move of the")
    say("close over the next h minutes, in $ per 0.01 lot, with its t and the share of positive outcomes.")
    say("A positive number after a DOWN bar means the drop gets bought back (fade works); after an UP bar a")
    say("positive number means the move continues. 'cost' is the spread that has to be paid to take it.")
    for side, slab in ((1, "DOWN bar (fade = BUY)"), (-1, "UP bar (fade = SELL)")):
        say(f"\n--- {slab} ---")
        say(f"{'k':>4} {'gate':>6} {'n':>6} " + " ".join(f"{hh:>6}m" for hh in HOR) + "   t at 20m  h1/h2 at 20m")
        for k in (2.0, 2.5, 3.0, 4.0, 5.0):
            for glab, gm in (("all", np.ones(n, bool)), (">=8", gate >= 8)):
                sig = base & gm & ((c < o) if side == 1 else (c > o)) & ((h_ - l_) >= k * atr)
                if sig.sum() < 60:
                    continue
                row, t20, h1, h2 = [], np.nan, np.nan, np.nan
                for hh in HOR:
                    j = fwd_index(ts, hh)
                    ok = sig & (j >= 0)
                    mv = (c[j[ok]] - c[ok]) * usd * side
                    row.append(np.nanmean(mv) if len(mv) > 30 else np.nan)
                    if hh == 20:
                        t20 = tstat(mv)
                        full = np.full(n, np.nan); full[ok] = mv
                        h1, h2, _, _ = halves(full, ok, mid)
                say(f"{k:4.1f} {glab:>6} {sig.sum():6d} " + " ".join(f"{x:7.2f}" for x in row) +
                    f" {t20:8.1f}  {h1:+.2f}/{h2:+.2f}")
        say("(for reference, the median spread is $%.3f, so a mean move below that is not tradable)" % np.median(spr))

    say("\nStops and targets: after a 3 ATR shock with the gate on, how far does it go the right way (MFE)")
    say("and the wrong way (MAE) within the hold, in $ per 0.01 lot? Medians, and the share that reach 1 ATR.")
    say(f"{'side':>22} {'hold':>5} {'n':>6} {'MFE med':>8} {'MAE med':>8} {'MFE p75':>8} {'MAE p25':>8} {'reach 1ATR':>11}")
    for side, slab in ((1, "DOWN bar (fade BUY)"), (-1, "UP bar (fade SELL)")):
        sig = base & (gate >= 8) & ((c < o) if side == 1 else (c > o)) & ((h_ - l_) >= 3 * atr)
        for hh in (10, 20, 30):
            mx, mn = fwd_ext(hh, h_, l_)
            ok = sig & np.isfinite(mx) & np.isfinite(mn)
            if ok.sum() < 50:
                continue
            fav = ((mx[ok] - c[ok]) if side == 1 else (c[ok] - mn[ok])) * usd
            adv = ((c[ok] - mn[ok]) if side == 1 else (mx[ok] - c[ok])) * usd
            reach = (fav >= atr_d[ok]).mean()
            say(f"{slab:>22} {hh:4d}m {ok.sum():6d} {np.median(fav):8.2f} {np.median(adv):8.2f} "
                f"{np.percentile(fav, 75):8.2f} {np.percentile(adv, 25):8.2f} {100 * reach:10.1f}%")

    # ---------------------------------------------------------------- C. is the gate usable in advance?
    say("\n=== C. Does the cost gate predict the next 20 minutes, or only describe the past? ===")
    say("The live rule uses ATR(14) of the bars BEFORE the signal. If volatility did not cluster, that would")
    say("be a hindsight filter. Here: given the gate now, what is the realised range of the next 20 minutes,")
    say("and what is the spread then?")
    mx20, mn20 = fwd_ext(20, h_, l_)
    rng20 = (mx20 - mn20) * usd
    sp_f = np.r_[spr[20:], np.full(20, np.nan)]
    say(f"{'gate now':>14} {'n':>8} {'next 20m range $':>17} {'spread then $':>14} {'range/spread':>13} {'h1':>7} {'h2':>7}")
    for lo, hi, lab in ((0, 4, "< 4"), (4, 6, "4 - 6"), (6, 8, "6 - 8"), (8, 12, "8 - 12"), (12, 20, "12 - 20"),
                        (20, 1e9, ">= 20")):
        m = base & (gate >= lo) & (gate < hi) & np.isfinite(rng20)
        if m.sum() < 100:
            continue
        a, b, _, _ = halves(rng20, m, mid)
        say(f"{lab:>14} {m.sum():8d} {np.nanmean(rng20[m]):17.2f} {np.nanmean(sp_f[m]):14.3f} "
            f"{np.nanmean(rng20[m]) / np.nanmean(sp_f[m]):13.1f} {a:7.2f} {b:7.2f}")
    gg = base & np.isfinite(rng20) & np.isfinite(gate)
    atr_f = np.r_[atr_d[20:], np.full(20, np.nan)]
    aa = base & np.isfinite(atr_d) & np.isfinite(atr_f)
    say(f"\ncorrelation(gate now, next 20m range) = {np.corrcoef(gate[gg], rng20[gg])[0, 1]:.3f}; "
        f"correlation(ATR now, ATR in 20 min) = {np.corrcoef(atr_d[aa], atr_f[aa])[0, 1]:.3f}")

    # ---------------------------------------------------------------- D. streaks
    say("\n=== D. After n minutes in a row in the same direction ===")
    up = (c > o).astype(np.int8)
    dn = (c < o).astype(np.int8)
    say(f"{'streak':>14} {'gate':>5} {'n':>7} " + " ".join(f"{hh:>6}m" for hh in (1, 5, 10, 20, 30)) + f" {'t 20m':>7}")
    for nst in (3, 4, 5, 6, 8):
        run_u = np.ones(n, bool)
        run_d = np.ones(n, bool)
        for q in range(nst):
            run_u &= np.r_[np.zeros(q, bool), up[: n - q].astype(bool)] if q else up.astype(bool)
            run_d &= np.r_[np.zeros(q, bool), dn[: n - q].astype(bool)] if q else dn.astype(bool)
        for lab, m, side in ((f"{nst} up", run_u, -1), (f"{nst} down", run_d, 1)):
            for glab, gm in (("all", np.ones(n, bool)), (">=8", gate >= 8)):
                sig = base & m & gm
                if sig.sum() < 100:
                    continue
                row, t20 = [], np.nan
                for hh in (1, 5, 10, 20, 30):
                    j = fwd_index(ts, hh)
                    ok = sig & (j >= 0)
                    mv = (c[j[ok]] - c[ok]) * usd * side          # + = reversion
                    row.append(np.nanmean(mv) if len(mv) > 30 else np.nan)
                    if hh == 20:
                        t20 = tstat(mv)
                say(f"{lab + ' (fade)':>14} {glab:>5} {sig.sum():7d} " + " ".join(f"{x:7.3f}" for x in row) +
                    f" {t20:7.1f}")

    # ---------------------------------------------------------------- E. contraction -> expansion
    say("\n=== E. After an unusually quiet stretch ===")
    atr100 = pd.Series(tr).ewm(alpha=1 / 100, adjust=False).mean().shift(1).values
    ratio = atr / atr100
    say("ratio = ATR(14) / ATR(100). Low = the last 15 minutes were quiet relative to the last hour and a half.")
    say(f"{'ratio':>14} {'n':>8} {'next 30m range $':>17} {'|next 30m move| $':>18} {'signed move $':>14} {'t':>6}")
    mx30, mn30 = fwd_ext(30, h_, l_)
    j30 = fwd_index(ts, 30)
    for lo, hi, lab in ((0, 0.6, "< 0.6 quiet"), (0.6, 0.8, "0.6 - 0.8"), (0.8, 1.2, "0.8 - 1.2"),
                        (1.2, 1.6, "1.2 - 1.6"), (1.6, 1e9, ">= 1.6 busy")):
        m = base & (ratio >= lo) & (ratio < hi) & (j30 >= 0) & np.isfinite(mx30)
        if m.sum() < 100:
            continue
        mv = (c[j30[m]] - c[m]) * usd
        say(f"{lab:>14} {m.sum():8d} {np.nanmean((mx30 - mn30)[m]) * usd:17.2f} {np.nanmean(np.abs(mv)):18.2f} "
            f"{np.nanmean(mv):14.3f} {tstat(mv):6.1f}")

    # ---------------------------------------------------------------- F. hour of day
    say("\n=== F. The hour-of-day profile (server time; MYT = server + 6 in winter) ===")
    say(f"{'server hour':>12} {'MYT':>5} {'bars':>8} {'med ATR $':>10} {'med spread $':>13} {'med gate':>9} "
        f"{'mean |1m| $':>12} {'drift $/h':>10} {'h1':>7} {'h2':>7}")
    j60 = fwd_index(ts, 60)
    for hh in range(0, 24):
        m = base & (hm // 60 == hh)
        if m.sum() < 500:
            continue
        mm = m & (j60 >= 0)
        dr = (c[j60[mm]] - c[mm]) * usd
        full = np.full(n, np.nan); full[mm] = dr
        a, b, _, _ = halves(full, mm, mid)
        say(f"{hh:10d}h  {(hh + 6) % 24:4d}h {m.sum():8d} {np.nanmedian(atr_d[m]):10.3f} {np.median(spr[m]):13.3f} "
            f"{np.nanmedian(gate[m]):9.1f} {np.nanmean(np.abs(r1[m])):12.3f} {np.nanmean(dr):10.3f} "
            f"{a:+7.2f} {b:+7.2f}")

    # ---------------------------------------------------------------- G. micro round numbers
    say("\n=== G. Micro round numbers ===")
    say("Gold is widely said to respect round numbers. For each step, bars whose close is within 10% of the")
    say("step from a level: does price push through (continuation) or turn back (reversion) over 20 minutes?")
    say("Measured against the SAME statistic for a level grid shifted by half a step, which is the control:")
    say("if the real levels are special, the shifted grid must behave differently.")
    j20 = fwd_index(ts, 20)
    say(f"{'step':>8} {'grid':>9} {'n':>8} {'|20m move| $':>13} {'toward level $':>15} {'away $':>9} {'t':>6}")
    for step in (1.0, 5.0, 10.0):
        for off, glab in ((0.0, "real"), (step / 2, "shifted")):
            rem = (c - off) % step
            dist = np.minimum(rem, step - rem)                   # distance to the nearest grid line
            near = dist <= 0.1 * step
            m = base & near & (j20 >= 0)
            if m.sum() < 200:
                continue
            mv = (c[j20[m]] - c[m]) * usd
            lvl = np.round((c[m] - off) / step) * step + off
            toward = np.sign(lvl - c[m])
            toward[toward == 0] = 1
            say(f"{step:8.1f} {glab:>9} {m.sum():8d} {np.nanmean(np.abs(mv)):13.2f} "
                f"{np.nanmean(mv * toward):15.3f} {np.nanmean(-mv * toward):9.3f} {tstat(mv * toward):6.1f}")

    # ---------------------------------------------------------------- H. session opens
    say("\n=== H. The first minutes after a session opens (server time) ===")
    say(f"{'open':>22} {'minute':>7} {'n':>6} {'mean |1m| $':>12} {'med spread $':>13} {'next 30m range $':>17}")
    for omin, olab in ((90, "Asia 01:30"), (540, "pre-London 09:00"), (600, "London 10:00"), (930, "New York 15:30")):
        for k in (0, 1, 2, 5, 15):
            m = base & (hm == omin + k) & np.isfinite(mx30)
            if m.sum() < 100:
                continue
            say(f"{olab:>22} {('+%d' % k):>7} {m.sum():6d} {np.nanmean(np.abs(r1[m])):12.3f} "
                f"{np.median(spr[m]):13.3f} {np.nanmean((mx30 - mn30)[m]) * usd:17.2f}")

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
