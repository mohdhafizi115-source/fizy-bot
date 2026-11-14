"""Round 113h (15 Nov 2026): the live GOLD FLIP (v2.31) day by day.  Owner: "kira ada loss jugak la walaupun 25$ sehari" -> "cuba kira".
Live rule: OCO at the 01:30 server open +- $3, stop $5 trailed until +$1 then frozen, reverse when hit, out 23:30, and the module's
own $25 target: once today's CLOSED profit reaches $25 the position is not reversed and the module waits for tomorrow.
Counts: days that reach $25, days in profit below $25, flat days, losing days by size, losing streaks, by month and by weekday,
with and without the target.  Gold M1, last 2 years, 0.01 lot, data run 43450356142."""
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
def sim(O, H, L, S, D, live, dayid, usd, lk, K, tgt):
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; locked = False; wait = False; up = 0.0; dn = 0.0; dsum = 0.0; done = False
    for j in range(n):
        if not live[j]:
            if pos != 0:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1; pos = 0
            wait = False
            continue
        if j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]:
            dsum = 0.0; done = False
            if pos == 0:
                wait = True; up = O[j] + K; dn = O[j] - K
        if done: continue
        if pos == 0 and wait:
            hb = H[j] + S[j] >= up; hs = L[j] <= dn
            if not hb and not hs: continue
            if hb and hs:
                if up - (O[j] + S[j]) <= O[j] - dn: hs = False
                else: hb = False
            wait = False; locked = False
            if hb:
                pos = 1; ent = max(up, O[j] + S[j]); stop = ent - S[j] - D
            else:
                pos = -1; ent = min(dn, O[j]); stop = ent + S[j] + D
            continue
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); v = (px - ent) * usd; xi[m] = j; pn[m] = v; m += 1; dsum += v
                if tgt > 0 and dsum >= tgt:
                    pos = 0; done = True
                else:
                    pos = -1; ent = px; stop = px + S[j] + D; locked = False
            elif not locked:
                stop = max(stop, H[j] - D)
                if H[j] - ent >= lk: locked = True
        elif pos == -1:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); v = (ent - px) * usd; xi[m] = j; pn[m] = v; m += 1; dsum += v
                if tgt > 0 and dsum >= tgt:
                    pos = 0; done = True
                else:
                    pos = 1; ent = px; stop = px - S[j] - D; locked = False
            elif not locked:
                stop = min(stop, al + D)
                if ent - al >= lk: locked = True
    return xi[:m], pn[:m]


def streak(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v else 0; best = max(best, cur)
    return best


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); a3 = end - pd.Timedelta(days=91); a12 = end - pd.Timedelta(days=365)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize()))
    say(f"GOLD FLIP v2.31 day by day: gold M1 {days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}, {len(days)} trading days, $ at 0.01 lot")
    for tgt in (25.0, 0.0):
        xi, p = sim(O, H, L, S, 5 * one, live, dayid, usd, one, 3 * one, tgt)
        te = T[xi]
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum().reindex(days, fill_value=0.0)
        nt = pd.Series(1, index=te.normalize()).groupby(level=0).sum().reindex(days, fill_value=0)
        tag = "WITH the $25 target (live)" if tgt else "WITHOUT the target"
        say(f"\n==== {tag}: {len(p)} trades, PF {pf(p):.2f}, net {p.sum():+,.0f} $, last 12 months {dp[dp.index >= a12].sum():+,.0f} $, "
            f"last 3 months {dp[dp.index >= a3].sum():+,.0f} $")
        for nm, sel in (("2 years", dp.index >= days[0]), ("last 12 months", dp.index >= a12), ("last 3 months", dp.index >= a3)):
            x = dp[sel]; n = len(x)
            hit = (x >= 25).sum(); win = ((x > 0) & (x < 25)).sum(); flat = (x == 0).sum(); los = (x < 0).sum()
            say(f"\n-- {nm}: {n} days")
            say(f"   reached +$25 or more : {hit:4d} days ({100 * hit / n:4.1f}%)   average {x[x >= 25].mean():+7.2f} $")
            say(f"   profit under $25     : {win:4d} days ({100 * win / n:4.1f}%)   average {x[(x > 0) & (x < 25)].mean():+7.2f} $")
            say(f"   no trade / zero      : {flat:4d} days ({100 * flat / n:4.1f}%)")
            say(f"   loss                 : {los:4d} days ({100 * los / n:4.1f}%)   average {x[x < 0].mean():+7.2f} $")
            for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 50), (50, 75), (75, 100), (100, 1e9)):
                c = ((x < -lo) & (x >= -hi)).sum()
                say(f"      loss {lo:>3}-{('...' if hi > 1e8 else int(hi)):>3} $ : {c:4d} days")
            say(f"   best day {x.max():+.2f} $, worst day {x.min():+.2f} $, median day {x.median():+.2f} $, trades a day {nt[sel].mean():.1f}")
            say(f"   longest run of losing days {streak((x < 0).values)}, of days without +$25 {streak((x < 25).values)}")
            wk = x.groupby(x.index.to_period("W")).sum()
            say(f"   weeks: {len(wk)}, in profit {(wk > 0).sum()} ({100 * (wk > 0).mean():.0f}%), worst week {wk.min():+.0f} $, best week {wk.max():+.0f} $")
        eq = dp.cumsum(); dd = eq - eq.cummax()
        say(f"\n   max drawdown {dd.min():+.0f} $ (low on {dd.idxmin():%Y-%m-%d}); days below the previous peak: {(dd < 0).sum()} of {len(dd)}")
        say("\n   by month: days / +$25 days / losing days / net $")
        for per, x in dp.groupby(dp.index.to_period("M")):
            say(f"   {per}  {len(x):3d}  {(x >= 25).sum():3d}  {(x < 0).sum():3d}  {x.sum():+8.0f}")
        say("\n   by weekday: days / +$25 days / losing days / net $")
        for w, x in dp.groupby(dp.index.day_of_week):
            say(f"   {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][w]}  {len(x):3d}  {(x >= 25).sum():3d}  {(x < 0).sum():3d}  {x.sum():+8.0f}")
        say("\n   10 worst days: " + ", ".join(f"{i:%Y-%m-%d} {v:+.0f}" for i, v in dp.nsmallest(10).items()))
        say("   10 best days : " + ", ".join(f"{i:%Y-%m-%d} {v:+.0f}" for i, v in dp.nlargest(10).items()))


if __name__ == "__main__":
    main()
