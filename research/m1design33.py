"""Round 33 (4 Nov 2026): design an M1 gold method from what the broker's own data has shown, instead of copying a
system from the web (owner: "dapatkan cara paling sesuai dan profitable ... berdasarkan pemerhatian kau").

What 11 rounds of M1 testing showed:
  1. The spread ($0.19 per 0.01 lot) is the whole problem. Any rule whose risk is about $1 pays 19% of its risk in
     costs; all 130+ indicator and web rules tested so far lose after spread while their raw PF is 0.88-1.23.
  2. The only edge ever found on a minute scale is a TIME window (sell 10:15 -> 10:30 London before the LBMA AM
     auction, PF 1.51 live). It works because a known flow moves gold further than the spread in 15 minutes.
  3. The only raw (pre-spread) M1 edge found is fading a big spike (PF 1.23, round 21), killed by a $1 risk.
So this round looks for what can actually beat the spread on M1: bigger moves, fewer trades, and real flow.

  MINSCAN  a systematic scan of every entry minute of the day and hold of 5 / 10 / 15 / 30 / 60 minutes, long and
           short, in London local time and again in New York local time (the two clocks gold's fixings and the US
           session follow). Two-stage: the FIRST HALF of the data must give |t| >= 3.5 on at least 200 days, then the
           SECOND HALF must agree in sign with t >= 2 and PF >= 1.1, and the whole period must pass the usual rule.
           Control: the same two-stage filter on day-shuffled returns, which says how many survivors chance alone
           gives.
  SPIKE    fade an M1 bar of k x ATR(14) (k = 3 / 4 / 5 / 6) but with a wide stop and a longer hold, so the spread is
           a small part of the risk: SL = 1 x the spike's own range beyond its extreme, TP = the spike's open (full
           retrace) or 2R, hold 15 / 60 / 240 minutes.
  NEWS     high-impact USD events from data/calendar.csv: measure the move from the event minute to +5 min, then fade
           or follow it when it is at least 1.5 x ATR(M1); SL 1 x the move beyond the extreme, TP = the pre-event
           price (fade) or 1R (follow), out after 60 minutes.
  AUCTION  can M1 timing improve the live LBMA pre-auction sell? Baseline sells at 10:15 London and is flat 10:30.
           Variants: wait for the first M1 close below the 10:00-10:15 low; wait for a green M1 bar (sell a bounce);
           add a 2 ATR stop; exit 10:35 instead.
Costs everywhere: the entry bar's spread, stress = 1.5x. Fixed 0.01 lot, so PF and net are in dollars.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
CAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "calendar.csv")
T0 = time.time()
LON, NYC, SRV = ZoneInfo("Europe/London"), ZoneInfo("America/New_York"), ZoneInfo("Europe/Athens")


def say(s=""):
    print(s, flush=True)


def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return np.inf if l <= 0 else g / l


def tstat(x):
    x = np.asarray(x, float)
    return 0.0 if len(x) < 3 or x.std(ddof=1) == 0 else x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


# ---------------------------------------------------------------- minute-of-day scan
def minscan(d, usd, tz, name, holds=(5, 10, 15, 30, 60)):
    loc = d.index.tz_localize(SRV, ambiguous=True, nonexistent="shift_forward").tz_convert(tz)
    hm = (loc.hour * 60 + loc.minute).values
    day = pd.Index(loc.date)
    O = pd.DataFrame({"d": day, "m": hm, "o": d.o.values, "s": d.s.values})
    O = O[~O.duplicated(["d", "m"])]
    P = O.pivot(index="d", columns="m", values="o").reindex(columns=range(1440))
    S = O.pivot(index="d", columns="m", values="s").reindex(columns=range(1440))
    idx = pd.to_datetime(P.index)
    ok_day = idx.dayofweek < 5
    P, S, idx = P.values[ok_day], S.values[ok_day], idx[ok_day]
    half = len(idx) // 2
    l12 = idx >= idx[-1] - pd.Timedelta(days=365)
    rng = np.random.default_rng(33)
    out, nfake, nwin = [], 0, 0
    for h in holds:
        for m in range(90, 1380 - h):                        # skip the 23:45-01:30 rollover
            a, b = P[:, m], P[:, m + h]
            good = np.isfinite(a) & np.isfinite(b) & np.isfinite(S[:, m])
            if good.sum() < 400:
                continue
            raw = (b - a)[good] * usd
            cost = S[:, m][good] * usd
            gl = l12[good]
            i1 = np.arange(good.sum()) < good[:half].sum()
            nwin += 1
            for side in (1, -1):
                net = side * raw - cost
                t1 = tstat(net[i1])
                if t1 < 3.5 or i1.sum() < 200:
                    continue
                t2 = tstat(net[~i1])
                P2, PA = pf(net[~i1]), pf(net)
                if t2 < 2 or P2 < 1.1 or PA < 1.15 or net[gl].sum() <= 0:
                    continue
                out.append(dict(tz=name, m=m, h=h, side=side, n=int(good.sum()), pf=PA, t1=t1, t2=t2,
                                pf1=pf(net[i1]), pf2=P2, st=pf(side * raw - 1.5 * cost), net=net.sum(),
                                l12=net[gl].sum(), per=net.mean()))
            # chance control: shuffle the day order, so any half-to-half agreement is luck
            sh = rng.permutation(raw)
            for side in (1, -1):
                net = side * sh - cost
                t1 = tstat(net[i1])
                if t1 >= 3.5 and i1.sum() >= 200 and tstat(net[~i1]) >= 2 and pf(net[~i1]) >= 1.1 and pf(net) >= 1.15:
                    nfake += 1
    return pd.DataFrame(out), nfake, nwin


# ---------------------------------------------------------------- spike fade with a wide stop
def spikes(d, usd, atr):
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(c)
    hm = d.index.hour.values * 60 + d.index.minute.values
    ok = (hm >= 90) & (hm < 1320) & np.isfinite(atr) & (np.arange(n) >= 300)
    rows = []
    rg = h - l
    for k in (3, 4, 5, 6):
        sig = np.where(ok & (rg >= k * atr) & (c != o))[0]
        for maxb, tp_mode in ((15, "half"), (60, "full"), (60, "2R"), (240, "full")):
            res = []
            busy = -1
            for i in sig:
                if i <= busy or i + 2 >= n:
                    continue
                dr = -1 if c[i] > o[i] else 1                # fade the spike
                e = o[i + 1]
                sl = (h[i] + rg[i]) if dr == -1 else (l[i] - rg[i])
                tp = o[i] if tp_mode == "full" else (c[i] - np.sign(c[i] - o[i]) * 0.5 * rg[i] if tp_mode == "half"
                                                     else e + dr * 2 * abs(e - sl))
                if (e - sl) * dr <= 0 or (tp - e) * dr <= 0:
                    continue
                ex, why = None, "time"
                for q in range(i + 1, min(i + 1 + maxb, n)):
                    if (dr == 1 and l[q] <= sl) or (dr == -1 and h[q] >= sl):
                        ex, why = sl, "SL"; break
                    if (dr == 1 and h[q] >= tp) or (dr == -1 and l[q] <= tp):
                        ex, why = tp, "TP"; break
                    if hm[q] >= 1350:
                        ex = c[q]; break
                if ex is None:
                    ex = c[min(i + maxb, n - 1)]
                busy = min(i + maxb, n - 1)
                res.append((d.index[i], (ex - e) * dr * usd, sp[i] * usd, abs(e - sl) * usd))
            rows.append((f"SPIKE {k}ATR {tp_mode} {maxb}m", res))
    return rows


# ---------------------------------------------------------------- news fade / follow
def news(d, usd, atr):
    if not os.path.exists(CAL):
        return []
    C = pd.read_csv(CAL, usecols=["time", "impact", "currency"])
    C = C[(C.currency == "USD") & (C.impact == C.impact.max())]
    t = pd.to_datetime(C.time.values, unit="s").tz_localize("Etc/GMT-2").tz_convert(SRV).tz_localize(None)
    ev = pd.DatetimeIndex(sorted(set(t)))
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(c)
    k0 = d.index.searchsorted(ev)
    rows = []
    for mode in ("fade", "follow"):
        res = []
        busy = -1
        for k in k0:
            if k <= busy or k + 70 >= n or not np.isfinite(atr[k]):
                continue
            mv = c[k + 5] - o[k]
            if abs(mv) < 1.5 * atr[k]:
                continue
            dr = (-1 if mv > 0 else 1) if mode == "fade" else (1 if mv > 0 else -1)
            e = o[k + 6]
            hi, lo = h[k:k + 6].max(), l[k:k + 6].min()
            sl = (hi + abs(mv)) if dr == -1 else (lo - abs(mv))
            tp = o[k] if mode == "fade" else e + dr * abs(e - sl)
            if (e - sl) * dr <= 0 or (tp - e) * dr <= 0:
                continue
            ex = None
            for q in range(k + 6, min(k + 66, n)):
                if (dr == 1 and l[q] <= sl) or (dr == -1 and h[q] >= sl):
                    ex = sl; break
                if (dr == 1 and h[q] >= tp) or (dr == -1 and l[q] <= tp):
                    ex = tp; break
            if ex is None:
                ex = c[min(k + 65, n - 1)]
            busy = k + 66
            res.append((d.index[k], (ex - e) * dr * usd, sp[k] * usd, abs(e - sl) * usd))
        rows.append((f"NEWS {mode}", res))
    return rows


# ---------------------------------------------------------------- the live auction scalp, with M1 timing
def auction(d, usd, atr):
    loc = d.index.tz_localize(SRV, ambiguous=True, nonexistent="shift_forward").tz_convert(LON)
    hm = (loc.hour * 60 + loc.minute).values
    day = pd.Index(loc.date)
    o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(c)
    starts = {}
    for i in np.where((hm == 615) & (pd.DatetimeIndex(pd.to_datetime(day)).dayofweek < 5))[0]:
        starts.setdefault(day[i], i)
    rows = []
    for name, wait, use_sl, exit_m in (("AUCTION base 10:15->10:30", "none", False, 630),
                                       ("AUCTION wait break of 10:00-10:15 low", "break", False, 630),
                                       ("AUCTION wait a green M1 bar", "green", False, 630),
                                       ("AUCTION base + SL 2 ATR", "none", True, 630),
                                       ("AUCTION base, exit 10:35", "none", False, 635)):
        res = []
        for dd, k in starts.items():
            if k + 25 >= n:
                continue
            lo15 = l[max(k - 15, 0):k].min()
            ent = None
            if wait == "none":
                ent = k
            else:
                for q in range(k, k + 15):
                    if q + 1 >= n:
                        break
                    if wait == "break" and c[q] < lo15:
                        ent = q + 1; break
                    if wait == "green" and c[q] > o[q]:
                        ent = q + 1; break
            if ent is None or ent + 2 >= n:
                continue
            e = o[ent]
            sl = e + 2 * atr[ent] if (use_sl and np.isfinite(atr[ent])) else np.inf
            ex = None
            for q in range(ent, n):
                if hm[q] >= exit_m or day[q] != dd:
                    ex = o[q]; break
                if h[q] >= sl:
                    ex = sl; break
            if ex is None:
                continue
            res.append((d.index[ent], (e - ex) * usd, sp[ent] * usd, (abs(e - sl) if np.isfinite(sl) else 2.0) * usd))
        rows.append((name, res))
    return rows


def report(title, rows, days):
    say(f"\n{title}")
    say("rule                              trades /day  win%   PF  half1 half2 stress last12$    net$  $/trade  by year")
    for name, res in rows:
        if len(res) < 20:
            say(f"{name:33s} {len(res):6d} (too few)"); continue
        T = pd.DataFrame(res, columns=["t", "net", "sp", "risk"])
        T["n"] = T.net - T.sp
        T["st"] = T.net - 1.5 * T.sp
        mid, end = T.t.iloc[len(T) // 2], T.t.max()
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].n.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        l12 = T[T.t >= end - pd.Timedelta(days=365)].n.sum()
        P, P1, P2 = pf(T.n.values), pf(T[T.t < mid].n.values), pf(T[T.t >= mid].n.values)
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and pf(T.st.values) >= 1.05 and l12 > 0
        say(f"{name:33s} {len(T):6d} {len(T) / days:4.2f} {100 * (T.n > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} "
            f"{SA.f2(pf(T.st.values))} {l12:+7.0f} {T.n.sum():+8.0f} {T.n.mean():+8.3f}  {yr} {'PASS' if ok else ''}")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    days = d.index.normalize().nunique()
    c1 = d.c.shift()
    tr = np.maximum(d.h - d.l, np.maximum((d.h - c1).abs(), (d.l - c1).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    say(f"XAUUSD M1 {d.index[0]:%Y-%m-%d} .. {d.index[-1]:%Y-%m-%d %H:%M} server, {len(d):,} bars, {days} days, "
        f"median spread ${np.median(d.s.values) * usd:.2f} at 0.01 lot")

    say("\n=== 1. MINUTE-OF-DAY SCAN (first half must give |t| >= 3.5, second half t >= 2 and PF >= 1.1) ===")
    tot_fake = 0
    for tz, nm in ((LON, "London"), (NYC, "New York")):
        R, nf, nw = minscan(d, usd, tz, nm)
        tot_fake += nf
        say(f"\n{nm} clock: {len(R)} survivors out of {nw} entry-minute / hold windows (chance control gave {nf})")
        if len(R):
            R = R.sort_values("net", ascending=False)
            say("  entry  hold side trades   PF  half1 half2 stress  t1   t2   $/trade    net$   last12$")
            for _, r in R.head(15).iterrows():
                say(f"  {int(r.m) // 60:02d}:{int(r.m) % 60:02d}  {int(r.h):3d}m {'BUY ' if r.side > 0 else 'SELL'} {int(r.n):6d} "
                    f"{SA.f2(r.pf)} {SA.f2(r.pf1)} {SA.f2(r.pf2)} {SA.f2(r.st)} {r.t1:4.1f} {r.t2:4.1f} {r.per:+8.3f} {r.net:+8.0f} {r.l12:+8.0f}")
    say(f"\ntotal chance survivors across both clocks: {tot_fake} (that is how many a shuffled control produced)")

    report("=== 2. BIG SPIKE FADE, wide stop ===", spikes(d, usd, atr), days)
    report("=== 3. HIGH-IMPACT USD NEWS ===", news(d, usd, atr), days)
    report("=== 4. LBMA PRE-AUCTION SELL, M1 entry timing (the live module is the baseline) ===", auction(d, usd, atr), days)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
