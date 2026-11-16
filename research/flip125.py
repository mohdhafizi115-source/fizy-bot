"""Round 125 (16 Nov 2026): FLIP with the D1 filter (v2.43), where to place the SECOND order of the same side after a close.
Owner: "kita still follow D1 ... kalau D1 merah, kita buy flip m1 berterusan tapi lepas hit tp, second order tu boleh ke place order kat
tempat2 yang possibility tinggi? sop tetap jalan macam biasa".  Live: after a stop the module waits with a STOP order $3 beyond the
exit (buy stop above for a buy day).  Tested instead: a LIMIT on a pullback (buy limit below for a buy day):
  exit -$X, the low (high) of the last N minutes, the entry price of the trade just closed, the M1 EMA 100 (~ M5 EMA 20),
  each alone or together with the live $3 stop (whichever fills first).
Applied after a stop in profit only, or after every stop.  Doji days (both sides allowed) keep the live market reversal.
Engines: TRAIL (v2.35, trustworthy; its stops are losses, so only 'every stop' means anything) and LADDER (v2.42, the live stop,
NOT trustworthy on M1 bars, round 121g).  Last 3 months and the 3 before, OHLC and coin path order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip122 as P
F = P.F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
P.DATA = DATA; F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf; jit = F.jit


@jit
def sim(O, H, L, C, S, live, dayid, usd, D, lk, K, tgt, order_rand, seed, allow, eng, beoff, step,
        rmode, X, swLoB, swHiB, ema, onlyprof, combo):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    lim = 0; lvB = 0.0; lvS = 0.0
    pts = np.zeros(4)
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False; lim = 0
        s = S[j]; al = allow[j]
        okL = al == 1 or al == 2; okS = al == -1 or al == 2
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + s
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0
            continue
        if not live[j]:
            oco = False; lim = 0
            continue
        if pos == 0 and not done and not oco and lim == 0 and (okL or okS):
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
            if b >= a:                                   # rising
                if pos == 0 and oco and okL and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = ent - s - D; locked = False; oco = False; lim = 0
                if pos == 0 and lim == -1 and okS and b >= lvS:
                    pos = -1; ent = max(lvS, a); stop = ent + s + D; locked = False; oco = False; lim = 0
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    old = ent
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okL:                              # doji day: reverse at market (live)
                        pos = 1; ent = px; stop = px - s - D; locked = False
                    else:                                # shorts only: wait for the next short
                        pos = 0; oco = True; bs = px + K; ss = px - s - K
                        if rmode > 0 and (p > 0 or not onlyprof):
                            lim = -1
                            if rmode == 1: lvS = px - s + X
                            elif rmode == 2: lvS = max(swHiB[j], px - s)
                            elif rmode == 3: lvS = max(old, px - s)
                            else: lvS = max(ema[j], px - s)
                            if not combo: oco = False
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
            else:                                        # falling
                if pos == 0 and oco and okS and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ent + s + D; locked = False; oco = False; lim = 0
                if pos == 0 and lim == 1 and okL and b + s <= lvB:
                    pos = 1; ent = min(lvB, a + s); stop = ent - s - D; locked = False; oco = False; lim = 0
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    old = ent
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okS:
                        pos = -1; ent = px; stop = px + s + D; locked = False
                    else:                                # buys only: wait for the next buy
                        pos = 0; oco = True; bs = px + K; ss = px - K
                        if rmode > 0 and (p > 0 or not onlyprof):
                            lim = 1
                            if rmode == 1: lvB = px + s - X
                            elif rmode == 2: lvB = min(swLoB[j] + s, px + s)
                            elif rmode == 3: lvB = min(old, px + s)
                            else: lvB = min(ema[j] + s, px + s)
                            if not combo: oco = False
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
    SW = {nm: (pd.Series(L).rolling(nm, min_periods=1).min().shift(1).bfill().values,
               pd.Series(H).rolling(nm, min_periods=1).max().shift(1).bfill().values) for nm in (15, 30, 60)}
    ema = pd.Series(C).ewm(span=100, adjust=False).mean().shift(1).bfill().values

    def row(lab, eng, onlyprof, rmode=0, X=0.0, nm=30, combo=False):
        lo, hi = SW[nm]
        args = (d1rev, eng, 0.5, 0.5, rmode, X, lo, hi, ema, onlyprof, combo)
        out = [sim(O, H, L, C, S, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, orr, 1, *args) for orr in (False, True)]
        xS, pS = sim(O, H, L, C, S * 1.5, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, *args)
        xi, p = out[0]; te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        xc, pc = out[1]; tc = T[xc]
        say(f"{lab:38s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")

    say(f"FLIP + D1 FILTER: WHERE TO PUT THE NEXT SAME-SIDE ORDER, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), 0.01 lot")
    hdr = (f"{'next order':38s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | "
           f"{'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    for eng, en, profs in ((0, "TRAIL v2.35 (trustworthy)", (False,)), (1, "LADDER v2.42 = live stop (UNRELIABLE)", (True, False))):
        for onlyprof in profs:
            say(""); say(f"=== {en}, after {'a close in PROFIT' if onlyprof else 'EVERY stop'} ==="); say(hdr)
            row("LIVE: stop $3 beyond the exit", eng, onlyprof)
            for combo in (False, True):
                tag = " + $3 stop" if combo else ""
                for X in (1.0, 2.0, 3.0, 5.0):
                    row(f"LIMIT exit -${X:g}{tag}", eng, onlyprof, 1, X, 30, combo)
                for nm in (15, 30, 60):
                    row(f"LIMIT at {nm}-min low/high{tag}", eng, onlyprof, 2, 0.0, nm, combo)
                row(f"LIMIT at the closed trade's entry{tag}", eng, onlyprof, 3, 0.0, 30, combo)
                row(f"LIMIT at M1 EMA 100{tag}", eng, onlyprof, 4, 0.0, 30, combo)


if __name__ == "__main__":
    main()
