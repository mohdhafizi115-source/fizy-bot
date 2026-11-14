"""Round 113l (15 Nov 2026): is round 113k's H4 EMA 50 slope direction filter for GOLD FLIP real?
Neighbours: EMA 20 / 34 / 50 / 100 / 200 slope on H4; EMA 50 / 100 / 200 slope on H1; EMA 10 / 20 slope on D1; H4 close vs EMA 50.
Controls: a RANDOM sign per H4 bar (5 seeds, same "trade less" effect without information) and the opposite sign (against the slope).
Gap $4 and $5, lock $1, OCO +-$3, own $25 target.  Gold M1, last 2 years, 0.01 lot.  Uses flip113k.sim."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flip113k as K

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; K.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    full = d[["o", "h", "l", "c", "s"]]
    agg = dict(o="first", h="max", l="min", c="last")
    B = full[full.index >= start]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd; N = len(O)
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize()))
    f = lambda x: np.nan_to_num(np.asarray(x, dtype=float), nan=0.0)
    filt = {"none": np.zeros(N, np.int64)}
    for fr, lab, spans in (("4h", "H4", (20, 34, 50, 100, 200)), ("1h", "H1", (50, 100, 200)), ("1D", "D1", (10, 20))):
        b = full.resample(fr).agg(agg).dropna()
        for sp in spans:
            e = b.c.ewm(span=sp, adjust=False).mean()
            filt[f"{lab} EMA{sp} slope"] = f(K.to_m1(np.sign(e.diff()), T, fr)).astype(np.int64)
        if lab == "H4":
            e = b.c.ewm(span=50, adjust=False).mean()
            filt["H4 close vs EMA50"] = f(K.to_m1(np.sign(b.c - e), T, fr)).astype(np.int64)
            base = filt["H4 EMA50 slope"]
            filt["H4 EMA50 slope REVERSED"] = -base
            for sd in range(5):
                r = pd.Series(np.random.default_rng(sd).choice([-1, 1], len(b)), index=b.index)
                filt[f"RANDOM sign per H4 bar #{sd}"] = f(K.to_m1(r, T, fr)).astype(np.int64)
    say(f"GOLD FLIP direction-filter check: gold M1 {days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}, {len(days)} days, lock $1, OCO +-$3, $25 target, $ at 0.01 lot")
    hdr = (f"{'filter':32s} {'trades':>6} {'/day':>5} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'buy':>5} {'sell':>5} | {'net$':>6} {'12m$':>6} {'3m$':>5} {'pr3m':>5} | "
           f"{'DD':>5} {'wDay':>5} {'lossD':>5} {'d<-50':>5} {'d<-100':>6} {'Q+':>3}")
    for g in (4, 5):
        say(f"\n== gap ${g}\n" + hdr)
        for nm, tf in filt.items():
            Dg = np.ones(N) * g * one
            args = (0.0, one, live, dayid, usd, 3 * one, 25.0, tf)
            xi, p = K.sim(O, H, L, S, Dg, *args)
            _, ps = K.sim(O, H, L, S * 1.5, Dg, *args)
            te = T[xi]
            # direction of each closed trade: sign of (exit - entry) unknown here; use filter sign at exit bar as proxy for the
            # side when a filter is on, else skip
            dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
            eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
            q = dp.groupby(dp.index.to_period("Q")).sum()
            side = tf[xi]
            pb = pf(p[side > 0]) if (side > 0).sum() > 30 else float("nan"); psl = pf(p[side < 0]) if (side < 0).sum() > 30 else float("nan")
            say(f"{nm:32s} {len(p):6d} {len(p) / len(days):5.1f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(ps):5.2f} {pb:5.2f} {psl:5.2f} | "
                f"{p.sum():+6.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | "
                f"{dd:+5.0f} {dp.min():+5.0f} {(dp < 0).sum():5d} {(dp < -50).sum():5d} {(dp < -100).sum():6d} {(q > 0).sum():2d}/{len(q)}")
            if nm.startswith("H4 EMA50 slope") and not nm.endswith("REVERSED") and g == 4:
                say("   by quarter: " + " / ".join(f"{v:+.0f}" for v in q.values))


if __name__ == "__main__":
    main()
