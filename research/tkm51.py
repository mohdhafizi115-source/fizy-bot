"""Round 51 (6 Nov 2026): TKM thought through properly - measure its components, then use them as
FILTERS on the rule that already works, instead of as a rule of their own.

The owner: "kau fikir lebih dalam bagaimana nak modified supaya profitable."

Round 50 killed TKM's levels with the fake-anchor control: moving the anchor +3 or +7 ATR gave 0.90 /
0.91 against 0.91 for the real EMA 63 levels. But that only tested ONE of TKM's three components, and
it tested it the way the ebook uses it - as a trigger. Three things were never isolated:

  A  DISTANCE FROM THE MA AS A CONTINUOUS VARIABLE, measured rather than traded. Round 50 asked "does
     touching a level work"; it never asked "what does the forward return actually look like as a
     function of how far price is from the EMA 63". That is the round-42 method, which is the only
     approach that has ever produced anything here. Measured in ATR units, split by the sign, by the
     gate, by whether the EMA 63 is rising or falling, and into halves.
  B  THE BOUNDED CCI BAND, which is TKM's one real oddity. The ebook does not say "CCI above 175", it
     says BETWEEN 175 and 233 - momentum extreme but not too extreme. Nobody tests bounded bands, and
     round 50 found the CCI filter did help a little (L5 scored 0.96 with the taught window against
     0.92 with no CCI). This makes that falsifiable: if 175-233 is special, the band above 233 must
     behave DIFFERENTLY, not just less often. Buckets: 100-150, 150-175, 175-233, 233-300, >300.
  C  TKM AS A FILTER ON THE LIVE SPIKE FADE, which is where a weak-but-real signal is actually worth
     something. A weak standalone rule is useless; a weak filter on a strong rule can add value, and
     it can also tell us which spikes to SKIP, which costs almost no trades.

Discipline for C: filtering is a subset search on a rule already known to work, so it fits easily.
A filter is only taken seriously if BOTH halves improve, the by-year numbers stay sane, and it keeps
enough trades. A subset that only looks better in one half is noise.

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
HDR = ("variant                            trades /day  win%   PF  half1 half2 stress last12$   net$"
       "  $/yr  maxDD$ mth+   by year")


def tstat(x):
    x = x[np.isfinite(x)]
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 20 else np.nan


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
    spr_d = spr * usd
    ts = B.index.values.astype("datetime64[s]").astype(np.int64)
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h_ - l_, np.maximum(np.abs(h_ - c1), np.abs(l_ - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = np.where(spr > 0, atr / spr, np.nan)
    tp_ = (h_ + l_ + c) / 3.0
    Sp = pd.Series(tp_)
    e63 = Sp.ewm(span=63, adjust=False).mean().shift(1).values
    e83 = Sp.ewm(span=83, adjust=False).mean().shift(1).values
    sma14 = Sp.rolling(14).mean()
    mad14 = (Sp - sma14).abs().rolling(14).mean()
    cci = ((Sp - sma14) / (0.015 * mad14.replace(0, np.nan))).shift(1).values
    dist = np.where(atr > 0, (c - e63) / atr, np.nan)          # how far price is from the MA, in ATR
    e63r = np.r_[np.nan, np.diff(e63)]                          # is the MA rising or falling
    rng = h_ - l_
    base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & np.isfinite(e63) & np.isfinite(e83) \
        & np.isfinite(cci) & np.isfinite(dist) & (spr > 0) & (np.arange(n) >= 300)
    base[-3:] = False
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    days = B.index.normalize().nunique()
    yrs = days / 255.0
    mid_i = n // 2
    mid_t, end_t = B.index[mid_i], B.index[-1]
    say(f"XAUUSD M1, {n:,} bars, {days} days ({yrs:.1f} y). Median spread ${np.median(spr_d):.3f}, "
        f"median ATR(M1) ${np.nanmedian(atr[base]) * usd:.2f}.")
    say(f"Distance from EMA63 in ATR: p10 {np.nanpercentile(dist[base], 10):.1f}, "
        f"p50 {np.nanpercentile(dist[base], 50):.1f}, p90 {np.nanpercentile(dist[base], 90):.1f}.")

    def fwd(hh):
        j = np.searchsorted(ts, ts + 60 * hh)
        ok = j < n
        j2 = np.where(ok, j, 0)
        ok &= ts[j2] == ts + 60 * hh
        return np.where(ok, j2, -1)

    FW = {hh: fwd(hh) for hh in (5, 15, 30, 60)}

    def path(mask, side):
        """mean forward move in $ per 0.01 lot, signed by `side`, plus t and halves at 30 min"""
        out, t30, h1, h2 = [], np.nan, np.nan, np.nan
        for hh in (5, 15, 30, 60):
            j = FW[hh]
            ok = mask & (j >= 0)
            if ok.sum() < 50:
                out.append(np.nan); continue
            mv = (c[j[ok]] - c[ok]) * usd * side
            out.append(mv.mean())
            if hh == 30:
                t30 = tstat(mv)
                idx = np.where(ok)[0]
                a, b = mv[idx < mid_i], mv[idx >= mid_i]
                h1 = a.mean() if len(a) > 20 else np.nan
                h2 = b.mean() if len(b) > 20 else np.nan
        return out, t30, h1, h2

    # ------------------------------------------------------------------ A
    say("\n=== A. MEASURED: forward move as a function of distance from the EMA 63 ===")
    say("Not 'does touching a level work' but 'what does price actually do from here'. Signed so + is")
    say("a move back TOWARD the MA (mean reversion). Cost to take it is the $%.3f spread." % np.median(spr_d))
    say(f"\n{'distance (ATR)':>16} {'gate':>5} {'n':>8} {'5m':>7} {'15m':>7} {'30m':>7} {'60m':>7} "
        f"{'t 30m':>7} {'h1 / h2 at 30m':>18}")
    buckets = [(-99, -8, "below -8"), (-8, -5, "-8 .. -5"), (-5, -3, "-5 .. -3"), (-3, -1.5, "-3 .. -1.5"),
               (-1.5, 1.5, "-1.5 .. 1.5"), (1.5, 3, "1.5 .. 3"), (3, 5, "3 .. 5"), (5, 8, "5 .. 8"),
               (8, 99, "above 8")]
    for lo, hi, lab in buckets:
        for glab, gm in (("all", np.ones(n, bool)), (">=8", gate >= 8)):
            m = base & gm & (dist >= lo) & (dist < hi)
            if m.sum() < 200:
                continue
            side = 1 if (lo + hi) / 2 < 0 else -1              # toward the MA
            row, t30, h1, h2 = path(m, side)
            say(f"{lab:>16} {glab:>5} {m.sum():8d} " + " ".join(f"{x:7.3f}" for x in row) +
                f" {t30:7.1f} {h1:+8.3f} /{h2:+8.3f}")
    say("\nsame, but split by whether the EMA 63 is RISING or FALLING (TKM's momentum claim),")
    say("for the stretched buckets only, gate >= 8:")
    say(f"\n{'distance':>16} {'MA':>8} {'n':>8} {'5m':>7} {'15m':>7} {'30m':>7} {'60m':>7} {'t 30m':>7}")
    for lo, hi, lab in ((-99, -3, "below -3"), (3, 99, "above 3")):
        for rl, rlab in ((e63r > 0, "rising"), (e63r < 0, "falling")):
            m = base & (gate >= 8) & (dist >= lo) & (dist < hi) & rl
            if m.sum() < 200:
                continue
            side = 1 if lo < 0 else -1
            row, t30, _, _ = path(m, side)
            say(f"{lab:>16} {rlab:>8} {m.sum():8d} " + " ".join(f"{x:7.3f}" for x in row) + f" {t30:7.1f}")

    # ------------------------------------------------------------------ B
    say("\n=== B. MEASURED: is TKM's BOUNDED CCI band 175-233 actually special? ===")
    say("If it is, the band ABOVE 233 must behave differently, not just occur less often. Signed so +")
    say("means the CCI extreme reverted (which is how TKM trades it).")
    say(f"\n{'|CCI|':>14} {'gate':>5} {'n':>8} {'5m':>7} {'15m':>7} {'30m':>7} {'60m':>7} {'t 30m':>7} "
        f"{'h1 / h2 at 30m':>18}")
    for lo, hi, lab in ((100, 150, "100 - 150"), (150, 175, "150 - 175"), (175, 233, "175 - 233 (TKM)"),
                        (233, 300, "233 - 300"), (300, 1e9, "above 300")):
        for glab, gm in (("all", np.ones(n, bool)), (">=8", gate >= 8)):
            ac = np.abs(cci)
            m = base & gm & (ac >= lo) & (ac < hi)
            if m.sum() < 200:
                continue
            side = -np.sign(cci)                               # fade the extreme
            j = FW[30]
            ok = m & (j >= 0)
            rows = []
            for hh in (5, 15, 30, 60):
                jj = FW[hh]
                o2 = m & (jj >= 0)
                mv = (c[jj[o2]] - c[o2]) * usd * side[o2]
                rows.append(mv.mean() if o2.sum() > 50 else np.nan)
            mv30 = (c[j[ok]] - c[ok]) * usd * side[ok]
            idx = np.where(ok)[0]
            a, b = mv30[idx < mid_i], mv30[idx >= mid_i]
            say(f"{lab:>14} {glab:>5} {m.sum():8d} " + " ".join(f"{x:7.3f}" for x in rows) +
                f" {tstat(mv30):7.1f} {a.mean():+8.3f} /{b.mean():+8.3f}")

    # ------------------------------------------------------------------ C
    say("\n=== C. TKM's components as FILTERS on the live spike fade ===")
    say("This is where a weak signal can be worth something. The live v1.99 rule is k 2.0, gate 8,")
    say("SL 0.2 ATR, TP 0.5 x range, 45 min. A filter is only taken seriously if BOTH halves improve")
    say("and it keeps enough trades.")

    def spike(mask=None, k=2.0, tp_f=0.5, maxb=45):
        hit = base & (gate >= 8) & (c < o) & (rng >= k * atr)
        if mask is not None:
            hit &= mask
        S = []
        for i in np.where(hit)[0]:
            sl = l_[i] - 0.2 * atr[i]
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
            say(f"{lab:34s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:34s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+6.0f} {T.net.sum() / yrs:+5.0f} {dd:+7.0f} "
            f"{(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok and mark else ''}")
        return ok

    say("\nbaseline:")
    say(HDR)
    line("LIVE v1.99 (k2.0 TP0.5 45m)", spike())
    line("profit-max (k2.5 no TP 45m)", spike(k=2.5, tp_f=None))

    say("\nfiltered by where price sits relative to the EMA 63 at the signal:")
    say(HDR)
    for lo, hi, lab in ((-99, -5, "dist < -5 ATR"), (-5, -2, "-5 .. -2"), (-2, 0, "-2 .. 0"),
                        (0, 2, "0 .. 2"), (2, 99, "above 2")):
        line(f"LIVE, {lab}", spike(mask=(dist >= lo) & (dist < hi)))
    say("")
    for thr in (-5, -3, -2):
        line(f"LIVE, SKIP dist < {thr} ATR", spike(mask=dist >= thr))

    say("\nfiltered by the CCI at the signal:")
    say(HDR)
    for lo, hi, lab in ((0, 100, "|CCI| < 100"), (100, 175, "100 - 175"), (175, 233, "175 - 233 (TKM)"),
                        (233, 1e9, "above 233")):
        ac = np.abs(cci)
        line(f"LIVE, {lab}", spike(mask=(ac >= lo) & (ac < hi)))
    say("")
    line("LIVE, CCI <= -175 (oversold)", spike(mask=cci <= -175))
    line("LIVE, SKIP |CCI| > 300", spike(mask=np.abs(cci) <= 300))

    say("\nfiltered by TKM's trend state (EMA 63 vs EMA 83, and the MA's slope):")
    say(HDR)
    line("LIVE, EMA63 > EMA83 (up)", spike(mask=e63 > e83))
    line("LIVE, EMA63 < EMA83 (down)", spike(mask=e63 < e83))
    line("LIVE, EMA63 rising", spike(mask=e63r > 0))
    line("LIVE, EMA63 falling", spike(mask=e63r < 0))

    say("\nthe same filters on the profit-max version, to check a filter is not just fitting v1.99:")
    say(HDR)
    for thr in (-5, -3):
        line(f"k2.5 noTP, SKIP dist < {thr}", spike(mask=dist >= thr, k=2.5, tp_f=None))
    line("k2.5 noTP, EMA63 > EMA83", spike(mask=e63 > e83, k=2.5, tp_f=None))
    line("k2.5 noTP, SKIP |CCI| > 300", spike(mask=np.abs(cci) <= 300, k=2.5, tp_f=None))

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
