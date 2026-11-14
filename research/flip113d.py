"""Round 113d (14 Nov 2026): is round 113c's FREEZE cell (trail the reverse stop until +$1, then freeze it) real?
Checks on gold M1, last 2 years, 0.01 lot: start direction each day long / short / random; buys vs sells; stress 1.5x spread;
gap 3-10 x lock trigger $0.5-3; STATIC (fixed stop at D, reverse only on the stop, no TP) and an always-buy 01:30 -> 23:30
baseline; by quarter; last 3 months / previous 3."""
import os, sys, time
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
T0 = time.time()


@jit
def sim(O, H, L, S, D, live, dayid, sdir, usd, target, mode, lk):
    """mode 3 FREEZE, mode 2 STATIC (no TP), mode 0 TRAIL. Returns exit bar, pnl, direction."""
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); dr = np.zeros(2 * n, np.int64); m = 0
    pos = 0; ent = 0.0; stop = 0.0; dpnl = 0.0; done = False; locked = False
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + S[j]
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; dr[m] = pos; m += 1; pos = 0; dpnl += p
            continue
        if pos == 0:
            if not live[j] or done: continue
            if not (j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]): continue
            pos = sdir[j]; locked = False
            if pos == 1: ent = O[j] + S[j]; stop = O[j] - D
            else: ent = O[j]; stop = O[j] + S[j] + D
        rec = False; p = 0.0; od = pos
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); p = (px - ent) * usd; rec = True
                pos = -1; ent = px; stop = px + S[j] + D; locked = False
            elif mode == 3:
                if not locked:
                    stop = max(stop, H[j] - D)
                    if H[j] - ent >= lk: locked = True
            elif mode == 0:
                stop = max(stop, H[j] - D)
        else:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); p = (ent - px) * usd; rec = True
                pos = 1; ent = px; stop = px - S[j] - D; locked = False
            elif mode == 3:
                if not locked:
                    stop = min(stop, al + D)
                    if ent - al >= lk: locked = True
            elif mode == 0:
                stop = min(stop, al + D)
        if rec:
            xi[m] = j; pn[m] = p; dr[m] = od; m += 1; dpnl += p
            if dpnl >= target: done = True
    return xi[:m], pn[:m], dr[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]].copy()
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    ndays = len(np.unique(dayid[live])); one = 1.0 / usd
    rng = np.random.default_rng(7); ud = np.unique(dayid); rmap = dict(zip(ud, rng.choice([-1, 1], len(ud))))
    sd_rand = np.array([rmap[x] for x in dayid], dtype=np.int64)
    sd_long = np.ones(len(O), np.int64); sd_short = -sd_long

    def row(nm, xi, p, dr, extra=""):
        te = T[xi]
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        bal = 100.0; blow = 0
        for v in p:
            bal += v
            if bal <= 0: blow += 1; bal = 100.0
        prev3 = p[(te >= a6) & (te < a3)].sum()
        say(f"{nm:34s} {len(p):6d} {len(p) / ndays:4.0f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} "
            f"{pf(p[dr == 1]):5.2f} {pf(p[dr == -1]):5.2f} | {p.sum():+6.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} {prev3:+5.0f} | "
            f"{dd:+5.0f} {dp.min():+5.0f} {p.min():+5.0f} | {blow:3d}{extra}")
        return te, p

    H_ = f"{'variant':34s} {'trades':>6} {'/day':>4} {'win':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'buys':>5} {'sells':>5} | {'net':>6} {'12m':>6} {'3m':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5} {'wTr':>5} | blow"
    say(f"gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {ndays} days, $ per 0.01 lot; 01:30-23:30 server, flat overnight")
    say(H_)
    # baseline: always buy 01:30 -> 23:30
    xs = []; ps = []
    for dd_ in np.unique(dayid[live]):
        k = np.where(live & (dayid == dd_))[0]
        if len(k) < 30: continue
        e = k[-1] + 1 if k[-1] + 1 < len(O) else k[-1]
        xs.append(e); ps.append((O[e] - O[k[0]] - S[k[0]]) * usd)
    row("ALWAYS BUY 01:30->23:30", np.array(xs), np.array(ps), np.ones(len(ps), np.int64))
    say("\n-- FREEZE gap $5 lock +$1, start direction")
    for nm, sd in (("start LONG", sd_long), ("start SHORT", sd_short), ("start RANDOM", sd_rand)):
        xi, p, dr = sim(O, H, L, S, 5 * one, live, dayid, sd, usd, 1e9, 3, one); row("FREEZE5 " + nm, xi, p, dr)
    xi, p, dr = sim(O, H, L, S * 1.5, 5 * one, live, dayid, sd_long, usd, 1e9, 3, one); row("FREEZE5 start LONG stress 1.5x", xi, p, dr)
    say("\n-- FREEZE gap x lock trigger (start LONG | start SHORT PF)")
    for gap in (3, 4, 5, 6, 8, 10):
        for lk in (0.5, 1.0, 2.0, 3.0):
            xi, p, dr = sim(O, H, L, S, gap * one, live, dayid, sd_long, usd, 1e9, 3, lk * one)
            xs_, ps_, _ = sim(O, H, L, S, gap * one, live, dayid, sd_short, usd, 1e9, 3, lk * one)
            row(f"FREEZE gap${gap} lock+${lk:g}", xi, p, dr, f"  short-start PF {pf(ps_):.2f}")
    say("\n-- STATIC stop (no trailing, reverse on the stop only) and TRAIL, start LONG | SHORT")
    for mode, mn in ((2, "STATIC"), (0, "TRAIL")):
        for gap in (3, 5, 8, 10, 15):
            xi, p, dr = sim(O, H, L, S, gap * one, live, dayid, sd_long, usd, 1e9, mode, one)
            xs_, ps_, _ = sim(O, H, L, S, gap * one, live, dayid, sd_short, usd, 1e9, mode, one)
            row(f"{mn} gap${gap}", xi, p, dr, f"  short-start PF {pf(ps_):.2f}")
    say("\n-- FREEZE gap $5 lock $1 start LONG, $25 target, by quarter")
    xi, p, dr = sim(O, H, L, S, 5 * one, live, dayid, sd_long, usd, 25.0, 3, one); te, p2 = row("FREEZE5 T25", xi, p, dr)
    xi, p, dr = sim(O, H, L, S, 5 * one, live, dayid, sd_long, usd, 1e9, 3, one); te, p = row("FREEZE5 no target", xi, p, dr)
    q = pd.Series(p, index=te); say("quarters: " + "  ".join(f"{k}: {v:+.0f}" for k, v in q.groupby(q.index.to_period("Q")).sum().items()))
    mo = q.groupby(q.index.to_period("M")).sum(); say(f"months positive {int((mo > 0).sum())} of {len(mo)}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
