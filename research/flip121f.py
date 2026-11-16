"""(also used by round 121g)
Round 121f (16 Nov 2026): the owner's own FLIP stop.  Owner: "kau buat je trailing real time bila dah profit 1$. untuk sl 4$ tapi
bila dah profit 1$ baru trailing follow".  FIXED stop $D from the entry (no trail) until the trade is +$1, then the stop follows the
price in real time $T behind it (never frozen); stop hit -> reverse at market; OCO +-$3 at 01:30, $25 target, out 23:30.
D 4 / 5 x T 1 / 2 / 3 / 4 / 5 against the live v2.35 rule.  Path engine of round 121, last 3 months and the 3 before, OHLC and coin
order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf
jit = F.jit


@jit
def sim(O, H, L, C, S, live, first, dayid, usd, D, T, lk, K, tgt, order_rand, seed, step=0.0):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; act = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0
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
            if b >= a:
                if pos == 0 and oco and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = bs - D; act = False; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    pos = 1; ent = px; stop = px - s - D; act = False
                if pos == 1:
                    if not act and b - ent >= lk: act = True
                    if act:
                        if step > 0: stop = max(stop, ent + np.floor((b - ent - lk) / step + 1e-9) * step)
                        else: stop = max(stop, b - T)
            else:
                if pos == 0 and oco and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ss + D; act = False; oco = False
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    pos = -1; ent = px; stop = px + s + D; act = False
                if pos == -1:
                    if not act and ent - (b + s) >= lk: act = True
                    if act:
                        if step > 0: stop = min(stop, ent - np.floor((ent - (b + s) - lk) / step + 1e-9) * step)
                        else: stop = min(stop, b + s + T)
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
    say(f"FLIP: FIXED SL then TRAIL after +$1, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), 0.01 lot")
    say(f"{'rule':30s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bigW':>5} | {'prev PF':>7} {'net$':>6} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")

    def row(lab, fn):
        xi, p = fn(S, False); xc, pc = fn(S, True); xS, pS = fn(S * 1.5, False)
        te = Tx[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum()
        tc = Tx[xc]
        say(f"{lab:30s} | {len(v):5d} {len(v) / nd:4.0f} {100 * (v > 0).mean():4.0f} {pf(v):5.2f} {pf(pS[Tx[xS] >= a3]):5.2f} {v.sum():+6.0f} "
            f"{(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} {v.max():+5.0f} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {dp2.min():+5.0f} | "
            f"{pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")

    row("LIVE v2.35 (trail $5, freeze)", lambda s, r: F.sim(O, H, L, C, s, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, True, r, 1))
    for D in (4.0, 5.0):
        for T in (4.0, 1.0, 2.0, 3.0, 5.0, 8.0):
            row(f"SL ${D:g} fixed, trail ${T:g} after +$1", lambda s, r, D=D, T=T: sim(O, H, L, C, s, live, first, dayid, usd, D, T, 1.0, 3.0, 25.0, r, 1))


if __name__ == "__main__":
    main()
