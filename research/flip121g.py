"""Round 121g (16 Nov 2026): the owner's corrected FLIP stop.  Owner: "maksud aku lepas profit 1$ terus alih sl ke area profit ...
kalau price bertambah profit lagi 0.50$, adjust lagi sl" -> chose "lock breakeven first": SL fixed $4 from the entry; once the trade
is +$1 the SL goes to the entry; every further +$0.50 moves it up $0.50 (SL = entry + floor((profit - 1) / 0.5) x 0.5), real time;
stop hit -> reverse; OCO +-$3, $25 target, out 23:30.  Also lock at +$2 / +$3 and steps $0.25 / $1.  Path engine, last 3 months
and the 3 before, OHLC and coin order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip121 as F
import flip121f as G
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
    Tx = d.index; hm = Tx.hour.values * 60 + Tx.minute.values; wd = Tx.day_of_week.values < 5
    dayid = Tx.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    first = live & np.r_[True, (dayid[1:] != dayid[:-1]) | ~live[:-1]]
    nd = len(np.unique(dayid[live & (Tx >= a3)]))
    say(f"FLIP: SL $4, BREAKEVEN at +$1, then +$0.50 steps, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), 0.01 lot")
    say(f"{'rule':34s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bigW':>5} | {'prev PF':>7} {'net$':>6} {'wDay':>5} | {'coin PF':>7} {'prev':>5} {'net$':>6}")

    def row(lab, fn):
        xi, p = fn(S, False); xc, pc = fn(S, True); xS, pS = fn(S * 1.5, False)
        te = Tx[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum()
        tc = Tx[xc]
        say(f"{lab:34s} | {len(v):5d} {len(v) / nd:4.0f} {100 * (v > 0).mean():4.0f} {pf(v):5.2f} {pf(pS[Tx[xS] >= a3]):5.2f} {v.sum():+6.0f} "
            f"{(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} {v.max():+5.0f} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {dp2.min():+5.0f} | "
            f"{pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f} {pc[tc >= a3].sum():+6.0f}")

    row("LIVE v2.35 (trail $5, freeze)", lambda s, r: F.sim(O, H, L, C, s, live, first, dayid, usd, 5.0, 1.0, 3.0, 25.0, True, r, 1))
    row("v2.36 (SL $4, trail $4 after +$1)", lambda s, r: G.sim(O, H, L, C, s, live, first, dayid, usd, 4.0, 4.0, 1.0, 3.0, 25.0, r, 1))
    for lk, st in ((1.0, 0.5), (1.0, 0.25), (1.0, 1.0), (2.0, 0.5), (3.0, 0.5)):
        row(f"OWNER: BE at +${lk:g}, step ${st:g}", lambda s, r, lk=lk, st=st: G.sim(O, H, L, C, s, live, first, dayid, usd, 4.0, 0.0, lk, 3.0, 25.0, r, 1, st))


if __name__ == "__main__":
    main()
