"""Round 22 (3 Nov 2026): gold M1 scalps judged on ONE month, the way the owner wants ("test 1 bulan dah cukup").

Same M1 data as round 21 (run 41663561048). A wider grid of M1 scalps (53 variants, fixed before the run) plus 10
random-entry rules with different seeds:
  EMA_X     fast / slow EMA cross on the EMA 200 side: (5,13) (9,21) (20,50) x SL 1 / 2 ATR x TP 1R / 2R
  BB_RSI    close outside BB (20, 2 / 2.5) with RSI(7) beyond 20/80 or 10/90, fade to the middle band, SL 1.5 / 3 ATR
  STOCH     Stochastic (5,3,3) cross out of 20/80 or 10/90, with or without the EMA 50 side, TP 1R / 2R, SL 1.5 ATR
  RSI2      RSI(2) beyond 10/90 or 5/95 on the EMA 200 side, exit at the SMA 5 or 24 bars, SL 2 / 4 ATR
  DON_BO    20- / 60-bar breakout on the EMA 200 side, SL 1.5 ATR, TP 1.5R / 3R
  PULL      candle off the EMA 21 / 50 in trend, TP 1R / 2R
  OPEN_BO   London 08:00 + New York 09:30 breakout of the 15 / 30 min pre-open range, TP 1R / 2R
  SPK_FADE  fade an M1 bar >= 2.5 / 3 / 4 ATR, TP half the bar back or 1R
  SPK_FOLW  follow it, TP 1R
  RAND_s    random entries, about one per 30 min, random side, SL 1.5 ATR, TP 1.5R, seeds 1-10 (pure chance)
Signals 09:00-21:00 server, flat 22:30, costs = bar spread, fixed 0.01 lot ($).
Questions:
  1. Last month (the 31 days to the end of the data): which rules made money, and how many of the random ones did too?
  2. The owner's method, tested honestly: at the start of every month pick the rule that made the most in the month
     before (at least 30 trades), trade it for the month, repeat. Out-of-sample result over 2020-2026, also for the
     best 3 rules, and against picking a random rule.
  3. Does a winning month repeat? Share of rules that are positive in a month after a positive month vs after a
     negative month.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import m1scalp21 as M

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def build(d):
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    C = pd.Series(c)
    F = M.features(d)
    for n in (5, 13, 20):
        F[f"e{n}"] = C.ewm(span=n, adjust=False).mean().values
    m20, s20 = C.rolling(20).mean().values, C.rolling(20).std(ddof=0).values
    F["bbu25"], F["bbl25"] = m20 + 2.5 * s20, m20 - 2.5 * s20
    F["hi60"] = np.r_[np.nan, pd.Series(h).rolling(60).max().values[:-1]]
    F["lo60"] = np.r_[np.nan, pd.Series(l).rolling(60).min().values[:-1]]
    A = F["atr"]
    n = len(c)
    hm = d.index.hour.values * 60 + d.index.minute.values
    ok = (hm >= 540) & (hm < 1260) & np.isfinite(A) & np.isfinite(F["e200"]) & (np.arange(n) >= 300)
    ok[-2:] = False
    V = {}

    def add(name, i, dr, sl, **kw):
        if (sl - c[i]) * dr >= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=kw.pop("maxb", 60))
        g.update(kw)
        V.setdefault(name, []).append(g)

    def cross(a, b):
        return (a > b) & np.r_[False, a[:-1] <= b[:-1]], (a < b) & np.r_[False, a[:-1] >= b[:-1]]

    e200 = F["e200"]
    for fs in ((5, 13), (9, 21), (20, 50)):
        up, dn = cross(F[f"e{fs[0]}"], F[f"e{fs[1]}"])
        for slm in (1, 2):
            for tpr in (1, 2):
                nm = f"EMA_X {fs[0]}/{fs[1]} sl{slm} tp{tpr}"
                for i in np.where(ok & up & (c > e200))[0]:
                    add(nm, i, 1, c[i] - slm * A[i], tp_r=tpr)
                for i in np.where(ok & dn & (c < e200))[0]:
                    add(nm, i, -1, c[i] + slm * A[i], tp_r=tpr)
    for dev, (bu, bl) in ((2, ("bbu", "bbl")), (2.5, ("bbu25", "bbl25"))):
        for lo_, hi_ in ((20, 80), (10, 90)):
            for slm in (1.5, 3):
                nm = f"BB_RSI {dev} rsi{lo_} sl{slm}"
                for i in np.where(ok & (c < F[bl]) & (F["rsi7"] < lo_))[0]:
                    add(nm, i, 1, c[i] - slm * A[i], tp=F["bbm"][i], maxb=30)
                for i in np.where(ok & (c > F[bu]) & (F["rsi7"] > hi_))[0]:
                    add(nm, i, -1, c[i] + slm * A[i], tp=F["bbm"][i], maxb=30)
    K, D = F["k"], F["dd"]
    kup, kdn = cross(K, D)
    K1 = np.r_[np.nan, K[:-1]]
    for lo_, hi_ in ((20, 80), (10, 90)):
        for filt in (True, False):
            for tpr in (1, 2):
                nm = f"STOCH {lo_}/{hi_} {'ema50' if filt else 'nofilt'} tp{tpr}"
                fu = (c > F["e50"]) if filt else np.ones(n, bool)
                fd = (c < F["e50"]) if filt else np.ones(n, bool)
                for i in np.where(ok & kup & (K1 < lo_) & fu)[0]:
                    add(nm, i, 1, c[i] - 1.5 * A[i], tp_r=tpr, maxb=30)
                for i in np.where(ok & kdn & (K1 > hi_) & fd)[0]:
                    add(nm, i, -1, c[i] + 1.5 * A[i], tp_r=tpr, maxb=30)
    xl, xs = c > F["sma5"], c < F["sma5"]
    for lo_, hi_ in ((10, 90), (5, 95)):
        for slm in (2, 4):
            nm = f"RSI2 {lo_}/{hi_} sl{slm}"
            for i in np.where(ok & (c > e200) & (F["rsi2"] < lo_))[0]:
                add(nm, i, 1, c[i] - slm * A[i], xl=xl, xs=xs, maxb=24)
            for i in np.where(ok & (c < e200) & (F["rsi2"] > hi_))[0]:
                add(nm, i, -1, c[i] + slm * A[i], xl=xl, xs=xs, maxb=24)
    for N in (20, 60):
        for tpr in (1.5, 3):
            nm = f"DON_BO {N} tp{tpr}"
            for i in np.where(ok & (c > F[f"hi{N}"]) & (c > e200))[0]:
                add(nm, i, 1, c[i] - 1.5 * A[i], tp_r=tpr)
            for i in np.where(ok & (c < F[f"lo{N}"]) & (c < e200))[0]:
                add(nm, i, -1, c[i] + 1.5 * A[i], tp_r=tpr)
    for en in (21, 50):
        E = F[f"e{en}"]
        for tpr in (1, 2):
            nm = f"PULL ema{en} tp{tpr}"
            for i in np.where(ok & (c > e200) & (E > e200) & (l <= E) & (c > E) & (c > o))[0]:
                add(nm, i, 1, l[i] - 0.2 * A[i], tp_r=tpr)
            for i in np.where(ok & (c < e200) & (E < e200) & (h >= E) & (c < E) & (c < o))[0]:
                add(nm, i, -1, h[i] + 0.2 * A[i], tp_r=tpr)
    op = M.opens(d)
    for pre in (15, 30):
        for tpr in (1, 2):
            nm = f"OPEN_BO pre{pre} tp{tpr}"
            for k in op:
                if k < pre or not np.isfinite(A[k]):
                    continue
                H_, L_ = h[k - pre:k].max(), l[k - pre:k].min()
                if not (L_ < o[k] < H_):
                    continue
                bf = 0.05 * A[k]
                V.setdefault(nm, []).append(dict(k0=k, kind="oco", dir=0, P=H_ + bf, sl=L_, P2=L_ - bf, sl2=H_, tp_r=tpr, exp=k + 29, maxb=60))
    rg = h - l
    for th in (2.5, 3, 4):
        for i in np.where(ok & (rg >= th * A) & (c != o))[0]:
            dr = 1 if c[i] > o[i] else -1
            sl = (h[i] + 0.2 * A[i]) if dr == 1 else (l[i] - 0.2 * A[i])
            add(f"SPK_FADE {th} tpHalf", i, -dr, sl, tp=c[i] - dr * 0.5 * rg[i], maxb=15)
            add(f"SPK_FADE {th} tp1R", i, -dr, sl, tp_r=1.0, maxb=15)
            add(f"SPK_FOLW {th}", i, dr, (h[i] + l[i]) / 2, tp_r=1.0, maxb=15)
    for s in range(1, 11):
        r = np.random.default_rng(100 + s)
        for i in np.where(ok & (r.random(n) < 1 / 30))[0]:
            dr = 1 if r.random() < 0.5 else -1
            add(f"RAND_{s}", i, dr, c[i] - dr * 1.5 * A[i], tp_r=1.5)
    return V


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    m = meta["XAUUSD"]
    usd = m["tick_value"] / m["tick_size"] * 0.01 if m["tick_size"] > 0 else 1.0
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), m["point"])
    dates = d.index.normalize().values
    hm = d.index.hour.values * 60 + d.index.minute.values
    flat = (hm >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    say(f"XAUUSD M1 {d.index[0]:%Y-%m-%d} .. {d.index[-1]:%Y-%m-%d %H:%M}, {len(d):,} bars")
    V = build(d)
    say(f"{len(V)} rules built in {time.time() - T0:.0f} s")
    arr = [d[x].values for x in ("o", "h", "l", "c", "s")]
    rows = []
    for nm, S in V.items():
        for (k, dr, pnl, sp, risk, why) in SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat):
            rows.append((nm, k, (pnl - sp) * usd))
    T = pd.DataFrame(rows, columns=["rule", "k", "net"])
    T["t"] = d.index[T.k.values]
    T["mon"] = T.t.dt.to_period("M")
    rules = list(V)
    real = [r for r in rules if not r.startswith("RAND")]
    rand = [r for r in rules if r.startswith("RAND")]
    say(f"simulated in {time.time() - T0:.0f} s, {len(T):,} trades")

    # 1. last month
    end = d.index[-1]
    t1 = end - pd.Timedelta(days=31)
    pfx = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.inf
    L = T[T.t >= t1].groupby("rule").net.agg(["count", "sum", lambda x: (x > 0).mean() * 100, pfx])
    L.columns = ["trades", "net", "win", "pf"]
    L = L.sort_values("net", ascending=False)
    full = T.groupby("rule").net.agg(["count", "sum", pfx])
    full.columns = ["n", "net", "pf"]
    mon = T.groupby(["rule", "mon"]).net.sum().unstack(fill_value=0.0)
    say(f"\n1. LAST MONTH ({t1:%d %b} - {end:%d %b %Y}): top 15 of {len(rules)} rules (RAND_x = random entries)")
    say("rule                         trades  win%    PF   net$ |  2020-2026: PF   net$   months +")
    for nm, r in L.head(15).iterrows():
        f = full.loc[nm]
        mp = (mon.loc[nm] > 0).sum()
        say(f"{nm:28s} {int(r.trades):6d} {r.win:5.1f} {SA.f2(r.pf)} {r.net:+7.2f} | {SA.f2(f.pf):>13s} {f.net:+7.0f}   {mp}/{mon.shape[1]}")
    pr = [r for r in real if r in L.index and L.loc[r, "net"] > 0]
    pz = [r for r in rand if r in L.index and L.loc[r, "net"] > 0]
    say(f"\nprofitable last month: {len(pr)} of {len(real)} real rules ({100 * len(pr) / len(real):.0f}%), "
        f"{len(pz)} of {len(rand)} random rules ({100 * len(pz) / len(rand):.0f}%)")
    say(f"real rules over 2020-2026: {sum(full.loc[r, 'net'] > 0 for r in real)} of {len(real)} profitable; "
        f"PF {full.loc[real, 'pf'].min():.2f} - {full.loc[real, 'pf'].max():.2f}")

    # 2. walk-forward: pick last month's best, trade it next month
    months = list(mon.columns)
    cnt = T.groupby(["rule", "mon"]).net.count().unstack(fill_value=0)
    say("\n2. THE '1 MONTH TEST' METHOD, out of sample: each month trade the rule(s) that made the most the month before")
    for label, pool in (("real rules only", real), ("real + random", rules)):
        for top in (1, 3):
            res, picks = [], []
            for j in range(1, len(months)):
                prev, cur = months[j - 1], months[j]
                cand = [r for r in pool if cnt.loc[r, prev] >= 30]
                if not cand:
                    continue
                best = sorted(cand, key=lambda r: mon.loc[r, prev], reverse=True)[:top]
                res.append((cur, np.mean([mon.loc[r, cur] for r in best])))
                picks.append(best[0])
            R = pd.Series(dict(res))
            tr = T[T.rule.isin(pool)]
            say(f"  {label:16s} best {top}: {len(R)} months, net {R.sum():+8.0f} $, months positive {(R > 0).sum()}/{len(R)}, "
                f"worst month {R.min():+.0f} $, by year " + " ".join(f"{y}:{R[[p.year == y for p in R.index]].sum():+.0f}" for y in range(2020, 2027)))
    rng = np.random.default_rng(5)
    rr = []
    for _ in range(200):
        tot = 0.0
        for j in range(1, len(months)):
            tot += mon.loc[real[rng.integers(len(real))], months[j]]
        rr.append(tot)
    say(f"  picking a random real rule each month (200 tries): median net {np.median(rr):+.0f} $, best {max(rr):+.0f} $")

    # 3. persistence
    say("\n3. DOES A GOOD MONTH REPEAT? (real rules, months with >= 30 trades)")
    a = b = c_ = e = 0
    for r in real:
        for j in range(1, len(months)):
            p, q = months[j - 1], months[j]
            if cnt.loc[r, p] < 30 or cnt.loc[r, q] < 30:
                continue
            if mon.loc[r, p] > 0:
                a += 1; b += mon.loc[r, q] > 0
            else:
                c_ += 1; e += mon.loc[r, q] > 0
    say(f"  after a profitable month: next month profitable {100 * b / max(a, 1):.0f}% of {a}")
    say(f"  after a losing month:     next month profitable {100 * e / max(c_, 1):.0f}% of {c_}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
