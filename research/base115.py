"""Round 115 (15 Nov 2026): the LAST H1 CANDLE of the day as a base zone on gold.  Owner: "teknik candle terakhir close sebagai base dan
cara entry keesokan nya atau bila2 apabila price kembali ke area tu. base tu di tanda pada tf h1, antara wick atas bawah. gold".
Base = high / low (wick to wick) of the last H1 bar of a trading day (22:00 or 23:00 server; Mon-Fri).  From 01:30 server on the next
trading day the side of price is read (if price is inside the zone, wait until a close outside it).  Then on the first RETURN to the zone:
  BOUNCE : price above the zone -> BUY LIMIT at the zone high (ask), SL below the zone low; below -> SELL LIMIT at the zone low, SL above.
  BREAK  : price above -> SELL STOP at the zone low (it went through), SL above the zone high; below -> BUY STOP at the zone high.
SL buffer = spread + 0.1 x zone height.  TP 1R / 2R / 3R / none; every trade closed at 23:30 server of its fill day.  Zone valid for
the next 1 / 3 / 5 / 10 trading days, one trade per zone (overlapping zones allowed).  Min zone height $0 / $3.
Control: FAKE zones of the same height shifted by +-(0.5..2) x height (3 seeds).  Entries 01:30-23:00 server.  Gold M1, last 2 years, 0.01 lot."""
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
def run_zones(O, H, L, C, S, hm, eod, zhi, zlo, zs, ze, mode, R, usd):
    nz = len(zhi); pn = np.zeros(nz); xi = np.full(nz, -1, np.int64); dr = np.zeros(nz, np.int64); rk = np.zeros(nz)
    for z in range(nz):
        hi = zhi[z]; lo = zlo[z]; ht = hi - lo; j = zs[z]; side = 0
        if ht <= 0: continue
        while j < ze[z] and side == 0:                       # read the side (wait outside the zone)
            if hm[j] >= 90 and hm[j] < 1380:
                if C[j] > hi: side = 1
                elif C[j] < lo: side = -1
            j += 1
        if side == 0: continue
        filled = False; d = 0; ent = 0.0; sl = 0.0; tp = 0.0
        while j < ze[z]:
            if hm[j] < 90 or hm[j] >= 1380: j += 1; continue
            buf = S[j] + 0.1 * ht
            if mode == 0:
                if side == 1 and L[j] + S[j] <= hi:
                    d = 1; ent = min(O[j] + S[j], hi); sl = lo - buf
                elif side == -1 and H[j] >= lo:
                    d = -1; ent = max(O[j], lo); sl = hi + buf
            else:
                if side == 1 and L[j] <= lo:
                    d = -1; ent = min(O[j], lo); sl = hi + buf
                elif side == -1 and H[j] + S[j] >= hi:
                    d = 1; ent = max(O[j] + S[j], hi); sl = lo - buf
            if d != 0:
                filled = True; break
            j += 1
        if not filled: continue
        risk = abs(ent - sl); tp = ent + d * R * risk if R > 0 else 0.0
        e = eod[j]; px = 0.0; k = j; done = False
        # fill bar: only the stop can be hit (conservative)
        if d == 1 and L[j] <= sl: px = sl; done = True
        if d == -1 and H[j] + S[j] >= sl: px = sl; done = True
        k = j + 1
        while not done and k <= e:
            if d == 1:
                if L[k] <= sl: px = min(O[k], sl); done = True
                elif R > 0 and H[k] >= tp: px = max(O[k], tp); done = True
            else:
                ah = H[k] + S[k]; al = L[k] + S[k]
                if ah >= sl: px = max(O[k] + S[k], sl); done = True
                elif R > 0 and al <= tp: px = min(O[k] + S[k], tp); done = True
            if not done: k += 1
        if not done:
            k = e; px = O[e] if d == 1 else O[e] + S[e]
        pn[z] = (px - ent) * d * usd; xi[z] = k; dr[z] = d; rk[z] = risk * usd
    return pn, xi, dr, rk


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start - pd.Timedelta(days=5)][["o", "h", "l", "c", "s"]]
    O, H, L, C, S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = B.index; N = len(O); one = 1.0 / usd
    hm = (T.hour.values * 60 + T.minute.values).astype(np.int64)
    day = T.normalize()
    # end-of-day index: the first bar at/after 23:30 of the same day, else the day's last bar
    pos = pd.Series(np.arange(N), index=T)
    lastbar = pos.groupby(day).transform("max").values
    cut = pd.Series(np.where(hm >= 1410, np.arange(N), N + 1), index=T).groupby(day).transform("min").values
    eod = np.minimum(cut, lastbar).astype(np.int64)
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    h1 = B.resample("1h").agg(dict(o="first", h="max", l="min", c="last")).dropna()
    say(f"LAST H1 CANDLE BASE: gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot; years split {mid:%Y-%m-%d}")
    hdr = (f"{'variant':40s} {'trades':>6} {'/wk':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'fake':>5} {'buy':>5} {'sell':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5} {'risk':>5}")

    def zones(hb, mindz, valid):
        hh = h1[(h1.index.hour == hb) & (h1.index.dayofweek < 5) & (h1.index >= start)]
        zh, zl, zs, ze, zd = [], [], [], [], []
        for t, r in hh.iterrows():
            dd = t.normalize(); nx = days[days > dd]
            if len(nx) < 1 or (r.h - r.l) < mindz * one: continue
            s0 = first_of_day[nx[0]]; last = nx[min(valid, len(nx)) - 1]
            zh.append(r.h); zl.append(r.l); zs.append(s0); ze.append(eod[first_of_day[last]] + 1); zd.append(dd)
        return (np.array(zh), np.array(zl), np.array(zs, np.int64), np.array(ze, np.int64), pd.DatetimeIndex(zd))

    def run(nm, hb, mode, R, valid, mindz):
        zh, zl, zs, ze, zd = zones(hb, mindz, valid)
        p, xi, dr, rk = run_zones(O, H, L, C, S, hm, eod, zh, zl, zs, ze, mode, R, usd)
        ok = xi >= 0
        _, _, _, _ = None, None, None, None
        pS, xS, _, _ = run_zones(O, H, L, C, S * 1.5, hm, eod, zh, zl, zs, ze, mode, R, usd)
        fk = []
        for sd in range(3):
            rng = np.random.default_rng(sd); ht = zh - zl
            off = rng.uniform(0.5, 2.0, len(zh)) * ht * rng.choice([-1, 1], len(zh))
            pf_, xf, _, _ = run_zones(O, H, L, C, S, hm, eod, zh + off, zl + off, zs, ze, mode, R, usd)
            fk.append(pf_[xf >= 0])
        p = p[ok]; te = T[xi[ok]]; dr = dr[ok]
        if len(p) < 20: say(f"{nm:40s} {len(p):6d}"); return
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:40s} {len(p):6d} {len(p) / 104:4.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} "
            f"{pf(pS[xS >= 0]):5.2f} {pf(np.concatenate(fk)):5.2f} {pf(p[dr == 1]):5.2f} {pf(p[dr == -1]):5.2f} | {p.sum():+6.0f} {p[te >= mid].sum():+5.0f} "
            f"{p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+5.0f} {dp.min():+5.0f} {np.median(rk[ok]):5.1f}")

    for hb in (22, 23):
        for mode, mn in ((0, "BOUNCE"), (1, "BREAK")):
            say(f"\n== base = H1 {hb}:00 server bar, {mn}\n" + hdr)
            for valid in (1, 3, 5, 10):
                for R in (1.0, 2.0, 3.0, 0.0):
                    run(f"{mn} valid {valid}d TP {('%gR' % R) if R else 'none'}", hb, mode, R, valid, 0.0)
            for R in (1.0, 2.0, 0.0):
                run(f"{mn} valid 3d TP {('%gR' % R) if R else 'none'} zone>=$3", hb, mode, R, 3, 3.0)


if __name__ == "__main__":
    main()
