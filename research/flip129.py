"""Round 129 (16 Nov 2026): FLIP v2.44 with a TIGHTENING real-time trail.  Owner: "sl tu real time naik sikit2 sampai lock profit. bukan terus be ...
kalau gold junam 100pip, maybe sl tu dah lock profit dekat 80-90pip".
eng 3: the stop follows the price at distance d = max(Tmin, D - k * profit) (profit = best price so far vs the entry, >= 0), never loosened:
$D behind at the entry, tightening by $k per $1 of profit down to $Tmin.  eng 0 / 1 / 2 as round 128.
Last 3 months and the 3 before, OHLC and coin path order, 0.01 lot."""
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
        rmode, X, swLoB, swHiB, ema, onlyprof, combo, R):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    lim = 0; lvB = 0.0; lvS = 0.0; rj = -1
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
            oco = True; bs = O[j] + K; ss = O[j] - K; rj = -1
        if R > 0 and pos == 0 and oco and rj >= 0 and j - rj >= R:
            bs = O[j] + s + K; ss = O[j] - K; rj = j
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
                    pos = 1; ent = max(bs, a + s); stop = ent - s - D; locked = False; oco = False; lim = 0; rj = -1
                if pos == 0 and lim == -1 and okS and b >= lvS:
                    pos = -1; ent = max(lvS, a); stop = ent + s + D; locked = False; oco = False; lim = 0; rj = -1
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    old = ent
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okL:                              # doji day: reverse at market (live)
                        pos = 1; ent = px; stop = px - s - D; locked = False
                    else:                                # shorts only: wait for the next short
                        pos = 0; oco = True; bs = px + K; ss = px - s - K
                        rj = j if (p > 0 or not onlyprof) else -1
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
                    elif eng == 3:
                        stop = max(stop, b - max(beoff, D - step * max(pr, 0.0)))
                    elif eng == 2:
                        if pr >= lk: stop = max(stop, b - beoff)
                    elif pr >= lk:
                        stop = max(stop, ent + beoff + np.floor((pr - lk) / step + 1e-9) * step)
            else:                                        # falling
                if pos == 0 and oco and okS and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ent + s + D; locked = False; oco = False; lim = 0; rj = -1
                if pos == 0 and lim == 1 and okL and b + s <= lvB:
                    pos = 1; ent = min(lvB, a + s); stop = ent - s - D; locked = False; oco = False; lim = 0; rj = -1
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    old = ent
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okS:
                        pos = -1; ent = px; stop = px + s + D; locked = False
                    else:                                # buys only: wait for the next buy
                        pos = 0; oco = True; bs = px + K; ss = px - K
                        rj = j if (p > 0 or not onlyprof) else -1
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
                    elif eng == 3:
                        stop = min(stop, b + s + max(beoff, D - step * max(pr, 0.0)))
                    elif eng == 2:
                        if pr >= lk: stop = min(stop, b + s + beoff)
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
    T = d.index; T_ = T; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    nd = len(np.unique(dayid[live & (T >= a3)]))
    d1 = P.rs(full, "1D")
    d1rev = -P.sgn(P.to_m1(d1.c - d1.o, "1D", T)); d1rev[d1rev == -2] = 2
    SW = {nm: (pd.Series(L).rolling(nm, min_periods=1).min().shift(1).bfill().values,
               pd.Series(H).rolling(nm, min_periods=1).max().shift(1).bfill().values) for nm in (15, 30, 60)}
    ema = pd.Series(C).ewm(span=100, adjust=False).mean().shift(1).bfill().values

    def row(lab, eng, D=5.0, lk=1.0, T=0.5, R=5, k=0.5):
        lo, hi = SW[30]
        args = (d1rev, eng, T, k, 0, 0.0, lo, hi, ema, False, False, R)
        out = [sim(O, H, L, C, S, live, dayid, usd, D, lk, 3.0, 25.0, orr, 1, *args) for orr in (False, True)]
        xS, pS = sim(O, H, L, C, S * 1.5, live, dayid, usd, D, lk, 3.0, 25.0, False, 1, *args)
        xi, p = out[0]; te = T_[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        xc, pc = out[1]; tc = T_[xc]; vc = pc[tc >= a3]
        dc = pd.Series(vc, index=tc[tc >= a3].normalize()).groupby(level=0).sum(); ec = dc.cumsum()
        say(f"{lab:40s} | {len(v):5d} {len(v) / nd:4.0f} {100 * (v > 0).mean():3.0f}% {pf(v):5.2f} {pf(pS[T_[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} {v.max():+5.0f} | "
            f"{pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(vc):7.2f} {vc.sum():+6.0f} {(ec - ec.cummax()).min():+5.0f} {pf(pc[tc < a3]):5.2f}")

    say(f"FLIP v2.44 + TIGHTENING TRAIL, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), D1 filter, reset 5 min, 0.01 lot")
    say(f"{'stop':40s} | {'trd':>5} {'/day':>4} {'win':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bigW':>5} | {'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'net$':>6} {'DD':>5} {'prev':>5}")
    row("v2.35 trail $5 to +$1 then FROZEN", 0)
    row("v2.45 ~ SL $5, from +$1 trail $1", 2, D=5.0, lk=1.0, T=1.0)
    for D in (5.0, 4.0, 3.0):
        say(f"-- start ${D:g} behind, tighten $k per $1 of profit, floor $Tmin --")
        for k in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
            for Tm in (1.0, 1.5, 2.0):
                row(f"D ${D:g} k {k:g} floor ${Tm:g}", 3, D=D, T=Tm, k=k)


if __name__ == "__main__":
    main()
