"""Round 113g (14 Nov 2026): GOLD FLIP started by an OCO pair instead of a market BUY.
Owner: "untuk permulaan kita buat buy dan sell stop dulu tanpa terus entry. so mana2 trigger baru kita follow setup ni".
At 01:30 server: BUY STOP at open + K (ask) and SELL STOP at open - K (bid); the first to fill opens the first trade,
the other is cancelled; from then on the live rule (stop $5, trail until +$1 then frozen, reverse when hit, out 23:30).
K 0 (= live, market BUY) / 1 / 2 / 3 / 5 / 8 / 10 / 15 / 20 $, also K = 0.15 / 0.25 x ATR14(D1). Gold M1, last 2 years, 0.01 lot.
The fill bar is checked by the first level its open is nearer to when both are inside one bar (conservative order)."""
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
def sim(O, H, L, S, D, live, dayid, usd, lk, K):
    """K[j] = OCO distance for the day starting at bar j (price); K <= 0 -> market BUY."""
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0; fills = 0
    pos = 0; ent = 0.0; stop = 0.0; locked = False; wait = False; up = 0.0; dn = 0.0
    for j in range(n):
        if not live[j]:
            if pos != 0:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1; pos = 0
            wait = False
            continue
        start = j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]
        if pos == 0 and start:
            if K[j] <= 0:
                pos = 1; locked = False; ent = O[j] + S[j]; stop = O[j] - D
            else:
                wait = True; up = O[j] + K[j]; dn = O[j] - K[j]
        if pos == 0 and wait:
            hb = H[j] + S[j] >= up; hs = L[j] <= dn
            if not hb and not hs: continue
            if hb and hs:                                     # both in one bar: take the one nearer the open
                if up - (O[j] + S[j]) <= O[j] - dn: hs = False
                else: hb = False
            wait = False; fills += 1; locked = False
            if hb:
                pos = 1; ent = max(up, O[j] + S[j]); stop = ent - S[j] - D
            else:
                pos = -1; ent = min(dn, O[j]); stop = ent + S[j] + D
            continue                                          # stop checks from the next bar
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); xi[m] = j; pn[m] = (px - ent) * usd; m += 1
                pos = -1; ent = px; stop = px + S[j] + D; locked = False
            elif not locked:
                stop = max(stop, H[j] - D)
                if H[j] - ent >= lk: locked = True
        elif pos == -1:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); xi[m] = j; pn[m] = (ent - px) * usd; m += 1
                pos = 1; ent = px; stop = px - S[j] - D; locked = False
            elif not locked:
                stop = min(stop, al + D)
                if ent - al >= lk: locked = True
    return xi[:m], pn[:m], fills


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365); a3 = end - pd.Timedelta(days=91)
    Bw = d[d.index >= start - pd.Timedelta(days=40)][["o", "h", "l", "c", "s"]].copy()
    day = Bw.index.normalize(); Dd = Bw.groupby(day).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    pc = Dd.c.shift(); tr = np.maximum(Dd.h - Dd.l, np.maximum((Dd.h - pc).abs(), (Dd.l - pc).abs()))
    datr = tr.rolling(14).mean().shift(1)
    B = Bw[Bw.index >= start]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410); ndays = len(np.unique(dayid[live]))
    A = datr.reindex(T.normalize()).values
    say(f"gold M1 last 2 years, {ndays} days, $ at 0.01 lot; first trade from an OCO at the 01:30 server open +- K, then the live rule")
    say(f"{'start':30s} {'filled':>6} {'trades':>6} {'/day':>5} {'PF':>5} {'yr1':>5} {'yr2':>5} {'stress':>6} | {'net$':>7} {'12m$':>6} {'3m$':>5} {'pr3m$':>5} | {'maxDD':>6} {'wDay':>5}")
    cells = [("market BUY at 01:30 (LIVE)", np.zeros(len(O)))] + \
            [(f"OCO open +- ${k:g}", np.full(len(O), k * one)) for k in (1, 2, 3, 5, 8, 10, 15, 20)] + \
            [(f"OCO open +- {f:g} x ATR(D1)", np.nan_to_num(f * A, nan=5 * one)) for f in (0.1, 0.15, 0.25)]
    for nm, K in cells:
        xi, p, fl = sim(O, H, L, S, 5 * one, live, dayid, usd, one, K)
        _, ps, _ = sim(O, H, L, S * 1.5, 5 * one, live, dayid, usd, one, K)
        te = T[xi]; dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        a6 = end - pd.Timedelta(days=182)
        say(f"{nm:30s} {(fl if K.max() > 0 else ndays):6d} {len(p):6d} {len(p) / ndays:5.1f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(ps):6.2f} | "
            f"{p.sum():+7.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+6.0f} {dp.min():+5.0f}")


if __name__ == "__main__":
    main()
