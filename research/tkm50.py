"""Round 50 (6 Nov 2026): TKM (Teknik Keabadian Momentum) on M1, with the cost gate, modified.

The owner: "kau tengok balik teknik tkm yang aku pernah share dulu. cuba faham lepas tu modified
sampai jadi."

TKM was tested once before, on M15 (claude/strategy-research-gold-2026.md), and the counter-level
scalp lost: all 12 variants PF 0.71-0.90 in both halves, layering without a stop PF 0.73-0.82
(-$1,000), trend-aligned pullback 0.70-0.86. Only one component was positive: the EMA 63 / 83 cross in
the trend direction, PF 1.17-1.30 on 156 trades.

TWO THINGS MAKE THIS WORTH RE-RUNNING, both written in that doc as open:
  1. "M1 was not tested (needs an M1 export)." The M1 export exists now.
  2. That test predates the COST GATE (round 37), which is the only thing that has ever turned an M1
     rule from losing to passing - it took the spike fade from PF 0.80 to 1.16. TKM was never run
     under it.
And TKM fires often, which is exactly what the owner is asking for: on M15 the counter-level scalp
took 1,086 trades in 10 months, about 5 a day. On M1 the level touches are far more frequent.

TKM as taught, the baseline:
  - EMA 63 and EMA 83 of the typical price (H+L+C)/3.
  - Levels at +-220 / 320 / 420 points from the MA (1 point = $0.01 for gold).
  - CCI(14) of the typical price; entry only while CCI is 175..233 (sell side) or -175..-233 (buy).
  - COUNTER entry when price touches a level; TP 125 / 185 / 320 points back toward the MA.

The modifications tested ("modified sampai jadi"), each one named so the result is attributable:
  M1     run it on M1 instead of M15
  GATE   require ATR(14, M1) >= x times the bar's spread
  SCALE  levels as a share of PRICE or in ATR instead of fixed points, because gold went from
         $1,700 to $4,100 over this history and a fixed $2.20 is a different thing at each end.
         The ebook's own ">= x2.3 for today's price" is an admission of this.
  CCI    with the CCI window, with a looser |CCI| >= 150, and with no CCI filter at all
  SL     a real stop (1 / 2 / 3 ATR) instead of none, plus the taught no-stop + time exit
  TPATR  the target in ATR instead of fixed points
  TREND  with-trend instead of counter, since the only positive TKM component was trend-following
  CROSS  the EMA 63 / 83 cross on M1, gated - the one piece that worked on M15

Controls, both of which have killed level-based ideas in this project before: random entries under the
same gate, and FAKE levels (the same offsets applied to a shifted anchor). If the real TKM levels
matter, the fake ones must behave differently.

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
HDR = ("variant                             trades /day  win%   PF  half1 half2 stress last12$   net$"
       "  $/yr  maxDD$ mth+   by year")


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
    # TKM indicators, all on the typical price and all shifted so only closed bars are used
    tp_ = (h_ + l_ + c) / 3.0
    S = pd.Series(tp_)
    e63 = S.ewm(span=63, adjust=False).mean().shift(1).values
    e83 = S.ewm(span=83, adjust=False).mean().shift(1).values
    sma14 = S.rolling(14).mean()
    mad14 = (S - sma14).abs().rolling(14).mean()
    cci = ((S - sma14) / (0.015 * mad14.replace(0, np.nan))).shift(1).values
    base = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & np.isfinite(e63) & np.isfinite(e83) \
        & np.isfinite(cci) & (spr > 0) & (np.arange(n) >= 300)
    base[-3:] = False
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    days = B.index.normalize().nunique()
    yrs = days / 255.0
    mid_t, end_t = B.index[n // 2], B.index[-1]
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, {days} days "
        f"({yrs:.1f} y). Median spread ${np.median(spr) * usd:.3f} per 0.01 lot.")
    say(f"Price went from ${c[300]:.0f} to ${c[-1]:.0f}, which is why a FIXED 220-point ($2.20) level "
        f"is {2.20 / c[300] * 100:.3f}% of price at the start and {2.20 / c[-1] * 100:.3f}% at the end.")
    say(f"Median |close - EMA63| = ${np.nanmedian(np.abs(c - e63)[base]):.2f}, "
        f"p90 ${np.nanpercentile(np.abs(c - e63)[base], 90):.2f}; median ATR(M1) ${np.nanmedian(atr[base]) * usd:.2f}.")
    say(f"|CCI| in 175-233 on {100 * np.nanmean((np.abs(cci) >= 175) & (np.abs(cci) <= 233))[()]:.2f}% of bars, "
        f"|CCI| >= 150 on {100 * np.nanmean(np.abs(cci) >= 150)[()]:.2f}%.")

    def go(sigs):
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
            say(f"{lab:35s} {0 if T is None else len(T):6d} (too few)")
            return None
        P, P1 = pf(T.net.values), pf(T[T.t < mid_t].net.values)
        P2, PS = pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        mo = T.groupby(T.t.dt.to_period("M")).net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        say(f"{lab:35s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+6.0f} {T.net.sum() / yrs:+5.0f} {dd:+7.0f} "
            f"{(mo > 0).sum():2d}/{len(mo)}  {yr}{'  PASS' if ok and mark else ''}")
        return ok

    # ---- level distance in price terms, by scaling mode
    def levels(mode, mult):
        """returns the distance from the MA for level `mult`, as a price array"""
        if mode == "fixed":                                   # the ebook, 1 point = $0.01
            return np.full(n, mult * 0.01)
        if mode == "x2.3":                                    # the ebook's own rescale for today's price
            return np.full(n, mult * 0.01 * 2.3)
        if mode == "pct":                                      # share of price: adapts across the history
            return c * mult
        if mode == "atr":                                      # in ATR(M1): adapts to volatility too
            return mult * atr
        raise ValueError(mode)

    def tkm(mode, lv, tp_mode, tp_v, x=8.0, cci_mode="taught", sl_mode="none", sl_v=2.0,
            maxb=24, counter=True, fake=0.0):
        """TKM counter entry at a level, target back toward the MA"""
        dist = levels(mode, lv)
        anchor = e63 + fake * atr                              # fake>0 shifts the levels: the control
        up, dn = anchor + dist, anchor - dist
        if cci_mode == "taught":
            cb = (cci <= -175) & (cci >= -233)
            cs = (cci >= 175) & (cci <= 233)
        elif cci_mode == "loose":
            cb, cs = cci <= -150, cci >= 150
        else:
            cb = cs = np.ones(n, bool)
        ok = base & (gate >= x)
        buy = ok & (l_ <= dn) & cb
        sell = ok & (h_ >= up) & cs
        if not counter:                                        # with-trend instead of counter
            buy, sell = ok & (h_ >= up) & cs, ok & (l_ <= dn) & cb
        S = []
        for arr_, side in ((np.where(buy)[0], 1), (np.where(sell)[0], -1)):
            for i in arr_:
                if tp_mode == "pts":
                    tgt = c[i] + side * tp_v * 0.01
                elif tp_mode == "atr":
                    tgt = c[i] + side * tp_v * atr[i]
                else:                                          # back to the MA itself
                    tgt = anchor[i]
                if (tgt - c[i]) * side <= 0:
                    continue
                g = dict(k0=i + 1, kind="mkt", dir=side, exp=i + 1, maxb=maxb, tp=tgt)
                if sl_mode == "atr":
                    g["sl"] = c[i] - side * sl_v * atr[i]
                elif sl_mode == "pts":
                    g["sl"] = c[i] - side * sl_v * 0.01
                else:                                          # taught: no stop, time exit only
                    g["sl"] = c[i] - side * 50.0 * max(atr[i], 0.01)
                if (g["sl"] - c[i]) * side >= 0:
                    continue
                S.append(g)
        return go(S)

    say("\n=== 1. TKM AS TAUGHT, moved to M1: counter entry, CCI window, TP back toward the MA ===")
    say("Levels as the ebook gives them (fixed points) and as it rescales them (x2.3). No stop, out")
    say("after 24 bars, which on M1 is 24 minutes rather than 6 hours.")
    say(HDR)
    for mode in ("fixed", "x2.3"):
        for lv in (220, 320, 420):
            for tp_v in (125, 185, 320):
                line(f"{mode} L{lv} TP{tp_v}pts gate8", tkm(mode, lv, "pts", tp_v))
    say("\nsame, with NO gate (what the original test effectively did, but on M1):")
    say(HDR)
    for lv in (220, 320):
        line(f"fixed L{lv} TP185 NO gate", tkm("fixed", lv, "pts", 185, x=0))

    say("\n=== 2. MODIFICATION: levels scaled to price and to ATR, not fixed dollars ===")
    say("Gold went from $%.0f to $%.0f here, so a fixed $2.20 is a different animal at each end." %
        (c[300], c[-1]))
    say(HDR)
    for lvp in (0.0005, 0.0008, 0.0011):
        line(f"pct L{lvp:.4%} TP->MA gate8", tkm("pct", lvp, "ma", 0))
    for lva in (3, 5, 8, 12):
        line(f"atr L{lva} TP->MA gate8", tkm("atr", lva, "ma", 0))
    say("")
    for lva in (3, 5, 8):
        for tpa in (0.5, 1.0, 2.0):
            line(f"atr L{lva} TP{tpa}atr gate8", tkm("atr", lva, "atr", tpa))

    say("\n=== 3. MODIFICATION: the CCI filter on, loosened, and off ===")
    say(HDR)
    for cm in ("taught", "loose", "off"):
        line(f"atr L5 TP1atr CCI {cm}", tkm("atr", 5, "atr", 1.0, cci_mode=cm))
        line(f"atr L8 TP1atr CCI {cm}", tkm("atr", 8, "atr", 1.0, cci_mode=cm))

    say("\n=== 4. MODIFICATION: a real stop, and a longer hold ===")
    say(HDR)
    for sl in (1.0, 2.0, 3.0):
        line(f"atr L5 TP1atr SL{sl}atr", tkm("atr", 5, "atr", 1.0, sl_mode="atr", sl_v=sl))
    for mb in (24, 60, 120):
        line(f"atr L5 TP1atr SL2atr hold{mb}", tkm("atr", 5, "atr", 1.0, sl_mode="atr", sl_v=2.0, maxb=mb))

    say("\n=== 5. MODIFICATION: the gate swept. A real cost effect is MONOTONE ===")
    say(HDR)
    for x in (0, 2, 4, 6, 8, 12, 16):
        line(f"atr L5 TP1atr SL2atr gate{x}", tkm("atr", 5, "atr", 1.0, sl_mode="atr", sl_v=2.0, x=x))

    say("\n=== 6. MODIFICATION: with-trend instead of counter ===")
    say("On M15 the only positive TKM piece was trend-following, so the counter rule may have the")
    say("sign backwards.")
    say(HDR)
    for lva in (3, 5, 8):
        line(f"atr L{lva} WITH-trend TP1atr SL2", tkm("atr", lva, "atr", 1.0, sl_mode="atr",
                                                      sl_v=2.0, counter=False))

    say("\n=== 7. CONTROLS: fake levels, and random entries under the same gate ===")
    say("If the TKM levels carry information, moving the anchor must change the result.")
    say(HDR)
    for fk in (0.0, 3.0, 7.0):
        line(f"atr L5 TP1atr SL2, anchor +{fk}ATR", tkm("atr", 5, "atr", 1.0, sl_mode="atr",
                                                        sl_v=2.0, fake=fk), mark=(fk == 0))
    rg = np.random.default_rng(50)
    idx = np.where(base & (gate >= 8) & (rg.random(n) < 0.004))[0]
    Sr = []
    for i in idx:
        side = 1 if rg.random() < 0.5 else -1
        Sr.append(dict(k0=i + 1, kind="mkt", dir=side, sl=c[i] - side * 2 * atr[i],
                       tp=c[i] + side * atr[i], exp=i + 1, maxb=24))
    line("RANDOM gate8 TP1atr SL2atr", go(Sr), mark=False)

    say("\n=== 8. the one TKM piece that worked on M15: the EMA 63 / 83 cross, on M1, gated ===")
    cu = (e63 > e83) & (np.r_[np.nan, e63[:-1]] <= np.r_[np.nan, e83[:-1]])
    cd = (e63 < e83) & (np.r_[np.nan, e63[:-1]] >= np.r_[np.nan, e83[:-1]])
    say(HDR)
    for x in (0, 8, 12):
        for sl in (2.0, 3.0):
            S2 = []
            for i in np.where(base & cu & (gate >= x))[0]:
                S2.append(dict(k0=i + 1, kind="mkt", dir=1, sl=c[i] - sl * atr[i], exp=i + 1,
                               maxb=240, xl=cd, xs=cu))
            for i in np.where(base & cd & (gate >= x))[0]:
                S2.append(dict(k0=i + 1, kind="mkt", dir=-1, sl=c[i] + sl * atr[i], exp=i + 1,
                               maxb=240, xl=cd, xs=cu))
            line(f"EMA63/83 cross gate{x} SL{sl}atr", go(S2))

    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
