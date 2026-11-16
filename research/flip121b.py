"""Round 121b (16 Nov 2026): real-time FLIP, where to lock the stop once the trade is +X.  Owner: "untung 10pip tu kenapa tak terus lock
be dekat 10pip?".  Live v2.35: at +$1 the stop freezes at entry - $4 (lock - gap).  Variants: at +X ($1 / $2 / $3 / $5) the stop jumps to
entry - 4 (live) / entry + 0 (breakeven) / entry + $0.5 / entry + X - $0.5 (just behind the price); the rest unchanged (gap $5, OCO +-3,
reverse on a stop, $25 target).  Same path engine as round 121, last 3 months and the 3 before, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf


def main():
    mt, sw = F.W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = F.SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    nd = len(np.unique(dayid[live & (T >= a3)]))
    say(f"REAL-TIME FLIP, lock level, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), gap $5, $ at 0.01 lot")
    say(f"{'lock rule':40s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bigWin':>6} | {'prev PF':>7} {'net$':>6}")
    for X in (1.0, 2.0, 3.0, 5.0):
        for nm, fz in (("entry - $4 (live at +$1)", -4.0), ("breakeven (entry + 0)", 0.0), ("entry + $0.5", 0.5), (f"entry + ${X - 0.5:g} (behind price)", X - 0.5)):
            if X == 1.0 and nm.startswith("entry + $0.5"): continue
            for orr in (False, True):
                xi, p = F.sim(O, H, L, C, S, live, first, dayid, usd, 5.0, X, 3.0, 25.0, True, orr, 1, fz)
                xS, pS = F.sim(O, H, L, C, S * 1.5, live, first, dayid, usd, 5.0, X, 3.0, 25.0, True, orr, 1, fz)
                te = T[xi]; m = te >= a3; m2 = te < a3; x = p[m]
                dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
                lab = f"at +${X:g} -> {nm}" + (" [coin]" if orr else "")
                say(f"{lab:40s} | {len(x):5d} {len(x) / nd:4.0f} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {x.sum():+6.0f} "
                    f"{(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} {x.max():+6.0f} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f}")
        say("")


if __name__ == "__main__":
    main()
