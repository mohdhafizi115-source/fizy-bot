"""Round 115h (15 Nov 2026): live v2.32 base zone vs the same with a thickness filter, judged on the LAST 3 MONTHS (owner's new test
window, 15 Nov: "lepas ni semua modul test 3 bulan je") with the 3 months before as a repeat check.  Owner: "mana lagi better? bagi
perbandingan".  Filters: base height >= 0 (live) / 0.3 / 0.4 / 0.5 x ATR(H1); controls: a random H1 bar of the same day (3 seeds).
Gold M1, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import base115g as BG

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; BG.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    start = a6 - pd.Timedelta(days=10)
    B = d[d.index >= start - pd.Timedelta(days=10)][["o", "h", "l", "c", "s"]]
    O, H, L, C, S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = B.index; N = len(O)
    hm = (T.hour.values * 60 + T.minute.values).astype(np.int64)
    day = T.normalize()
    pos = pd.Series(np.arange(N), index=T)
    lastbar = pos.groupby(day).transform("max").values
    cut = pd.Series(np.where(hm >= 1410, np.arange(N), N + 1), index=T).groupby(day).transform("min").values
    eod = np.minimum(cut, lastbar).astype(np.int64)
    dayend = (np.arange(N) == lastbar)
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["d"] = day
    d1 = b.groupby("d").agg(o=("o", "first"), c=("c", "last"))
    h1 = b.groupby(["d", "hr"]).agg(h=("h", "max"), l=("l", "min"))
    h1["atr"] = (h1.h - h1.l).rolling(14).mean().values
    say(f"BASE ZONE, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat check: {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")

    def zones(randseed=None):
        rng = np.random.default_rng(randseed if randseed is not None else 0)
        rows = []
        for dd in days:
            if dd < a6 - pd.Timedelta(days=7) or dd not in d1.index: continue
            nx = days[days > dd]
            if len(nx) < 1: continue
            D = d1.loc[dd]; col = -1 if D.c < D.o else (1 if D.c > D.o else 0)
            if col == 0: continue
            hr = 23 if randseed is None else int(rng.integers(2, 21))
            if (dd, hr) not in h1.index: continue
            r = h1.loc[(dd, hr)]
            if r.h <= r.l or not np.isfinite(r.atr) or r.atr <= 0: continue
            rows.append(dict(hi=r.h, lo=r.l, want=-col, zs=first_of_day[nx[0]], ze=eod[first_of_day[nx[min(5, len(nx)) - 1]]] + 1,
                             ratio=(r.h - r.l) / r.atr))
        return pd.DataFrame(rows)

    hdr = (f"{'variant':38s} | {'trd':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bestD':>5} {'+days':>5} {'-days':>5} | "
           f"{'prev3m: trd':>11} {'PF':>5} {'net$':>6}")
    say("\n" + hdr)

    def run(Z, mask, nm):
        Zm = Z[mask]
        args = (Zm.hi.values, Zm.lo.values, Zm.zs.values.astype(np.int64), Zm.ze.values.astype(np.int64), Zm.want.values.astype(np.int64), np.zeros(len(Zm)))
        p, xi = BG.run_g(O, H, L, C, S, hm, eod, dayend, *args, usd)
        pS, xS = BG.run_g(O, H, L, C, S * 1.5, hm, eod, dayend, *args, usd)
        ok = xi >= 0; te = T[xi[ok]]; p = p[ok]; teS = T[xS[xS >= 0]]; pS = pS[xS >= 0]
        m = te >= a3; m2 = (te >= a6) & (te < a3)
        x = p[m]; tx = te[m]
        if len(x) == 0: say(f"{nm:38s} |    0"); return
        dp = pd.Series(x, index=tx.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        say(f"{nm:38s} | {len(x):4d} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {pf(pS[teS >= a3]):5.2f} {x.sum():+6.0f} {ddn:+5.0f} {dp.min():+5.0f} "
            f"{dp.max():+5.0f} {(dp > 0).sum():5d} {(dp < 0).sum():5d} | {m2.sum():11d} {pf(p[m2]):5.2f} {p[m2].sum():+6.0f}")

    Z = zones()
    for x in (0, .3, .4, .5):
        run(Z, Z.ratio >= x, f"base >= {x:.1f} ATR(H1)" + ("  (LIVE now)" if x == 0 else ""))
    run(Z, Z.ratio < .4, "only the thin bases (< 0.4 ATR)")
    for sd in (1, 2, 3):
        R = zones(sd)
        run(R, R.ratio >= 0, f"control random H1 bar seed {sd}")
        run(R, R.ratio >= .4, f"control random H1 bar seed {sd}, >= 0.4")


if __name__ == "__main__":
    main()
