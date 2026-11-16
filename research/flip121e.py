"""Round 121e (16 Nov 2026): make the real-time FLIP cope with chop WITHOUT stopping for the day.  Owner: "aku tak nak stop tapi aku nak
kau perbaiki apa yang patut. cari jalan".  After N losing closes in a row (N 2-5) the module changes behaviour until it gets a winner:
  WIDEN  the stop gap becomes $D2 (8 / 10 / 15) for the next trades;
  RANGE  no reversal; go flat and place an OCO at the high + B / low - B of the bid since the losing streak began (B 0 / 1 / 3), i.e. wait
         for price to break out of the chop, then the live rule again;
  REARM  no reversal; OCO at the exit price +- B (3 / 5 / 8).
Live v2.35 otherwise (OCO +-$3 at 01:30, $5 real-time trail, lock +$1, $25 target, out 23:30).  Path engine of round 121, last 3 months
and the 3 before, OHLC and coin order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf
jit = F.jit


@jit
def sim(O, H, L, C, S, live, first, dayid, usd, D, lk, K, tgt, order_rand, seed, maxc, mode, D2, B):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    pts = np.zeros(4); cons = 0; Dc = D; rhi = 0.0; rlo = 0.0
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False; cons = 0; Dc = D
        s = S[j]
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + s
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0
            continue
        if not live[j]:
            oco = False
            continue
        if first[j] and pos == 0 and not done:
            oco = True; bs = O[j] + K; ss = O[j] - K; rhi = O[j]; rlo = O[j]
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
            if b > rhi: rhi = b
            if b < rlo: rlo = b
            if b >= a:
                if pos == 0 and oco and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = ent - s - Dc; locked = False; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if p < 0:
                        cons += 1
                    else:
                        cons = 0; Dc = D; rhi = b; rlo = b
                    if maxc > 0 and cons >= maxc and mode == 1:
                        Dc = D2
                    if maxc > 0 and cons >= maxc and mode >= 2:
                        pos = 0; oco = True
                        if mode == 2:
                            bs = rhi + s + B; ss = rlo - B
                        else:
                            bs = px + B; ss = px - s - B
                        cons = 0; Dc = D; rhi = b; rlo = b
                    else:
                        pos = 1; ent = px; stop = px - s - Dc; locked = False
                if pos == 1 and not locked:
                    if b - ent >= lk:
                        stop = max(stop, ent + lk - Dc); locked = True
                    else:
                        stop = max(stop, b - Dc)
            else:
                if pos == 0 and oco and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ent + s + Dc; locked = False; oco = False
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if p < 0:
                        cons += 1
                    else:
                        cons = 0; Dc = D; rhi = b; rlo = b
                    if maxc > 0 and cons >= maxc and mode == 1:
                        Dc = D2
                    if maxc > 0 and cons >= maxc and mode >= 2:
                        pos = 0; oco = True
                        if mode == 2:
                            bs = rhi + s + B; ss = rlo - B
                        else:
                            bs = px + s + B; ss = px - B
                        cons = 0; Dc = D; rhi = b; rlo = b
                    else:
                        pos = -1; ent = px; stop = px + s + Dc; locked = False
                if pos == -1 and not locked:
                    if ent - (b + s) >= lk:
                        stop = min(stop, ent - lk + Dc); locked = True
                    else:
                        stop = min(stop, b + s + Dc)
    return xi[:m], pn[:m]


def main():
    mt, sw = F.W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = F.SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    nd = len(np.unique(dayid[live & (T >= a3)]))
    say(f"REAL-TIME FLIP, CHOP HANDLING, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), gap $5, 0.01 lot")
    say(f"{'rule':26s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | {'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    cells = [("LIVE", 0, 0, 0.0, 0.0)]
    for N in (2, 3, 4, 5):
        cells += [(f"WIDEN ${x:g} after {N}", N, 1, x, 0.0) for x in (8.0, 10.0, 15.0)]
        cells += [(f"RANGE +{x:g} after {N}", N, 2, 0.0, x) for x in (0.0, 1.0, 3.0)]
        cells += [(f"REARM +-{x:g} after {N}", N, 3, 0.0, x) for x in (3.0, 5.0, 8.0)]
    for lab, N, md, d2, B in cells:
        xi, p = sim(O, H, L, C, S, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, N, md, d2, B)
        xc, pc = sim(O, H, L, C, S, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, True, 1, N, md, d2, B)
        xS, pS = sim(O, H, L, C, S * 1.5, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, N, md, d2, B)
        te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        tc = T[xc]
        say(f"{lab:26s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")


if __name__ == "__main__":
    main()
