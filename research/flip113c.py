"""Round 113c (14 Nov 2026): the TikTok stop-and-reverse with a 10-pip ($1) idea.
Owner: "sell buy stop tu ada trailing, bukan statik. maybe profit dia target 1 entry 10 pip je. so sell buy stop sentiasa move
tunggu profit 10pip kemudian baru dia tunggu kena langgar".  (Round 113 already trailed the reverse stop every bar.)
Modes, reverse stop at gap D (bid terms for a long, ask terms for a short), gold M1, last 2 years, 0.01 lot:
  TRAIL     the round 113 rule: the stop trails at D behind the best price, reverse when hit
  TRAIL+TP  the same plus TP $1 (10 pips) per entry; after a TP re-enter the same way at the next bar's open
  STATIC+TP stop fixed at D from the entry (not trailing), TP $1, reverse on the stop
  FREEZE    trail until the trade is +$1, then the stop stops moving and waits to be hit (then reverse)
  BE+TRAIL  trail; once +$1 the stop is at least at breakeven, and keeps trailing
Each with and without the owner's $25 daily target; $100 account refilled after each wipe-out.
Bars: stop checked before TP in the same bar (conservative), at most one flip per bar, stops set from earlier bars."""
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
def sim(O, H, L, S, D, live, dayid, usd, target, mode, tp, lk):
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; dpnl = 0.0; done = False; locked = False; reent = 0
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + S[j]
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0; reent = 0; dpnl += p
            continue
        if pos == 0:
            if not live[j] or done:
                continue
            if reent != 0:
                d = reent
            elif j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]:
                d = 1
            else:
                continue
            reent = 0; locked = False; pos = d
            if d == 1:
                ent = O[j] + S[j]; stop = O[j] - D
            else:
                ent = O[j]; stop = O[j] + S[j] + D
        rec = False; p = 0.0
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); p = (px - ent) * usd; rec = True
                pos = -1; ent = px; stop = px + S[j] + D; locked = False
            elif (mode == 1 or mode == 2) and H[j] >= ent + tp:
                px = max(O[j], ent + tp); p = (px - ent) * usd; rec = True; pos = 0; reent = 1
            else:
                if mode == 3:
                    if not locked:
                        stop = max(stop, H[j] - D)
                        if H[j] - ent >= lk: locked = True
                elif mode == 4:
                    if H[j] - ent >= lk: stop = max(stop, ent)
                    stop = max(stop, H[j] - D)
                elif mode != 2:
                    stop = max(stop, H[j] - D)
        else:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); p = (ent - px) * usd; rec = True
                pos = 1; ent = px; stop = px - S[j] - D; locked = False
            elif (mode == 1 or mode == 2) and al <= ent - tp:
                px = min(O[j] + S[j], ent - tp); p = (ent - px) * usd; rec = True; pos = 0; reent = -1
            else:
                if mode == 3:
                    if not locked:
                        stop = min(stop, al + D)
                        if ent - al >= lk: locked = True
                elif mode == 4:
                    if ent - al >= lk: stop = min(stop, ent)
                    stop = min(stop, al + D)
                elif mode != 2:
                    stop = min(stop, al + D)
        if rec:
            xi[m] = j; pn[m] = p; m += 1; dpnl += p
            if dpnl >= target: done = True
    return xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365); a3 = end - pd.Timedelta(days=91)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]].copy()
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; a1 = M.atr(B).values
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    base = wd & (hm >= 90) & (hm < 1410); gate = base & (a1 >= 8 * S)
    ndays = len(np.unique(dayid[base])); one = 1.0 / usd
    say(f"gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {ndays} trading days, $1 = 10 pips; $ per 0.01 lot")
    say(f"{'variant':38s} {'trades':>7} {'/day':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} | {'net$':>7} {'12m$':>7} {'3m$':>6} | {'maxDD':>6} {'wDay':>5} | {'d+25':>4} {'blow':>4}")
    names = ["TRAIL", "TRAIL+TP$1", "STATIC+TP$1", "FREEZE@+$1", "BE@+$1+TRAIL"]
    best = []
    for wname, live in (("all", base), ("gate8", gate)):
        for mode in range(5):
            for gap in (0.5, 1.0, 2.0, 3.0, 5.0):
                for tgt in (1e9, 25.0):
                    xi, p = sim(O, H, L, S, gap * one, live, dayid, usd, tgt, mode, one, one)
                    if len(p) < 20: continue
                    te = T[xi]
                    dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
                    bal = 100.0; blow = 0
                    for v in p:
                        bal += v
                        if bal <= 0: blow += 1; bal = 100.0
                    nm = f"{wname} {names[mode]} gap${gap:g}" + (" T25" if tgt < 1e8 else "")
                    row = (pf(p), nm)
                    best.append(row)
                    say(f"{nm:38s} {len(p):7d} {len(p) / ndays:5.0f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} | "
                        f"{p.sum():+7.0f} {p[te >= mid].sum():+7.0f} {p[te >= a3].sum():+6.0f} | {dd:+6.0f} {dp.min():+5.0f} | {int((dp >= 25).sum()):4d} {blow:4d}")
            say("")
    best.sort(reverse=True)
    say("top 10 by PF: " + "; ".join(f"{b[1]} {b[0]:.2f}" for b in best[:10]))
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
