"""Gold grid EA test on the broker's M5 history (2 Nov 2026): does a fixed-lot grid survive on a $100 account?

The owner asked for a gold grid ("pastikan test dan kalau result ok proceed"). CLAUDE.md says no grids because they
look fine until one trend wipes the account, so this test is about the account, not the profit factor.
Grid (fixed lot 0.01 per level, NO martingale), one basket per direction:
  open 1 position at the next bar open when the basket is empty (and the direction is allowed),
  add 1 position every STEP dollars against the last entry, up to MAXLEV levels (or no limit),
  close the whole basket when the price is STEP dollars beyond the average entry (basket take profit),
  with MAXLEV: close the whole basket at a loss one STEP beyond the last level (basket stop).
Directions: LONG only, SHORT only, BOTH (two independent baskets), TREND (new baskets only in the direction of the
D1 EMA 200, known the day before).
Accounts: STD = $100, 0.01 lot = $1 per $1 gold move; CENT = $100 (10,000 US cents), 0.01 lot = $0.01 per $1 move.
Leverage 1:500, stop-out at 50% margin level (all positions closed at that price). After a blow-up the test counts
it and starts a new $100 life, to show how often it happens.
Bars in the 23:45-01:30 server rollover are skipped (no adds, closes or stop-out checks; the bid is distorted there,
which slightly favours the grid). Costs: the bar's spread on every position; swap per position per night: long -4% a year of the gold price, short
-1% a year (estimates), triple on the Wednesday rollover.
"Result OK" (fixed before the run): 0 blow-ups in 6.6 years, max drawdown <= 50% of the peak balance, profit in both
halves and in the last 12 months. A LONG pass is also checked against SHORT: a grid that only survives in one
direction depends on gold's 2020-2026 uptrend, not on the grid.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYM = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
T0 = time.time()
LEV, SO = 500.0, 0.5
ACC = {"STD": 1.0, "CENT": 0.01}                    # $ per $1 move per 0.01 lot
STEPS = (10.0, 20.0, 40.0)
MAXLEVS = (10, 0)                                   # 0 = no limit


def say(s=""):
    print(s, flush=True)


def run(d, trend, step, maxlev, mode, val, start=100.0):
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(o)
    days = d.index.normalize().values
    newday = np.r_[False, days[1:] != days[:-1]]
    dow = d.index.day_of_week.values
    hm = d.index.hour.values * 60 + d.index.minute.values
    roll = (hm >= 1425) | (hm < 90)                 # server rollover: the bid is distorted, no grid actions
    dirs = {"LONG": (1,), "SHORT": (-1,), "BOTH": (1, -1), "TREND": (1, -1)}[mode]
    pos = {1: [], -1: []}                           # (bid level, fill price): long fills at the ask, short at the bid
    st = dict(bal=start)
    blow, pnl_t = [], []
    peak, maxdd, worst, baskets = start, 0.0, 0.0, 0

    def floating(price, spr):
        return (sum((price - f) * val for _, f in pos[1]) +
                sum((f - (price + spr)) * val for _, f in pos[-1]))

    def close_basket(dr, price, spr, k):
        if not pos[dr]:
            return
        r = sum((price - f) * val for _, f in pos[1]) if dr == 1 else sum((f - (price + spr)) * val for _, f in pos[-1])
        st["bal"] += r
        pnl_t.append((k, r))
        pos[dr] = []

    for k in range(n):
        if newday[k] and (pos[1] or pos[-1]):        # swap for the night
            mult = 3 if dow[k] == 3 else 1          # Wednesday -> Thursday rollover
            sw = (-0.04 * len(pos[1]) - 0.01 * len(pos[-1])) / 360 * c[k - 1] * val * mult
            st["bal"] += sw
            pnl_t.append((k, sw))
        if roll[k]:
            continue
        spr = sp[k]
        for dr in dirs:                             # new baskets at the bar open
            if pos[dr] or (mode == "TREND" and trend[k] != dr):
                continue
            pos[dr].append((o[k], o[k] + spr if dr == 1 else o[k]))
            baskets += 1
        path = (o[k], l[k], h[k], c[k]) if c[k] >= o[k] else (o[k], h[k], l[k], c[k])
        for si in range(3):
            x, y = path[si], path[si + 1]
            for dr in dirs:
                if not pos[dr]:
                    continue
                if (y - x) * dr > 0:                # in favour: basket take profit at average fill + step
                    avg = sum(f for _, f in pos[dr]) / len(pos[dr])
                    tgt = avg + step if dr == 1 else avg - step - spr
                    if (dr == 1 and y >= tgt) or (dr == -1 and y <= tgt):
                        close_basket(dr, tgt, spr, k)
                elif (y - x) * dr < 0:              # against: add levels, basket stop
                    while pos[dr]:
                        nxt = pos[dr][-1][0] - dr * step
                        if (dr == 1 and y > nxt) or (dr == -1 and y < nxt):
                            break
                        if maxlev and len(pos[dr]) >= maxlev:
                            close_basket(dr, nxt, spr, k)
                            break
                        pos[dr].append((nxt, nxt + spr if dr == 1 else nxt))
            npos = len(pos[1]) + len(pos[-1])
            if npos:                                # account check at this point of the bar
                fl = floating(y, spr)
                worst = min(worst, fl)
                eq = st["bal"] + fl
                if eq <= SO * npos * y * val / LEV or eq <= 0:
                    close_basket(1, y, spr, k); close_basket(-1, y, spr, k)
                    if st["bal"] < 0:                # negative balance protection: the loss stops at the deposit
                        pnl_t.append((k, -st["bal"]))
                    blow.append(k)
                    st["bal"] = start
                    peak = start
        eqc = st["bal"] + floating(c[k], spr)
        if st["bal"] > peak:
            peak = st["bal"]
        if peak > 0:
            maxdd = max(maxdd, (peak - eqc) / peak)
    close_basket(1, c[-1], sp[-1], n - 1); close_basket(-1, c[-1], sp[-1], n - 1)
    return dict(blow=blow, bal=st["bal"], maxdd=maxdd, pnl=pnl_t, worst=worst, baskets=baskets)


def flipped(d, seed=11):
    """control: gold with the sign of every bar's move flipped at random (same volatility, no trend, no reversion)"""
    rng = np.random.default_rng(seed)
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    sg = rng.choice([-1.0, 1.0], size=len(o))
    gap = np.r_[0.0, o[1:] - c[:-1]]
    up, dn, mv = h - o, o - l, c - o
    O = np.empty_like(o); C = np.empty_like(o); H = np.empty_like(o); L = np.empty_like(o)
    prev = c[0] - mv[0]
    for k in range(len(o)):
        O[k] = prev + sg[k] * gap[k]
        C[k] = O[k] + sg[k] * mv[k]
        H[k] = O[k] + (up[k] if sg[k] > 0 else dn[k])
        L[k] = O[k] - (dn[k] if sg[k] > 0 else up[k])
        prev = C[k]
    shift = max(0.0, 500.0 - L.min())                 # keep prices positive
    return pd.DataFrame({"o": O + shift, "h": H + shift, "l": L + shift, "c": C + shift, "s": d.s.values}, index=d.index)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    d = SA.load(os.path.join(DATA, SYM + ".csv"), meta[SYM]["point"])
    D = d.c.groupby(d.index.normalize()).last()
    ema = D.ewm(span=200, adjust=False).mean()
    tr_d = np.sign(D - ema).shift(1)                                         # known from the day before
    trend = tr_d.reindex(d.index.normalize()).fillna(0).values
    idx = d.index
    weeks = (idx[-1] - idx[0]).days / 7
    mid, end = idx[len(idx) // 2], idx[-1]
    say(f"{SYM} M5 {idx[0].date()} .. {idx[-1].date()} ({weeks:.0f} weeks), gold {d.c.iloc[0]:.0f} -> {d.c.iloc[-1]:.0f}, "
        f"lowest {d.l.min():.0f}, highest {d.h.max():.0f}")
    say(f"Buy and hold 0.01 lot (STD) for the whole period: {d.c.iloc[-1] - d.c.iloc[0]:+.0f} $ before swaps "
        f"(about {-0.04 / 360 * d.c.mean() * (idx[-1] - idx[0]).days:.0f} $ of swap)")
    say("Per variant: blow-ups (each = a $100 account lost), days to the first blow-up, end balance of the last life,"
        " realised $ in total / per week, max drawdown of the balance+floating, worst floating loss, $ in half 1 / half 2 / last 12 months")
    say(f"{'variant':26s} {'blowups':>7s} {'1st(d)':>7s} {'total$':>8s} {'$/wk':>6s} {'maxDD':>6s} {'worst$':>8s} {'h1$':>7s} {'h2$':>7s} {'l12$':>7s} result")
    passed = []
    for acc, val in ACC.items():
        for mode in ("LONG", "SHORT", "BOTH", "TREND"):
            for step in STEPS:
                for maxlev in MAXLEVS:
                    r = run(d, trend, step, maxlev, mode, val)
                    P = pd.Series([p for _, p in r["pnl"]], index=idx[[k for k, _ in r["pnl"]]]) if r["pnl"] else pd.Series(dtype=float)
                    tot = P.sum()
                    lost = 100.0 * len(r["blow"])
                    net = tot                                # realised P/L includes the losses that blew the accounts
                    h1, h2 = P[P.index < mid].sum(), P[P.index >= mid].sum()
                    l12 = P[P.index >= end - pd.Timedelta(days=365)].sum()
                    first = (idx[r["blow"][0]] - idx[0]).days if r["blow"] else -1
                    ok = not r["blow"] and r["maxdd"] <= 0.5 and h1 > 0 and h2 > 0 and l12 > 0
                    name = f"{acc} {mode} ${step:.0f} {'max ' + str(maxlev) if maxlev else 'no limit'}"
                    if ok:
                        passed.append(name)
                    say(f"{name:26s} {len(r['blow']):7d} {first:7d} {net:8.0f} {net / weeks:6.2f} {100 * r['maxdd']:5.0f}% "
                        f"{r['worst']:8.0f} {h1:7.0f} {h2:7.0f} {l12:7.0f} {'OK' if ok else ''}")
    say(f"\nResult OK (0 blow-ups, max DD <= 50%, both halves and the last 12 months positive): {len(passed)}")
    if passed:
        F = flipped(d)
        Df = F.c.groupby(F.index.normalize()).last()
        trend_f = np.sign(Df - Df.ewm(span=200, adjust=False).mean()).shift(1).reindex(F.index.normalize()).fillna(0).values
        say("Control: the same variants on gold with every bar's move flipped at random (5 seeds; a real edge should beat it)")
        for p in passed:
            acc, mode, step, rest = p.split(" ", 3)
            maxlev = 0 if rest == "no limit" else int(rest.split()[1])
            res = []
            for seed in range(5):
                Fs = flipped(d, seed)
                Dfs = Fs.c.groupby(Fs.index.normalize()).last()
                tfs = np.sign(Dfs - Dfs.ewm(span=200, adjust=False).mean()).shift(1).reindex(Fs.index.normalize()).fillna(0).values
                r = run(Fs, tfs, float(step[1:]), maxlev, mode, ACC[acc])
                res.append((len(r["blow"]), sum(x for _, x in r["pnl"])))
            say(f"  {p:26s} control: blow-ups {[b for b, _ in res]}, total $ {[round(t) for _, t in res]}")
    for p in passed:
        mirror = p.replace("LONG", "SHORT") if " LONG " in p else (p.replace("SHORT", "LONG") if " SHORT " in p else None)
        note = ""
        if mirror:
            note = " (its mirror " + mirror + (" also passes)" if mirror in passed else " FAILS: depends on the trend direction)")
        say("  " + p + note)
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
