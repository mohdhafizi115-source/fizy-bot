"""Gold martingale grid with reasoned entries (2 Nov 2026): does it survive on a $100 account?

The owner asked for martingale on top of the grid, with entries that have a reason ("bukan entry membuta tuli").
A basket starts only on a signal; while it is open, other signals are ignored:
  WVB       Williams volatility breakout k 0.7 (live module, PF 1.19 on gold): stop at D1 open +- 0.7 x yesterday's
            range, 01:30-20:00, the first side hit; skipped if the open is already beyond
  LBO       London breakout (live module, PF 1.23): Asian range 03:00-08:00, squeeze < 0.6 x D1 ATR, range
            0.30-1.60% of price, stops +-0.10 from 08:00 to 21:00
  PULLBACK  buy the first touch of yesterday's low in a D1 uptrend (close > EMA 200), sell the first touch of
            yesterday's high in a downtrend, after the price was 0.25 D1 ATR away
  RANDOM    one random start a day (random time 02:00-20:00, random side), 5 seeds: the control for "reason"
Martingale: first lot 0.01; a new level every STEP (0.5 or 1.0 x the previous D1 ATR(14)) against the first entry,
lot = 0.01 x MULT^level rounded up to 0.01 (MULT 1.5 or 2.0); basket take profit at the lot-weighted average entry
+ 0.5 x STEP; 6 levels at most, then either SL (close the basket one STEP beyond the last level) or HOLD (keep it
until the take profit or the stop-out).
Accounts, costs and the "Result OK" rule as in research/grid.py: STD $100 ($1 per $1 per 0.01 lot) and CENT $100
($0.01), 1:500, stop-out 50%, negative balance protection, spread, swap (long -4% / short -1% a year, triple on
Wednesdays), rollover bars 23:45-01:30 skipped. OK = 0 blow-ups, max drawdown <= 50%, both halves and the last
12 months positive, and more profit than all 5 RANDOM runs with the same settings.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYM = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
T0 = time.time()
LEV, SO, START = 500.0, 0.5, 100.0
ACC = {"STD": 1.0, "CENT": 0.01}
MAXLEV = 6


def say(s=""):
    print(s, flush=True)


def signals(d):
    """per-bar start signal: direction (+1 / -1 / 0) and fill price (bid)"""
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    n = len(o)
    day = d.index.normalize()
    hm = d.index.hour.values * 60 + d.index.minute.values
    D = d.groupby(day).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    c1 = D.c.shift()
    D["atr"] = np.maximum(D.h - D.l, np.maximum((D.h - c1).abs(), (D.l - c1).abs())).rolling(14).mean()
    D["ema"] = D.c.ewm(span=200, adjust=False).mean()
    P = D.shift(1)
    datr = P.atr.reindex(day).values
    pr = (P.h - P.l).reindex(day).values
    pdh, pdl = P.h.reindex(day).values, P.l.reindex(day).values
    trend = np.sign(P.c - P.ema).reindex(day).values
    dopen = D.o.reindex(day).values
    codes = pd.factorize(day)[0]
    NR = 5
    S = {k: (np.zeros(n, int), np.zeros(n)) for k in ["WVB", "LBO", "PULLBACK"] + [f"RANDOM{j}" for j in range(NR)]}
    rngs = [np.random.default_rng(3 + j) for j in range(NR)]
    starts = np.r_[0, np.where(np.diff(codes) != 0)[0] + 1, n]
    for a, b in zip(starts[:-1], starts[1:]):
        if not np.isfinite(datr[a]) or not np.isfinite(pr[a]):
            continue
        # WVB
        up, dn = dopen[a] + 0.7 * pr[a], dopen[a] - 0.7 * pr[a]
        for k in range(a, b):
            if hm[k] < 90:
                continue
            if hm[k] >= 1200:
                break
            if o[k] >= up or o[k] <= dn:
                break
            if h[k] >= up and l[k] <= dn:
                break
            if h[k] >= up:
                S["WVB"][0][k], S["WVB"][1][k] = 1, up; break
            if l[k] <= dn:
                S["WVB"][0][k], S["WVB"][1][k] = -1, dn; break
        # LBO
        asia = [k for k in range(a, b) if 180 <= hm[k] < 480]
        if asia:
            ahi, alo = h[asia].max(), l[asia].min()
            rngp = (ahi - alo) / c[asia[-1]] * 100
            if 0.30 <= rngp <= 1.60 and ahi - alo < 0.6 * datr[a]:
                for k in range(a, b):
                    if hm[k] < 480:
                        continue
                    if hm[k] >= 1260:
                        break
                    bu, bd = h[k] >= ahi + 0.10, l[k] <= alo - 0.10
                    if bu and bd:
                        break
                    if bu:
                        S["LBO"][0][k], S["LBO"][1][k] = 1, max(o[k], ahi + 0.10); break
                    if bd:
                        S["LBO"][0][k], S["LBO"][1][k] = -1, min(o[k], alo - 0.10); break
        # PULLBACK to yesterday's low (uptrend) / high (downtrend)
        tr = trend[a]
        if tr != 0 and np.isfinite(pdh[a]):
            lvl = pdl[a] if tr > 0 else pdh[a]
            armed = False
            for k in range(a, b):
                if hm[k] < 90:
                    continue
                if hm[k] >= 1320:
                    break
                if not armed and (c[k - 1] - lvl) * tr >= 0.25 * datr[a]:
                    armed = True
                if armed and ((tr > 0 and l[k] <= lvl) or (tr < 0 and h[k] >= lvl)):
                    S["PULLBACK"][0][k] = int(tr)
                    S["PULLBACK"][1][k] = min(o[k], lvl) if tr > 0 else max(o[k], lvl)
                    break
        # RANDOM (5 seeds)
        cand = [k for k in range(a, b) if 120 <= hm[k] < 1200]
        if cand:
            for j, rng in enumerate(rngs):
                k = cand[rng.integers(len(cand))]
                S[f"RANDOM{j}"][0][k], S[f"RANDOM{j}"][1][k] = (1 if rng.random() < 0.5 else -1), o[k]
    return S, datr


def run(d, sig, datr, stepm, mult, exitmode, val):
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(o)
    days = d.index.normalize().values
    newday = np.r_[False, days[1:] != days[:-1]]
    dow = d.index.day_of_week.values
    hm = d.index.hour.values * 60 + d.index.minute.values
    roll = (hm >= 1425) | (hm < 90)
    sdir, spx = sig
    lots = [int(np.ceil(round(mult ** j, 6))) for j in range(MAXLEV)]   # in 0.01-lot units
    bas = []                                        # (bid level, fill price, units)
    dr, step = 0, 0.0
    st = dict(bal=START)
    blow, pnl_t = [], []
    peak, maxdd, worst, nb = START, 0.0, 0.0, 0

    def floating(price, spr):
        if dr == 1:
            return sum((price - f) * u * val for _, f, u in bas)
        return sum((f - (price + spr)) * u * val for _, f, u in bas)

    def close(price, spr, k):
        nonlocal bas, dr
        if bas:
            r = floating(price, spr)
            st["bal"] += r
            pnl_t.append((k, r))
        bas, dr = [], 0

    for k in range(n):
        if newday[k] and bas:
            units = sum(u for _, _, u in bas)
            sw = -(0.04 if dr == 1 else 0.01) / 360 * c[k - 1] * val * units * (3 if dow[k] == 3 else 1)
            st["bal"] += sw
            pnl_t.append((k, sw))
        if roll[k]:
            continue
        spr = sp[k]
        fresh = False
        if not bas and sdir[k] != 0 and np.isfinite(datr[k]):
            dr, step = int(sdir[k]), stepm * datr[k]
            px = spx[k]
            bas = [(px, px + spr if dr == 1 else px, lots[0])]
            nb += 1
            fresh = True
        if not bas:
            continue
        path = (o[k], l[k], h[k], c[k]) if c[k] >= o[k] else (o[k], h[k], l[k], c[k])
        for si in range(3):
            x, y = path[si], path[si + 1]
            if not bas:
                break
            if (y - x) * dr > 0 and not fresh:      # in favour: basket take profit
                units = sum(u for _, _, u in bas)
                avg = sum(f * u for _, f, u in bas) / units
                tgt = avg + 0.5 * step if dr == 1 else avg - 0.5 * step - spr
                if (dr == 1 and y >= tgt) or (dr == -1 and y <= tgt):
                    close(tgt, spr, k)
                    continue
            elif (y - x) * dr < 0:                  # against: martingale levels, basket stop
                while bas:
                    nxt = bas[0][0] - dr * step * len(bas)
                    if (dr == 1 and y > nxt) or (dr == -1 and y < nxt):
                        break
                    if len(bas) >= MAXLEV:
                        if exitmode == "SL":
                            close(nxt, spr, k)
                        break
                    bas.append((nxt, nxt + spr if dr == 1 else nxt, lots[len(bas)]))
            if bas:
                fl = floating(y, spr)
                worst = min(worst, fl)
                eq = st["bal"] + fl
                units = sum(u for _, _, u in bas)
                if eq <= SO * units * y * val / LEV or eq <= 0:
                    close(y, spr, k)
                    if st["bal"] < 0:
                        pnl_t.append((k, -st["bal"]))
                    blow.append(k)
                    st["bal"] = START
                    peak = START
        eqc = st["bal"] + (floating(c[k], spr) if bas else 0.0)
        peak = max(peak, st["bal"])
        maxdd = max(maxdd, (peak - eqc) / peak)
    if bas:
        close(c[-1], sp[-1], n - 1)
    return dict(blow=blow, maxdd=maxdd, pnl=pnl_t, worst=worst, nb=nb, maxlot=lots[-1])


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    d = SA.load(os.path.join(DATA, SYM + ".csv"), meta[SYM]["point"])
    S, datr = signals(d)
    idx = d.index
    weeks = (idx[-1] - idx[0]).days / 7
    mid, end = idx[len(idx) // 2], idx[-1]
    say(f"{SYM} M5 {idx[0].date()} .. {idx[-1].date()} ({weeks:.0f} weeks); signals: " +
        ", ".join(f"{k} {int((v[0] != 0).sum())}" for k, v in S.items()) + f"; built in {time.time() - T0:.0f} s")
    say("martingale lots per level: x1.5 -> " + str([int(np.ceil(round(1.5 ** j, 6))) for j in range(MAXLEV)]) +
        ", x2 -> " + str([2 ** j for j in range(MAXLEV)]) + " (units of 0.01 lot)")
    say(f"{'variant':34s} {'baskets':>7s} {'blowups':>7s} {'1st(d)':>7s} {'total$':>8s} {'$/wk':>6s} {'maxDD':>6s} {'worst$':>8s} "
        f"{'h1$':>7s} {'h2$':>7s} {'l12$':>7s} result")
    rows = {}
    for acc, val in ACC.items():
        for stepm in (0.5, 1.0):
            for mult in (1.5, 2.0):
                for ex in ("SL", "HOLD"):
                    for sname in S:
                        r = run(d, S[sname], datr, stepm, mult, ex, val)
                        P = pd.Series([p for _, p in r["pnl"]], index=idx[[k for k, _ in r["pnl"]]]) if r["pnl"] else pd.Series(dtype=float)
                        tot = P.sum()
                        h1, h2 = P[P.index < mid].sum(), P[P.index >= mid].sum()
                        l12 = P[P.index >= end - pd.Timedelta(days=365)].sum()
                        first = (idx[r["blow"][0]] - idx[0]).days if r["blow"] else -1
                        base = not r["blow"] and r["maxdd"] <= 0.5 and h1 > 0 and h2 > 0 and l12 > 0
                        key = (acc, stepm, mult, ex)
                        rows[key + (sname,)] = (tot, base)
                        name = f"{acc} {sname} step {stepm} ATR x{mult} {ex}"
                        say(f"{name:34s} {r['nb']:7d} {len(r['blow']):7d} {first:7d} {tot:8.0f} {tot / weeks:6.2f} {100 * r['maxdd']:5.0f}% "
                            f"{r['worst']:8.0f} {h1:7.0f} {h2:7.0f} {l12:7.0f} {'base OK' if base else ''}")
    def best_random(k):
        return max(rows[k[:-1] + (f"RANDOM{j}",)][0] for j in range(5))
    ok = [k for k, (tot, base) in rows.items() if base and not k[-1].startswith("RANDOM") and tot > best_random(k)]
    say(f"\nResult OK (0 blow-ups, max DD <= 50%, both halves and the last 12 months positive, beats all 5 RANDOM runs): {len(ok)}")
    for k in ok:
        say("  " + " ".join(str(x) for x in k))
    nr = sum(1 for k, (t, b) in rows.items() if b and k[-1].startswith("RANDOM"))
    say(f"RANDOM runs passing the base rule (luck baseline): {nr} of 80")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
