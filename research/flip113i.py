"""Round 113i (15 Nov 2026): GOLD FLIP with a BREAKEVEN stop instead of the frozen $4-under-entry stop.
Owner: "kalau kau adjust bila dah profit 10pip, sl terus ke atas entry tak boleh ke walaupun profit dapat 0".
Live v2.31: OCO at the 01:30 open +- $3, stop $5 trailed on closed M1 bars until the trade is +$X (X = $1), then FROZEN where it is
(about $4 under the entry).  Here: once the trade is +$X, the stop jumps to entry + B (B = 0 / +spread / +$0.5 / +$1) and stays.
After a stop: (a) reverse at market as live, or (b) re-arm an OCO at the exit price +- $3 and wait for a fill.
X = $1 / 2 / 3 / 5.  Own $25 daily target on and off.  Gold M1, last 2 years, 0.01 lot."""
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
def sim(O, H, L, S, D, live, dayid, usd, lk, K, tgt, be, bemode, rearm):
    """bemode 0 = live freeze, 1 = stop to entry + be after +lk.  rearm 1 = after a stop wait for an OCO at exit +- K."""
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; locked = False; wait = False; up = 0.0; dn = 0.0; dsum = 0.0; done = False
    for j in range(n):
        if not live[j]:
            if pos != 0:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1; pos = 0
            wait = False
            continue
        if j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]:
            dsum = 0.0; done = False
            if pos == 0:
                wait = True; up = O[j] + K; dn = O[j] - K
        if done: continue
        if pos == 0 and wait:
            hb = H[j] + S[j] >= up; hs = L[j] <= dn
            if not hb and not hs: continue
            if hb and hs:
                if up - (O[j] + S[j]) <= O[j] - dn: hs = False
                else: hb = False
            wait = False; locked = False
            if hb:
                pos = 1; ent = max(up, O[j] + S[j]); stop = ent - S[j] - D
            else:
                pos = -1; ent = min(dn, O[j]); stop = ent + S[j] + D
            continue
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); v = (px - ent) * usd; xi[m] = j; pn[m] = v; m += 1; dsum += v
                if tgt > 0 and dsum >= tgt:
                    pos = 0; done = True
                elif rearm == 1:
                    pos = 0; wait = True; up = px + S[j] + K; dn = px - K
                else:
                    pos = -1; ent = px; stop = px + S[j] + D; locked = False
            elif not locked:
                if H[j] - ent >= lk:
                    locked = True
                    if bemode == 1: stop = max(stop, ent + be)
                    else: stop = max(stop, H[j] - D)
                else:
                    stop = max(stop, H[j] - D)
        elif pos == -1:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); v = (ent - px) * usd; xi[m] = j; pn[m] = v; m += 1; dsum += v
                if tgt > 0 and dsum >= tgt:
                    pos = 0; done = True
                elif rearm == 1:
                    pos = 0; wait = True; up = px + K; dn = px - S[j] - K
                else:
                    pos = 1; ent = px; stop = px - S[j] - D; locked = False
            elif not locked:
                if ent - al >= lk:
                    locked = True
                    if bemode == 1: stop = min(stop, ent - be)
                    else: stop = min(stop, al + D)
                else:
                    stop = min(stop, al + D)
    return xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd; spr = float(np.median(S))
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize())); nd = len(days)
    say(f"GOLD FLIP with a breakeven stop: gold M1 {days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}, {nd} days, median spread ${spr * usd:.2f}, $ at 0.01 lot")
    hdr = (f"{'variant':44s} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'net$':>6} {'12m$':>6} {'3m$':>5} {'pr3m':>5} | "
           f"{'DD':>5} {'wDay':>5} {'lossD%':>6} {'avgLD':>6} {'big':>4}")

    def run(nm, tgt, bemode, be, lk, rearm):
        xi, p = sim(O, H, L, S, 5 * one, live, dayid, usd, lk * one, 3 * one, tgt, be, bemode, rearm)
        _, ps = sim(O, H, L, S * 1.5, 5 * one, live, dayid, usd, lk * one, 3 * one, tgt, be, bemode, rearm)
        te = T[xi]
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
        eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:44s} {len(p):6d} {len(p) / nd:5.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(ps):5.2f} | "
            f"{p.sum():+6.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | "
            f"{dd:+5.0f} {dp.min():+5.0f} {100 * (dp < 0).mean():6.0f} {dp[dp < 0].mean():+6.1f} {p.max():4.0f}")

    for tgt in (25.0, 0.0):
        say(f"\n==== {'WITH the $25 target (live)' if tgt else 'WITHOUT the target'}\n" + hdr)
        run("LIVE: freeze at +$1 (stop ~$4 under entry)", tgt, 0, 0.0, 1.0, 0)
        for lk in (1.0, 2.0, 3.0, 5.0):
            for bnm, be in (("entry", 0.0), ("entry+spread", spr), ("entry+$0.5", 0.5 * one), ("entry+$1", 1.0 * one)):
                if be >= lk * one: continue
                run(f"BE after +${lk:g}: SL to {bnm}, reverse", tgt, 1, be, lk, 0)
        for lk in (1.0, 2.0, 3.0):
            run(f"BE after +${lk:g}: SL to entry+spread, re-arm OCO", tgt, 1, spr, lk, 1)
        run("LIVE freeze, re-arm OCO after a stop", tgt, 0, 0.0, 1.0, 1)


if __name__ == "__main__":
    main()
