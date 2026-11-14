"""Round 113f (14 Nov 2026): GOLD FLIP with the stop following the price again after a bigger profit.
Owner: "kenapa sl tak follow harga? macam mana kalau buat dia follow, kan untung lebih besar".
Live rule: gap $5, trail until +$1 then freeze.  New: once the trade is +$X (best price), the stop trails again at $Y
behind the best price (only tightens).  X 3/5/10/15/20/30, Y 3/5/8/10/15/20.  Reference rows: live (no re-trail),
and the plain always-trailing stop (round 113, gap $5/$10/$15).  Gold M1, last 2 years, 0.01 lot."""
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
def sim(O, H, L, S, D, live, dayid, usd, lk, X, Y, mode):
    """mode 0 plain trail at D; 3 freeze after lk, re-trail at Y once the best price is X beyond the entry."""
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; locked = False; best = 0.0
    for j in range(n):
        if pos != 0 and not live[j]:
            px = O[j] if pos == 1 else O[j] + S[j]
            xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1; pos = 0
            continue
        if pos == 0:
            if not live[j]: continue
            if not (j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]): continue
            pos = 1; locked = False; ent = O[j] + S[j]; stop = O[j] - D; best = 0.0
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); xi[m] = j; pn[m] = (px - ent) * usd; m += 1
                pos = -1; ent = px; stop = px + S[j] + D; locked = False; best = 0.0
            else:
                best = max(best, H[j] - ent)
                if mode == 0:
                    stop = max(stop, H[j] - D)
                else:
                    if not locked:
                        stop = max(stop, H[j] - D)
                        if H[j] - ent >= lk: locked = True
                    if best >= X:
                        stop = max(stop, H[j] - Y)
        else:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); xi[m] = j; pn[m] = (ent - px) * usd; m += 1
                pos = 1; ent = px; stop = px - S[j] - D; locked = False; best = 0.0
            else:
                best = max(best, ent - al)
                if mode == 0:
                    stop = min(stop, al + D)
                else:
                    if not locked:
                        stop = min(stop, al + D)
                        if ent - al >= lk: locked = True
                    if best >= X:
                        stop = min(stop, al + Y)
    return xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365); a3 = end - pd.Timedelta(days=91)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]].copy()
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410); ndays = len(np.unique(dayid[live]))
    say(f"gold M1 last 2 years, {ndays} days, $ at 0.01 lot")
    say(f"{'variant':40s} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'stress':>6} | {'net$':>7} {'12m$':>6} {'3m$':>5} | {'avgWin':>6} {'bigWin':>6} {'maxDD':>6} {'wDay':>5}")

    def row(nm, mode, X, Y, Gp=5.0, sm=1.0):
        xi, p = sim(O, H, L, S * sm, Gp * one, live, dayid, usd, one, X * one, Y * one, mode)
        if sm != 1.0: return pf(p)
        te = T[xi]; dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        st = row(nm, mode, X, Y, Gp, 1.5)
        say(f"{nm:40s} {len(p):6d} {len(p) / ndays:5.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {st:6.2f} | "
            f"{p.sum():+7.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} | {p[p > 0].mean():6.2f} {p.max():6.0f} {dd:+6.0f} {dp.min():+5.0f}")
    row("LIVE: freeze at +$1, never trail again", 3, 1e9, 1e9)
    for g in (5.0, 10.0, 15.0):
        row(f"always trail at ${g:g} (follow the price)", 0, 0, 0, g)
    say("")
    for X in (3, 5, 10, 15, 20, 30):
        for Y in (3, 5, 8, 10, 15, 20):
            if Y > X + 5: continue
            row(f"freeze, re-trail at ${Y} once +${X}", 3, float(X), float(Y))


if __name__ == "__main__":
    main()
