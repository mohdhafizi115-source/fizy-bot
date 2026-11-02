"""Round 19 (2 Nov 2026): technical families never tested in this project, M15 and H1, 12 instruments incl. gold.

The owner wants a gold trade every day and asked for more techniques ("banyak lagi teknikal lain"). New families,
rules fixed before the run (server time; M15 day trades flat 23:00, H1 at most 48 bars, swap not counted):
  ICHI_TK    Ichimoku (9, 26, 52): Tenkan crosses Kijun with the close beyond the cloud and the close beyond the close
             26 bars ago (Chikou); SL 0.5 ATR beyond the Kijun (at least 1 ATR); exit when Tenkan crosses back
  ICHI_KUMO  close breaks out of the cloud with Tenkan on the same side of Kijun; SL 0.2 ATR beyond the far cloud
             edge (at least 0.5 ATR); exit on a close back inside the cloud
  DIV_RSI    regular divergence on 5-bar fractal swings: a lower low with a higher RSI(14) low, the second RSI low
             < 40 (bearish mirrored, > 60), swings at most 30 bars apart; next open; SL 0.1 ATR beyond the swing; TP 2R
  DIV_MACD   the same with the MACD (12, 26, 9) histogram (second low below zero)
  ENGULF     bullish engulfing (body >= 0.5 ATR) whose low touched the EMA 20 in an uptrend (close > EMA 50 > EMA 200);
             next open; SL 0.1 ATR below its low; TP 2R (bearish mirrored)
  PINBAR     hammer (lower wick >= 2x body, upper wick <= body, range >= 0.8 ATR) that dipped through the EMA 20 and
             closed above it in an uptrend; SL 0.1 ATR below; TP 2R (shooting star mirrored)
  GARTLEY    harmonic XABCD on fractal swings: AB 0.568-0.668 of XA, BC 0.382-0.886 of AB, D = 0.786 XA; limit at D,
             SL 0.1 ATR beyond X, TP at C (at least 1R), valid 48 bars (research/quasimodo.py fill rules)
  BAT        the same with AB 0.382-0.50 and D = 0.886 XA
  FAKE_HARM  control: the Gartley and Bat setups moved 0.5 ATR at random (limit-fill effects)
  RAND       random market entries at about one a day, SL 1.5 ATR, TP 2R
Usual pass rule per instrument and timeframe; harmonics must also beat FAKE_HARM by 0.10 PF.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import quasimodo as QM

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP", "BTCUSD"]
TFS = [("M15", "15min"), ("H1", "1h")]
RULES = ["ICHI_TK", "ICHI_KUMO", "DIV_RSI", "DIV_MACD", "ENGULF", "PINBAR", "GARTLEY", "BAT", "FAKE_HARM", "RAND"]
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def swings(h, l):
    """alternating fractal swings: list of (type, price, bar, confirm bar)"""
    sw = []
    n = len(h)
    for k in range(4, n):
        i = k - 2
        for typ, cond, px in (("H", h[i] > max(h[i - 2], h[i - 1], h[i + 1], h[i + 2]), h[i]),
                              ("L", l[i] < min(l[i - 2], l[i - 1], l[i + 1], l[i + 2]), l[i])):
            if not cond:
                continue
            if sw and sw[-1][0] == typ:
                if (typ == "H" and px > sw[-1][1]) or (typ == "L" and px < sw[-1][1]):
                    sw[-1] = (typ, px, i, k)
            else:
                sw.append((typ, px, i, k))
    return sw


def build(B, maxb, rng):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    A = B.atr.values
    hm = B.hm.values
    n = len(B)
    ok = (hm >= 90) & (hm < 1320) & np.isfinite(A)
    C = B.c
    hh = lambda k: B.h.rolling(k).max()
    ll = lambda k: B.l.rolling(k).min()
    ten = ((hh(9) + ll(9)) / 2).values
    kij = ((hh(26) + ll(26)) / 2).values
    sa = ((pd.Series(ten) + pd.Series(kij)) / 2).shift(26).values
    sb = ((hh(52) + ll(52)) / 2).shift(26).values
    ctop, cbot = np.fmax(sa, sb), np.fmin(sa, sb)
    e20, e50, e200 = ema(C, 20).values, ema(C, 50).values, ema(C, 200).values
    d = C.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    macd = ema(C, 12) - ema(C, 26)
    hist = (macd - ema(macd, 9)).values
    S = {r: [] for r in RULES}
    xl_tk, xs_tk = ten < kij, ten > kij
    xl_ku, xs_ku = c < ctop, c > cbot

    def mk(rule, i, dr, sl, **kw):
        if (c[i] - sl) * dr <= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=maxb)
        g.update(kw)
        S[rule].append(g)

    for i in range(60, n - 2):
        if not ok[i]:
            continue
        a = A[i]
        # Ichimoku TK cross
        if np.isfinite(ctop[i]):
            if ten[i] > kij[i] and ten[i - 1] <= kij[i - 1] and c[i] > ctop[i] and c[i] > c[i - 26]:
                mk("ICHI_TK", i, 1, min(kij[i] - 0.5 * a, c[i] - a), tp=None, xl=xl_tk, xs=xs_tk)
            if ten[i] < kij[i] and ten[i - 1] >= kij[i - 1] and c[i] < cbot[i] and c[i] < c[i - 26]:
                mk("ICHI_TK", i, -1, max(kij[i] + 0.5 * a, c[i] + a), tp=None, xl=xl_tk, xs=xs_tk)
            # Kumo breakout
            if c[i] > ctop[i] and c[i - 1] <= ctop[i - 1] and ten[i] > kij[i]:
                mk("ICHI_KUMO", i, 1, min(cbot[i] - 0.2 * a, c[i] - 0.5 * a), tp=None, xl=xl_ku, xs=xs_ku)
            if c[i] < cbot[i] and c[i - 1] >= cbot[i - 1] and ten[i] < kij[i]:
                mk("ICHI_KUMO", i, -1, max(ctop[i] + 0.2 * a, c[i] + 0.5 * a), tp=None, xl=xl_ku, xs=xs_ku)
        # engulfing / pin bar at the EMA 20 in a trend
        body = abs(c[i] - o[i])
        upt, dnt = c[i] > e50[i] > e200[i], c[i] < e50[i] < e200[i]
        if upt and c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body >= 0.5 * a and l[i] <= e20[i]:
            mk("ENGULF", i, 1, l[i] - 0.1 * a, tp_r=2.0)
        if dnt and c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1] and body >= 0.5 * a and h[i] >= e20[i]:
            mk("ENGULF", i, -1, h[i] + 0.1 * a, tp_r=2.0)
        rg = h[i] - l[i]
        lw, uw = min(o[i], c[i]) - l[i], h[i] - max(o[i], c[i])
        if upt and rg >= 0.8 * a and lw >= 2 * body and uw <= body and l[i] < e20[i] < c[i]:
            mk("PINBAR", i, 1, l[i] - 0.1 * a, tp_r=2.0)
        if dnt and rg >= 0.8 * a and uw >= 2 * body and lw <= body and h[i] > e20[i] > c[i]:
            mk("PINBAR", i, -1, h[i] + 0.1 * a, tp_r=2.0)
    # divergences and harmonics on fractal swings
    sw = swings(h, l)
    lows = [s for s in sw if s[0] == "L"]
    highs = [s for s in sw if s[0] == "H"]
    for grp, dr in ((lows, 1), (highs, -1)):
        for p, q in zip(grp[:-1], grp[1:]):
            k = q[3]
            if k + 1 >= n or not ok[k] or q[2] - p[2] > 30:
                continue
            a = A[k]
            if dr == 1 and q[1] < p[1]:
                if rsi[q[2]] > rsi[p[2]] and rsi[q[2]] < 40:
                    mk("DIV_RSI", k, 1, q[1] - 0.1 * a, tp_r=2.0)
                if hist[q[2]] > hist[p[2]] and hist[q[2]] < 0:
                    mk("DIV_MACD", k, 1, q[1] - 0.1 * a, tp_r=2.0)
            if dr == -1 and q[1] > p[1]:
                if rsi[q[2]] < rsi[p[2]] and rsi[q[2]] > 60:
                    mk("DIV_RSI", k, -1, q[1] + 0.1 * a, tp_r=2.0)
                if hist[q[2]] < hist[p[2]] and hist[q[2]] > 0:
                    mk("DIV_MACD", k, -1, q[1] + 0.1 * a, tp_r=2.0)
    harm = {"GARTLEY": [], "BAT": []}
    for j in range(3, len(sw)):
        X, Aa, Bb, Cc = sw[j - 3], sw[j - 2], sw[j - 1], sw[j]
        k = Cc[3]
        if k + 1 >= n or not ok[k]:
            continue
        dr = 1 if X[0] == "L" else -1                 # bullish: X low, A high, B low, C high, D low
        xa = (Aa[1] - X[1]) * dr
        if xa <= 0:
            continue
        ab = (Aa[1] - Bb[1]) * dr / xa
        abl = (Aa[1] - Bb[1]) * dr
        if abl <= 0:
            continue
        bc = (Cc[1] - Bb[1]) * dr / abl
        if not (0.382 <= bc <= 0.886) or (Cc[1] - Aa[1]) * dr >= 0:
            continue
        for nm, lo, hi_, r in (("GARTLEY", 0.568, 0.668, 0.786), ("BAT", 0.382, 0.50, 0.886)):
            if lo <= ab <= hi_:
                D = Aa[1] - dr * r * xa
                harm[nm].append((k, dr, D, X[1], Cc[1]))   # (bar, side, entry, SL reference, target)
    return S, harm


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    rows, info = [], {}
    rng = np.random.default_rng(19)
    for sym in SYMS:
        f = os.path.join(DATA, sym + ".csv")
        if sym not in meta or not os.path.exists(f):
            continue
        d5 = SA.load(f, meta[sym]["point"])
        info[sym] = dict(mid=d5.index[len(d5) // 2], end=d5.index[-1], days=d5.index.normalize().nunique(),
                         usd=meta[sym]["tick_value"] / meta[sym]["tick_size"] * 0.01 if meta[sym]["tick_size"] > 0 else 0.0)
        for tf, rule in TFS:
            B = DT.bars(d5, rule)
            dates = B.date.values
            newday = np.r_[True, dates[1:] != dates[:-1]]
            flat = ((B.hm.values >= 1380) | newday) if tf == "M15" else np.zeros(len(B), bool)
            maxb = 10 ** 6 if tf == "M15" else 48
            S, harm = build(B, maxb, rng)
            arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
            A = B.atr.values
            res = {}
            for r in ("ICHI_TK", "ICHI_KUMO", "DIV_RSI", "DIV_MACD", "ENGULF", "PINBAR"):
                res[r] = SA.sim(*arr, sorted(S[r], key=lambda g: g["k0"]), flat)
            fake = []
            for nm in ("GARTLEY", "BAT"):
                res[nm] = QM.sim_limit(B, harm[nm], A, flat, "BOS", maxb)
                sh = rng.choice([-0.5, 0.5], size=len(harm[nm]))
                fake += [(k, dr, e + x * A[k], s + x * A[k], t + x * A[k]) for (k, dr, e, s, t), x in zip(harm[nm], sh)]
            res["FAKE_HARM"] = QM.sim_limit(B, sorted(fake), A, flat, "BOS", maxb)
            hm = B.hm.values
            cand = np.where((hm >= 90) & (hm < 1320) & np.isfinite(A))[0]
            cand = cand[cand < len(B) - 2]
            pick = np.sort(rng.choice(cand, size=min(len(cand), info[sym]["days"]), replace=False))
            sig = []
            for i in pick:
                dr = 1 if rng.random() < 0.5 else -1
                sig.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=B.c.values[i] - dr * 1.5 * A[i], tp_r=2.0, exp=i + 1, maxb=maxb))
            res["RAND"] = SA.sim(*arr, sig, flat)
            for r, rr in res.items():
                for (k, dr, pnl, s_, risk, why) in rr:
                    rows.append((sym, tf, r, B.index[k], pnl, s_, risk))
        say(f"  {sym:7s} done, {time.time() - T0:5.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "tf", "rule", "t", "pnl", "sp", "risk"])
    T["R"] = (T.pnl - T.sp) / T.risk
    T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = (T.pnl - T.sp) * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [t >= info[s]["mid"] for s, t in zip(T.sym, T.t)]
    T["l12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    pf, f2 = SA.pf, SA.f2
    say("\n== All instruments together (R after spread) ==")
    say("tf   rule        trades /sym/day  win%    PF  half1 half2 stress  syms PF>1  pass")
    passes = []
    for tf, _ in TFS:
        for r in RULES:
            g = T[(T.tf == tf) & (T.rule == r)]
            if g.empty:
                say(f"{tf:4s} {r:10s} no trades"); continue
            npass = 0
            for s, x in g.groupby("sym"):
                P, P1, P2, PS = pf(x.R.values), pf(x[~x.half].R.values), pf(x[x.half].R.values), pf(x.Rs.values)
                ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and x[x.l12].R.sum() > 0
                if ok and r in ("GARTLEY", "BAT"):
                    fk = T[(T.tf == tf) & (T.rule == "FAKE_HARM") & (T.sym == s)]
                    ok = len(fk) > 0 and P - pf(fk.R.values) >= 0.10
                if ok:
                    npass += 1
                    passes.append(f"{tf:3s} {r:9s} {s:7s} {len(x):5d} trades ({len(x) / info[s]['days']:.2f}/day) PF {f2(P)} halves {f2(P1)} {f2(P2)} "
                                  f"stress {f2(PS)} net ${x.usd.sum():+.0f}/0.01 lot")
            days = np.mean([info[s]["days"] for s in g.sym.unique()])
            npos = sum(1 for s, x in g.groupby("sym") if pf(x.R.values) > 1)
            say(f"{tf:4s} {r:10s} {len(g):7d} {len(g) / days / g.sym.nunique():7.2f} {100 * (g.R > 0).mean():5.1f} {f2(pf(g.R.values))} "
                f"{f2(pf(g[~g.half].R.values))} {f2(pf(g[g.half].R.values))} {f2(pf(g.Rs.values))} {npos:3d}/{g.sym.nunique():2d}  {npass:3d}")
    say("\n== Gold (XAUUSD) ==")
    for tf, _ in TFS:
        for r in RULES:
            x = T[(T.sym == "XAUUSD") & (T.tf == tf) & (T.rule == r)]
            if len(x):
                say(f"  {tf:3s} {r:10s} {len(x):5d} trades ({len(x) / info['XAUUSD']['days']:.2f}/day) win {100 * (x.R > 0).mean():4.1f}% "
                    f"PF {f2(pf(x.R.values))} halves {f2(pf(x[~x.half].R.values))} {f2(pf(x[x.half].R.values))} "
                    f"last12 {x[x.l12].R.sum():+.1f}R net ${x.usd.sum():+.0f}/0.01 lot")
    say("\n== Per instrument PF (R) ==")
    for tf, _ in TFS:
        say(f"  {tf}: sym     " + " ".join(f"{r[:9]:>9s}" for r in RULES))
        for s in SYMS:
            if s in info:
                say(f"       {s:7s} " + " ".join(f"{f2(pf(T[(T.sym == s) & (T.tf == tf) & (T.rule == r)].R.values)):>9s}" for r in RULES))
    say("\n== Passed ==")
    for p in passes:
        say("  " + p)
    nr = sum(1 for p in passes if " RAND " in p or "FAKE_HARM" in p)
    say(f"  {len(passes) - nr} passes of {8 * len(TFS) * len(info)} real rule tests; controls (RAND / FAKE_HARM) passed {nr} of {2 * len(TFS) * len(info)}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
