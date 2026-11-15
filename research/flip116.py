"""Round 116 (15 Nov 2026): the live GOLD FLIP (v2.31) on the owner's new test window, the LAST 3 MONTHS, with the 3 months before as a
repeat check.  Owner: "test modul flip kita untuk 3 bulan".  Live rule: OCO at the 01:30 server open +- $3, stop $5 trailed until the
trade is +$1 then frozen, reverse when hit, no TP, out 23:30, own $25 daily target.  Also: no target, gap $4, and baselines (always BUY /
always SELL 01:30 -> 23:30 with a fixed $5 stop).  Day statistics as round 113h.  Gold M1, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import flip113h as F

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; F.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit


@jit
def hold(O, H, L, S, live, dayid, usd, d, stop):
    n = len(O); xi = np.zeros(n, np.int64); pn = np.zeros(n); m = 0; pos = 0; ent = 0.0; sl = 0.0
    for j in range(n):
        if not live[j]:
            if pos == 1 or pos == -1:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1
            pos = 0
            continue
        if (j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]) and pos == 0:
            pos = d; ent = O[j] + S[j] if d == 1 else O[j]; sl = ent - d * stop
            continue
        if pos == 1 and L[j] <= sl:
            xi[m] = j; pn[m] = (min(O[j], sl) - ent) * usd; m += 1; pos = 2
        elif pos == -1 and H[j] + S[j] >= sl:
            xi[m] = j; pn[m] = (ent - max(O[j] + S[j], sl)) * usd; m += 1; pos = 2
    return xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= a6 - pd.Timedelta(days=3)][["o", "h", "l", "c", "s"]]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize()))
    say(f"GOLD FLIP, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat check {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    hdr = (f"{'variant':34s} | {'trd':>5} {'/day':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'bestD':>5} "
           f"{'+25d':>4} {'lossD':>5} {'days':>4} | {'prev: trd':>9} {'PF':>5} {'net$':>6} {'DD':>5} {'wDay':>5}")
    say("\n" + hdr)

    def show(nm, xi, p, xS, pS):
        te = T[xi]; tS = T[xS]
        out = []
        for lo, hi in ((a3, end + pd.Timedelta(days=1)), (a6, a3)):
            m = (te >= lo) & (te < hi); x = p[m]
            dd_ = days[(days >= lo) & (days < hi)]
            dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum().reindex(dd_, fill_value=0.0)
            eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
            ms = (tS >= lo) & (tS < hi)
            out.append((len(x), len(x) / max(len(dd_), 1), 100 * (x > 0).mean() if len(x) else 0, pf(x), pf(pS[ms]), x.sum(), ddn,
                        dp.min(), dp.max(), (dp >= 25).sum(), (dp < 0).sum(), len(dd_)))
        a, b = out
        say(f"{nm:34s} | {a[0]:5d} {a[1]:4.1f} {a[2]:4.0f} {a[3]:5.2f} {a[4]:5.2f} {a[5]:+6.0f} {a[6]:+5.0f} {a[7]:+5.0f} {a[8]:+5.0f} "
            f"{a[9]:4d} {a[10]:5d} {a[11]:4d} | {b[0]:9d} {b[3]:5.2f} {b[5]:+6.0f} {b[6]:+5.0f} {b[7]:+5.0f}")
        return te, p

    for nm, D, tgt in (("LIVE v2.31 ($5 gap, $25 target)", 5, 25.0), ("no $25 target", 5, 0.0), ("gap $4, $25 target", 4, 25.0), ("gap $4, no target", 4, 0.0)):
        xi, p = F.sim(O, H, L, S, D * one, live, dayid, usd, one, 3 * one, tgt)
        xS, pS = F.sim(O, H, L, S * 1.5, D * one, live, dayid, usd, one, 3 * one, tgt)
        r = show(nm, xi, p, xS, pS)
        if nm.startswith("LIVE"): live_te, live_p = r
    for nm, dr in (("baseline: always BUY 01:30-23:30", 1), ("baseline: always SELL 01:30-23:30", -1)):
        xi, p = hold(O, H, L, S, live, dayid, usd, dr, 5 * one)
        xS, pS = hold(O, H, L, S * 1.5, live, dayid, usd, dr, 5 * one)
        show(nm + ", SL $5", xi, p, xS, pS)
    say("\nLIVE v2.31, last 3 months by month and by week:")
    m3 = live_te >= a3
    dp = pd.Series(live_p[m3], index=live_te[m3].normalize()).groupby(level=0).sum().reindex(days[days >= a3], fill_value=0.0)
    for per, x in dp.groupby(dp.index.to_period("M")):
        say(f"   {per}: {len(x):2d} days, +$25 days {(x >= 25).sum():2d}, losing days {(x < 0).sum():2d}, net {x.sum():+7.0f} $")
    wk = dp.groupby(dp.index.to_period("W")).sum()
    say("   weeks: " + ", ".join(f"{w.start_time:%d %b} {v:+.0f}" for w, v in wk.items()))
    say("   10 worst days: " + ", ".join(f"{i:%d %b} {v:+.0f}" for i, v in dp.nsmallest(10).items()))
    say("   10 best days : " + ", ".join(f"{i:%d %b} {v:+.0f}" for i, v in dp.nlargest(10).items()))


if __name__ == "__main__":
    main()
