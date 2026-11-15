"""Round 119b (15 Nov 2026): the TikTok clip on an ECN / raw-spread account.  Owner: "aku perasan akaun dia ecn, maybe 0 spread".
Same simulator as round 119 (flip113c.sim), last 3 months / the 3 before, 0.01 lot.  Costs replaced by a fixed raw spread of
$0.00 / $0.05 / $0.10 (gold price units = $ per 0.01 lot) plus a commission of $0 / $0.06 / $0.07 per round turn at 0.01 lot
($6-7 per lot, the usual ECN rate).  $0 spread + $0 commission is the theoretical best case (no account has it).
At most one flip per bar, so tight gaps UNDER-count flips (optimistic)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flip113c as FC

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; FC.DATA = DATA
say = M.say; pf = M.pf


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= a6][["o", "h", "l", "c", "s"]]
    O, H, L, S0 = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410); one = 1.0 / usd
    nd3 = len(np.unique(dayid[live & (T >= a3)]))
    say(f"TIKTOK FLIP, ECN COSTS, XAUUSD LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    say(f"broker (standard) median spread ${np.median(S0) * usd:.2f} per 0.01 lot")
    say(f"{'variant':44s} | {'trd':>6} {'/day':>4} {'win%':>4} {'PF':>5} {'net$':>7} {'DD':>6} {'wDay':>5} {'blow':>4} | {'prev PF':>7} {'net$':>7}")
    for sp, cm in ((0.0, 0.0), (0.0, 0.06), (0.05, 0.06), (0.10, 0.07), (0.10, 0.0)):
        S = np.full(len(O), sp * one)
        for nm0, mode, gap in [("TRAIL", 0, g) for g in (0.3, 0.5, 1.0, 2.0, 3.0)] + [("TRAIL+TP$1", 1, g) for g in (0.5, 1.0, 2.0)] + [("FREEZE", 3, 5.0)]:
            xi, p = FC.sim(O, H, L, S, gap * one, live, dayid, usd, 1e9, mode, one, one)
            p = p - cm
            te = T[xi]; m = te >= a3; m2 = te < a3; x = p[m]
            if len(x) == 0: continue
            dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
            bal = 100.0; blow = 0
            for v in x:
                bal += v
                if bal <= 0: blow += 1; bal = 100.0
            nm = f"sp${sp:.2f} com${cm:.2f} {nm0} gap${gap:g}"
            say(f"{nm:44s} | {len(x):6d} {len(x) / nd3:4.0f} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {x.sum():+7.0f} {dd:+6.0f} {dp.min():+5.0f} {blow:4d} | "
                f"{pf(p[m2]):7.2f} {p[m2].sum():+7.0f}")
        say("")


if __name__ == "__main__":
    main()
