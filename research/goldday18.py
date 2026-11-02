"""Round 18 (2 Nov 2026): more daily gold day trades from the family that works (breakouts after compression).

The owner asked again for another daily gold scalp ("carikan aku gold scalping untuk harian yang lain lagi"). Gold's
tested edges are London breakout with a squeeze, NR7 D1 and the Williams breakout, all breakouts after quiet
periods. New rules from that family, fixed before the run (server time, day trades closed by 22:30, no swap):
  NYBO       New York breakout of the London range: range 10:00-15:00; at 15:30 OCO stops 0.02 D1 ATR beyond it,
             SL at the other side, TP 2R, orders until 20:00 (skipped if 15:30 is already outside)
  NYBO_SQ    the same, only when the London range < 0.6 x D1 ATR (the squeeze idea of the live London breakout)
  ID_D1      yesterday was an inside day (high below and low above the day before): from 01:30 OCO stops at
             yesterday's high / low, SL at the other side, no TP, orders until 20:00
  ID_NONR7   ID_D1 without the days that are also NR7 (those are traded by the live NR7 module)
  NR4_D1     yesterday's range was the narrowest of the last 4 days: the same orders
  NR4ID      NR4 and inside day together (Crabel): the same orders
  ASIA_EARLY early Asian range 01:30-04:00 (0.10-0.50 D1 ATR): at 04:00 OCO stops 0.02 ATR beyond it, SL at the other
             side, TP 2R, orders until 08:00, close 10:00
  BIG_FOLLOW / BIG_FADE  yesterday's range > 1.8 x D1 ATR: at 01:30 follow / fade yesterday's candle, SL 0.5 D1 ATR,
             TP 1R
  RAND       one random M15 entry a day 09:00-18:00, random side, SL 1.5 ATR(H1), TP 2R (chance baseline)
Checked on XAUUSD and, as a family check, on USDJPY / EURJPY / GBPJPY (where gold's breakouts also work).
Usual pass rule per instrument.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYMS = ["XAUUSD", "USDJPY", "EURJPY", "GBPJPY"]
RULES = ["NYBO", "NYBO_SQ", "ID_D1", "ID_NONR7", "NR4_D1", "NR4ID", "ASIA_EARLY", "BIG_FOLLOW", "BIG_FADE", "RAND"]
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def rules(B, D, seed):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    hm = B.hm.values
    dates = B.date.values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    flat2230 = (hm >= 1350) | newday
    flat10 = (hm >= 600) | newday
    DI = DT.day_index(B)
    # daily flags known before the day starts
    Dh, Dl, Dc, Do = D.h, D.l, D.c, D.o
    rng_ = Dh - Dl
    inside = (Dh < Dh.shift(1)) & (Dl > Dl.shift(1))
    nr4 = rng_ < rng_.shift(1).rolling(3).min()
    nr7 = rng_ < rng_.shift(1).rolling(6).min()
    big = rng_ > 1.8 * D.atr
    F = pd.DataFrame({"inside": inside.shift(1), "nr4": nr4.shift(1), "nr7": nr7.shift(1), "big": big.shift(1),
                      "pdir": np.sign(Dc - Do).shift(1)}, index=D.index)
    S = {r: [] for r in RULES}
    flats = {r: flat2230 for r in RULES}
    flats["ASIA_EARLY"] = flat10
    r = np.random.default_rng(seed)
    for dt, ent in DI.items():
        if dt not in D.index:
            continue
        dd, ff = D.loc[dt], F.loc[dt]
        if not np.isfinite(dd.atr) or not np.isfinite(dd.ph):
            continue
        a, b, hms = ent
        atr = dd.atr
        i20 = DT.at(ent, 1200); i20 = (i20 - 1) if i20 is not None else b - 1
        # NY breakout of the London range
        k1530 = DT.at(ent, 930)
        if k1530 is not None and hm[k1530] == 930:
            m = (hm[a:k1530] >= 600) & (hm[a:k1530] < 900)
            if m.sum() >= 16:
                H_, L_ = h[a:k1530][m].max(), l[a:k1530][m].min()
                rg = H_ - L_
                if rg >= 0.15 * atr and L_ < o[k1530] < H_:
                    bf = 0.02 * atr
                    g = dict(k0=k1530, kind="oco", dir=0, P=H_ + bf, sl=L_, P2=L_ - bf, sl2=H_, tp_r=2.0, exp=i20, maxb=10 ** 6)
                    S["NYBO"].append(g)
                    if rg < 0.6 * atr:
                        S["NYBO_SQ"].append(dict(g))
        # inside day / NR4 / NR4ID: yesterday's high / low from 01:30
        k130 = DT.at(ent, 90)
        if k130 is not None and dd.pl < o[k130] < dd.ph:
            g = dict(k0=k130, kind="oco", dir=0, P=dd.ph, sl=dd.pl, P2=dd.pl, sl2=dd.ph, tp=None, exp=i20, maxb=10 ** 6)
            if ff.inside is True or ff.inside == 1.0:
                S["ID_D1"].append(dict(g))
                if not (ff.nr7 is True or ff.nr7 == 1.0):          # the live NR7 module already trades NR7 days
                    S["ID_NONR7"].append(dict(g))
            if ff.nr4 is True or ff.nr4 == 1.0:
                S["NR4_D1"].append(dict(g))
                if ff.inside is True or ff.inside == 1.0:
                    S["NR4ID"].append(dict(g))
        # early Asian range breakout
        k4 = DT.at(ent, 240)
        if k4 is not None and hm[k4] == 240:
            m = hm[a:k4] >= 90
            if m.sum() >= 8:
                H_, L_ = h[a:k4][m].max(), l[a:k4][m].min()
                rg = H_ - L_
                if 0.10 * atr <= rg <= 0.50 * atr and L_ < o[k4] < H_:
                    k8 = DT.at(ent, 480); k8 = (k8 - 1) if k8 is not None else b - 1
                    bf = 0.02 * atr
                    S["ASIA_EARLY"].append(dict(k0=k4, kind="oco", dir=0, P=H_ + bf, sl=L_, P2=L_ - bf, sl2=H_, tp_r=2.0, exp=k8, maxb=10 ** 6))
        # day after a big day
        if k130 is not None and (ff.big is True or ff.big == 1.0) and ff.pdir != 0 and np.isfinite(ff.pdir):
            for nm, sd in (("BIG_FOLLOW", 1), ("BIG_FADE", -1)):
                dr = int(sd * ff.pdir)
                S[nm].append(dict(k0=k130, kind="mkt", dir=dr, sl=o[k130] - dr * 0.5 * atr, tp_r=1.0, exp=k130, maxb=10 ** 6))
        # random
        idx = np.arange(a, b)[(hms >= 540) & (hms < 1080)]
        if len(idx) > 3:
            i = int(r.choice(idx))
            if i + 1 < len(B) and np.isfinite(B.atr.values[i]):
                dr = 1 if r.random() < 0.5 else -1
                S["RAND"].append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c[i] - dr * 1.5 * 2 * B.atr.values[i], tp_r=2.0, exp=i + 1, maxb=10 ** 6))
    return S, flats


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    rows, info = [], {}
    for n_, sym in enumerate(SYMS):
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")):
            continue
        d5 = SA.load(os.path.join(DATA, sym + ".csv"), meta[sym]["point"])
        B, D = DT.bars(d5, "15min"), DT.daily(d5)
        info[sym] = dict(days=D.index.nunique(), mid=d5.index[len(d5) // 2], end=d5.index[-1],
                         usd=meta[sym]["tick_value"] / meta[sym]["tick_size"] * 0.01 if meta[sym]["tick_size"] > 0 else 0.0)
        S, flats = rules(B, D, 31 + n_)
        arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
        for rule in RULES:
            for (k, dr, pnl, s_, risk, why) in SA.sim(*arr, sorted(S[rule], key=lambda g: g["k0"]), flats[rule]):
                rows.append((sym, rule, B.index[k], dr, pnl, s_, risk))
        say(f"  {sym} done, {time.time() - T0:.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "rule", "t", "dir", "pnl", "sp", "risk"])
    T["R"] = (T.pnl - T.sp) / T.risk
    T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = (T.pnl - T.sp) * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [t >= info[s]["mid"] for s, t in zip(T.sym, T.t)]
    T["l12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    T["year"] = T.t.dt.year
    pf, f2 = SA.pf, SA.f2
    say("\nrule        sym     trades /day  win%    PF  half1 half2 stress  last12R   net$(0.01)  by year")
    passes = []
    for rule in RULES:
        for sym in [s_ for s_ in SYMS if s_ in info]:
            x = T[(T.rule == rule) & (T.sym == sym)]
            if x.empty:
                say(f"{rule:11s} {sym:7s} no trades"); continue
            P, P1, P2, PS = pf(x.R.values), pf(x[~x.half].R.values), pf(x[x.half].R.values), pf(x.Rs.values)
            l12 = x[x.l12].R.sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
            yr = " ".join(f"{y % 100}:{f2(pf(x[x.year == y].R.values)).strip()}" for y in sorted(x.year.unique()))
            say(f"{rule:11s} {sym:7s} {len(x):6d} {len(x) / info[sym]['days']:5.2f} {100 * (x.R > 0).mean():5.1f} {f2(P)} {f2(P1)} {f2(P2)} "
                f"{f2(PS)} {l12:+8.1f} {x.usd.sum():+10.0f}  {yr} {'PASS' if ok else ''}")
            if ok:
                passes.append((rule, sym))
    say(f"\nPASSED: {', '.join(f'{r} {s}' for r, s in passes) if passes else 'none'}")
    nr = sum(1 for r, s in passes if r == "RAND")
    say(f"{len(passes) - nr} rule passes of {(len(RULES) - 1) * len(SYMS)}; RAND passed on {nr} of {len(SYMS)}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
