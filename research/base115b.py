"""Round 115b (15 Nov 2026): robustness of round 115's last-H1-candle base zone.  Round 115 found the 22:00 server base passing as a
BREAK (year 1 < 1) and the 23:00 base passing as a BOUNCE with no TP (PF 1.14-1.28) -- opposite directions on neighbouring bars.
Here: base = the H1 bar of 18 / 19 / 20 / 21 / 22 / 23 server, and 23:00-23:44 only (the rollover minutes cut out), plus a RANDOM H1
bar of the day (01-23, 3 seeds) as a control for "is the LAST candle special".  BOUNCE / BREAK, valid 5 / 10 days, TP 2R / none.
Same rules as base115.py (run_zones)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import base115 as Bz

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; Bz.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start - pd.Timedelta(days=5)][["o", "h", "l", "c", "s"]]
    O, H, L, C, S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = B.index; N = len(O)
    hm = (T.hour.values * 60 + T.minute.values).astype(np.int64)
    day = T.normalize()
    pos = pd.Series(np.arange(N), index=T)
    lastbar = pos.groupby(day).transform("max").values
    cut = pd.Series(np.where(hm >= 1410, np.arange(N), N + 1), index=T).groupby(day).transform("min").values
    eod = np.minimum(cut, lastbar).astype(np.int64)
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["mn"] = T.minute; b["d"] = day
    say(f"BASE ZONE robustness: gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot")
    hdr = (f"{'variant':40s} {'trades':>6} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'buy':>5} {'sell':>5} | {'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5}")

    def zones_from(tbl, valid):
        zh, zl, zs, ze = [], [], [], []
        for dd, r in tbl.iterrows():
            if dd < start or dd.dayofweek >= 5: continue
            nx = days[days > dd]
            if len(nx) < 1: continue
            zh.append(r.h); zl.append(r.l); zs.append(first_of_day[nx[0]]); ze.append(eod[first_of_day[nx[min(valid, len(nx)) - 1]]] + 1)
        return np.array(zh), np.array(zl), np.array(zs, np.int64), np.array(ze, np.int64)

    def tbl_hour(hb, maxmin=60):
        x = b[(b.hr == hb) & (b.mn < maxmin)]
        return x.groupby("d").agg(h=("h", "max"), l=("l", "min"))

    def tbl_random(seed):
        rng = np.random.default_rng(seed); dl = np.unique(b.d.values); pick = dict(zip(dl, rng.integers(2, 23, len(dl))))
        x = b[b.hr.values == np.array([pick[v] for v in b.d.values])]
        return x.groupby("d").agg(h=("h", "max"), l=("l", "min"))

    def run(nm, tbl, mode, R, valid):
        zh, zl, zs, ze = zones_from(tbl, valid)
        p, xi, dr, rk = Bz.run_zones(O, H, L, C, S, hm, eod, zh, zl, zs, ze, mode, R, usd)
        pS, xS, _, _ = Bz.run_zones(O, H, L, C, S * 1.5, hm, eod, zh, zl, zs, ze, mode, R, usd)
        ok = xi >= 0; p = p[ok]; te = T[xi[ok]]; dr = dr[ok]
        if len(p) < 20: say(f"{nm:40s} {len(p):6d}"); return
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:40s} {len(p):6d} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(pS[xS >= 0]):5.2f} {pf(p[dr == 1]):5.2f} {pf(p[dr == -1]):5.2f} | "
            f"{p.sum():+6.0f} {p[te >= mid].sum():+5.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+5.0f} {dp.min():+5.0f}")

    tabs = [(f"H1 {h}:00", tbl_hour(h)) for h in (18, 19, 20, 21, 22, 23)] + [("H1 23:00-23:44 (no rollover)", tbl_hour(23, 45))] + \
           [(f"RANDOM H1 bar #{s}", tbl_random(s)) for s in range(3)]
    for mode, mn in ((0, "BOUNCE"), (1, "BREAK")):
        for valid in (5, 10):
            for R in (2.0, 0.0):
                say(f"\n== {mn}, valid {valid}d, TP {('%gR' % R) if R else 'none (23:30)'}\n" + hdr)
                for nm, tb in tabs:
                    run(nm, tb, mode, R, valid)


if __name__ == "__main__":
    main()
