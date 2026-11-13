"""Round 103 (13 Nov 2026): BTCUSD at JustMarkets, last 2 years.  Owner: "aku nak kau cari macam mana nak trade btc. kenapa ia
agak susah nak bina. cari bro".

Part 1 MEASURES why BTC has failed so far (rounds 87 / 98: PF 0.35-0.83): its spread against its moves on each timeframe, the
overnight swap against its daily range, weekend trading, the volatility and drift by hour and weekday per year, and whether its
moves persist (variance ratio, autocorrelation), with gold and EURUSD beside it for scale.
Part 2 TESTS the families that are said to work on crypto, each with the broker's spread and swap, rollover entries dropped:
  S1 session range breakout (Asia 01:30-09:00 / London 09:00-15:30 range, stop at the high / low, out 23:30, no swap)
  S2 H1 Donchian breakout, intraday (out 23:30), with / without a D1 trend filter
  S3 D1 trend-following swing (20-day breakout, exit on the 10-day opposite, SL 2 ATR(D1)); EMA 20/50 D1 - pays swap
  S4 time-of-day: every entry hour x hold 1/2/4/8 h, long and short; chosen on year 1, judged on year 2
  S5 weekday / weekend drift
  S6 M5 spike fade / follow with a cost gate (gold's M1 edge transplanted)
  S7 H1 mean reversion: RSI(2) with the EMA 200, BB 20,2 fade to the middle, intraday
  S8 Williams volatility breakout from the 01:30 open (k 0.3 / 0.5 / 0.7), out 23:30
  S9 the live gold SMC rule (M15 BOS + OB in the killzone, round 102c) and its neighbours, on BTC
Every trade has a RANDOM-direction twin and an ALWAYS-BUY twin at the same moment with the same SL / TP distances.
$ are per 0.01 lot (0.01 BTC: $1 of BTC move = $0.01).  Pass rule: >= 150 trades, PF >= 1.15, both years >= 1.05, stress
(1.5x spread) >= 1.05, last 12 months > 0, PF >= both twins + 0.10.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: float(v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9)) if len(v) else 0.0
try:
    from numba import njit
except Exception:
    njit = None


def _exits(O, H, L, S, day, ei, ep, dr, slp, tpp, xi, swl, sws):
    """per trade: enter at bar ei at price ep (dir dr), SL / TP prices, forced exit at the open of bar xi.
    SL first when SL and TP fall in one bar; on the entry bar only the SL is checked. Returns exit price, exit bar, nights."""
    m = len(ei); n = len(O)
    xp = np.zeros(m); xb = np.zeros(m, np.int64); ng = np.zeros(m)
    for k in range(m):
        i = ei[k]; d = dr[k]; sl = slp[k]; tp = tpp[k]; z = i; nights = 0; px = 0.0; done = False
        while z < n:
            if z > i and day[z] != day[z - 1]: nights += 1
            if z >= xi[k] and z > i:
                px = O[z] + (S[z] if d == -1 else 0.0); done = True; break
            if d == 1:
                if L[z] <= sl:
                    px = min(O[z], sl) if z > i else sl; done = True; break
                if z > i and tp == tp and H[z] >= tp:
                    px = max(O[z], tp); done = True; break
            else:
                if H[z] + S[z] >= sl:
                    px = max(O[z] + S[z], sl) if z > i else sl; done = True; break
                if z > i and tp == tp and L[z] + S[z] <= tp:
                    px = min(O[z] + S[z], tp); done = True; break
            z += 1
        if not done: z = n - 1; px = O[z]
        xp[k] = px; xb[k] = z; ng[k] = nights
    return xp, xb, ng


EX = njit(cache=False)(_exits) if njit else _exits


class Book:
    """turns a list of signals into trades with costs, plus the two twins"""

    def __init__(s, B, usd, swl, sws, start, mid, end):
        s.B = B; s.usd = usd; s.swl = swl; s.sws = sws; s.start = start; s.mid = mid; s.end = end
        s.O, s.H, s.L, s.C, s.S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
        s.T = B.index; s.day = B.index.normalize().values.astype("datetime64[D]").astype(np.int64)
        s.hm = (B.index.hour * 60 + B.index.minute).values
        s.rng = np.random.default_rng(103)

    def run(s, sig, one=True):
        """sig: DataFrame with i (entry bar), d (+1 / -1), ep (entry price or nan = market at the open), sl (distance),
        tp (distance or nan), x (forced exit bar). one = one position at a time."""
        if len(sig) == 0: return None
        sig = sig.sort_values("i").reset_index(drop=True)
        sig = sig[(s.hm[sig.i.values] >= 90) & (s.hm[sig.i.values] < 1425) & (s.T[sig.i.values] >= s.start)].reset_index(drop=True)
        if len(sig) == 0: return None
        i = sig.i.values.astype(np.int64); d = sig.d.values.astype(np.int64); x = sig.x.values.astype(np.int64)
        mk = np.where(d == 1, s.O[i] + s.S[i], s.O[i])
        ep = np.where(np.isnan(sig.ep.values), mk, sig.ep.values)
        dist = sig.sl.values.astype(float); tpd = sig.tp.values.astype(float)
        out = {}
        for lab, dd, e in (("sig", d, ep), ("rand", np.where(s.rng.random(len(d)) < 0.5, 1, -1), None), ("buy", np.ones(len(d), np.int64), None)):
            if e is None: e = np.where(dd == 1, s.O[i] + s.S[i], s.O[i])
            sl = e - dd * dist; tp = e + dd * tpd
            xp, xb, ng = EX(s.O, s.H, s.L, s.S, s.day, i, e, dd.astype(np.int64), sl, tp, x, s.swl, s.sws)
            swap = np.where(dd == 1, s.swl, s.sws) * ng
            pnl = ((xp - e) * dd + swap) * s.usd
            out[lab] = (pnl, xb, (xp - e) * dd * s.usd, swap * s.usd)
        pnl, xb, gross, swp = out["sig"]
        keep = np.ones(len(i), bool)
        if one:
            last = -1
            for k in range(len(i)):
                if i[k] <= last: keep[k] = False
                else: last = xb[k]
        t = s.T[i]
        r = dict(n=int(keep.sum()), t=t[keep], pnl=pnl[keep], d=d[keep], risk=dist[keep] * s.usd, swap=swp[keep],
                 sp=s.S[i][keep] * s.usd, rand=out["rand"][0][keep], buy=out["buy"][0][keep])
        return r


def line(name, r, mid, end):
    if r is None or r["n"] < 20: return None
    p, t = r["pnl"], r["t"]; y1 = t < mid
    a3, a6 = end - pd.Timedelta(days=91), end - pd.Timedelta(days=182)
    eq = np.cumsum(p); dd = float((eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min())
    st = pf(p - 0.5 * r["sp"])
    P, PR, PB = pf(p), pf(r["rand"]), pf(r["buy"])
    ok = (r["n"] >= 150 and P >= 1.15 and pf(p[y1]) >= 1.05 and pf(p[~y1]) >= 1.05 and st >= 1.05 and p[~y1].sum() > 0
          and P >= max(PR, PB) + 0.10)
    return dict(name=name, n=r["n"], wk=r["n"] / 104, win=100 * (p > 0).mean(), PF=P, y1=pf(p[y1]), y2=pf(p[~y1]), st=st,
                net=p.sum(), u12=p[~y1].sum(), u3=p[t >= a3].sum(), p3=p[(t >= a6) & (t < a3)].sum(), buy=pf(p[r["d"] == 1]),
                sell=pf(p[r["d"] == -1]), nb=int((r["d"] == 1).sum()), rand=PR, ab=PB, dd=dd, worst=float(p.min()),
                risk=float(np.nanmean(r["risk"])), swap=float(r["swap"].sum()), ok=ok)


HDR = (f"{'variant':52s} {'n':>5} {'/wk':>4} {'win':>3} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'net$':>6} {'12m$':>6} {'3m$':>5} "
       f"{'p3m$':>5} {'buys':>5} {'sells':>5} {'RAND':>5} {'BUY':>5} {'maxDD':>6} {'worst':>5} {'risk':>5} {'swap$':>6}")


def show(x):
    if x is None: return
    say(f"{x['name']:52s} {x['n']:5d} {x['wk']:4.1f} {x['win']:3.0f} {x['PF']:5.2f} {x['y1']:5.2f} {x['y2']:5.2f} {x['st']:5.2f} "
        f"{x['net']:+6.0f} {x['u12']:+6.0f} {x['u3']:+5.0f} {x['p3']:+5.0f} {x['buy']:5.2f} {x['sell']:5.2f} {x['rand']:5.2f} "
        f"{x['ab']:5.2f} {x['dd']:+6.0f} {x['worst']:+5.0f} {x['risk']:5.1f} {x['swap']:+6.0f} {'PASS' if x['ok'] else ''}")


def resample(B, m):
    g = B.resample(f"{m}min", label="left", closed="left")
    X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
    X["s"] = g.s.median().reindex(X.index).values
    return X


def atr(X, n=14):
    c1 = X.c.shift()
    tr = np.maximum(X.h - X.l, np.maximum((X.h - c1).abs(), (X.l - c1).abs()))
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def m5_index(B, times):
    """first M5 bar at or after each time"""
    return np.searchsorted(B.index.values, np.asarray(times, dtype="datetime64[ns]"), side="left")


def exit_bar(B, i, hhmm=1410):
    """the M5 bar at 23:30 server of the entry bar's day (or the next day's first bar if the day ends earlier)"""
    day = B.index.normalize()
    tgt = day[np.minimum(i, len(B) - 1)] + pd.Timedelta(minutes=hhmm)
    x = m5_index(B, tgt)
    return np.maximum(x, i + 1)


def measure(meta, SW):
    say("=" * 30 + " PART 1: WHY BTC IS HARD (last 2 years) " + "=" * 30)
    rows = []
    for sym in ("BTCUSD", "XAUUSD", "EURUSD"):
        if sym not in meta: continue
        mt = meta[sym]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
        d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
        end = d.index[-1]; d = d[d.index >= end - pd.Timedelta(days=730)]
        px = float(d.c.median()); sp = float(d.s.median())
        sw = SW.get(sym)
        swl = sw["long"] * mt["point"] if sw and sw["mode"] == 1 else 0; sws = sw["short"] * mt["point"] if sw and sw["mode"] == 1 else 0
        a = {}
        for m in (5, 15, 60, 240, 1440):
            X = d if m == 5 else resample(d, m)
            a[m] = float(atr(X).median())
        wd = d.index.day_of_week
        rows.append((sym, px, sp, usd, swl, sws, a, (wd >= 5).mean()))
        say(f"\n{sym}: median price {px:,.2f}, median spread {sp:,.4f} ({100 * sp / px:.4f}% of price) = ${sp * usd:.3f} per 0.01 lot")
        say("  median ATR(14) and the spread as a share of it:  " + "  ".join(
            f"{'M5' if m == 5 else 'M15' if m == 15 else 'H1' if m == 60 else 'H4' if m == 240 else 'D1'} ${a[m] * usd:.2f} "
            f"({100 * sp / a[m]:.1f}%)" for m in a))
        say(f"  swap per night at 0.01 lot: long ${swl * usd:+.3f}, short ${sws * usd:+.3f} = {100 * abs(swl) / a[1440]:.1f}% / "
            f"{100 * abs(sws) / a[1440]:.1f}% of a median D1 ATR; a year of nights = {100 * abs(swl) * 365 / px:.0f}% / "
            f"{100 * abs(sws) * 365 / px:.0f}% of the price")
        say(f"  share of M5 bars on Saturday / Sunday: {100 * (wd == 5).mean():.1f}% / {100 * (wd == 6).mean():.1f}%")
        if sym == "BTCUSD": BT = d
    d = BT; mt = meta["BTCUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    end = d.index[-1]; mid = end - pd.Timedelta(days=365)
    say("\nBTC spread and move size by server hour (median spread $, median |M5 move| $, spread / M5 ATR) at 0.01 lot")
    hr = d.index.hour; mv = (d.c - d.o).abs()
    a5 = atr(d)
    tab = pd.DataFrame({"sp": d.s * usd, "mv": mv * usd, "ratio": d.s / a5, "h": hr})
    g = tab.groupby("h").median()
    say("  " + "  ".join(f"{h:02d}:{g.sp[h]:.3f}/{g.mv[h]:.2f}/{g.ratio[h]:.2f}" for h in g.index))
    say("\nBTC signed H1 return by server hour, $ per 0.01 lot per bar, year 1 | year 2 (t-stat)")
    H1 = resample(d, 60); r = (H1.c - H1.o) * usd; y1 = H1.index < mid
    out = []
    for h in range(24):
        a_ = r[(H1.index.hour == h) & y1]; b_ = r[(H1.index.hour == h) & ~y1]
        ta = a_.mean() / (a_.std() / np.sqrt(len(a_))) if len(a_) > 2 else 0; tb = b_.mean() / (b_.std() / np.sqrt(len(b_))) if len(b_) > 2 else 0
        out.append(f"{h:02d}: {a_.mean():+.2f}({ta:+.1f}) | {b_.mean():+.2f}({tb:+.1f})")
    for k in range(0, 24, 4): say("  " + "   ".join(out[k:k + 4]))
    say("\nBTC signed D1 return by weekday ($ per 0.01 lot), year 1 | year 2")
    D1 = resample(d, 1440); rd = (D1.c - D1.o) * usd; y1d = D1.index < mid
    say("  " + "  ".join(f"{n}: {rd[(D1.index.day_of_week == k) & y1d].mean():+.1f} | {rd[(D1.index.day_of_week == k) & ~y1d].mean():+.1f}"
                         for k, n in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))))
    say("\nBTC persistence: variance ratio VR(q) of log returns (> 1 = trends, < 1 = reverts), year 1 | year 2")
    for base, qs in ((5, (3, 6, 12, 48)), (60, (4, 12, 24)), (1440, (5, 10, 20))):
        X = d if base == 5 else resample(d, base); lr = np.log(X.c).diff().dropna()
        s = []
        for q in qs:
            v = []
            for msk in (lr.index < mid, lr.index >= mid):
                x = lr[msk].values; v1 = x.var()
                xq = pd.Series(x).rolling(q).sum().dropna().values
                v.append(xq.var() / (q * v1))
            s.append(f"q{q}: {v[0]:.2f} | {v[1]:.2f}")
        say(f"  base {'M5' if base == 5 else 'H1' if base == 60 else 'D1'}: " + "   ".join(s))
    lr = np.log(D1.c).diff().dropna()
    say(f"  daily return autocorrelation lag 1: year 1 {lr[lr.index < mid].autocorr():+.3f}, year 2 {lr[lr.index >= mid].autocorr():+.3f}")
    say(f"  BTC over the window: {D1.c.iloc[0]:,.0f} -> {D1.c.iloc[-1]:,.0f} (high {D1.h.max():,.0f}, low {D1.l.min():,.0f})")


def strategies(meta, SW):
    say("\n" + "=" * 30 + " PART 2: STRATEGY FAMILIES ON BTC " + "=" * 30)
    mt = meta["BTCUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    sw = SW.get("BTCUSD")
    swl = sw["long"] * mt["point"] if sw and sw["mode"] == 1 else 0; sws = sw["short"] * mt["point"] if sw and sw["mode"] == 1 else 0
    d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    B = d[d.index >= start - pd.Timedelta(days=200)][["o", "h", "l", "c", "s"]].copy()
    bk = Book(B, usd, swl, sws, start, mid, end)
    say(f"window {start:%Y-%m-%d} .. {end:%Y-%m-%d}; swap long {swl * usd:+.3f} / short {sws * usd:+.3f} $ a night at 0.01 lot")
    res = []

    def go(name, sig, one=True):
        x = line(name, bk.run(sig, one), mid, end)
        if x: res.append(x); show(x)

    O, H, L, C = bk.O, bk.H, bk.L, bk.C
    day = B.index.normalize(); hm = bk.hm

    # S1 session range breakout
    say("\n-- S1 session range breakout (stop at the range high / low, first touch, out 23:30, one a day)"); say(HDR)
    for nm, a0, a1, last in (("Asia 01:30-09:00", 90, 540, 1380), ("pre-NY 09:00-15:30", 540, 930, 1380), ("Asia 01:30-07:00", 90, 420, 1380)):
        for slm, tpm in (("other side", np.nan), ("other side", 1.0), ("other side", 2.0), ("half range", 2.0)):
            sig = []
            for dd, grp in B.groupby(day):
                h = grp.index.hour * 60 + grp.index.minute
                rgn = grp[(h >= a0) & (h < a1)]
                if len(rgn) < (a1 - a0) / 5 * 0.8: continue
                hi, lo = rgn.h.max(), rgn.l.min(); rg = hi - lo
                if rg <= 0: continue
                after = grp[(h >= a1) & (h < last)]
                if not len(after): continue
                up = np.where(after.h.values >= hi)[0]; dn = np.where(after.l.values + after.s.values <= lo)[0]
                fu = up[0] if len(up) else 10 ** 9; fd = dn[0] if len(dn) else 10 ** 9
                if fu == fd == 10 ** 9: continue
                k = min(fu, fd); dr = 1 if fu < fd else -1
                ii = B.index.get_loc(after.index[k])
                ep = max(hi + after.s.values[k], O[ii] + bk.S[ii]) if dr == 1 else min(lo, O[ii])
                dist = rg if slm == "other side" else rg / 2
                sig.append((ii, dr, ep, dist, tpm * dist if tpm == tpm else np.nan))
            if not sig: continue
            sg = pd.DataFrame(sig, columns=["i", "d", "ep", "sl", "tp"]); sg["x"] = exit_bar(B, sg.i.values)
            go(f"S1 {nm} SL {slm} TP {'none' if tpm != tpm else f'{tpm:.0f}R'}", sg)

    # S2 H1 Donchian intraday
    say("\n-- S2 H1 Donchian breakout, intraday (enter on the next M5 bar after the H1 close, out 23:30)"); say(HDR)
    H1 = resample(B, 60); a1 = atr(H1); D1 = resample(B, 1440); e20d = D1.c.ewm(span=20, adjust=False).mean()
    d1tr = np.sign(D1.c - e20d).shift(1).reindex(H1.index.normalize()).values           # yesterday's close vs its EMA 20
    for N in (12, 24, 48):
        up = H1.c > H1.h.rolling(N).max().shift(1); dn = H1.c < H1.l.rolling(N).min().shift(1)
        for flt in (False, True):
            for slk, tpr in ((1.5, np.nan), (1.5, 2.0), (3.0, np.nan)):
                rows = []
                for k in np.where(up | dn)[0]:
                    dr = 1 if up.iloc[k] else -1
                    if flt and d1tr[k] != dr: continue
                    rows.append((H1.index[k] + pd.Timedelta(minutes=60), dr, slk * a1.iloc[k], tpr * slk * a1.iloc[k] if tpr == tpr else np.nan))
                if not rows: continue
                sg = pd.DataFrame(rows, columns=["tm", "d", "sl", "tp"]); sg["i"] = m5_index(B, sg.tm.values); sg = sg[sg.i < len(B) - 1]
                sg["ep"] = np.nan; sg["x"] = exit_bar(B, sg.i.values)
                go(f"S2 Donchian {N} H1{' +D1 trend' if flt else ''} SL {slk} ATR TP {'none' if tpr != tpr else f'{tpr:.0f}R'}", sg)

    # S3 D1 trend swing (pays swap)
    say("\n-- S3 D1 trend-following swing, holds overnight (pays the swap)"); say(HDR)
    aD = atr(D1)
    for nm, ent_n, ex_n in (("20/10 breakout", 20, 10), ("55/20 breakout", 55, 20)):
        hiN = D1.h.rolling(ent_n).max().shift(1); loN = D1.l.rolling(ent_n).min().shift(1)
        hiX = D1.h.rolling(ex_n).max().shift(1); loX = D1.l.rolling(ex_n).min().shift(1)
        rows = []; pos = 0; k0 = 0
        for k in range(len(D1)):
            if pos == 0:
                if D1.c.iloc[k] > hiN.iloc[k]: pos = 1; k0 = k
                elif D1.c.iloc[k] < loN.iloc[k]: pos = -1; k0 = k
                else: continue
                kx = k + 1
                while kx < len(D1) and not ((pos == 1 and D1.c.iloc[kx] < loX.iloc[kx]) or (pos == -1 and D1.c.iloc[kx] > hiX.iloc[kx])): kx += 1
                rows.append((D1.index[k] + pd.Timedelta(days=1, minutes=90), pos, 2 * aD.iloc[k], np.nan,
                             D1.index[min(kx, len(D1) - 1)] + pd.Timedelta(days=1, minutes=90)))
                pos = 0
        if rows:
            sg = pd.DataFrame(rows, columns=["tm", "d", "sl", "tp", "xt"]); sg["i"] = m5_index(B, sg.tm.values); sg["x"] = m5_index(B, sg.xt.values)
            sg = sg[sg.i < len(B) - 1]; sg["ep"] = np.nan
            go(f"S3 {nm}, SL 2 ATR(D1)", sg)
    e20, e50 = D1.c.ewm(span=20, adjust=False).mean(), D1.c.ewm(span=50, adjust=False).mean()
    cr = np.sign(e20 - e50); ch = np.where(cr.values[1:] != cr.values[:-1])[0] + 1
    rows = []
    for a_, b_ in zip(ch, list(ch[1:]) + [len(D1) - 1]):
        rows.append((D1.index[a_] + pd.Timedelta(days=1, minutes=90), int(cr.iloc[a_]), 3 * aD.iloc[a_], np.nan, D1.index[b_] + pd.Timedelta(days=1, minutes=90)))
    sg = pd.DataFrame(rows, columns=["tm", "d", "sl", "tp", "xt"]); sg["i"] = m5_index(B, sg.tm.values); sg["x"] = m5_index(B, sg.xt.values)
    sg = sg[(sg.i < len(B) - 1) & (sg.d != 0)]; sg["ep"] = np.nan
    go("S3 EMA 20/50 D1 cross, SL 3 ATR(D1)", sg)

    # S4 time of day, chosen on year 1
    say("\n-- S4 time-of-day: entry at HH:00 server, hold 1/2/4/8 h (no overnight), long / short; picked on year 1, judged on year 2")
    cells = []
    for h in range(2, 23):
        for hold in (1, 2, 4, 8):
            if h + hold > 23: continue
            tms = pd.DatetimeIndex(day.unique()) + pd.Timedelta(hours=h)
            ii = m5_index(B, tms); ii = ii[ii < len(B) - 1]
            ii = ii[(B.index[ii].hour == h)]
            xi = m5_index(B, B.index[ii] + pd.Timedelta(hours=hold))
            for dr in (1, -1):
                ep = np.where(dr == 1, O[ii] + bk.S[ii], O[ii]); xp = O[np.minimum(xi, len(B) - 1)] + (bk.S[np.minimum(xi, len(B) - 1)] if dr == -1 else 0)
                p = (xp - ep) * dr * usd; t = B.index[ii]
                okm = t >= start
                cells.append((h, hold, dr, p[okm & (t < mid)], p[okm & (t >= mid)]))
    sc = []
    for h, hold, dr, p1, p2 in cells:
        if len(p1) < 50: continue
        t1 = p1.mean() / (p1.std() / np.sqrt(len(p1)) + 1e-12)
        sc.append((t1, h, hold, dr, pf(p1), pf(p2), p1.sum(), p2.sum(), len(p2)))
    sc.sort(reverse=True)
    say(f"  {len(sc)} cells; top 12 by year-1 t-stat -> year 2:")
    for t1, h, hold, dr, P1, P2, s1, s2, n2 in sc[:12]:
        say(f"  {h:02d}:00 {'BUY ' if dr == 1 else 'SELL'} hold {hold} h: yr1 t {t1:+.1f} PF {P1:.2f} ${s1:+.0f} -> yr2 PF {P2:.2f} ${s2:+.0f} ({n2} days)")
    top = [x for x in sc if x[0] >= 2.0]
    say(f"  cells with year-1 t >= 2: {len(top)}; of those positive in year 2: {sum(1 for x in top if x[7] > 0)}; "
        f"all cells positive in year 2: {sum(1 for x in sc if x[7] > 0)} of {len(sc)}")

    # S5 weekday / weekend
    say("\n-- S5 weekday / weekend holds"); say(HDR)
    for nm, wd_, h0, hold_h, dr in (("Mon 01:30 -> 23:30 BUY", 0, 90, 22, 1), ("Mon 01:30 -> 23:30 SELL", 0, 90, 22, -1),
                                     ("Fri 01:30 -> 23:30 BUY", 4, 90, 22, 1), ("Fri 01:30 -> 23:30 SELL", 4, 90, 22, -1),
                                     ("Sat 01:30 -> Sun 23:30 BUY", 5, 90, 46, 1), ("Sat 01:30 -> Sun 23:30 SELL", 5, 90, 46, -1)):
        dd = pd.DatetimeIndex(day.unique()); dd = dd[dd.day_of_week == wd_]
        ii = m5_index(B, dd + pd.Timedelta(minutes=h0)); ok = ii < len(B) - 1; ii = ii[ok]
        if not len(ii): say(f"{nm}: no bars"); continue
        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 1e9, "tp": np.nan})
        sg["x"] = m5_index(B, B.index[ii].normalize() + pd.Timedelta(hours=hold_h + 1, minutes=30))
        go(f"S5 {nm}", sg)

    # S6 M5 spike fade / follow with a cost gate
    say("\n-- S6 M5 spike fade / follow: |bar| >= k ATR(M5) and ATR >= g x spread; next open, SL 0.3 ATR beyond the bar, out after 6 / 12 bars"); say(HDR)
    a5 = atr(B).values; body = C - O
    for k_ in (2.5, 3.0, 4.0):
        for g_ in (4, 8):
            for mode in ("fade", "follow"):
                for hold in (6, 12):
                    big = (np.abs(body) >= k_ * a5) & (a5 >= g_ * bk.S)
                    ii = np.where(big)[0] + 1; ii = ii[ii < len(B) - 1]
                    dr = -np.sign(body[ii - 1]) if mode == "fade" else np.sign(body[ii - 1])
                    ext = np.where(dr == 1, L[ii - 1], H[ii - 1])
                    entry_mk = np.where(dr == 1, O[ii] + bk.S[ii], O[ii])
                    dist = np.abs(entry_mk - (ext - dr * 0.3 * a5[ii - 1]))
                    sg = pd.DataFrame({"i": ii, "d": dr.astype(int), "ep": np.nan, "sl": dist, "tp": np.nan, "x": ii + hold})
                    sg = sg[sg.d != 0]
                    go(f"S6 {mode} k {k_} gate {g_} hold {hold}", sg)

    # S7 H1 mean reversion, intraday
    say("\n-- S7 H1 mean reversion, intraday (out at the exit rule, 12 bars or 23:30)"); say(HDR)
    c = H1.c; dl = c.diff()
    up_ = dl.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean(); dn_ = (-dl.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    rsi2 = 100 - 100 / (1 + up_ / dn_.replace(0, np.nan)); e200 = c.ewm(span=200, adjust=False).mean()
    m20 = c.rolling(20).mean(); s20 = c.rolling(20).std(ddof=0)
    for nm, cond_b, cond_s in (("RSI2 < 10 / > 90 with EMA 200", (rsi2 < 10) & (c > e200), (rsi2 > 90) & (c < e200)),
                               ("RSI2 < 5 / > 95, no trend filter", rsi2 < 5, rsi2 > 95),
                               ("BB 20,2 close outside, fade", c < m20 - 2 * s20, c > m20 + 2 * s20)):
        for slk in (1.5, 3.0):
            rows = []
            for k in np.where(cond_b | cond_s)[0]:
                dr = 1 if cond_b.iloc[k] else -1
                rows.append((H1.index[k] + pd.Timedelta(minutes=60), dr, slk * a1.iloc[k], abs(m20.iloc[k] - c.iloc[k]) if "BB" in nm else np.nan))
            sg = pd.DataFrame(rows, columns=["tm", "d", "sl", "tp"]); sg["i"] = m5_index(B, sg.tm.values); sg = sg[sg.i < len(B) - 1]
            sg["ep"] = np.nan; sg["x"] = np.minimum(sg.i.values + 144, exit_bar(B, sg.i.values))
            go(f"S7 {nm} SL {slk} ATR(H1)", sg)

    # S8 Williams volatility breakout
    say("\n-- S8 Williams volatility breakout from the 01:30 open (stop at open +- k x yesterday's range), SL at the open, out 23:30"); say(HDR)
    prev_rg = (D1.h - D1.l).shift(1)
    for k_ in (0.3, 0.5, 0.7):
        for dirs in ("both", "buy only"):
            rows = []
            for dd, grp in B.groupby(day):
                if dd not in prev_rg.index or not prev_rg.loc[dd] == prev_rg.loc[dd]: continue
                h = grp.index.hour * 60 + grp.index.minute; g2 = grp[(h >= 90) & (h < 1380)]
                if not len(g2): continue
                op = g2.o.iloc[0]; lvl = k_ * prev_rg.loc[dd]
                up = np.where(g2.h.values >= op + lvl)[0]; dn = np.where(g2.l.values + g2.s.values <= op - lvl)[0] if dirs == "both" else np.array([], int)
                fu = up[0] if len(up) else 10 ** 9; fd = dn[0] if len(dn) else 10 ** 9
                if fu == fd == 10 ** 9: continue
                kk = min(fu, fd); dr = 1 if fu < fd else -1
                ii = B.index.get_loc(g2.index[kk])
                ep = max(op + lvl + g2.s.values[kk], O[ii] + bk.S[ii]) if dr == 1 else min(op - lvl, O[ii])
                rows.append((ii, dr, ep, lvl, np.nan))
            sg = pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp"]); sg["x"] = exit_bar(B, sg.i.values)
            go(f"S8 Williams k {k_} {dirs}", sg)

    # S9 the gold SMC rule on BTC
    say("\n-- S9 the live gold SMC rule (round 102c) on BTC"); say(HDR)
    try:
        import smc102 as SM
        SM.PAIRS = ((15, 240), (10, 240), (20, 240)); SM.BUY_CTRL = True
        A, END = SM.run("BTCUSD", mt, sw)
        for c_ in ("entry", "tp", "typ"): A[c_] = A[c_].astype(str)
        A = A.sort_values("t", kind="stable")
        kz = ((A.hr >= 9) & (A.hr < 12)) | ((A.hr >= 14) & (A.hr < 17))
        for tf in (10, 15, 20):
            for n_ in (3, 5):
                for en in ("OB top", "OTE 0.705"):
                    for tp in ("2R", "3R"):
                        g = A[(A.tf == tf) & (A.n == n_) & (A.entry == en) & (A.tp == tp) & (A.typ == "BOS") & kz]
                        g = SM.busy(g)
                        if len(g) < 20: continue
                        r = dict(n=len(g), t=pd.DatetimeIndex(g.t), pnl=(g.r * g.risk).values.astype(float), d=g.d.values, risk=g.risk.values.astype(float),
                                 swap=np.zeros(len(g)), sp=(g.sp * g.risk).values.astype(float), rand=(g.rr * g.risk).values.astype(float),
                                 buy=(g.rb * g.risk).values.astype(float))
                        r["rand"] = r["rand"][~np.isnan(r["rand"])]; r["buy"] = r["buy"][~np.isnan(r["buy"])]
                        x = line(f"S9 SMC M{tf}/H4 n{n_} BOS killzone {en} TP {tp}", r, mid, END)
                        if x: res.append(x); show(x)
    except Exception as e:
        say(f"S9 skipped: {e}")

    R = pd.DataFrame(res)
    say(f"\nSUMMARY: {int(R.ok.sum())} of {len(R)} BTC variants pass "
        f"({int((R.n >= 150).sum())} with >= 150 trades); median PF {R.PF.median():.2f}, random twin {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
    say("by family (median PF / best PF / median random twin):")
    R["fam"] = R.name.str.split(" ").str[0]
    for f, g in R.groupby("fam"):
        say(f"  {f}: {len(g):3d} rows  PF median {g.PF.median():.2f}  best {g.PF.max():.2f}  rand {g.rand.median():.2f}  "
            f"buys {g.buy.median():.2f}  sells {g.sell.median():.2f}  swap $ median {g.swap.median():+.0f}")
    say("\nTOP 15 by PF (>= 100 trades)"); say(HDR)
    for x in R[R.n >= 100].sort_values("PF", ascending=False).head(15).to_dict("records"): show(x)
    if R.ok.any():
        say("\nPASSES"); say(HDR)
        for x in R[R.ok].sort_values("PF", ascending=False).to_dict("records"): show(x)
    say(f"\ndone in {time.time() - T0:.0f} s")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps()
    say(f"numba: {'yes' if njit else 'no'}")
    measure(meta, SW)
    strategies(meta, SW)


if __name__ == "__main__":
    main()
