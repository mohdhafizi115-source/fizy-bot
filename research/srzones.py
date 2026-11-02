"""Gold M15 support / resistance zones: which entry idea at a zone (if any) passes on 6.6 years of broker data?

Zones (the same algorithm as the EA module mt5/FizySR.mqh):
  every hour, take the 5-bar swing highs and lows (fractals) of the last 480 M15 bars (5 days), cluster their
  prices within 1 x ATR(M15, 14), keep clusters with >= 2 touches, widen each by 0.15 ATR, merge overlaps.
  Zones above the price are resistance, zones below are support. Trend = H1 EMA 50 vs EMA 200.
CAPPED zones (run 2, what the EA alerts use since 2 Nov): a swing joins a cluster only while the cluster spans
<= 2 ATR, and overlapping zones merge only while the result is <= 2.5 ATR wide (otherwise the boundary moves to the
middle of the overlap). Without the cap, a few days of range trading chain into one zone 6+ ATR wide.
Zone event: an M15 bar trades into a zone coming from outside it (previous close outside); one event per zone area
per 4 hours.
Entry ideas tested (fixed before the run; entry at the next M15 open; flat 23:00 server; max 24 bars):
  BOUNCE_ALL   fade into the zone (buy support / sell resistance), SL beyond the zone + 0.5 ATR, TP 2R
  BOUNCE_TREND the same, only with the H1 trend (buy support in an uptrend, sell resistance in a downtrend)
  REJECT_ALL   wait for a bar that dips into the zone and closes back outside it, then fade; SL beyond the zone
               + 0.3 ATR, TP 2R
  REJECT_TREND the same with the H1 trend only
  BREAK_ALL    a bar closes through the far side of the zone -> follow; SL at the zone's near side + 0.3 ATR, TP 2R
  BREAK_TREND  the same with the H1 trend only
  RAND         random entries at the same rate, random side, SL 1.5 ATR, TP 2R (chance baseline)
Pass rule (CLAUDE.md): >= 150 trades, PF >= 1.15, both halves >= 1.05, stress 1.5x spread >= 1.05, last 12 months
positive.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYM = sys.argv[2] if len(sys.argv) > 2 else "XAUUSD"
T0 = time.time()


def m15(d5):
    r = d5.resample("15min", label="left", closed="left")
    B = pd.DataFrame({"o": r.o.first(), "h": r.h.max(), "l": r.l.min(), "c": r.c.last(), "s": r.s.median()}).dropna()
    c1 = B.c.shift()
    tr = np.maximum(B.h - B.l, np.maximum((B.h - c1).abs(), (B.l - c1).abs()))
    B["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    H = B.c.resample("1h").last().dropna()
    e50, e200 = H.ewm(span=50, adjust=False).mean(), H.ewm(span=200, adjust=False).mean()
    tr_h = np.sign(e50 - e200).shift(1)                                # known at the start of the hour
    B["trend"] = tr_h.reindex(B.index, method="ffill").fillna(0).values
    B["hm"] = B.index.hour * 60 + B.index.minute
    return B


def zones_at(ph, pl, i, atr, cap=False):
    """zones from the swing prices of bars i-480 .. i-3 (a swing at bar j is confirmed by the close of bar j+2, so
    only swings confirmed before bar i opens are used; until 2 Nov the slice ended at i-2, one bar of look-ahead)"""
    p = np.r_[ph[max(0, i - 480):i - 2], pl[max(0, i - 480):i - 2]]
    p = np.sort(p[np.isfinite(p)])
    if len(p) < 2 or not np.isfinite(atr) or atr <= 0:
        return []
    out, cur = [], [p[0]]
    for x in p[1:]:
        if x - np.mean(cur) <= atr and (not cap or x - cur[0] <= 2 * atr):
            cur.append(x)
        else:
            out.append(cur); cur = [x]
    out.append(cur)
    Z = [[min(c) - 0.15 * atr, max(c) + 0.15 * atr, len(c)] for c in out if len(c) >= 2]
    M = []
    for z in sorted(Z):
        if M and z[0] <= M[-1][1]:
            if not cap or max(M[-1][1], z[1]) - M[-1][0] <= 2.5 * atr:
                M[-1] = [M[-1][0], max(M[-1][1], z[1]), M[-1][2] + z[2]]
            else:
                b = (z[0] + M[-1][1]) / 2
                M[-1][1] = b
                M.append([b, z[1], z[2]])
        else:
            M.append(z)
    return M


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    d5 = SA.load(os.path.join(DATA, SYM + ".csv"), meta[SYM]["point"])
    B = m15(d5)
    for cap in (False, True):
        print(f"\n==== zones {'CAPPED (2 ATR clusters, 2.5 ATR merge)' if cap else 'ORIGINAL (no width cap)'} ====")
        run(B, meta, cap)
    print(f"done in {time.time() - T0:.0f} s")


def run(B, meta, cap):
    o, h, l, c, sp, A, tr, hm = (B[x].values for x in ("o", "h", "l", "c", "s", "atr", "trend", "hm"))
    n = len(B)
    dates = B.index.normalize().values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    flat = (hm >= 1380) | newday
    # fractals, confirmed 2 bars later
    ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for i in range(2, n - 2):
        if h[i] > max(h[i - 2], h[i - 1], h[i + 1], h[i + 2]):
            ph[i] = h[i]
        if l[i] < min(l[i - 2], l[i - 1], l[i + 1], l[i + 2]):
            pl[i] = l[i]
    sig = {k: [] for k in ("BOUNCE_ALL", "BOUNCE_TREND", "REJECT_ALL", "REJECT_TREND", "BREAK_ALL", "BREAK_TREND")}
    Z = []
    recent = []                                                         # (bar, price) of recent zone events
    n_events = 0
    widths = []
    ok_time = (hm >= 90) & (hm < 1320)
    for i in range(500, n - 1):
        if i % 4 == 0:
            Z = zones_at(ph, pl, i, A[i], cap)
            widths.extend((z[1] - z[0]) / A[i] for z in Z)
        if not ok_time[i] or not Z:
            continue
        a = A[i]
        recent = [(k, p) for (k, p) in recent if i - k < 16]
        for zlo, zhi, cnt in Z:
            mid = (zlo + zhi) / 2
            if any(abs(p - mid) < a for (_, p) in recent):
                continue
            sup = c[i - 1] > zhi and l[i] <= zhi                       # coming down into a support zone
            res = c[i - 1] < zlo and h[i] >= zlo                       # coming up into a resistance zone
            if not (sup or res):
                continue
            recent.append((i, mid)); n_events += 1
            dr = 1 if sup else -1                                      # fade direction
            withtrend = (tr[i] == dr)
            sl = (zlo - 0.5 * a) if dr == 1 else (zhi + 0.5 * a)
            g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, tp_r=2.0, exp=i + 1, maxb=24)
            sig["BOUNCE_ALL"].append(g)
            if withtrend:
                sig["BOUNCE_TREND"].append(dict(g))
            # rejection: this bar or the next 3 close back outside the zone on the fade side
            for j in range(i, min(i + 4, n - 1)):
                if (dr == 1 and c[j] > zhi and l[j] <= zhi) or (dr == -1 and c[j] < zlo and h[j] >= zlo):
                    slr = (min(l[i:j + 1].min(), zlo) - 0.3 * a) if dr == 1 else (max(h[i:j + 1].max(), zhi) + 0.3 * a)
                    g2 = dict(k0=j + 1, kind="mkt", dir=dr, sl=slr, tp_r=2.0, exp=j + 1, maxb=24)
                    sig["REJECT_ALL"].append(g2)
                    if withtrend:
                        sig["REJECT_TREND"].append(dict(g2))
                    break
                if (dr == 1 and c[j] < zlo) or (dr == -1 and c[j] > zhi):
                    break
            # break: a close through the far side within 8 bars -> follow
            for j in range(i, min(i + 8, n - 1)):
                if (dr == 1 and c[j] < zlo) or (dr == -1 and c[j] > zhi):
                    slb = (zhi + 0.3 * a) if dr == 1 else (zlo - 0.3 * a)
                    g3 = dict(k0=j + 1, kind="mkt", dir=-dr, sl=slb, tp_r=2.0, exp=j + 1, maxb=24)
                    sig["BREAK_ALL"].append(g3)
                    if tr[j] == -dr:
                        sig["BREAK_TREND"].append(dict(g3))
                    break
                if (dr == 1 and c[j] > zhi + a) or (dr == -1 and c[j] < zlo - a):
                    break
    # chance baseline at the same rate
    rng = np.random.default_rng(5)
    cand = np.where(ok_time[500:n - 1])[0] + 500
    pick = np.sort(rng.choice(cand, size=min(len(cand), len(sig["BOUNCE_ALL"])), replace=False))
    sig["RAND"] = [dict(k0=i + 1, kind="mkt", dir=(1 if rng.random() < 0.5 else -1), sl=None, tp_r=2.0, exp=i + 1, maxb=24) for i in pick]
    for g in sig["RAND"]:
        i = g["k0"] - 1; g["sl"] = c[i] - g["dir"] * 1.5 * A[i]
    days = len(np.unique(dates))
    usd = meta[SYM]["tick_value"] / meta[SYM]["tick_size"] * 0.01
    w = np.array(widths)
    print(f"{SYM} M15 {B.index[0].date()} .. {B.index[-1].date()}, {days} days, {n_events} zone events ({n_events / days:.1f} a day), "
          f"zone width in ATR: median {np.median(w):.2f}, 90% {np.percentile(w, 90):.2f}, max {w.max():.1f}, {time.time() - T0:.0f} s")
    print("rule          trades  /day  win%    PF  half1 half2 stress last12R   net$(0.01)  by year")
    mid_t = B.index[n // 2]; end_t = B.index[-1]
    for name, sg in sig.items():
        sg = sorted(sg, key=lambda g: g["k0"])
        res = SA.sim(o, h, l, c, sp, sg, flat)
        if not res:
            print(f"{name:12s} no trades"); continue
        T = pd.DataFrame(res, columns=["k", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.k.values]
        T["R"] = (T.pnl - T.sp) / T.risk; T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
        P, P1, P2, PS = SA.pf(T.R.values), SA.pf(T[T.t < mid_t].R.values), SA.pf(T[T.t >= mid_t].R.values), SA.pf(T.Rs.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].R.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        yr = " ".join(f"{y % 100}:{SA.f2(SA.pf(T[T.t.dt.year == y].R.values))}" for y in sorted(T.t.dt.year.unique()))
        print(f"{name:12s} {len(T):6d} {len(T) / days:5.2f} {100 * (T.R > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
              f"{l12:7.1f} {((T.pnl - T.sp) * usd).sum():9.0f}  {yr} {'PASS' if ok else ''}")


if __name__ == "__main__":
    main()
