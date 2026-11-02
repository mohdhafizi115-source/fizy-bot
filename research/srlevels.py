"""Gold M15: which support / resistance LEVELS with a real reason hold up on 6.6 years of broker data?

The owner wants only zones that pass a test and have a reason ("bukan main tembak marking zone"). Swing-cluster zones
failed (research/srzones.py, PF 0.83-1.01). This tests reference levels that traders and dealers actually watch:
  PDH / PDL / PDC   previous server day's high / low / close
  PWH / PWL         previous week's high / low
  PMH / PML         previous month's high / low
  DO / WO           today's / this week's opening price
  ASH / ASL         Asian range high / low (03:00-08:00 server, known from 08:00)
  PP / R1 / S1      floor pivots from the previous day
  RN50              round numbers (multiples of $50; the nearest one above and below the price)
Event: the first touch of a level in a server day (01:30-22:00) after the price has closed at least 1 ATR(M15) away
from it since the level became known. Coming from above = support test, from below = resistance test.
Control: FAKE levels = each real level moved by 0.5 x the previous D1 ATR(14), random side per level and day (round
numbers: the nearest $x25 / $x75 level instead of $x00 / $x50). A real level must beat its fake twin, not just be profitable.
Rules (fixed before the run; costs = the M15 bar's median spread; flat 23:00 server, max 24 bars):
  HOLD%        no costs: from the touch, does the price go 1 ATR back (level held) before 1 ATR through? 50% = chance
  LIMIT        limit order at the level (fade): SL 1 ATR beyond, TP 2 ATR (2R)
  LIMIT_TREND  the same, only with the H1 EMA 50 / 200 trend
  REJECT       within 4 bars a close back on the fade side -> next open; SL beyond the extreme + 0.3 ATR, TP 2R
  BREAK        within 8 bars a close 0.3 ATR through the level -> follow at the next open; SL 0.5 ATR back on the
               other side of the level, TP 2R
Pass rule (CLAUDE.md): >= 150 trades, PF >= 1.15, both halves >= 1.05, stress 1.5x spread >= 1.05, last 12 months
positive, and PF at least 0.10 above the same rule on the fake levels.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import srzones as SZ

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYM = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
T0 = time.time()
TYPES = ["PDH", "PDL", "PDC", "PWH", "PWL", "PMH", "PML", "DO", "WO", "ASH", "ASL", "PP", "R1", "S1", "RN50_UP", "RN50_DN"]


def say(s=""):
    print(s, flush=True)


def levels(B):
    """per-bar arrays of each level (NaN while unknown), real and fake"""
    idx = B.index
    day = idx.normalize()
    wk = idx.to_period("W")
    mo = idx.to_period("M")
    hm = B.hm.values
    D = B.groupby(day).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    c1 = D.c.shift()
    tr = np.maximum(D.h - D.l, np.maximum((D.h - c1).abs(), (D.l - c1).abs()))
    D["atr"] = tr.rolling(14).mean()
    P = D.shift(1)                                                      # the previous trading day
    W = B.groupby(wk).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"))
    PW = W.shift(1)
    M = B.groupby(mo).agg(h=("h", "max"), l=("l", "min"))
    PM = M.shift(1)
    L = {}
    L["PDH"] = P.h.reindex(day).values
    L["PDL"] = P.l.reindex(day).values
    L["PDC"] = P.c.reindex(day).values
    L["PWH"] = PW.h.reindex(wk).values
    L["PWL"] = PW.l.reindex(wk).values
    L["PMH"] = PM.h.reindex(mo).values
    L["PML"] = PM.l.reindex(mo).values
    first_bar = np.r_[True, day[1:] != day[:-1]]
    L["DO"] = np.where(first_bar, np.nan, D.o.reindex(day).values)
    first_wbar = np.r_[True, wk[1:] != wk[:-1]]
    L["WO"] = np.where(first_wbar, np.nan, W.o.reindex(wk).values)
    asia = (hm >= 180) & (hm < 480)
    A = B[asia].groupby(day[asia]).agg(h=("h", "max"), l=("l", "min"))
    L["ASH"] = np.where(hm >= 480, A.h.reindex(day).values, np.nan)
    L["ASL"] = np.where(hm >= 480, A.l.reindex(day).values, np.nan)
    pp = (P.h + P.l + P.c) / 3
    L["PP"] = pp.reindex(day).values
    L["R1"] = (2 * pp - P.l).reindex(day).values
    L["S1"] = (2 * pp - P.h).reindex(day).values
    c_prev = np.r_[np.nan, B.c.values[:-1]]
    L["RN50_UP"] = np.ceil(c_prev / 50) * 50
    L["RN50_DN"] = np.floor(c_prev / 50) * 50
    # fakes: the same level moved by 0.5 x D1 ATR, random side per type and day (round numbers: $25)
    rng = np.random.default_rng(7)
    datr = P.atr.reindex(day).values
    codes, uniq = pd.factorize(day)
    F = {}
    for t in TYPES:
        if t == "RN50_UP":                                              # the nearest $25 / $75 level instead
            F[t] = np.ceil((c_prev - 25) / 50) * 50 + 25
        elif t == "RN50_DN":
            F[t] = np.floor((c_prev - 25) / 50) * 50 + 25
        else:
            side = rng.choice([-1.0, 1.0], size=len(uniq))[codes]
            F[t] = L[t] + side * 0.5 * datr
    return L, F


def find_events(B, Lv):
    """first armed touch per level and day: list of (bar, level, fade direction)"""
    c, h, l, A, hm = B.c.values, B.h.values, B.l.values, B.atr.values, B.hm.values
    day = B.index.normalize().values
    n = len(B)
    ok = (hm >= 90) & (hm < 1320)
    ev = []
    armed, done = {}, set()
    for i in range(1, n - 1):
        if day[i] != day[i - 1]:
            armed.clear(); done.clear()
        Lx = Lv[i]
        if not np.isfinite(Lx) or not np.isfinite(A[i]):
            continue
        key = round(Lx, 2)
        if key in done:
            continue
        if not armed.get(key) and abs(c[i - 1] - Lx) >= A[i]:
            armed[key] = True
        if not armed.get(key) or not ok[i]:
            continue
        if c[i - 1] > Lx and l[i] <= Lx:
            ev.append((i, Lx, 1)); done.add(key)
        elif c[i - 1] < Lx and h[i] >= Lx:
            ev.append((i, Lx, -1)); done.add(key)
    return ev


def limit_trades(B, ev, flat, tp_mult, trend_only=False, costs=True):
    o, h, l, c, sp, A, tr = (B[x].values for x in ("o", "h", "l", "c", "s", "atr", "trend"))
    n = len(B)
    out = []
    for i, Lx, dr in ev:
        if trend_only and tr[i] != dr:
            continue
        a = A[i]
        e = min(o[i], Lx) if dr == 1 else max(o[i], Lx)
        sl, tp = Lx - dr * a, Lx + dr * tp_mult * a
        risk = (e - sl) * dr
        if risk <= 0.2 * a:
            continue
        # fill bar: the price came from the other side, so its high (support test) may come before the fill; only
        # the SL (beyond the level) or a close past the TP can be counted after the fill on this bar
        ex = None
        if (l[i] <= sl) if dr == 1 else (h[i] >= sl):
            ex = sl
        elif (c[i] >= tp) if dr == 1 else (c[i] <= tp):
            ex = tp
        k = i + 1
        while ex is None and k < n:
            if flat[k] or k - i > 24:
                ex = o[k]; break
            if (o[k] - sl) * dr <= 0:
                ex = o[k]; break
            if (o[k] - tp) * dr >= 0:
                ex = o[k]; break
            if (l[k] <= sl) if dr == 1 else (h[k] >= sl):
                ex = sl; break
            if (h[k] >= tp) if dr == 1 else (l[k] <= tp):
                ex = tp; break
            k += 1
        if ex is None:
            ex = c[n - 1]
        out.append((i, dr, (ex - e) * dr, sp[i] if costs else 0.0, risk, ""))
    return out


def mkt_signals(B, ev, kind):
    o, h, l, c, A = (B[x].values for x in ("o", "h", "l", "c", "atr"))
    n = len(B)
    sig = []
    for i, Lx, dr in ev:
        a = A[i]
        if kind == "REJECT":
            for j in range(i, min(i + 4, n - 1)):
                if (c[j] - Lx) * dr > 0:
                    ext = l[i:j + 1].min() if dr == 1 else h[i:j + 1].max()
                    sl = (min(ext, Lx) - 0.3 * a) if dr == 1 else (max(ext, Lx) + 0.3 * a)
                    sig.append(dict(k0=j + 1, kind="mkt", dir=dr, sl=sl, tp_r=2.0, exp=j + 1, maxb=24)); break
                if (Lx - c[j]) * dr >= a:
                    break
        else:                                                           # BREAK: follow a close through the level
            for j in range(i, min(i + 8, n - 1)):
                if (Lx - c[j]) * dr >= 0.3 * a:
                    sig.append(dict(k0=j + 1, kind="mkt", dir=-dr, sl=Lx + dr * 0.5 * a, tp_r=2.0, exp=j + 1, maxb=24)); break
                if (c[j] - Lx) * dr >= a:
                    break
    return sorted(sig, key=lambda g: g["k0"])


def stats(B, res, days):
    if not res:
        return None
    T = pd.DataFrame(res, columns=["k", "dir", "pnl", "sp", "risk", "why"])
    t = B.index[T.k.values]
    R = ((T.pnl - T.sp) / T.risk).values
    RS = ((T.pnl - 1.5 * T.sp) / T.risk).values
    mid, end = B.index[len(B) // 2], B.index[-1]
    first = t < mid
    return dict(n=len(T), perday=len(T) / days, win=100 * (R > 0).mean(), pf=SA.pf(R), h1=SA.pf(R[first]), h2=SA.pf(R[~first]),
                st=SA.pf(RS), l12=R[t >= end - pd.Timedelta(days=365)].sum(), avg=R.mean())


def passes(s, fake):
    return (s is not None and s["n"] >= 150 and s["pf"] >= 1.15 and s["h1"] >= 1.05 and s["h2"] >= 1.05 and s["st"] >= 1.05
            and s["l12"] > 0 and (fake is None or s["pf"] - fake["pf"] >= 0.10))


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    d5 = SA.load(os.path.join(DATA, SYM + ".csv"), meta[SYM]["point"])
    B = SZ.m15(d5)
    days = B.index.normalize().nunique()
    dates = B.index.normalize().values
    flat = (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]]
    o, h, l, c, sp = (B[x].values for x in ("o", "h", "l", "c", "s"))
    Lr, Lf = levels(B)
    say(f"{SYM} M15 {B.index[0].date()} .. {B.index[-1].date()}, {days} days, levels built in {time.time() - T0:.0f} s")
    say("HOLD% = level held 1 ATR before breaking 1 ATR (no costs; 50% = chance). PF columns: real (fake) after spread.")
    say(f"{'level':8s} {'events':>6s} {'hold%':>6s} {'fake':>5s} | {'LIMIT':>11s} {'LIMIT_TREND':>11s} {'REJECT':>11s} {'BREAK':>11s} | passes")
    total_pass, fake_pass = [], 0
    detail = []
    for tname in TYPES:
        er, ef = find_events(B, Lr[tname]), find_events(B, Lf[tname])
        hr = stats(B, limit_trades(B, er, flat, 1.0, costs=False), days)
        hf = stats(B, limit_trades(B, ef, flat, 1.0, costs=False), days)
        cells, ok_rules = [], []
        for rule in ("LIMIT", "LIMIT_TREND", "REJECT", "BREAK"):
            if rule.startswith("LIMIT"):
                sr = stats(B, limit_trades(B, er, flat, 2.0, trend_only=rule.endswith("TREND")), days)
                sf = stats(B, limit_trades(B, ef, flat, 2.0, trend_only=rule.endswith("TREND")), days)
            else:
                sr = stats(B, SA.sim(o, h, l, c, sp, mkt_signals(B, er, rule), flat), days)
                sf = stats(B, SA.sim(o, h, l, c, sp, mkt_signals(B, ef, rule), flat), days)
            cells.append(f"{SA.f2(sr['pf']) if sr else '  -  '}({SA.f2(sf['pf']) if sf else ' - '})")
            if passes(sr, sf):
                ok_rules.append(rule); total_pass.append((tname, rule, sr))
            if passes(sf, None):
                fake_pass += 1
            if sr:
                detail.append((tname, rule, sr, sf))
        say(f"{tname:8s} {len(er):6d} {hr['win'] if hr else 0:6.1f} {hf['win'] if hf else 0:5.1f} | " + " ".join(f"{x:>11s}" for x in cells)
            + f" | {', '.join(ok_rules)}")
    say("\nDetail (real): trades, a day, win%, PF, halves, stress, last 12 months R, avg R")
    for tname, rule, s, f in detail:
        say(f"  {tname:8s} {rule:12s} {s['n']:5d} {s['perday']:5.2f} {s['win']:5.1f} {SA.f2(s['pf'])} {SA.f2(s['h1'])} {SA.f2(s['h2'])} "
            f"{SA.f2(s['st'])} {s['l12']:7.1f} {s['avg']:+.3f}   fake PF {SA.f2(f['pf']) if f else '-'}")
    say(f"\nPASSED (real, all rules incl. beating the fake level by 0.10 PF): {len(total_pass)} of {len(TYPES) * 4}")
    for tname, rule, s in total_pass:
        say(f"  {tname} {rule}: {s['n']} trades, PF {SA.f2(s['pf'])}, halves {SA.f2(s['h1'])} / {SA.f2(s['h2'])}, stress {SA.f2(s['st'])}")
    say(f"fake levels passing the base rule (luck baseline): {fake_pass} of {len(TYPES) * 4}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
