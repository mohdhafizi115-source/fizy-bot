"""Round 122 (16 Nov 2026): indicator FILTERS on the stable real-time FLIP (v2.35 / v2.41).
Owner: "kau undo balik flip ni pada version yang paling stabil dan kau cuba backtest kot ada indikator yang membantu untuk filter".
Engine = round 121 TICK (stop $5 trailed in real time, frozen at +$1, reverse on a stop, OCO at the 01:30 open +- $3, $25 target,
out 23:30, weekdays).  A filter gives each M1 bar a permission from the LAST CLOSED higher-timeframe bar:
  +1 = longs only, -1 = shorts only, 2 = both, 0 = none.
A reversal into a direction that is not allowed -> go flat; while flat and allowed, an OCO is armed at the current price +- $3 and only
an allowed side can fill.  An open position is never closed by the filter (only its stop / 23:30 / the target).
Direction filters are run with their REVERSED twin and a RANDOM sign per H4 bar (3 seeds); regime filters (both / none) with a random
mask of the same share.  Last 3 months and the 3 before, OHLC and coin path order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf; jit = F.jit


@jit
def sim(O, H, L, C, S, live, first, dayid, usd, D, lk, K, tgt, order_rand, seed, allow):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    pts = np.zeros(4)
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False
        s = S[j]; al = allow[j]
        okL = al == 1 or al == 2; okS = al == -1 or al == 2
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + s
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0
            continue
        if not live[j]:
            oco = False
            continue
        if pos == 0 and not done and not oco and (okL or okS):
            oco = True; bs = O[j] + K; ss = O[j] - K
        up = C[j] >= O[j]
        if order_rand: up = np.random.random() < 0.5
        pts[0] = O[j]; pts[3] = C[j]
        if up:
            pts[1] = L[j]; pts[2] = H[j]
        else:
            pts[1] = H[j]; pts[2] = L[j]
        for q in range(3):
            a = pts[q]; b = pts[q + 1]
            if done: break
            if b >= a:
                if pos == 0 and oco and okL and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = bs - D; locked = False; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okL:
                        pos = 1; ent = px; stop = px - s - D; locked = False
                    else:
                        pos = 0; oco = True; bs = px - s + K; ss = px - s - K
                if pos == 1 and not locked:
                    if b - ent >= lk:
                        stop = max(stop, ent + lk - D); locked = True
                    else:
                        stop = max(stop, b - D)
            else:
                if pos == 0 and oco and okS and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ss + D; locked = False; oco = False
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okS:
                        pos = -1; ent = px; stop = px + s + D; locked = False
                    else:
                        pos = 0; oco = True; bs = px + K; ss = px - K
                if pos == -1 and not locked:
                    if ent - (b + s) >= lk:
                        stop = min(stop, ent - lk + D); locked = True
                    else:
                        stop = min(stop, b + s + D)
    return xi[:m], pn[:m]


# ---------- higher-timeframe indicators, known from the bar's CLOSE ----------
def rs(d, fr):
    r = d.resample(fr, label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    return r


def to_m1(sr, fr, T):
    sr = sr.copy(); sr.index = sr.index + pd.Timedelta(fr)
    return sr.reindex(T, method="ffill").values


def ema(x, n): return x.ewm(span=n, adjust=False).mean()


def wilder(x, n): return x.ewm(alpha=1.0 / n, adjust=False).mean()


def atr(r, n):
    pc = r.c.shift(1)
    tr = pd.concat([r.h - r.l, (r.h - pc).abs(), (r.l - pc).abs()], axis=1).max(axis=1)
    return wilder(tr, n)


def adx(r, n=14):
    up = r.h.diff(); dn = -r.l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(r, n)
    pdi = 100 * wilder(pd.Series(pdm, r.index), n) / a; mdi = 100 * wilder(pd.Series(mdm, r.index), n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return wilder(dx, n), pdi, mdi


def supertrend(r, n=10, k=3.0):
    a = atr(r, n).values; hl = ((r.h + r.l) / 2).values; c = r.c.values
    ub = hl + k * a; lb = hl - k * a; dirn = np.ones(len(c)); fu = ub.copy(); fl = lb.copy()
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        dirn[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else dirn[i - 1])
    return pd.Series(dirn, r.index)


def chop(r, n=14):
    tr = atr(r, 1)
    return 100 * np.log10(tr.rolling(n).sum() / (r.h.rolling(n).max() - r.l.rolling(n).min())) / np.log10(n)


def sgn(x): return np.where(np.isnan(x), 2, np.where(x > 0, 1, -1)).astype(np.int64)


def main():
    mt, sw = F.W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = F.SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    full = d
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    nd = len(np.unique(dayid[live & (T >= a3)]))

    h1 = rs(full, "1h"); h4 = rs(full, "4h"); m15 = rs(full, "15min"); d1 = rs(full, "1D")
    DIR = {}
    for n_ in (20, 50, 100):
        DIR[f"H4 EMA{n_} slope"] = sgn(to_m1(ema(h4.c, n_).diff(), "4h", T))
    DIR["H4 EMA20>EMA50"] = sgn(to_m1(ema(h4.c, 20) - ema(h4.c, 50), "4h", T))
    DIR["H4 close vs EMA50"] = sgn(to_m1(h4.c - ema(h4.c, 50), "4h", T))
    DIR["H4 Supertrend 10,3"] = sgn(to_m1(supertrend(h4), "4h", T))
    DIR["H4 MACD hist"] = sgn(to_m1((ema(h4.c, 12) - ema(h4.c, 26)) - ema(ema(h4.c, 12) - ema(h4.c, 26), 9), "4h", T))
    DIR["H1 EMA50 slope"] = sgn(to_m1(ema(h1.c, 50).diff(), "1h", T))
    DIR["H1 EMA50>EMA200"] = sgn(to_m1(ema(h1.c, 50) - ema(h1.c, 200), "1h", T))
    DIR["H1 Supertrend 10,3"] = sgn(to_m1(supertrend(h1), "1h", T))
    DIR["H1 RSI14 vs 50"] = sgn(to_m1((wilder(h1.c.diff().clip(lower=0), 14) / wilder((-h1.c.diff()).clip(lower=0), 14)) - 1, "1h", T))
    _, pdi, mdi = adx(h1)
    DIR["H1 DI+ vs DI-"] = sgn(to_m1(pdi - mdi, "1h", T))
    DIR["M15 EMA200 side"] = sgn(to_m1(m15.c - ema(m15.c, 200), "15min", T))
    DIR["M15 Supertrend 10,3"] = sgn(to_m1(supertrend(m15), "15min", T))
    DIR["D1 EMA20 slope"] = sgn(to_m1(ema(d1.c, 20).diff(), "1D", T))
    DIR["D1 yesterday colour"] = sgn(to_m1(d1.c - d1.o, "1D", T))
    DIR["D1 yesterday colour REV"] = -DIR["D1 yesterday colour"]; DIR["D1 yesterday colour REV"][DIR["D1 yesterday colour"] == 2] = 2

    REG = {}
    ax, _, _ = adx(h1)
    for lv in (20, 25):
        v = to_m1(ax, "1h", T); REG[f"H1 ADX >= {lv}"] = np.where(np.isnan(v) | (v >= lv), 2, 0).astype(np.int64)
    for lv in (50.0, 61.8):
        v = to_m1(chop(m15), "15min", T); REG[f"M15 CHOP < {lv:g}"] = np.where(np.isnan(v) | (v < lv), 2, 0).astype(np.int64)
        v = to_m1(chop(h1), "1h", T); REG[f"H1 CHOP < {lv:g}"] = np.where(np.isnan(v) | (v < lv), 2, 0).astype(np.int64)
    am = to_m1(atr(m15, 14), "15min", T); sm = pd.Series(S, T).rolling(60, min_periods=1).median().values
    for g in (20, 30):
        REG[f"ATR(M15) >= {g} x spread"] = np.where(am >= g * sm, 2, 0).astype(np.int64)
    ah = to_m1(atr(h1, 14) / atr(h1, 14).rolling(100).mean(), "1h", T)
    REG["H1 ATR14 > its 100-bar mean"] = np.where(np.isnan(ah) | (ah > 1), 2, 0).astype(np.int64)
    REG["H1 ATR14 < its 100-bar mean"] = np.where(np.isnan(ah) | (ah < 1), 2, 0).astype(np.int64)

    h4id = ((T - T[0]) // pd.Timedelta("4h")).values.astype(np.int64)

    def row(lab, allow):
        out = []
        for orr in (False, True):
            xi, p = sim(O, H, L, C, S, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, orr, 1, allow)
            out.append((xi, p))
        xS, pS = sim(O, H, L, C, S * 1.5, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, allow)
        xi, p = out[0]; te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        xc, pc = out[1]; tc = T[xc]
        say(f"{lab:30s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")

    say(f"REAL-TIME FLIP (v2.35 / v2.41) + INDICATOR FILTERS, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), gap $5, 0.01 lot")
    say(f"{'filter':30s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | {'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    row("NONE (live)", np.full(len(T), 2, np.int64))
    say("-- direction filters (+ reversed twin) --")
    for k, a in DIR.items():
        row(k, a)
        if "REV" not in k:
            r = -a; r[a == 2] = 2; row("   reversed", r)
    say("-- random direction per H4 bar --")
    for sd in (1, 2, 3):
        rng = np.random.default_rng(sd); sg = np.where(rng.random(h4id.max() + 1) < 0.5, 1, -1)
        row(f"random H4 sign seed {sd}", sg[h4id].astype(np.int64))
    say("-- regime filters (trade / pause) + random mask of the same share --")
    for k, a in REG.items():
        row(k, a)
        sh = (a[live] == 2).mean(); rng = np.random.default_rng(7); mk = np.where(rng.random(h4id.max() + 1) < sh, 2, 0)
        row(f"   random {100 * sh:.0f}% of H4 bars", mk[h4id].astype(np.int64))


if __name__ == "__main__":
    main()
