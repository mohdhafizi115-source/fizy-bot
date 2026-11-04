"""Round 30 (4 Nov 2026): more gold M1 scalps not tested before (owner: "aku tak nak yang dah test, cari lagi yang lain,
m1 sahaja"). Rules from public pages, fixed before the run (open choices named as assumptions):
  SS_GOLD    "XAUUSD Sweep & Shift SS-GOLD-02" (sweep-96c.pages.dev): Asia range 00:00-07:00 UTC; London kill zone
             07:00-10:00 UTC sweeps the Asia high / low, NY kill zone 13:00-16:00 UTC sweeps the London (07:00-13:00)
             high / low. Sweep = an M5 wick beyond the level with the body back inside (that candle or the next 2).
             MSS = an M5 body close beyond the last internal swing (3-bar fractal) the other way, leaving an M5 FVG.
             Limit at the FVG edge (M1 fills), SL 0.20 beyond the sweep extreme, T1 = FVG far edge (half off, SL to
             entry), T2 = the opposing range level; skip if T2 < 2.5R; exit at the kill-zone end if T1 was not reached,
             otherwise by 19:30 UTC; max 2 trades a day
  SB_NY      ICT Silver Bullet on M1: the first M1 FVG formed 10:00-11:00 New York; limit at its near edge until 11:00,
             SL beyond the first candle of the gap, TP 2R (assumption)
  SB_LDN     the same 03:00-04:00 New York
  TSOUP      Turtle soup on M1: a new 20-bar low (the old low at least 4 bars back), then a close back above the old
             low within 3 bars: buy next open, SL 0.1 ATR below the new low, TP 1.5R (sell mirrored)
  BB_SQZ     Bollinger squeeze breakout (sahi.com rules on M1): band width < 50% of 20 bars ago and >= 5 closes inside;
             close beyond the band with tick volume >= 1.5x the 10-bar average: follow, SL the middle band, TP 2x
             the 10-bar range
  RIBBON     EMA ribbon 8/13/21/50/100/200 stacked; low touches EMA 21 and the close is back beyond EMA 8: follow,
             SL beyond the 10-bar swing, TP 1.5R
  RAND       random entries, SL 1.5 ATR, TP 1.5R
Signals 09:00-21:00 server unless the rule has its own window, flat 22:30. Costs: bar spread, 0.01 lot.
Limit fills: on the fill bar only the SL counts (or a close beyond the TP). Usual pass rule, PF 0.10 above RAND.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
SRV, NYC, UTC = ZoneInfo("Europe/Athens"), ZoneInfo("America/New_York"), ZoneInfo("UTC")
RULES = ["SS_GOLD", "SB_NY", "SB_LDN", "TSOUP", "BB_SQZ", "RIBBON", "RAND"]


def srv_idx(idx, day, hh, mm, tz):
    t = pd.Timestamp(day.year, day.month, day.day, hh, mm, tzinfo=tz).tz_convert(SRV).tz_localize(None)
    return idx.searchsorted(t)


def run_limit(o, h, l, c, sp, k0, k1, dr, P, sl, tp, t1=None, kz_end=None, hard_end=None, flat=None):
    """limit order live k0..k1; returns (fill k, pnl in price, spread) or None. Optional T1 half-off + break-even."""
    n = len(o)
    for k in range(k0, min(k1, n - 1) + 1):
        if (dr == 1 and l[k] <= P) or (dr == -1 and h[k] >= P):
            e = min(P, o[k]) if dr == 1 else max(P, o[k])
            # fill bar: SL only, or a close beyond the TP
            if (dr == 1 and l[k] <= sl) or (dr == -1 and h[k] >= sl):
                return k, (sl - e) * dr, sp[k]
            half, stop, got1 = 0.0, sl, False
            if (c[k] - tp) * dr >= 0:
                return k, (tp - e) * dr, sp[k]
            end = hard_end if hard_end is not None else n - 1
            for m in range(k + 1, min(end, n - 1) + 1):
                if flat is not None and flat[m]:
                    return k, half + (o[m] - e) * dr * (0.5 if got1 else 1.0), sp[k]
                if kz_end is not None and not got1 and m >= kz_end:
                    return k, (o[m] - e) * dr, sp[k]
                if (dr == 1 and l[m] <= stop) or (dr == -1 and h[m] >= stop):
                    return k, half + (stop - e) * dr * (0.5 if got1 else 1.0), sp[k]
                if t1 is not None and not got1 and ((dr == 1 and h[m] >= t1) or (dr == -1 and l[m] <= t1)):
                    got1, half, stop = True, 0.5 * (t1 - e) * dr, e
                if (dr == 1 and h[m] >= tp) or (dr == -1 and l[m] <= tp):
                    return k, half + (tp - e) * dr * (0.5 if got1 else 1.0), sp[k]
            return k, half + (c[min(end, n - 1)] - e) * dr * (0.5 if got1 else 1.0), sp[k]
    return None


def ss_gold(B, flat):
    o, h, l, c, sp = (B[x].values for x in ("o", "h", "l", "c", "s"))
    idx = B.index
    M5 = B.resample("5min", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    m5i = idx.searchsorted(M5.index)                                 # first M1 bar of each M5 bar
    mo, mh, ml, mc = (M5[x].values for x in ("o", "h", "l", "c"))
    out = []
    for day in pd.DatetimeIndex(idx.normalize().unique()):
        dU = day                                                    # server date ~ UTC date for these windows
        a0, a1 = srv_idx(idx, dU, 0, 0, UTC), srv_idx(idx, dU, 7, 0, UTC)
        l0, l1 = a1, srv_idx(idx, dU, 13, 0, UTC)
        n0, n1 = l1, srv_idx(idx, dU, 16, 0, UTC)
        hard = srv_idx(idx, dU, 19, 30, UTC)
        if a1 - a0 < 300 or n1 >= len(idx):
            continue
        trades = 0
        for (r0, r1, z0, z1) in ((a0, a1, a1, l1 - 180), (l0, l1, n0, n1)):     # London KZ 07-10, NY KZ 13-16 UTC
            if trades >= 2 or r1 - r0 < 60:
                continue
            HI, LO = h[r0:r1].max(), l[r0:r1].min()
            j0, j1 = M5.index.searchsorted(idx[z0]), M5.index.searchsorted(idx[min(z1, len(idx) - 1)])
            for side in (1, -1):                                    # 1 = sweep of the low -> long
                lvl = LO if side == 1 else HI
                done = False
                for j in range(j0 + 3, j1):
                    if done or trades >= 2:
                        break
                    swept = (ml[j] < lvl) if side == 1 else (mh[j] > lvl)
                    if not swept:
                        continue
                    back = next((q for q in range(j, min(j + 3, j1)) if (side == 1 and mc[q] > lvl) or (side == -1 and mc[q] < lvl)), None)
                    if back is None:
                        continue
                    ext = ml[j:back + 1].min() if side == 1 else mh[j:back + 1].max()
                    # last internal swing before the sweep (3-bar fractal)
                    sw = None
                    for q in range(j - 1, max(j0 - 30, 2), -1):
                        if side == 1 and mh[q] > mh[q - 1] and mh[q] >= mh[q + 1]:
                            sw = mh[q]; break
                        if side == -1 and ml[q] < ml[q - 1] and ml[q] <= ml[q + 1]:
                            sw = ml[q]; break
                    if sw is None:
                        continue
                    for q in range(back, min(back + 12, j1)):
                        if (side == 1 and mc[q] > sw) or (side == -1 and mc[q] < sw):
                            fv = None
                            for g in range(q, max(q - 3, back), -1):        # FVG made by the MSS move
                                if side == 1 and ml[g] > mh[g - 2]:
                                    fv = (mh[g - 2], ml[g]); break
                                if side == -1 and mh[g] < ml[g - 2]:
                                    fv = (mh[g], ml[g - 2]); break
                            if fv is None:
                                break
                            P = fv[1] if side == 1 else fv[0]
                            sl = ext - 0.20 if side == 1 else ext + 0.20
                            tp = HI if side == 1 else LO
                            if (P - sl) * side <= 0 or (tp - P) * side < 2.5 * (P - sl) * side:
                                break
                            # T1: the internal swing the MSS broke, if it is beyond the entry; else 1R
                            t1 = sw if (sw - P) * side > 0 else P + side * (P - sl) * side
                            k0 = m5i[q + 1] if q + 1 < len(m5i) else len(idx) - 1
                            kz_end = srv_idx(idx, dU, 10, 0, UTC) if z0 == a1 else n1
                            r = run_limit(o, h, l, c, sp, k0, kz_end, side, P, sl, tp, t1=t1, kz_end=kz_end, hard_end=hard, flat=flat)
                            if r:
                                out.append((r[0], side, r[1], r[2], abs(P - sl)))
                                trades += 1
                            done = True
                            break
                    if done:
                        break
    return out


def silver(B, hh, flat):
    o, h, l, c, sp = (B[x].values for x in ("o", "h", "l", "c", "s"))
    idx = B.index
    out = []
    for day in pd.DatetimeIndex(idx.normalize().unique()):
        k0, k1 = srv_idx(idx, day, hh, 0, NYC), srv_idx(idx, day, hh + 1, 0, NYC)
        if k1 >= len(idx) - 2 or k1 - k0 < 50:
            continue
        for j in range(k0 + 2, k1):
            if l[j] > h[j - 2]:
                P, sl, dr = l[j], l[j - 2] - 0.01, 1
            elif h[j] < l[j - 2]:
                P, sl, dr = h[j], h[j - 2] + 0.01, -1
            else:
                continue
            tp = P + dr * 2 * abs(P - sl)
            r = run_limit(o, h, l, c, sp, j + 1, k1, dr, P, sl, tp, flat=flat)
            if r:
                out.append((r[0], dr, r[1], r[2], abs(P - sl)))
            break
    return out


def market(B):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    I = R.ind(B)
    A = I["atr"]
    hm = B.hm.values
    ok = (hm >= 540) & (hm < 1260) & np.isfinite(A) & (np.arange(n) >= 300)
    ok[-2:] = False
    S = {"TSOUP": [], "BB_SQZ": [], "RIBBON": [], "RAND": []}

    def add(rule, i, dr, sl, **kw):
        if (sl - c[i]) * dr >= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=60); g.update(kw); S[rule].append(g)

    lo20 = np.r_[np.nan, pd.Series(l).rolling(20).min().values[:-1]]
    hi20 = np.r_[np.nan, pd.Series(h).rolling(20).max().values[:-1]]
    age_l = pd.Series(l).rolling(20).apply(lambda x: 19 - np.argmin(x), raw=True).values
    age_h = pd.Series(h).rolling(20).apply(lambda x: 19 - np.argmax(x), raw=True).values
    age_l, age_h = np.r_[np.nan, age_l[:-1]], np.r_[np.nan, age_h[:-1]]
    newlo = (l < lo20) & (age_l >= 4)
    newhi = (h > hi20) & (age_h >= 4)
    lastlo = np.full(n, -1); lasthi = np.full(n, -1); lvl_l = np.full(n, np.nan); lvl_h = np.full(n, np.nan)
    cur, cl = -1, np.nan
    for i in range(n):
        if newlo[i]:
            cur, cl = i, lo20[i]
        lastlo[i], lvl_l[i] = cur, cl
    cur, ch = -1, np.nan
    for i in range(n):
        if newhi[i]:
            cur, ch = i, hi20[i]
        lasthi[i], lvl_h[i] = cur, ch
    mnl = pd.Series(l).rolling(4).min().values; mxh = pd.Series(h).rolling(4).max().values
    for i in np.where(ok & (np.arange(n) - lastlo <= 3) & (lastlo >= 0) & (c > lvl_l) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, lvl_l[:-1]]))[0]:
        add("TSOUP", i, 1, mnl[i] - 0.1 * A[i], tp_r=1.5)
    for i in np.where(ok & (np.arange(n) - lasthi <= 3) & (lasthi >= 0) & (c < lvl_h) & (np.r_[np.nan, c[:-1]] >= np.r_[np.nan, lvl_h[:-1]]))[0]:
        add("TSOUP", i, -1, mxh[i] + 0.1 * A[i], tp_r=1.5)
    bw = I["bbu"] - I["bbl"]
    bw20 = np.r_[np.full(20, np.nan), bw[:-20]]
    inside = ((c <= I["bbu"]) & (c >= I["bbl"])).astype(float)
    in5 = np.r_[np.nan, pd.Series(inside).rolling(5).sum().values[:-1]] >= 5
    sq = np.r_[False, (bw < 0.5 * bw20)[:-1]] & in5
    vol = B["v"].values
    v10 = np.r_[np.nan, pd.Series(vol).rolling(10).mean().values[:-1]]
    rng10 = np.r_[np.nan, (pd.Series(h).rolling(10).max() - pd.Series(l).rolling(10).min()).values[:-1]]
    for i in np.where(ok & sq & (c > I["bbu"]) & (vol >= 1.5 * v10))[0]:
        add("BB_SQZ", i, 1, I["bbm"][i], tp=c[i] + 2 * rng10[i])
    for i in np.where(ok & sq & (c < I["bbl"]) & (vol >= 1.5 * v10))[0]:
        add("BB_SQZ", i, -1, I["bbm"][i], tp=c[i] - 2 * rng10[i])
    E = {p: pd.Series(c).ewm(span=p, adjust=False).mean().values for p in (8, 13, 21, 50, 100, 200)}
    up = (E[8] > E[13]) & (E[13] > E[21]) & (E[21] > E[50]) & (E[50] > E[100]) & (E[100] > E[200])
    dn = (E[8] < E[13]) & (E[13] < E[21]) & (E[21] < E[50]) & (E[50] < E[100]) & (E[100] < E[200])
    lo10 = np.r_[np.nan, pd.Series(l).rolling(10).min().values[:-1]]
    hi10 = np.r_[np.nan, pd.Series(h).rolling(10).max().values[:-1]]
    for i in np.where(ok & up & (l <= E[21]) & (c > E[8]))[0]:
        add("RIBBON", i, 1, lo10[i], tp_r=1.5)
    for i in np.where(ok & dn & (h >= E[21]) & (c < E[8]))[0]:
        add("RIBBON", i, -1, hi10[i], tp_r=1.5)
    rg = np.random.default_rng(30)
    for i in np.where(ok & (rg.random(n) < 1 / 30))[0]:
        dr = 1 if rg.random() < 0.5 else -1
        add("RAND", i, dr, c[i] - dr * 1.5 * A[i], tp_r=1.5)
    return S


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); B["v"] = d.v.reindex(B.index).fillna(1.0).values
    dates = B.date.values
    flat = (B.hm.values >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    print(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {len(B):,} bars", flush=True)
    res = {}
    res["SS_GOLD"] = ss_gold(B, flat); print(f"SS_GOLD done {time.time() - T0:.0f} s", flush=True)
    res["SB_NY"] = silver(B, 10, flat); res["SB_LDN"] = silver(B, 3, flat)
    S = market(B)
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    for rule, sg in S.items():
        res[rule] = [(k, dr, pnl, sp, risk) for (k, dr, pnl, sp, risk, why) in SA.sim(*arr, sorted(sg, key=lambda g: g["k0"]), flat)]
    print(f"all simulated {time.time() - T0:.0f} s", flush=True)
    mid, end, days = B.index[len(B) // 2], B.index[-1], B.index.normalize().nunique()
    t1 = end - pd.Timedelta(days=31)
    pf = SA.pf
    PR = pf(np.array([(p - s) for (k, dr, p, s, r) in res["RAND"]]))
    print("\nrule      trades /day  win%   PF  half1 half2 stress last12$    net$ rawPF | last month: trades   PF   net$ | by year")
    for rule in RULES:
        T = pd.DataFrame(res[rule], columns=["k", "dir", "pnl", "sp", "risk"])
        if T.empty:
            print(f"{rule:9s} no trades"); continue
        T["t"] = B.index[T.k.values]; T["net"] = (T.pnl - T.sp) * usd; T["st"] = (T.pnl - 1.5 * T.sp) * usd; T["raw"] = T.pnl * usd
        P, P1, P2, PS = pf(T.net.values), pf(T[T.t < mid].net.values), pf(T[T.t >= mid].net.values), pf(T.st.values)
        l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P - PR >= 0.10
        M = T[T.t >= t1]
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        print(f"{rule:9s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
              f"{l12:+7.0f} {T.net.sum():+8.0f} {SA.f2(pf(T.raw.values))} | {len(M):6d} {SA.f2(pf(M.net.values))} {M.net.sum():+7.0f} | {yr} "
              f"{'PASS' if ok and rule != 'RAND' else ''}", flush=True)
    print(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
