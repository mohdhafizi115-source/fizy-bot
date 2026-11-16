"""Round 121h (16 Nov 2026): the owner's re-entry rule for FLIP.  Owner: "bila kena sl tanpa profit langsung jangan follow entry
berlawanan, tapi entry yang sama terus. ni untuk yang hit sl loss la".  Live v2.38 stop (SL $4; at +$1 to entry + $0.10, then +$0.50
steps); after a LOSING stop the EA re-enters the SAME way (fresh $4 stop) instead of reversing; a stop in profit still reverses.
Also: after N losing stops in a row the same way, reverse (N 2 / 3).  Path engine, last 3 months and the 3 before, OHLC and coin
order, 0.01 lot.  The tight lock makes the path model optimistic (round 121g); compare the rows with each other."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf
jit = F.jit


@jit
def sim(O, H, L, C, S, live, first, dayid, usd, D, lk, K, tgt, order_rand, seed, step, beoff, same, maxsame):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
    pts = np.zeros(4); cons = 0
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False; cons = 0
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
            if b >= a:
                if pos == 0 and oco and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = bs - D; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if p < 0: cons += 1
                    else: cons = 0
                    if same and p < 0 and (maxsame == 0 or cons < maxsame):
                        pos = -1; ent = px - s; stop = px + D            # re-enter short, fresh $D stop on the ask
                    else:
                        cons = 0; pos = 1; ent = px; stop = px - s - D
                if pos == 1 and b - ent >= lk:
                    stop = max(stop, ent + beoff + np.floor((b - ent - lk) / step + 1e-9) * step)
            else:
                if pos == 0 and oco and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ss + D; oco = False
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if p < 0: cons += 1
                    else: cons = 0
                    if same and p < 0 and (maxsame == 0 or cons < maxsame):
                        pos = 1; ent = px + s; stop = px - D               # re-enter long
                    else:
                        cons = 0; pos = -1; ent = px; stop = px + s + D
                if pos == -1 and ent - (b + s) >= lk:
                    stop = min(stop, ent - beoff - np.floor((ent - (b + s) - lk) / step + 1e-9) * step)
    return xi[:m], pn[:m]


def main():
    mt, sw = F.W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = F.SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    Tx = d.index; hm = Tx.hour.values * 60 + Tx.minute.values; wd = Tx.day_of_week.values < 5
    dayid = Tx.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    nd = len(np.unique(dayid[live & (Tx >= a3)]))
    say(f"FLIP v2.38 stop, REVERSE vs SAME-WAY RE-ENTRY after a losing stop, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), 0.01 lot")
    say(f"{'rule':36s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | {'prev PF':>7} {'net$':>6} {'wDay':>5} | {'coin PF':>7} {'prev':>5} {'net$':>6} {'wDay':>5}")
    for lab, same, mx in (("v2.38 live: always reverse", False, 0), ("OWNER: same way after a loss", True, 0),
                          ("same way, reverse after 2 losses", True, 2), ("same way, reverse after 3 losses", True, 3)):
        fn = lambda s, r: sim(O, H, L, C, s, live, first, dayid, usd, 4.0, 1.0, 3.0, 25.0, r, 1, 0.5, 0.10, same, mx)
        xi, p = fn(S, False); xc, pc = fn(S, True); xS, pS = fn(S * 1.5, False)
        te = Tx[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum()
        tc = Tx[xc]; mc = tc >= a3
        dpc = pd.Series(pc[mc], index=tc[mc].normalize()).groupby(level=0).sum()
        say(f"{lab:36s} | {len(v):5d} {len(v) / nd:4.0f} {100 * (v > 0).mean():4.0f} {pf(v):5.2f} {pf(pS[Tx[xS] >= a3]):5.2f} {v.sum():+6.0f} "
            f"{(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} {(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {dp2.min():+5.0f} | "
            f"{pf(pc[mc]):7.2f} {pf(pc[~mc]):5.2f} {pc[mc].sum():+6.0f} {dpc.min():+5.0f}")


if __name__ == "__main__":
    main()
