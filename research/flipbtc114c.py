"""Round 114c (14 Nov 2026): the FLIP rule turned upside down on BTCUSD (a FADE).  Owner: "kau guna konsep ea ni yang sama tapi
terbalik kan buy dan sell".  Same frame as round 114: one position, 01:30-23:30 server, flat overnight, gap D as a share of the
01:30 open.  The day starts with an OCO of LIMIT orders: SELL LIMIT at open + K, BUY LIMIT at open - K (K = 0.6 x D).
In a position the opposite order is a LIMIT on the profit side: long -> SELL LIMIT at entry + D (take the profit and go short),
short -> BUY LIMIT at entry - D.  Modes:
  static : the limit stays at entry +- D.
  trail  : the limit follows the price AGAINST the trade (long: lowest low since entry + D), the mirror of FLIP's trailed stop,
           so it sells a D bounce off the low and buys a D drop off the high (a zigzag fade).
Optional stop X x D against the trade (0 = none): stopped -> flat, then a new limit OCO at the exit price +- K.
Stop and limit in one bar: the stop is assumed first (conservative).  $ per 0.01 lot.  Data run 43573032913 (BTCUSD M1)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flipbtc114 as F

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; F.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit
SYM = "BTCUSD"


@jit
def fade(O, H, L, S, D, K, X, trail, live, dayid, usd):
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); dr = np.zeros(2 * n, np.int64); m = 0
    pos = 0; ent = 0.0; lim = 0.0; stp = 0.0; wait = False; up = 0.0; dn = 0.0
    for j in range(n):
        if not live[j]:
            if pos != 0:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; dr[m] = pos; m += 1; pos = 0
            wait = False
            continue
        if j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]:
            if pos == 0:
                wait = True; up = O[j] + K[j]; dn = O[j] - K[j]
        if pos == 0 and wait:
            hs = H[j] >= up; hb = L[j] + S[j] <= dn                  # sell limit by the bid, buy limit by the ask
            if not hs and not hb: continue
            if hs and hb:
                if up - O[j] <= (O[j] + S[j]) - dn: hb = False
                else: hs = False
            wait = False
            if hs:
                pos = -1; ent = max(up, O[j]); lim = ent - D[j]; stp = ent + X * D[j]
            else:
                pos = 1; ent = min(dn, O[j] + S[j]); lim = ent + D[j]; stp = ent - X * D[j]
            continue
        if pos == 1:
            if X > 0 and L[j] <= stp:
                px = min(O[j], stp); xi[m] = j; pn[m] = (px - ent) * usd; dr[m] = 1; m += 1
                pos = 0; wait = True; up = px + K[j]; dn = px - K[j]
            elif H[j] >= lim:
                px = max(O[j], lim); xi[m] = j; pn[m] = (px - ent) * usd; dr[m] = 1; m += 1
                pos = -1; ent = px; lim = px - D[j]; stp = px + X * D[j]
            elif trail:
                lim = min(lim, L[j] + D[j])
        elif pos == -1:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if X > 0 and ah >= stp:
                px = max(O[j] + S[j], stp); xi[m] = j; pn[m] = (ent - px) * usd; dr[m] = -1; m += 1
                pos = 0; wait = True; up = px + K[j]; dn = px - K[j]
            elif al <= lim:
                px = min(O[j] + S[j], lim); xi[m] = j; pn[m] = (ent - px) * usd; dr[m] = -1; m += 1
                pos = 1; ent = px; lim = px + D[j]; stp = px - X * D[j]
            elif trail:
                lim = max(lim, ah - D[j])
    return xi[:m], pn[:m], dr[:m]


def main():
    mt, sw = W.read_meta(SYM)
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, SYM + ".csv"), mt["point"])
    end = d.index[-1]; start = max(d.index[0], end - pd.Timedelta(days=730))
    mid = start + (end - start) / 2; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182); a12 = end - pd.Timedelta(days=365)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]].copy()
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index
    hm = T.hour.values * 60 + T.minute.values; wdm = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    win = (hm >= 90) & (hm < 1410)
    first = pd.Series(np.where(win, O, np.nan), index=T).groupby(T.normalize()).transform("first").values
    say(f"{SYM} M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, median spread ${np.median(S):.1f}; halves split {mid:%Y-%m-%d}; $ per 0.01 lot")
    say("FADE = the FLIP rule reversed: limit SELL above / limit BUY below, flip at the limit; FLIP column = the original stop rule, same gap")
    hdr = (f"{'variant':34s} {'gap$':>5} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'h1':>5} {'h2':>5} {'strs':>5} {'FLIP':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>6} {'wDay':>5} {'wTrd':>5}")
    sd_long = np.ones(len(O), np.int64)

    def run(nm, live, pct, X, trail):
        Dv = np.nan_to_num(first * pct / 100.0, nan=0.0); Kv = Dv * 0.6; lv = live & (Dv > 0)
        xi, p, dr = fade(O, H, L, S, Dv, Kv, float(X), trail, lv, dayid, usd)
        if len(p) < 30: return
        _, ps, _ = fade(O, H, L, S * 1.5, Dv, Kv, float(X), trail, lv, dayid, usd)
        _, pfl, _ = F.sim(O, H, L, S, Dv, Dv * 0.2, Kv, lv, dayid, sd_long, usd)
        te = T[xi]; nd = len(np.unique(dayid[lv]))
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:34s} {np.median(Dv[lv]):5.0f} {len(p):6d} {len(p) / nd:5.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} "
            f"{pf(p[te >= mid]):5.2f} {pf(ps):5.2f} {pf(pfl):5.2f} | {p.sum():+6.0f} {p[te >= a12].sum():+5.0f} {p[te >= a3].sum():+5.0f} "
            f"{p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+6.0f} {dp.min():+5.0f} {p.min():+5.0f}")

    for wname, live in (("wkdy", win & wdm), ("all", win)):
        for trail in (False, True):
            for X in (0, 1, 2, 3):
                say(f"\n== {wname}, {'trail' if trail else 'static'} limit, stop {X} x gap{' (none)' if X == 0 else ''}\n" + hdr)
                for pct in (0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0):
                    run(f"{wname} {'trl' if trail else 'sta'} X{X} gap {pct:g}%", live, pct, X, trail)


if __name__ == "__main__":
    main()
