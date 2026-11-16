"""Round 126 (16 Nov 2026): after a FLIP close, let an INDICATOR choose the next direction instead of always reversing.
Owner: "senario kalau sell dah hit tp, kalau flip ori kita akan open buy terus tapi ada tak apa-apa indikator atau ema yang membantu untuk
kita tentukan open posisi sell atau buy ... mungkin tunggu indikator validkan arah kemudian baru kita follow".
NO D1:  after a stop the next trade goes the indicator's way at market (live: the opposite way).
D1 ON:  (v2.43, one side a day) after a stop re-enter the allowed side at market only when the indicator agrees; otherwise wait flat
        until it does (live: a stop $3 beyond the exit).
Indicators from the last CLOSED bar of their timeframe.  Controls: a random direction per 5 minutes (3 seeds), always the same way,
the indicator reversed.  Applied after a close in profit only, or after every stop.  Engines TRAIL (v2.35, trustworthy) and LADDER (v2.42 =
live stop, unreliable on M1 bars).  Last 3 months and the 3 before, OHLC and coin path order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip122 as P
F = P.F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
P.DATA = DATA; F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf; jit = F.jit


@jit
def sim(O, H, L, C, S, live, dayid, usd, D, lk, K, tgt, order_rand, seed, allow, eng, beoff, step, sig, use, onlyprof):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    wait = 0; armed = False
    pts = np.zeros(4)
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False; wait = 0; armed = False
        s = S[j]; al = allow[j]
        okL = al == 1 or al == 2; okS = al == -1 or al == 2
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + s
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0
            continue
        if not live[j]:
            oco = False; wait = 0
            continue
        if pos == 0 and wait != 0 and not done and sig[j] == wait and ((wait == 1 and okL) or (wait == -1 and okS)):
            if wait == 1:
                pos = 1; ent = O[j] + s; stop = O[j] - D
            else:
                pos = -1; ent = O[j]; stop = O[j] + s + D
            locked = False; wait = 0
        if pos == 0 and not done and not oco and wait == 0 and not armed and (okL or okS):
            oco = True; bs = O[j] + K; ss = O[j] - K; armed = True
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
                    pos = 1; ent = max(bs, a + s); stop = ent - s - D; locked = False; oco = False
                if pos == -1 and b + s >= stop:          # short stopped at px (ask)
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    nd = 1 if okL else -1                 # live choice
                    if use and (p > 0 or not onlyprof):
                        if al == 2:
                            nd = sig[j] if sig[j] != 2 else 1
                            if sig[j] == 3: nd = -1
                        else:
                            nd = al if sig[j] == al else 0
                    if nd == 0:
                        pos = 0; wait = al; oco = False
                    elif nd == 1 and okL:
                        pos = 1; ent = px; stop = px - s - D; locked = False
                    elif nd == -1 and okS and (use and (p > 0 or not onlyprof)):
                        pos = -1; ent = px - s; stop = ent + s + D; locked = False
                    else:                                  # live D1 wait: stop $K beyond the exit
                        pos = 0; oco = True; bs = px + K; ss = px - s - K
                if pos == 1:
                    pr = b - ent
                    if eng == 0:
                        if not locked:
                            if pr >= lk:
                                stop = max(stop, ent + lk - D); locked = True
                            else:
                                stop = max(stop, b - D)
                    elif pr >= lk:
                        stop = max(stop, ent + beoff + np.floor((pr - lk) / step + 1e-9) * step)
            else:
                if pos == 0 and oco and okS and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ent + s + D; locked = False; oco = False
                if pos == 1 and b <= stop:                # long stopped at px (bid)
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    nd = -1 if okS else 1
                    if use and (p > 0 or not onlyprof):
                        if al == 2:
                            nd = sig[j] if sig[j] != 2 else -1
                            if sig[j] == 3: nd = 1
                        else:
                            nd = al if sig[j] == al else 0
                    if nd == 0:
                        pos = 0; wait = al; oco = False
                    elif nd == -1 and okS:
                        pos = -1; ent = px; stop = px + s + D; locked = False
                    elif nd == 1 and okL and (use and (p > 0 or not onlyprof)):
                        pos = 1; ent = px + s; stop = ent - s - D; locked = False
                    else:
                        pos = 0; oco = True; bs = px + K; ss = px - K
                if pos == -1:
                    pr = ent - (b + s)
                    if eng == 0:
                        if not locked:
                            if pr >= lk:
                                stop = min(stop, ent - lk + D); locked = True
                            else:
                                stop = min(stop, b + s + D)
                    elif pr >= lk:
                        stop = min(stop, ent - beoff - np.floor((pr - lk) / step + 1e-9) * step)
    return xi[:m], pn[:m]


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
    nd = len(np.unique(dayid[live & (T >= a3)]))
    d1 = P.rs(full, "1D")
    d1rev = -P.sgn(P.to_m1(d1.c - d1.o, "1D", T)); d1rev[d1rev == -2] = 2
    ALL = np.full(len(T), 2, np.int64)

    m1 = full[["o", "h", "l", "c"]]
    m5 = P.rs(full, "5min"); m15 = P.rs(full, "15min"); h1 = P.rs(full, "1h")

    def rsi(c, n=14):
        g = c.diff().clip(lower=0); l_ = (-c.diff()).clip(lower=0)
        return 100 - 100 / (1 + P.wilder(g, n) / P.wilder(l_, n))

    def macdh(c):
        mm = P.ema(c, 12) - P.ema(c, 26); return mm - P.ema(mm, 9)

    SIG = {
        "M1 EMA20 slope": P.to_m1(P.ema(m1.c, 20).diff(), "1min", T),
        "M1 EMA50 slope": P.to_m1(P.ema(m1.c, 50).diff(), "1min", T),
        "M1 close vs EMA50": P.to_m1(m1.c - P.ema(m1.c, 50), "1min", T),
        "M1 RSI14 vs 50": P.to_m1(rsi(m1.c) - 50, "1min", T),
        "M5 EMA20 slope": P.to_m1(P.ema(m5.c, 20).diff(), "5min", T),
        "M5 close vs EMA50": P.to_m1(m5.c - P.ema(m5.c, 50), "5min", T),
        "M5 Supertrend 10,3": P.to_m1(P.supertrend(m5), "5min", T),
        "M5 MACD hist": P.to_m1(macdh(m5.c), "5min", T),
        "M5 RSI14 vs 50": P.to_m1(rsi(m5.c) - 50, "5min", T),
        "M15 EMA50 slope": P.to_m1(P.ema(m15.c, 50).diff(), "15min", T),
        "M15 Supertrend 10,3": P.to_m1(P.supertrend(m15), "15min", T),
        "H1 EMA50 slope": P.to_m1(P.ema(h1.c, 50).diff(), "1h", T),
        "momentum 15 min": P.to_m1(m1.c - m1.c.shift(15), "1min", T),
        "momentum 30 min": P.to_m1(m1.c - m1.c.shift(30), "1min", T),
    }
    SIG = {k: P.sgn(v) for k, v in SIG.items()}
    blk = ((T - T[0]) // pd.Timedelta("5min")).values.astype(np.int64)

    def row(lab, allow, eng, sig, use, onlyprof):
        args = (allow, eng, 0.5, 0.5, sig, use, onlyprof)
        out = [sim(O, H, L, C, S, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, orr, 1, *args) for orr in (False, True)]
        xS, pS = sim(O, H, L, C, S * 1.5, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, *args)
        xi, p = out[0]; te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        xc, pc = out[1]; tc = T[xc]
        say(f"{lab:30s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")

    say(f"FLIP: AN INDICATOR CHOOSES THE NEXT DIRECTION, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), gap $5, 0.01 lot")
    hdr = (f"{'next direction':30s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | "
           f"{'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    z = np.full(len(T), 2, np.int64)
    for eng, en, profs in ((0, "TRAIL v2.35 (trustworthy)", (False,)), (1, "LADDER v2.42 = live stop (UNRELIABLE)", (True, False))):
        for onlyprof in profs:
            for allow, an in ((ALL, "NO D1 filter"), (d1rev, "D1 filter ON (v2.43)")):
                say(""); say(f"=== {en}, {an}, after {'a close in PROFIT' if onlyprof else 'EVERY stop'} ==="); say(hdr)
                row("LIVE rule", allow, eng, z, False, onlyprof)
                for k, sg in SIG.items():
                    row(k, allow, eng, sg, True, onlyprof)
                    if k in ("M5 EMA20 slope", "M15 Supertrend 10,3", "momentum 30 min"):
                        rv = -sg; rv[sg == 2] = 2; row("   reversed", allow, eng, rv, True, onlyprof)
                if allow is ALL:
                    row("always the SAME way", allow, eng, np.ones(len(T), np.int64) * 0 + 3, True, onlyprof)
                for sd in (1, 2, 3):
                    r = np.random.default_rng(sd); rs_ = np.where(r.random(blk.max() + 1) < 0.5, 1, -1)[blk].astype(np.int64)
                    row(f"random direction s{sd}", allow, eng, rs_, True, onlyprof)


if __name__ == "__main__":
    main()
