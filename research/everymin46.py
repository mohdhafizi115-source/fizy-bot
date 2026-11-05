"""Round 46 (5 Nov 2026): the owner wants an EA that trades EVERY MINUTE. Can that work at all?

"sekarang aku nak ea yang trade setiap minit. kau dah pandai kan baca pergerakan gold? ciptakan"

This is not answered by testing another rule. It is answered by finding the CEILING on how much any
rule could possibly make at a given trade rate, and comparing that with what the trading costs. If the
ceiling is below the cost, no amount of cleverness helps and the honest answer is no. So this round
measures the ceiling three different ways, each one more generous than the last, and then maps the
frontier of what IS reachable.

  A  THE COST WALL. Gold M1 has 1,370 bars a trading day and the median spread is $0.19 per 0.01 lot.
     Entering every minute means paying that every minute. The table shows the yearly spread bill at
     each trade rate against every edge this project has ever found, so the scale is explicit.
  B  THE LITERAL REQUEST, traded. Enter every single M1 bar and hold one minute, in five directions:
     long always, short always, random, follow the previous bar, fade the previous bar. Plus the
     cheaper honest version - stay in the market and only REVERSE when the signal flips, which pays
     the spread on reversals instead of every minute.
  C  THE PREDICTABILITY CEILING, and this is the decisive part. Fit a linear model of the NEXT
     minute's return on 20 features known at this minute's close (past returns, ATR, spread, the cost
     gate, range, body, momentum, distance from the EMA, hour), on ALL the data, IN SAMPLE. In-sample
     is deliberate: it is cheating, so whatever it achieves is an upper bound that no honest model can
     beat. Then do the same with a SATURATED model - the in-sample mean next-minute return in each
     bucket of (sign of last move x gate tercile x hour), which is an even higher ceiling because it
     can fit any shape. Report each one's implied edge per trade against the $0.19 it must beat, and
     trade both in sample with costs.
  D  THE FRONTIER. For the one family that does work (the spike fade), sweep the spike size from 5.0
     down to 0.5 ATR and the gate from 12 down to 0, and report trade rate against profit factor with
     pass/fail, so the honest answer to "more trades" has a number on it: the highest trade rate that
     still passes the project's pass rule.

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
    spr = B.s.values.astype(float)
    spr_d = spr * usd
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h_ - l_, np.maximum(np.abs(h_ - c1), np.abs(l_ - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = np.where(spr > 0, atr / spr, np.nan)
    days = B.index.normalize().nunique()
    mid, end_t = n // 2, B.index[-1]
    mid_t = B.index[mid]
    # next-minute open-to-open return in dollars, which is what a one-minute trade actually captures
    nxt = np.r_[(o[2:] - o[1:-1]) * usd, np.nan, np.nan]
    base = np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 300) & np.isfinite(nxt) & ~np.r_[newday[1:], True]
    base[-3:] = False
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars over {days} days "
        f"= {n / days:.0f} bars a trading day.")
    say(f"Spread per 0.01 lot: median ${np.median(spr_d):.3f}, mean ${spr_d.mean():.3f}. "
        f"Mean absolute 1-minute move ${np.nanmean(np.abs(nxt)):.3f}, standard deviation ${np.nanstd(nxt):.3f}.")

    # ---------------------------------------------------------------- A. the cost wall
    say("\n=== A. THE COST WALL: what the trading itself costs, before any strategy ===")
    say("Every entry pays the spread once. At 0.01 lot, per year (255 trading days):")
    say(f"\n{'trades a day':>14} {'trades a year':>14} {'spread bill a year':>19} {'needed per trade to break even':>31}")
    for r in (0.6, 1.3, 5, 20, 60, 240, 1370):
        yr = r * 255
        lab = "EVERY MINUTE" if r == 1370 else ""
        say(f"{r:>13.1f}{'':1} {yr:>14,.0f} {'$' + format(yr * np.median(spr_d), ',.0f'):>19} "
            f"{'$' + format(np.median(spr_d), '.3f'):>31}  {lab}")
    say("\nFor scale, the TOTAL profit of every edge this project has found, over 6.6 years at 0.01 lot:")
    say("  gold M1 spike fade +$1,445 | gold LBMA auction +$762 | gold Tenkan/Kijun +$1,796 |")
    say("  gold Kumo +$1,330 | Gotobi and month-end a few hundred each.")
    say("  Everything together is roughly +$6,000 over 6.6 years, about $900 a year.")
    say(f"  Trading every minute costs ${1370 * 255 * np.median(spr_d):,.0f} a year in spread alone.")
    say(f"  So an every-minute EA would have to find {1370 * 255 * np.median(spr_d) / 900:,.0f} times the total")
    say("  edge of every working strategy found so far, just to break even.")

    # ---------------------------------------------------------------- B. trade it anyway
    say("\n=== B. THE LITERAL REQUEST, actually traded: enter every M1 bar, hold one minute ===")
    say("Direction rules, all using only information known at the bar's close.")
    say(f"\n{'direction'      :>26} {'trades':>9} {'win%':>6} {'PF':>6} {'gross $':>10} {'spread paid $':>14} {'net $':>10} {'net/yr $':>10}")
    r_prev = np.r_[np.nan, (c[1:] - c[:-1])] * usd
    rg_ = np.random.default_rng(46)
    dirs = {
        "always LONG": np.ones(n),
        "always SHORT": -np.ones(n),
        "random each minute": np.where(rg_.random(n) < 0.5, 1.0, -1.0),
        "follow the last minute": np.sign(r_prev),
        "fade the last minute": -np.sign(r_prev),
        "follow EMA20 slope": np.sign(pd.Series(c).ewm(span=20, adjust=False).mean().diff().shift(1).values),
    }
    for lab, dr in dirs.items():
        m = base & np.isfinite(dr) & (dr != 0)
        g = (nxt[m] * dr[m])
        cost = spr_d[m]
        net = g - cost
        say(f"{lab:>26} {m.sum():9d} {100 * (net > 0).mean():6.1f} {SA.f2(pf(net)):>6} "
            f"{g.sum():+10.0f} {cost.sum():14,.0f} {net.sum():+10.0f} {net.sum() / (days / 255):+10.0f}")
    say("\nThe same direction rules but STAYING IN THE MARKET, paying the spread only when the signal")
    say("flips (the cheapest honest way to be 'always trading'):")
    say(f"\n{'direction':>26} {'flips':>9} {'flips/day':>10} {'gross $':>10} {'spread paid $':>14} {'net $':>10}")
    for lab, dr in dirs.items():
        if lab in ("always LONG", "always SHORT"):
            continue
        m = base & np.isfinite(dr) & (dr != 0)
        dd = np.where(m, dr, np.nan)
        prev = pd.Series(dd).ffill().shift(1).values
        flip = m & np.isfinite(prev) & (dd != prev)
        g = np.nansum(nxt[m] * dr[m])
        cost = spr_d[flip].sum()
        say(f"{lab:>26} {flip.sum():9d} {flip.sum() / days:10.1f} {g:+10.0f} {cost:14,.0f} {g - cost:+10.0f}")
    say("\n(always LONG / always SHORT are buy-and-hold with one spread paid, shown above for reference:")
    say(" they are not 'trading every minute' at all.)")

    # ---------------------------------------------------------------- C. the predictability ceiling
    say("\n=== C. THE PREDICTABILITY CEILING: the best a model could POSSIBLY do, fitted in sample ===")
    say("If a model that has already seen the answers cannot beat the spread, no honest model can.")
    ac = np.corrcoef(nxt[base], r_prev[base])[0, 1]
    say(f"\nFirst, the simplest check: correlation between this minute's move and the next one = {ac:+.4f}.")
    say("At that level there is essentially nothing to predict from the last move alone.")
    e20 = pd.Series(c).ewm(span=20, adjust=False).mean().shift(1).values
    feats = {
        "r1": r_prev, "r2": np.r_[np.nan, r_prev[:-1]], "r3": np.r_[[np.nan] * 2, r_prev[:-2]],
        "r5": np.r_[[np.nan] * 4, r_prev[:-4]],
        "mom5": np.r_[[np.nan] * 5, (c[5:] - c[:-5])] * usd,
        "mom20": np.r_[[np.nan] * 20, (c[20:] - c[:-20])] * usd,
        "absr1": np.abs(r_prev), "sgnr1": np.sign(r_prev),
        "atr": atr * usd, "spread": spr_d, "gate": gate,
        "range": (h_ - l_) * usd, "body": (c - o) * usd,
        "bodyrange": np.where(h_ > l_, (c - o) / (h_ - l_), 0.0),
        "distema": (c - e20) * usd, "distema_atr": np.where(atr > 0, (c - e20) / atr, 0.0),
        "hsin": np.sin(2 * np.pi * hm / 1440), "hcos": np.cos(2 * np.pi * hm / 1440),
        "hsin2": np.sin(4 * np.pi * hm / 1440), "hcos2": np.cos(4 * np.pi * hm / 1440),
    }
    names = list(feats)
    X = np.column_stack([feats[k] for k in names])
    ok = base & np.isfinite(X).all(axis=1)
    Xo = np.column_stack([np.ones(ok.sum()), X[ok]])
    y = nxt[ok]
    beta, *_ = np.linalg.lstsq(Xo, y, rcond=None)
    pred = Xo @ beta
    ss = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    say(f"\nLinear model, {len(names)} features, fitted on all {ok.sum():,} bars IN SAMPLE:")
    say(f"  in-sample R2 = {ss:.6f}  (so it explains {100 * ss:.3f}% of the next minute's move)")
    say(f"  mean |predicted move| = ${np.abs(pred).mean():.4f}, against a ${np.median(spr_d):.3f} spread")
    say(f"  the predictions are above the spread on only {100 * (np.abs(pred) > spr_d[ok]).mean():.1f}% of bars")
    net = np.sign(pred) * y - spr_d[ok]
    say(f"  trading its sign every minute, in sample, after cost: PF {pf(net):.3f}, "
        f"net ${net.sum():+,.0f} over {ok.sum():,} trades (${net.mean():+.4f} a trade)")
    sel = np.abs(pred) > spr_d[ok]
    if sel.sum() > 1000:
        net2 = (np.sign(pred) * y - spr_d[ok])[sel]
        say(f"  trading only when its own prediction exceeds the spread ({sel.sum():,} bars, "
            f"{sel.sum() / days:.0f} a day): PF {pf(net2):.3f}, net ${net2.sum():+,.0f}")
    say(f"  the five largest coefficients: " + ", ".join(
        f"{names[i]} {beta[i + 1]:+.5f}" for i in np.argsort(-np.abs(beta[1:]))[:5]))

    say("\nSaturated model - the in-sample mean next move in each bucket of")
    say("(sign of the last move x gate tercile x hour of day). This can fit any shape, so it is an")
    say("even higher ceiling than the linear fit:")
    q = np.nanpercentile(gate[base], [33, 67])
    gt = np.digitize(gate, q)
    key = (np.sign(r_prev) + 1).astype(np.int64) * 100 + gt * 10 + (hm // 60) % 24
    kk = key[ok].astype(np.int64)
    dfb = pd.DataFrame({"k": kk, "y": y})
    mu = dfb.groupby("k").y.transform("mean").values
    cnt = dfb.groupby("k").y.transform("size").values
    say(f"  {dfb.k.nunique()} buckets, median {int(np.median(cnt)):,} bars each")
    say(f"  mean |bucket mean| = ${np.abs(mu).mean():.4f}, against a ${np.median(spr_d):.3f} spread")
    say(f"  largest bucket mean = ${np.abs(mu).max():.4f}")
    netb = np.sign(mu) * y - spr_d[ok]
    say(f"  trading its sign every minute, in sample, after cost: PF {pf(netb):.3f}, net ${netb.sum():+,.0f}")
    selb = np.abs(mu) > spr_d[ok]
    say(f"  bars where a bucket mean even exceeds the spread: {selb.sum():,} "
        f"({100 * selb.mean():.2f}%)" + (f", PF {pf(netb[selb]):.3f}, net ${netb[selb].sum():+,.0f}"
                                         if selb.sum() > 500 else ""))
    say("\nAnd the same saturated model scored HONESTLY - bucket means learned on the first half only,")
    say("then applied to the second half, which is what a real EA would face:")
    h1 = np.arange(ok.sum()) < (ok.sum() // 2)
    m1 = dfb[h1].groupby("k").y.mean()
    pm = dfb.k.map(m1).values
    g2 = (~h1) & np.isfinite(pm)
    net3 = np.sign(pm[g2]) * y[g2] - spr_d[ok][g2]
    say(f"  second half: PF {pf(net3):.3f}, net ${net3.sum():+,.0f} over {g2.sum():,} trades "
        f"(${net3.mean():+.4f} a trade)")
    raw3 = np.sign(pm[g2]) * y[g2]
    say(f"  and BEFORE costs: PF {pf(raw3):.3f}, ${raw3.mean():+.4f} a trade - so even the gross edge is "
        f"{'below' if raw3.mean() < np.median(spr_d) else 'above'} the ${np.median(spr_d):.3f} spread")

    # ---------------------------------------------------------------- D. the frontier
    say("\n=== D. THE FRONTIER: the most trades a day that still PASSES ===")
    say("The spike fade is the only M1 family with an edge. Lowering the spike size and the gate buys")
    say("more trades; this is where that stops working. Settings otherwise as live: SL 0.2 ATR, no TP,")
    say("45 minutes, buy side only.")
    arr = [B[x].values.astype(float) for x in ("o", "h", "l", "c", "s")]
    flat = (hm >= 1350) | newday | np.r_[newday[1:], True]
    sbase = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (spr > 0) & (np.arange(n) >= 300)
    sbase[-3:] = False
    rng = h_ - l_
    say(f"\n{'k':>5} {'gate':>5} {'trades':>8} {'a day':>7} {'PF':>6} {'half1':>6} {'half2':>6} {'stress':>7}"
        f" {'last12$':>9} {'net$':>8} {'maxDD$':>8}  pass")
    for k in (5.0, 4.0, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5):
        for x in (12, 8, 4, 0):
            hit = sbase & (gate >= x) & (c < o) & (rng >= k * atr)
            idx = np.where(hit)[0]
            if len(idx) < 100:
                continue
            S = []
            for i in idx:
                sl = l_[i] - 0.2 * atr[i]
                if sl >= c[i]:
                    continue
                S.append(dict(k0=i + 1, kind="mkt", dir=1, sl=sl, exp=i + 1, maxb=45))
            tr_ = SA.sim(*arr, S, flat)
            if len(tr_) < 100:
                continue
            T = pd.DataFrame(tr_, columns=["kk", "dir", "pnl", "sp", "risk", "why"])
            T["t"] = B.index[T.kk.values]
            T["net"] = (T.pnl - T.sp) * usd
            T["st"] = (T.pnl - 1.5 * T.sp) * usd
            P = pf(T.net.values)
            P1, P2 = pf(T[T.t < mid_t].net.values), pf(T[T.t >= mid_t].net.values)
            PS = pf(T.st.values)
            l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
            eq = T.net.cumsum().values
            dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
            good = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
            say(f"{k:5.1f} {x:5d} {len(T):8d} {len(T) / days:7.2f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} "
                f"{SA.f2(PS)} {l12:+9.0f} {T.net.sum():+8.0f} {dd:+8.0f}  {'PASS' if good else ''}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
