"""Round 114b (14 Nov 2026): the FLIP rule on BTCUSD with wider stops.  Owner: "maybe sl kena ikut kos spread atau lebih.
konsep tetap sama cuma besarkan jarak stop".  Same simulation as flipbtc114.py.  Gap D per day from
  (a) k x the day's median spread (k 10 / 20 / 30 / 50 / 75 / 100 / 150 / 200),
  (b) f x ATR14(D1) (mean true range of the last 14 completed days; f 0.1 / 0.15 / 0.2 / 0.3 / 0.4 / 0.5 / 0.75),
  (c) wider shares of the 01:30 open (1.5 / 2 / 3 %).
Lock 0.2 x gap (as gold) and 1 x gap; OCO 0.6 x gap; weekdays / every day; flat overnight."""
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
SYM = "BTCUSD"


def main():
    mt, sw = W.read_meta(SYM)
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, SYM + ".csv"), mt["point"])
    end = d.index[-1]; start = max(d.index[0], end - pd.Timedelta(days=730))
    mid = start + (end - start) / 2; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182); a12 = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=30)][["o", "h", "l", "c", "s"]]
    day = Bw.index.normalize(); Dd = Bw.groupby(day).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"), s=("s", "median"))
    pc = Dd.c.shift(); tr = np.maximum(Dd.h - Dd.l, np.maximum((Dd.h - pc).abs(), (Dd.l - pc).abs()))
    datr = tr.rolling(14).mean().shift(1); dspr = Dd.s.shift(1)                          # yesterday's median spread (known at 01:30)
    B = Bw[Bw.index >= start]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; nd_ = T.normalize()
    hm = T.hour.values * 60 + T.minute.values; wdm = T.day_of_week.values < 5
    dayid = nd_.values.astype("datetime64[D]").astype(np.int64)
    win = (hm >= 90) & (hm < 1410)
    first = pd.Series(np.where(win, O, np.nan), index=T).groupby(nd_).transform("first").values
    A = datr.reindex(nd_).values; SP = dspr.reindex(nd_).values
    rng = np.random.default_rng(7); ud = np.unique(dayid); rmap = dict(zip(ud, rng.choice([-1, 1], len(ud))))
    sd_rand = np.array([rmap[x] for x in dayid], dtype=np.int64); sd_long = np.ones(len(O), np.int64)
    say(f"{SYM} M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; median ATR14(D1) ${np.nanmedian(A):,.0f} ({100 * np.nanmedian(A / first):.2f}% of price), "
        f"median spread ${np.nanmedian(SP):.1f}; $ per 0.01 lot")
    say(f"{'variant':38s} {'gap$':>6} {'trades':>6} {'/day':>5} {'PF':>5} {'h1':>5} {'h2':>5} {'strs':>5} {'rand':>5} | {'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5} {'big':>4}")

    def run(nm, live, Dv, lkf):
        Dv = np.nan_to_num(Dv, nan=0.0); lv = live & (Dv > 0)
        LK = Dv * lkf; K = Dv * 0.6
        xi, p, dr = F.sim(O, H, L, S, Dv, LK, K, lv, dayid, sd_long, usd)
        if len(p) < 30: return
        _, ps, _ = F.sim(O, H, L, S * 1.5, Dv, LK, K, lv, dayid, sd_long, usd)
        _, pr, _ = F.sim(O, H, L, S, Dv, LK, K * 0, lv, dayid, sd_rand, usd)
        te = T[xi]; ndays = len(np.unique(dayid[lv]))
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:38s} {np.median(Dv[lv]):6.0f} {len(p):6d} {len(p) / ndays:5.1f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(ps):5.2f} {pf(pr):5.2f} | "
            f"{p.sum():+6.0f} {p[te >= a12].sum():+5.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+5.0f} {dp.min():+5.0f} {p.max():4.0f}")

    for wname, live in (("wkdy", win & wdm), ("all", win)):
        for lkf in (0.2, 1.0):
            say(f"\n== {wname}, lock {lkf:g} x gap")
            for k in (10, 20, 30, 50, 75, 100, 150, 200):
                run(f"{wname} {k}x spread lock{lkf:g}", live, k * SP, lkf)
            for f in (0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75):
                run(f"{wname} {f:g}xATR(D1) lock{lkf:g}", live, f * A, lkf)
            for pct in (1.5, 2.0, 3.0):
                run(f"{wname} {pct:g}% of price lock{lkf:g}", live, first * pct / 100, lkf)


if __name__ == "__main__":
    main()
