"""Round 37 (5 Nov 2026): can a gold M1 SCALPER work if it only trades when the cost is small?

The owner wants a scalper: many trades, in and out fast ("aku nak scalper bro ... ciptakan untuku scalper").
Rounds 21-32 tested 130+ M1 rules at the account's full cost and all of them lost. One angle was never tried: a real
scalper does not trade all day, it trades when the cost is small relative to the move. The export carries the spread
of every single bar, so that can be tested exactly.

Candidate rules: the only M1 rules whose RAW (pre-cost) profit factor was above 1.0 in earlier rounds.
  SPK3/4/5 half   fade an M1 bar of 3 / 4 / 5 x ATR(14), target half the bar back, out after 15 min (raw PF 1.23)
  SPK4 1R         the same 4 ATR fade with a 1R target
  BB_RSI          close outside Bollinger(20,2) with RSI(7) beyond 20 / 80, target the middle band, SL 1.5 ATR
  WPR             Williams %R(14) crosses up through -80 (down through -20) on the EMA 200 side, SL 1.5 ATR, TP 2R
  STOCH           Stochastic(5,3,3) crosses out of 20 / 80 on the EMA 50 side, SL 1.5 ATR, TP 1R
  TK              Ichimoku Tenkan / Kijun cross beyond the cloud on M1, SL 2 ATR
  RAND            random entries (chance)
Cost filters, applied to the signal before it is taken:
  ALL             every signal
  SPR<=p25/p10    only when that bar's spread is in the cheapest 25% / 10% of all bars
  ATRx>=5/8/12    only when ATR(14, M1) is at least 5 / 8 / 12 times that bar's spread (the move must dwarf the cost)
  LDNNY           only 10:00-19:00 server (London and the New York overlap, where gold's spread is tightest)
  ATRx>=8+LDNNY   both
For every cell: the profit factor at the account's real spread, then at fixed costs of $0.15 / $0.10 / $0.07 / $0.05
per trade, the average RAW profit per trade, and the break-even cost, meaning the most a trade could cost and still
reach PF 1.15. That last number is the answer to "what account would make this work".
0.01 lot throughout, so every figure is in dollars.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
pf = SA.pf


def build(B, I, atr):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    hm = B.hm.values
    ok = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & np.isfinite(I["e200"]) & (np.arange(n) >= 300)
    ok[-2:] = False
    S = {}
    rg = h - l

    def add(name, i, dr, sl, **kw):
        if (sl - c[i]) * dr >= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=kw.pop("maxb", 60))
        g.update(kw)
        S.setdefault(name, []).append(g)

    for k in (3, 4, 5):
        for i in np.where(ok & (rg >= k * atr) & (c != o))[0]:
            dr = -1 if c[i] > o[i] else 1
            sl = (h[i] + 0.2 * atr[i]) if dr == -1 else (l[i] - 0.2 * atr[i])
            add(f"SPK{k} half", i, dr, sl, tp=c[i] + dr * 0.5 * rg[i], maxb=15)
            if k == 4:
                add("SPK4 1R", i, dr, sl, tp_r=1.0, maxb=15)
    r7 = I["rsi7"] if "rsi7" in I else None
    if r7 is None:                                                     # ind23 builds rsi(14); make RSI(7) here
        d_ = np.diff(c, prepend=c[0])
        r7 = 100 - 100 / (1 + R.wilder(np.clip(d_, 0, None), 7) / np.maximum(R.wilder(np.clip(-d_, 0, None), 7), 1e-12))
    for i in np.where(ok & (c < I["bbl"]) & (r7 < 20))[0]:
        add("BB_RSI", i, 1, c[i] - 1.5 * atr[i], tp=I["bbm"][i], maxb=30)
    for i in np.where(ok & (c > I["bbu"]) & (r7 > 80))[0]:
        add("BB_RSI", i, -1, c[i] + 1.5 * atr[i], tp=I["bbm"][i], maxb=30)
    w = I["wpr"]
    cu = R.cross_up
    for i in np.where(ok & cu(w, np.full(n, -80.0)) & (c > I["e200"]))[0]:
        add("WPR", i, 1, c[i] - 1.5 * atr[i], tp_r=2.0)
    for i in np.where(ok & cu(np.full(n, -20.0), w) & (c < I["e200"]))[0]:
        add("WPR", i, -1, c[i] + 1.5 * atr[i], tp_r=2.0)
    K, D = I["k"], I["d"]
    K1 = np.r_[np.nan, K[:-1]]
    for i in np.where(ok & cu(K, D) & (K1 < 20) & (c > I["e50"]))[0]:
        add("STOCH", i, 1, c[i] - 1.5 * atr[i], tp_r=1.0, maxb=30)
    for i in np.where(ok & cu(D, K) & (K1 > 80) & (c < I["e50"]))[0]:
        add("STOCH", i, -1, c[i] + 1.5 * atr[i], tp_r=1.0, maxb=30)
    top, bot, ten, kij = I["ctop"], I["cbot"], I["ten"], I["kij"]
    tu, td = cu(ten, kij), cu(kij, ten)
    kxl, kxs = c < top, c > bot
    for i in np.where(ok & tu & (c > top))[0]:
        add("TK", i, 1, c[i] - 2 * atr[i], xl=td, xs=tu)
    for i in np.where(ok & td & (c < bot))[0]:
        add("TK", i, -1, c[i] + 2 * atr[i], xl=td, xs=tu)
    rg_ = np.random.default_rng(37)
    for i in np.where(ok & (rg_.random(n) < 1 / 30))[0]:
        dr = 1 if rg_.random() < 0.5 else -1
        add("RAND", i, dr, c[i] - dr * 1.5 * atr[i], tp_r=1.5)
    return S


def breakeven(raw, target=1.15):
    """the largest cost per trade at which PF still reaches `target`"""
    lo, hi = 0.0, max(float(np.max(raw)), 1.0)
    for _ in range(40):
        mid = (lo + hi) / 2
        if pf(raw - mid) >= target:
            lo = mid
        else:
            hi = mid
    return lo


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    dates = B.date.values
    flat = (B.hm.values >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    I = R.ind(B)
    atr = I["atr"]
    spr = B.s.values * usd
    days = B.index.normalize().nunique()
    hm = B.hm.values
    q10, q25, q50 = np.percentile(spr[spr > 0], [10, 25, 50])
    say = lambda s="": print(s, flush=True)
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {len(B):,} bars. Spread per 0.01 lot: "
        f"median ${q50:.2f}, cheapest 25% <= ${q25:.2f}, cheapest 10% <= ${q10:.2f}")
    say(f"Spread by server hour: " + " ".join(f"{hh:02d}h ${np.median(spr[(hm // 60 == hh) & (spr > 0)]):.2f}" for hh in range(1, 23, 3)))
    S = build(B, I, atr)
    say(f"\nsignals built in {time.time() - T0:.0f} s: " + ", ".join(f"{k} {len(v)}" for k, v in S.items()))
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    FILTERS = {
        "ALL": np.ones(len(B), bool),
        "SPR<=p25": spr <= q25,
        "SPR<=p10": spr <= q10,
        "ATRx>=5": atr >= 5 * spr,
        "ATRx>=8": atr >= 8 * spr,
        "ATRx>=12": atr >= 12 * spr,
        "LDNNY": (hm >= 600) & (hm < 1140),
        "ATRx>=8+LDNNY": (atr >= 8 * spr) & (hm >= 600) & (hm < 1140),
    }
    say("\nrule        filter         trades /day | PF at the real spread | PF if a trade cost $0.15 $0.10 $0.07 $0.05 | "
        "raw $/trade | break-even cost for PF 1.15")
    hits = []
    for rule, sg in S.items():
        for fname, mask in FILTERS.items():
            sel = [g for g in sg if mask[g["k0"] - 1]]
            if len(sel) < 150:
                continue
            tr = SA.sim(*arr, sorted(sel, key=lambda g: g["k0"]), flat)
            if len(tr) < 150:
                continue
            T = pd.DataFrame(tr, columns=["k", "dir", "pnl", "sp", "risk", "why"])
            T["t"] = B.index[T.k.values]
            raw = (T.pnl * usd).values
            cost = (T.sp * usd).values
            real = raw - cost
            mid = T.t.iloc[len(T) // 2]
            P = pf(real)
            be = breakeven(raw)
            ok = (P >= 1.15 and pf(real[(T.t < mid).values]) >= 1.05 and pf(real[(T.t >= mid).values]) >= 1.05
                  and pf(raw - 1.5 * cost) >= 1.05)
            say(f"{rule:11s} {fname:14s} {len(T):6d} {len(T) / days:5.2f} | {SA.f2(P)} {'PASS' if ok else '    '} | "
                f"{SA.f2(pf(raw - 0.15))} {SA.f2(pf(raw - 0.10))} {SA.f2(pf(raw - 0.07))} {SA.f2(pf(raw - 0.05))} | "
                f"{raw.mean():+10.4f} | ${be:.3f}  (mean cost paid ${cost.mean():.2f})")
            hits.append((rule, fname, P, be, raw.mean(), len(T)))
    say("\nThe most a trade may cost, for the best cells (PF 1.15 target):")
    for rule, fname, P, be, mu, ntr in sorted(hits, key=lambda x: -x[3])[:8]:
        say(f"  {rule:11s} {fname:14s} {ntr:6d} trades, raw {mu:+.4f} $/trade, break-even cost ${be:.3f} "
            f"-> needs a spread under about {be / 1.0:.2f} $ per 0.01 lot")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
