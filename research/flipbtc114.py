"""Round 114 (14 Nov 2026): the live GOLD FLIP rule on BTCUSD.  Owner: "jom kita cuba dekat btc. maybe kena adjust sikit saiz gap".
Rule (v2.31 on gold): OCO at the 01:30 server open +- K, then always in until 23:30: stop D behind the price, trailed on closed
M1 bars until the trade is +LK, then frozen; reverse when hit; flat overnight.  BTC is far dearer than gold and its spread is
4-5x wider relative to price, so the gap is a share of the day's 01:30 open: D = 0.1 ... 1.0 %; lock LK = 10 / 20 / 40 % of D;
K = 60 % of D (gold: 3 / 5) or a market BUY.  Windows: weekdays only / every day (BTC trades 7 days).  No swap needed (flat
overnight).  Gold M1 export not used: BTCUSD M1 exported fresh (tf=M1, from 2024.09.01).  0.01 lot = $0.01 per $1 of BTC."""
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
SYM = "BTCUSD"


@jit
def sim(O, H, L, S, D, LK, K, live, dayid, sdir, usd):
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); dr = np.zeros(2 * n, np.int64); m = 0
    pos = 0; ent = 0.0; stop = 0.0; locked = False; wait = False; up = 0.0; dn = 0.0
    for j in range(n):
        if not live[j]:
            if pos != 0:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; dr[m] = pos; m += 1; pos = 0
            wait = False
            continue
        start = j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]
        if pos == 0 and start:
            if K[j] <= 0:
                pos = sdir[j]; locked = False
                if pos == 1: ent = O[j] + S[j]; stop = O[j] - D[j]
                else: ent = O[j]; stop = O[j] + S[j] + D[j]
            else:
                wait = True; up = O[j] + K[j]; dn = O[j] - K[j]
        if pos == 0 and wait:
            hb = H[j] + S[j] >= up; hs = L[j] <= dn
            if not hb and not hs: continue
            if hb and hs:
                if up - (O[j] + S[j]) <= O[j] - dn: hs = False
                else: hb = False
            wait = False; locked = False
            if hb: pos = 1; ent = max(up, O[j] + S[j]); stop = ent - S[j] - D[j]
            else: pos = -1; ent = min(dn, O[j]); stop = ent + S[j] + D[j]
            continue
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); xi[m] = j; pn[m] = (px - ent) * usd; dr[m] = 1; m += 1
                pos = -1; ent = px; stop = px + S[j] + D[j]; locked = False
            elif not locked:
                stop = max(stop, H[j] - D[j])
                if H[j] - ent >= LK[j]: locked = True
        elif pos == -1:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); xi[m] = j; pn[m] = (ent - px) * usd; dr[m] = -1; m += 1
                pos = 1; ent = px; stop = px - S[j] - D[j]; locked = False
            elif not locked:
                stop = min(stop, al + D[j])
                if ent - al >= LK[j]: locked = True
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
    # the day's anchor price: the first bar at / after 01:30
    first = pd.Series(np.where(win, O, np.nan), index=T).groupby(T.normalize()).transform("first").values
    rng = np.random.default_rng(7); ud = np.unique(dayid); rmap = dict(zip(ud, rng.choice([-1, 1], len(ud))))
    sd_rand = np.array([rmap[x] for x in dayid], dtype=np.int64); sd_long = np.ones(len(O), np.int64)
    say(f"{SYM} M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, median price ${np.median(O):,.0f}, median spread ${np.median(S):.1f} "
        f"({100 * np.median(S / O):.3f}% of price) = ${np.median(S) * usd:.2f} per 0.01 lot; halves split {mid:%Y-%m-%d}; $ per 0.01 lot")
    hdr = f"{'variant':44s} {'trades':>6} {'/day':>5} {'win%':>4} {'PF':>5} {'h1':>5} {'h2':>5} {'strs':>5} {'rand':>5} {'buy':>5} {'sell':>5} | {'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5} {'big':>4}"

    def run(nm, live, pct, lkf, kf, sd=sd_long, sm=1.0, show=True):
        Dv = np.nan_to_num(first * pct / 100.0, nan=0.0); LKv = Dv * lkf; Kv = Dv * kf if kf > 0 else np.zeros(len(O))
        lv = live & (Dv > 0)
        xi, p, dr = sim(O, H, L, S * sm, Dv, LKv, Kv, lv, dayid, sd, usd)
        if not show: return p
        if len(p) < 30: return p
        _, pr, _ = sim(O, H, L, S, Dv, LKv, Kv * 0, lv, dayid, sd_rand, usd)
        ps = run(nm, live, pct, lkf, kf, sd, 1.5, False)
        te = T[xi]; nd = len(np.unique(dayid[lv]))
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:44s} {len(p):6d} {len(p) / nd:5.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} "
            f"{pf(ps):5.2f} {pf(pr):5.2f} {pf(p[dr == 1]):5.2f} {pf(p[dr == -1]):5.2f} | {p.sum():+6.0f} {p[te >= a12].sum():+5.0f} {p[te >= a3].sum():+5.0f} "
            f"{p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+5.0f} {dp.min():+5.0f} {p.max():4.0f}")
        return p

    for wname, live in (("weekdays", win & wdm), ("every day", win)):
        say(f"\n== {wname} 01:30-23:30 server, OCO K = 0.6 x gap, lock = 0.2 x gap\n" + hdr)
        for pct in (0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0):
            run(f"{wname} gap {pct}%", live, pct, 0.2, 0.6)
    say("\n== weekdays, gap x lock fraction (OCO 0.6 x gap)\n" + hdr)
    for pct in (0.2, 0.3, 0.5):
        for lkf in (0.1, 0.4, 1.0):
            run(f"gap {pct}% lock {lkf:g} x gap", win & wdm, pct, lkf, 0.6)
    say("\n== weekdays, market BUY start instead of the OCO (lock 0.2)\n" + hdr)
    for pct in (0.2, 0.3, 0.5):
        run(f"gap {pct}% market BUY start", win & wdm, pct, 0.2, 0.0)
    say("\n== weekend days only (Sat / Sun), OCO 0.6, lock 0.2\n" + hdr)
    for pct in (0.2, 0.3, 0.5):
        run(f"weekend gap {pct}%", win & ~wdm, pct, 0.2, 0.6)


if __name__ == "__main__":
    main()
