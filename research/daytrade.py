"""Round 11: classic day-trading systems on the broker's history, all 30 instruments (Mar 2020 - Oct 2026).

Day trades only: every position is opened and closed the same server day (no swap). Bars: M15 and H1 built from
the broker's M5 export; cost = the fill bar's median spread (MT5 export) once per trade, stress test 1.5x.
Rules fixed before the run (server time = Europe/Athens, like the charts):
  ASIA_BO   Asian-range breakout on every instrument (the London-breakout idea, scaled by the daily ATR): range
            03:00-08:00; trade only if it is 0.15-0.6 x D1 ATR(14); at 08:00 OCO stops 0.02 D1 ATR beyond it, SL at
            the other side, TP 2.5R, close at 21:00.
  WILL50 / WILL70  Larry Williams volatility breakout: from 01:30 OCO stops at today's open +- 0.5 (0.7) x
            yesterday's range, SL at today's open, no TP, orders until 20:00, close at 22:30.
  PDHL      Yesterday's high / low breakout: from 02:00 OCO stops at yesterday's high and low, SL at yesterday's
            middle, TP 2R, orders until 20:00, close at 22:30 (skipped when 02:00 is already outside).
  PIVOT     Floor-pivot breakout: from 02:00 OCO stops at R1 / S1 (SL at the pivot, TP at R2 / S2), until 20:00,
            close at 22:30 (skipped when 02:00 is already outside R1-S1).
  NY_CONT   New York continuation: at 15:30 trade the direction of 09:00-15:30 (London session move), SL 1.5 x
            ATR(H1), no TP, close at 22:00.
  TREND_PB  Trend pullback on H1: D1 close above EMA 20 above EMA 50 (long side; short mirrored); 09:00-18:00 an H1
            RSI(14) cross back above 40 (below 60) -> next open, SL 1.5 ATR(H1), TP 2R, one trade a day, close 22:30.
  RAND      chance baseline: one random entry a day 09:00-18:00, random side, SL 1.5 ATR(H1), TP 2R, close 22:30.
Pass rule per instrument (fixed in advance): >= 150 trades, PF >= 1.15, both halves >= 1.05, stress PF >= 1.05,
last 12 months positive.
"""
import os, sys, glob, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def say(s=""):
    print(s, flush=True)


def bars(d5, rule):
    r = d5.resample(rule, label="left", closed="left")
    B = pd.DataFrame({"o": r.o.first(), "h": r.h.max(), "l": r.l.min(), "c": r.c.last(), "s": r.s.median()}).dropna()
    B["hm"] = B.index.hour * 60 + B.index.minute
    B["date"] = B.index.normalize()
    c1 = B.c.shift()
    tr = np.maximum(B.h - B.l, np.maximum((B.h - c1).abs(), (B.l - c1).abs()))
    B["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    return B


def daily(d5):
    g = d5.groupby(d5.index.normalize())
    D = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    c1 = D.c.shift()
    D["tr"] = np.maximum(D.h - D.l, np.maximum((D.h - c1).abs(), (D.l - c1).abs()))
    D["atr"] = D.tr.rolling(14).mean().shift(1)                       # known before the day starts
    D["ph"], D["pl"], D["pc"] = D.h.shift(), D.l.shift(), D.c.shift()
    D["e20"] = D.c.ewm(span=20, adjust=False).mean().shift(1); D["e50"] = D.c.ewm(span=50, adjust=False).mean().shift(1)
    return D


def day_index(B):
    """per date: dict minute -> bar index (first bar at or after that minute)"""
    out = {}
    hm = B.hm.values; dates = B.date.values
    starts = np.r_[0, np.where(dates[1:] != dates[:-1])[0] + 1, len(B)]
    for a, b in zip(starts[:-1], starts[1:]):
        out[dates[a]] = (a, b, hm[a:b])
    return out


def at(entry, minute):
    a, b, hms = entry
    k = np.searchsorted(hms, minute)
    return a + k if k < len(hms) else None


def rules(B15, BH, D):
    o, h, l, c = (B15[x].values for x in ("o", "h", "l", "c"))
    hm = B15.hm.values; dates = B15.date.values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    flat2230 = (hm >= 1350) | newday; flat21 = (hm >= 1260) | newday; flat22 = (hm >= 1320) | newday
    DI = day_index(B15)
    R = {}
    sig = {k: [] for k in ("ASIA_BO", "WILL50", "WILL70", "PDHL", "PIVOT", "NY_CONT")}
    for dt, ent in DI.items():
        if dt not in D.index:
            continue
        dd = D.loc[dt]
        if not np.isfinite(dd.atr) or not np.isfinite(dd.ph):
            continue
        a, b, hms = ent
        i20 = at(ent, 1200); i20 = (i20 - 1) if i20 is not None else b - 1
        # ASIA_BO
        k8 = at(ent, 480)
        if k8 is not None and hm[k8] == 480:
            m = (hm[a:k8] >= 180)
            if m.sum() >= 12:
                H_, L_ = h[a:k8][m].max(), l[a:k8][m].min()
                rg = H_ - L_
                if 0.15 * dd.atr <= rg <= 0.6 * dd.atr:
                    bf = 0.02 * dd.atr
                    i21 = at(ent, 1260); i21 = (i21 - 1) if i21 is not None else b - 1
                    sig["ASIA_BO"].append(dict(k0=k8, kind="oco", dir=0, P=H_ + bf, sl=L_, P2=L_ - bf, sl2=H_, tp_r=2.5, exp=i21, maxb=10 ** 6))
        # WILLIAMS
        k130 = at(ent, 90)
        if k130 is not None:
            O = o[a]; prg = dd.ph - dd.pl
            for kk, nm in ((0.5, "WILL50"), (0.7, "WILL70")):
                up, dn = O + kk * prg, O - kk * prg
                if dn < o[k130] < up and prg > 0:
                    sig[nm].append(dict(k0=k130, kind="oco", dir=0, P=up, sl=O, P2=dn, sl2=O, tp=None, exp=i20, maxb=10 ** 6))
        # PDHL / PIVOT
        k2 = at(ent, 120)
        if k2 is not None:
            mid = (dd.ph + dd.pl) / 2
            if dd.pl < o[k2] < dd.ph:
                sig["PDHL"].append(dict(k0=k2, kind="oco", dir=0, P=dd.ph, sl=mid, P2=dd.pl, sl2=mid, tp_r=2.0, exp=i20, maxb=10 ** 6))
            P = (dd.ph + dd.pl + dd.pc) / 3; R1, S1 = 2 * P - dd.pl, 2 * P - dd.ph; R2, S2 = P + (dd.ph - dd.pl), P - (dd.ph - dd.pl)
            if S1 < o[k2] < R1 and R1 > P > S1:
                g = dict(k0=k2, kind="oco", dir=0, P=R1, sl=P, P2=S1, sl2=P, tp=None, exp=i20, maxb=10 ** 6)
                g["tp_b"], g["tp_s"] = R2, S2
                sig["PIVOT"].append(g)
        # NY_CONT
        k9, k1530 = at(ent, 540), at(ent, 930)
        if k9 is not None and k1530 is not None and hm[k1530] == 930 and k1530 > k9:
            mv = c[k1530 - 1] - o[k9]
            if mv != 0 and np.isfinite(B15.atr.values[k1530]):
                dr = 1 if mv > 0 else -1
                atr_h = 2 * B15.atr.values[k1530]                       # ~ATR(H1) from M15
                sig["NY_CONT"].append(dict(k0=k1530, kind="mkt", dir=dr, sl=o[k1530] - dr * 1.5 * atr_h, tp=None, exp=k1530, maxb=10 ** 6))
    for k in sig:
        R[k] = ("M15", sig[k], {"ASIA_BO": flat21, "NY_CONT": flat22}.get(k, flat2230))
    # H1 rules
    o1, h1, l1, c1 = (BH[x].values for x in ("o", "h", "l", "c"))
    hm1 = BH.hm.values; d1 = BH.date.values
    nd1 = np.r_[True, d1[1:] != d1[:-1]]
    flatH = (hm1 >= 1350) | nd1
    dl = np.diff(c1, prepend=c1[0])
    up = pd.Series(np.clip(dl, 0, None)).ewm(alpha=1 / 14, adjust=False).mean().values
    dn = pd.Series(np.clip(-dl, 0, None)).ewm(alpha=1 / 14, adjust=False).mean().values
    rsi = 100 - 100 / (1 + up / np.where(dn > 0, dn, np.nan))
    A1 = BH.atr.values
    trend = pd.Series(d1).map(lambda x: 1 if (x in D.index and D.loc[x, "pc"] > D.loc[x, "e20"] > D.loc[x, "e50"]) else
                              (-1 if (x in D.index and D.loc[x, "pc"] < D.loc[x, "e20"] < D.loc[x, "e50"]) else 0)).values
    tp_sig, rnd = [], []
    used = set()
    rng = np.random.default_rng(99)
    for i in range(50, len(BH) - 1):
        if not (540 <= hm1[i] < 1080) or not np.isfinite(A1[i]):
            continue
        dr = 0
        if trend[i] == 1 and rsi[i - 1] < 40 <= rsi[i]:
            dr = 1
        elif trend[i] == -1 and rsi[i - 1] > 60 >= rsi[i]:
            dr = -1
        if dr and d1[i] not in used:
            used.add(d1[i])
            tp_sig.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c1[i] - dr * 1.5 * A1[i], tp_r=2.0, exp=i + 1, maxb=10 ** 6))
    for dt in np.unique(d1):
        idx = np.where((d1 == dt) & (hm1 >= 540) & (hm1 < 1080))[0]
        if len(idx) < 3:
            continue
        i = int(rng.choice(idx))
        if i + 1 < len(BH) and np.isfinite(A1[i]):
            dr = 1 if rng.random() < 0.5 else -1
            rnd.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c1[i] - dr * 1.5 * A1[i], tp_r=2.0, exp=i + 1, maxb=10 ** 6))
    R["TREND_PB"] = ("H1", tp_sig, flatH)
    R["RAND"] = ("H1", rnd, flatH)
    return R


def sim_pivot(o, h, l, c, sp, sigs, flat):
    """PIVOT needs different TPs per side: run the two legs as one OCO with fixed TP by side."""
    out = []
    for g in sigs:
        res = SA.sim(o, h, l, c, sp, [dict(g, tp=None)], flat)
        if not res:
            continue
        k, dr, pnl, s_, risk, why = res[0]
        # re-run the filled side with its own TP
        side = dict(k0=g["k0"], kind="stop", dir=dr, P=g["P"] if dr == 1 else g["P2"], sl=g["sl"] if dr == 1 else g["sl2"],
                    tp=g["tp_b"] if dr == 1 else g["tp_s"], exp=g["exp"], maxb=10 ** 6)
        r2 = SA.sim(o, h, l, c, sp, [side], flat)
        out.extend(r2 if r2 else res)
    return out


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    files = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    rows, info = [], {}
    for f in files:
        base = os.path.basename(f)[:-4]
        if base not in meta:
            continue
        d5 = SA.load(f, meta[base]["point"])
        if len(d5) < 20000:
            continue
        B15, BH, D = bars(d5, "15min"), bars(d5, "1h"), daily(d5)
        usd = meta[base]["tick_value"] / meta[base]["tick_size"] * 0.01 if meta[base]["tick_size"] > 0 else 0.0
        info[base] = dict(days=D.index.nunique(), mid=d5.index[len(d5) // 2], end=d5.index[-1], usd=usd)
        for rule, (tf, sig, flat) in rules(B15, BH, D).items():
            B = B15 if tf == "M15" else BH
            arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
            res = sim_pivot(*arr, sig, flat) if rule == "PIVOT" else SA.sim(*arr, sig, flat)
            for (k, dr, pnl, s_, risk, why) in res:
                rows.append((base, rule, B.index[k], dr, pnl, s_, risk, why))
        say(f"  {base:7s} done, {time.time() - T0:5.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "rule", "t", "dir", "pnl", "sp", "risk", "why"])
    T["R"] = (T.pnl - T.sp) / T.risk; T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = (T.pnl - T.sp) * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [1 if t >= info[s]["mid"] else 0 for s, t in zip(T.sym, T.t)]
    T["last12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    T["year"] = T.t.dt.year
    pf, f2 = SA.pf, SA.f2
    say("\n== All instruments together (R units) ==")
    say("rule        trades  win%    PF  half1 half2 stress  avgR   syms PF>1  pass")
    passes = []
    for rule, g in T.groupby("rule", sort=False):
        per = []
        for s, x in g.groupby("sym"):
            P, P1, P2, PS = pf(x.R.values), pf(x[x.half == 0].R.values), pf(x[x.half == 1].R.values), pf(x.Rs.values)
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and x[x.last12].R.sum() > 0
            per.append(ok or False)
            if ok:
                yr = " ".join(f"{y % 100}:{f2(pf(x[x.year == y].R.values))}" for y in sorted(x.year.unique()))
                passes.append(f"{rule:9s} {s:7s} {len(x):5d} trades PF {f2(P)} halves {f2(P1)} {f2(P2)} stress {f2(PS)} "
                              f"net ${x.usd.sum():+.0f}/0.01 lot | {yr}")
        npos = sum(1 for s, x in g.groupby("sym") if pf(x.R.values) > 1)
        say(f"{rule:10s} {len(g):7d} {100 * (g.R > 0).mean():5.1f} {f2(pf(g.R.values))} {f2(pf(g[g.half == 0].R.values))} "
            f"{f2(pf(g[g.half == 1].R.values))} {f2(pf(g.Rs.values))} {g.R.mean():+5.3f}  {npos:3d}/{g.sym.nunique():2d}  {sum(per):3d}")
    say("\n== Per instrument PF(R) ==")
    rl = list(dict.fromkeys(T.rule))
    say("sym     " + " ".join(f"{r[:8]:>8s}" for r in rl))
    for s in sorted(info):
        say(f"{s:7s} " + " ".join(f"{f2(pf(T[(T.sym == s) & (T.rule == r)].R.values)):>8s}" for r in rl))
    say("\n== Passed (instrument x rule) ==")
    for p in passes:
        say("  " + p)
    nr = sum(1 for p in passes if p.startswith("RAND"))
    say(f"  {len(passes)} passed of {len(rl) * len(info)}; RAND (no edge by design) passed on {nr} of {len(info)} instruments")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
