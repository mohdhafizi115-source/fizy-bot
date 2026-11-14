"""Round 113e (14 Nov 2026): GOLD FLIP (FREEZE, gap $5, lock +$1) by time of day.
Owner: "sesuai masa market sedang aktif atau tak".  Gold M1, last 2 years, 0.01 lot.
(1) the live rule's trades grouped by entry hour (server and MYT = server + 6 in winter, + 5 in summer: shown as server);
(2) the same rule with other windows: start 01:30 / 08:00 (London) / 10:00 / 14:00 / 15:30 (NY open) / 17:00, end 23:30,
    and Asia only 01:30-09:00, London only 09:00-15:30, NY only 15:30-23:30."""
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


@jit
def sim(O, H, L, S, D, live, dayid, usd, lk):
    n = len(O); ei = np.zeros(2 * n, np.int64); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; locked = False; e0 = 0
    for j in range(n):
        if pos != 0 and not live[j]:
            px = O[j] if pos == 1 else O[j] + S[j]
            ei[m] = e0; xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1; pos = 0
            continue
        if pos == 0:
            if not live[j]: continue
            if not (j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]): continue
            pos = 1; locked = False; e0 = j; ent = O[j] + S[j]; stop = O[j] - D
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); ei[m] = e0; xi[m] = j; pn[m] = (px - ent) * usd; m += 1
                pos = -1; ent = px; stop = px + S[j] + D; locked = False; e0 = j
            elif not locked:
                stop = max(stop, H[j] - D)
                if H[j] - ent >= lk: locked = True
        else:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); ei[m] = e0; xi[m] = j; pn[m] = (ent - px) * usd; m += 1
                pos = 1; ent = px; stop = px - S[j] - D; locked = False; e0 = j
            elif not locked:
                stop = min(stop, al + D)
                if ent - al >= lk: locked = True
    return ei[:m], xi[:m], pn[:m]


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
    ndays = len(np.unique(dayid[wd]))
    live = wd & (hm >= 90) & (hm < 1410)
    ei, xi, p = sim(O, H, L, S, 5 * one, live, dayid, usd, one)
    eh = T[ei].hour.values; dur = (xi - ei)
    say(f"LIVE rule (01:30-23:30 server), trades by ENTRY hour (server; MYT = server + 6 in winter); {ndays} days, $ at 0.01 lot")
    say(f"{'hour':>4} {'MYT':>5} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'net$':>7} {'avg min held':>12}")
    te = T[xi]
    for h in range(1, 24):
        k = eh == h
        if k.sum() < 20: continue
        q = p[k]; tq = te[k]
        say(f"{h:4d} {(h + 6) % 24:5d} {k.sum():6d} {k.sum() / ndays:5.1f} {100 * (q > 0).mean():4.0f} {pf(q):5.2f} {pf(q[tq < mid]):5.2f} {pf(q[tq >= mid]):5.2f} {q.sum():+7.0f} {dur[k].mean():12.0f}")
    say("\nwindows (start the day with a BUY at the window start, closed at the window end)")
    say(f"{'window (server)':28s} {'trades':>6} {'/day':>5} {'PF':>5} {'yr1':>5} {'yr2':>5} {'net$':>7} {'12m$':>6} {'3m$':>5} {'maxDD':>6} {'wDay':>5}")
    for nm, a, b in (("01:30-23:30 LIVE", 90, 1410), ("08:00-23:30 from London", 480, 1410), ("10:00-23:30", 600, 1410),
                     ("14:00-23:30", 840, 1410), ("15:30-23:30 from NY open", 930, 1410), ("17:00-23:30", 1020, 1410),
                     ("01:30-09:00 Asia only", 90, 540), ("09:00-15:30 London only", 540, 930), ("15:30-23:30 NY only", 930, 1410),
                     ("09:00-23:30 London+NY", 540, 1410), ("01:30-18:00", 90, 1080)):
        lv = wd & (hm >= a) & (hm < b)
        _, x2, q = sim(O, H, L, S, 5 * one, lv, dayid, usd, one)
        t2 = T[x2]; dp = pd.Series(q, index=t2.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:28s} {len(q):6d} {len(q) / ndays:5.1f} {pf(q):5.2f} {pf(q[t2 < mid]):5.2f} {pf(q[t2 >= mid]):5.2f} {q.sum():+7.0f} {q[t2 >= mid].sum():+6.0f} {q[t2 >= a3].sum():+5.0f} {dd:+6.0f} {dp.min():+5.0f}")


if __name__ == "__main__":
    main()
