"""Round 124 (16 Nov 2026): after FLIP is stopped (in profit, or any stop), wait for a LEVEL instead of reversing at market.
Owner: "mungkin lepas hit tp kau boleh place stop order dekat area2 yang possibility untuk sell" -> FLIP, "kau pilih sendiri".
Engines: TRAIL = v2.35 (trail $5, freeze at +$1; its stops are almost always losses), LADDER = v2.42 (fixed $5, at +$1 SL to
entry + $0.50, then $0.50 steps; NOT trustworthy on M1 bars, round 121g).  Live filter on top: D1REV (v2.43).
Re-entry after a stop: MKT = reverse at once (live); EXIT+-K = one opposite stop order K away from the exit; SWING N = opposite
stop at the lowest low / highest high of the last N minutes (M5 swing, entered at market if price is already through it);
OCO SWING N = stops at both swing levels.  APPLY = only after a stop in profit, or after every stop.
Last 3 months and the 3 before, OHLC and coin path order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip122 as P
F = P.F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
P.DATA = DATA; F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf; jit = F.jit
BIG = 1e18


@jit
def sim(O, H, L, C, S, live, dayid, usd, D, lk, K, tgt, order_rand, seed, allow, eng, beoff, step, mode, K2, swLo, swHi, onlyprof):
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
                    pos = 1; ent = max(bs, a + s); stop = ent - s - D; locked = False; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    use = mode > 0 and (p > 0 or not onlyprof) and okL
                    if use:
                        pos = 0; oco = True; ss = -BIG
                        if mode == 1: bs = px + K2
                        elif mode == 2: bs = max(swHi[j], px)
                        else:
                            bs = max(swHi[j], px)
                            if okS: ss = min(swLo[j], px - s)
                    elif okL:
                        pos = 1; ent = px; stop = px - s - D; locked = False
                    else:
                        pos = 0; oco = True; bs = px - s + K; ss = px - s - K
                        if mode > 0 and (p > 0 or not onlyprof):          # same-side re-entry level (D1 filter blocks the reversal)
                            if mode == 1: ss = px - s - K2
                            elif mode == 2: ss = min(swLo[j], px - s)
                            elif mode == 4: ss = px - s
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
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    use = mode > 0 and (p > 0 or not onlyprof) and okS
                    if use:
                        pos = 0; oco = True; bs = BIG
                        if mode == 1: ss = px - K2
                        elif mode == 2: ss = min(swLo[j], px)
                        else:
                            ss = min(swLo[j], px)
                            if okL: bs = max(swHi[j], px + s)
                    elif okS:
                        pos = -1; ent = px; stop = px + s + D; locked = False
                    else:
                        pos = 0; oco = True; bs = px + K; ss = px - K
                        if mode > 0 and (p > 0 or not onlyprof):
                            if mode == 1: bs = px + K2
                            elif mode == 2: bs = max(swHi[j], px + s)
                            elif mode == 4: bs = px + s
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
    SW = {}
    for nm in (15, 30, 60):
        SW[nm] = (pd.Series(L).rolling(nm, min_periods=1).min().shift(1).bfill().values,
                  pd.Series(H + S).rolling(nm, min_periods=1).max().shift(1).bfill().values)
    z = np.zeros(len(T))

    def row(lab, allow, eng, mode=0, K2=0.0, nm=30, onlyprof=True):
        lo, hi = SW[nm]
        args = (allow, eng, 0.5, 0.5, mode, K2, lo, hi, onlyprof)
        out = [sim(O, H, L, C, S, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, orr, 1, *args) for orr in (False, True)]
        xS, pS = sim(O, H, L, C, S * 1.5, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, *args)
        xi, p = out[0]; te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        xc, pc = out[1]; tc = T[xc]
        say(f"{lab:36s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")

    say(f"FLIP: WAIT FOR A LEVEL AFTER A STOP, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), gap $5, D1REV on, 0.01 lot")
    hdr = (f"{'variant':36s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | "
           f"{'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    for eng, en in ((0, "TRAIL v2.35"), (1, "LADDER v2.42 (unreliable)")):
        for onlyprof in ((False,) if eng == 0 else (True, False)):
            say(""); say(f"=== {en}, apply after {'a stop in PROFIT' if onlyprof else 'EVERY stop'} ==="); say(hdr)
            row("LIVE: D1REV, same side $3 away", d1rev, eng)
            say("-- with D1REV the reversal is blocked: these change the SAME-side re-entry level (live $3) --")
            row("same side at MARKET", d1rev, eng, 4, 0.0, 30, onlyprof)
            for k2 in (1.0, 5.0, 8.0):
                row(f"same side ${k2:g} beyond the exit", d1rev, eng, 1, k2, 30, onlyprof)
            for nm in (15, 30, 60):
                row(f"same side beyond the {nm}-min swing", d1rev, eng, 2, 0.0, nm, onlyprof)
            say("-- WITHOUT the D1 filter: opposite stop at a level instead of a market reversal --")
            row("no D1, MKT reverse", ALL, eng, 0, 0.0, 30, onlyprof)
            for k2 in (1.0, 3.0, 5.0):
                row(f"no D1, opposite stop ${k2:g} from exit", ALL, eng, 1, k2, 30, onlyprof)
            for nm in (15, 30, 60):
                row(f"no D1, opposite stop at {nm}-min swing", ALL, eng, 2, 0.0, nm, onlyprof)
            for nm in (15, 30, 60):
                row(f"no D1, OCO both swings {nm} min", ALL, eng, 3, 0.0, nm, onlyprof)


if __name__ == "__main__":
    main()
