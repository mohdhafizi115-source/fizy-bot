"""Round 121 (16 Nov 2026): GOLD FLIP with a REAL-TIME (tick) trailing stop instead of moving it on each closed M1 bar.
Owner: "flip ni aku perasan dia tunggu m1 close baru gerak sl. aku tak nak macam tu, aku nak on the spot real time".
Live v2.31 rule: OCO at the 01:30 open +- $3 (SL $5 beyond the level), stop $5 behind the price, trailed until the trade has been +$1,
then frozen; stop hit -> reverse at market; no TP; own $25 daily target; out 23:30; weekdays.
Each M1 bar is walked as a price path (bullish bar O->L->H->C, bearish O->H->L->C; a coin-flip order as a second check), so stops,
fills and reversals happen inside the bar.  BAR = the live EA (stop moved once per closed M1 bar from that bar's high / low); TICK = the
stop follows the price continuously (a long freezes at entry + lock - gap the moment it is +$1).  Gaps $4 / $5 / $6.
Last 3 months and the 3 before, 0.01 lot, real spread per bar."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit


@jit
def sim(O, H, L, C, S, live, first, dayid, usd, D, lk, K, tgt, tick, order_rand, seed, fz=-999.0, tp=0.0):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    pts = np.zeros(4)
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False
        s = S[j]
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + s
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0
            continue
        if not live[j]:
            oco = False
            continue
        if first[j] and pos == 0 and not done:
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
            if b >= a:   # rising bid a -> b
                if pos == 0 and oco and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = bs - 5.0; locked = False; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    pos = 1; ent = px; stop = px - s - D; locked = False
                if pos == 1 and tp > 0 and b - ent >= tp:
                    px = ent + tp; p = tp * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    ent = px + s; stop = px - D; locked = False
                if pos == 1 and tick and not locked:
                    if b - ent >= lk:
                        stop = max(stop, ent + (lk - D if fz < -900 else fz)); locked = True
                    else:
                        stop = max(stop, b - D)
            else:        # falling bid a -> b
                if pos == 0 and oco and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ss + 5.0; locked = False; oco = False
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    pos = -1; ent = px; stop = px + s + D; locked = False
                if pos == -1 and tp > 0 and ent - (b + s) >= tp:
                    px = ent - tp; p = tp * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    ent = px - s; stop = px + D; locked = False
                if pos == -1 and tick and not locked:
                    if ent - (b + s) >= lk:
                        stop = min(stop, ent - (lk - D if fz < -900 else fz)); locked = True
                    else:
                        stop = min(stop, b + s + D)
        if not tick and pos != 0 and not locked:     # live EA: once per closed M1 bar from its high / low
            if pos == 1:
                stop = max(stop, H[j] - D)
                if stop >= ent + lk - D: locked = True
            else:
                stop = min(stop, L[j] + s + D)
                if stop <= ent - lk + D: locked = True
    return xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    say(f"GOLD FLIP, BAR (live) vs TICK trailing, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    say(f"median spread ${np.median(S) * usd:.2f}; $1 = 10 pips")
    say(f"{'variant':34s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bDay':>5} {'-days':>5} | "
        f"{'prev trd':>8} {'PF':>5} {'net$':>6}")
    nd = len(np.unique(dayid[live & (T >= a3)]))
    for D in (5.0, 4.0, 6.0):
        for tick in (False, True):
            for orr in (False, True):
                xi, p = sim(O, H, L, C, S, live, first, dayid, usd, D, 1.0, 3.0, 25.0, tick, orr, 1)
                xS, pS = sim(O, H, L, C, S * 1.5, live, first, dayid, usd, D, 1.0, 3.0, 25.0, tick, orr, 1)
                te = T[xi]; m = te >= a3; m2 = te < a3; x = p[m]
                dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
                nm = f"{'TICK' if tick else 'BAR (live)'} gap${D:g} {'coin order' if orr else 'OHLC order'}"
                say(f"{nm:34s} | {len(x):5d} {len(x) / nd:4.0f} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {x.sum():+6.0f} "
                    f"{(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} {dp.max():+5.0f} {(dp < 0).sum():5d} | {m2.sum():8d} {pf(p[m2]):5.2f} {p[m2].sum():+6.0f}")
        say("")


if __name__ == "__main__":
    main()
