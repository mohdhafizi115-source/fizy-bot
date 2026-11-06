"""Round 54 (6 Nov 2026): how long do gold's M1 trends last, buy vs sell, and when in the day?

Owner: "aku nak kau check pola kekerapan gold di m1, kalau trend sell berapa bilangan candle, kalau
trend buy berapa bilangan candle, so dari situ kita dapat pola dia dalam sehari".

A measurement, not a rule. Two definitions of a "trend":
  A  runs of same-coloured M1 candles (how many green / red in a row)
  B  zigzag legs: from a swing low to the next swing high (buy leg) or high to low (sell leg), where a
     swing is confirmed once price reverses by X% of price (0.05% / 0.10% / 0.20%, about $2 / $4 / $8
     at $4,000). Reported: candles per leg, $ per leg, buy vs sell, by hour of day in MYT.
Every number has a CONTROL: the same M1 returns shuffled inside each day, which keeps each day's
volatility but destroys the order. If gold's legs look like the shuffled ones, the "pattern" is what a
random walk produces anyway and cannot be traded.
Also: does a leg that has already lasted N candles tend to continue (the hazard), real vs shuffled.
Note: zigzag legs are only known in hindsight (the end of a leg is confirmed after the reversal).
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def zigzag(c, pct, day):
    """legs between confirmed swing points; a new leg starts when price reverses pct from the extreme.
    Resets at each new day. Returns arrays: start idx, end idx, direction (+1 up / -1 down)."""
    st, en, dr = [], [], []
    n = len(c)
    i0 = 0
    while i0 < n:
        i1 = i0
        while i1 + 1 < n and day[i1 + 1] == day[i0]:
            i1 += 1
        # within one day
        ext_i = i0
        d = 0
        piv = i0
        for k in range(i0 + 1, i1 + 1):
            if d == 0:
                if c[k] >= c[piv] * (1 + pct):
                    d, ext_i = 1, k
                elif c[k] <= c[piv] * (1 - pct):
                    d, ext_i = -1, k
                continue
            if d == 1:
                if c[k] > c[ext_i]:
                    ext_i = k
                elif c[k] <= c[ext_i] * (1 - pct):
                    st.append(piv); en.append(ext_i); dr.append(1)
                    piv, d, ext_i = ext_i, -1, k
            else:
                if c[k] < c[ext_i]:
                    ext_i = k
                elif c[k] >= c[ext_i] * (1 + pct):
                    st.append(piv); en.append(ext_i); dr.append(-1)
                    piv, d, ext_i = ext_i, 1, k
        i0 = i1 + 1
    return np.array(st), np.array(en), np.array(dr)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    del d
    hm = B.hm.values
    keep = (hm >= 90) & (hm < 1425)                        # drop the rollover
    B = B[keep]
    o, c = B.o.values.astype(float), B.c.values.astype(float)
    hm = B.hm.values
    day = B.date.values
    n = len(c)
    yr = B.index.year.values
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars (rollover dropped). "
        f"MYT = server + 6 h in winter.")

    # shuffled control: permute 1-minute returns inside each day, rebuild a price path
    rng = np.random.default_rng(54)
    r = np.r_[0.0, np.diff(np.log(c))]
    newd = np.r_[True, day[1:] != day[:-1]]
    r[newd] = 0.0
    idx = np.arange(n)
    starts = np.where(newd)[0]
    ends = np.r_[starts[1:], n]
    rs = r.copy()
    for a, b in zip(starts, ends):
        seg = rs[a + 1:b].copy()
        rng.shuffle(seg)
        rs[a + 1:b] = seg
    cs = np.empty(n)
    for a, b in zip(starts, ends):
        cs[a:b] = c[a] * np.exp(np.cumsum(rs[a:b]))
    os_ = np.r_[cs[0], cs[:-1]]
    os_[newd] = cs[newd]

    # ------------------------------------------------------------------ A. candle colour runs
    say("\n=== A. How many M1 candles of the same colour in a row? ===")
    say("Share of runs of each length. 'random' is what a coin flip gives (each next candle 50/50).")

    def runs(op, cl):
        col = np.sign(cl - op)
        col[col == 0] = 0
        out = {1: [], -1: []}
        cur, ln = 0, 0
        for k in range(n):
            v = col[k]
            if newd[k] or v != cur:
                if cur != 0 and ln > 0:
                    out[int(cur)].append(ln)
                cur, ln = v, 1
            else:
                ln += 1
        return {s: np.array(x) for s, x in out.items()}

    R, RS = runs(o, c), runs(os_, cs)
    p_up = (c > o).mean()
    say(f"green candles {100 * p_up:.1f}%, red {100 * (c < o).mean():.1f}%, doji {100 * (c == o).mean():.1f}%")
    say(f"\n{'run length':>12} {'green real':>11} {'green shuf':>11} {'red real':>9} {'red shuf':>9} {'coin flip':>10}")
    for L in (1, 2, 3, 4, 5, 6, 7, 8, 10):
        def sh(a):
            return 100 * (a == L).mean() if L < 10 else 100 * (a >= L).mean()
        coin = 100 * (0.5 ** L) if L < 10 else 100 * (0.5 ** 9)
        lab = f"{L}" if L < 10 else ">=10"
        say(f"{lab:>12} {sh(R[1]):10.2f}% {sh(RS[1]):10.2f}% {sh(R[-1]):8.2f}% {sh(RS[-1]):8.2f}% {coin:9.2f}%")
    say(f"\naverage run: green {R[1].mean():.2f} candles (shuffled {RS[1].mean():.2f}), "
        f"red {R[-1].mean():.2f} (shuffled {RS[-1].mean():.2f}); longest green {R[1].max()}, longest red {R[-1].max()}")

    # ------------------------------------------------------------------ B. zigzag legs
    say("\n=== B. Trend legs (zigzag): swing low -> swing high = BUY leg, high -> low = SELL leg ===")
    for pct in (0.0005, 0.0010, 0.0020):
        s, e, dr = zigzag(c, pct, day)
        s2, e2, dr2 = zigzag(cs, pct, day)
        ln, ln2 = e - s, e2 - s2
        mv = np.abs(c[e] - c[s]) * usd
        mv2 = np.abs(cs[e2] - cs[s2]) * usd
        per_day = len(s) / len(starts)
        say(f"\n--- reversal threshold {pct * 100:.2f}% of price (about ${pct * 4000:.0f} at $4,000) ---")
        say(f"legs per day: real {per_day:.1f}, shuffled {len(s2) / len(starts):.1f}")
        say(f"{'':>10} {'n':>8} {'candles: median':>16} {'mean':>6} {'p75':>5} {'p90':>5} {'$ median':>9} {'$ p90':>7}"
            f" | {'shuffled: candles median':>25} {'mean':>6} {'$ median':>9}")
        for dd, lab in ((1, "BUY leg"), (-1, "SELL leg")):
            m, m2 = dr == dd, dr2 == dd
            say(f"{lab:>10} {m.sum():8d} {np.median(ln[m]):16.0f} {ln[m].mean():6.1f} {np.percentile(ln[m], 75):5.0f} "
                f"{np.percentile(ln[m], 90):5.0f} {np.median(mv[m]):9.2f} {np.percentile(mv[m], 90):7.2f}"
                f" | {np.median(ln2[m2]):25.0f} {ln2[m2].mean():6.1f} {np.median(mv2[m2]):9.2f}")
        # speed: $ per candle, buy vs sell
        say(f"speed ($ per candle): BUY {np.median(mv[dr == 1] / np.maximum(ln[dr == 1], 1)):.3f}, "
            f"SELL {np.median(mv[dr == -1] / np.maximum(ln[dr == -1], 1)):.3f} "
            f"(shuffled {np.median(mv2 / np.maximum(ln2, 1)):.3f})")
        if pct == 0.0010:
            S, E, D, LN, MV = s, e, dr, ln, mv
            S2, LN2, D2 = s2, ln2, dr2

    # ------------------------------------------------------------------ C. hazard
    say("\n=== C. If a leg has ALREADY lasted N candles, how often does it last 10 more? (0.10% legs) ===")
    say("This is the only part that could matter for trading: does a long leg tend to keep going?")
    say(f"{'already N':>10} {'BUY real':>9} {'BUY shuf':>9} {'SELL real':>10} {'SELL shuf':>10}")
    for N in (5, 10, 20, 30, 45, 60, 90):
        row = []
        for LL, DD in ((LN, D), (LN2, D2)):
            for dd in (1, -1):
                a = LL[DD == dd]
                row.append(100 * ((a >= N + 10).sum() / max((a >= N).sum(), 1)))
        say(f"{N:>10} {row[0]:8.1f}% {row[2]:8.1f}% {row[1]:9.1f}% {row[3]:9.1f}%")

    # ------------------------------------------------------------------ D. by hour of day
    say("\n=== D. The day's pattern: legs (0.10%) by the MYT hour they START ===")
    say("legs/day = how many legs start in that hour per trading day; buy% = share that are BUY legs;")
    say("candles = median leg length; $ = median size. Last column: 2026 only, to see if it holds now.")
    st_hm = hm[S]
    myt = ((st_hm // 60) + 6) % 24
    yrs = yr[S]
    nd = len(starts)
    nd26 = len(np.unique(day[yr == 2026]))
    say(f"{'MYT hour':>9} {'legs/day':>9} {'buy%':>6} {'candles':>8} {'$ med':>7} {'buy cand':>9} {'sell cand':>10}"
        f" | {'2026 legs/day':>14} {'2026 buy%':>10}")
    for hh in list(range(7, 24)) + list(range(0, 6)):
        m = myt == hh
        if m.sum() < 50:
            continue
        m26 = m & (yrs == 2026)
        bl = LN[m & (D == 1)]
        sl = LN[m & (D == -1)]
        say(f"{hh:>7}:00 {m.sum() / nd:9.2f} {100 * (D[m] == 1).mean():6.1f} {np.median(LN[m]):8.0f} "
            f"{np.median(MV[m]):7.2f} {np.median(bl) if len(bl) else 0:9.0f} {np.median(sl) if len(sl) else 0:10.0f}"
            f" | {m26.sum() / max(nd26, 1):14.2f} {100 * (D[m26] == 1).mean() if m26.sum() else 0:9.1f}")

    say("\n=== E. by year (0.10% legs): has the pattern changed? ===")
    say(f"{'year':>6} {'legs/day':>9} {'buy%':>6} {'buy candles':>12} {'sell candles':>13} {'buy $':>7} {'sell $':>7}")
    for y in sorted(np.unique(yrs)):
        m = yrs == y
        ndy = len(np.unique(day[yr == y]))
        say(f"{y:>6} {m.sum() / ndy:9.1f} {100 * (D[m] == 1).mean():6.1f} {np.median(LN[m & (D == 1)]):12.0f} "
            f"{np.median(LN[m & (D == -1)]):13.0f} {np.median(MV[m & (D == 1)]):7.2f} {np.median(MV[m & (D == -1)]):7.2f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
