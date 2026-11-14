"""Round 113 (14 Nov 2026): the TikTok "buy stop / sell stop" gold M1 trick the owner sent ("buat ea macam ni. makan sikit2 je").
The clip (zupper.fx, XAUUSD-ECN M1, 10 s): a BUY 0.5 lot open with a SELL STOP trailing just under price; when it fills the
buy is closed and a SELL 0.5 is open with a BUY STOP trailing just above, and so on: an always-in TRAILING STOP-AND-REVERSE
with a tight gap ($0.3-2 on screen).  At 0.5 lot a $2 move is $100, so the screen looks rich; at 0.01 lot it is $2.
Simulated on the broker's gold M1 bars, last 2 years (data run 43450356142):
  gap D fixed $0.3 / 0.5 / 1 / 2 / 3 / 5, or k x ATR(14, M1) (k 0.5 / 1 / 2 / 3), always in from 01:30 to 23:30 server, or
  only 15:30-18:00 server (NY open), or only while the cost gate ATR >= 8 x spread is open.
  Stop levels are frozen at the start of each bar from the previous bars (no intrabar look-ahead); a bar flips at most once,
  which UNDER-counts flips (and spreads paid) whenever D is smaller than the bar's range: the tight gaps are an optimistic
  upper bound.  Real spread on every flip (long in at the ask / out at the bid)."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()
jit = G.jit


@jit
def sar(O, H, L, S, D, live):
    """live[j] True = may be in the market at bar j. Returns arrays of (entry bar, exit bar, pnl in price)."""
    n = len(O); ei = np.zeros(n, np.int64); xi = np.zeros(n, np.int64); pn = np.zeros(n); m = 0
    pos = 0; ent = 0.0; e0 = 0; stop = 0.0
    for j in range(n):
        if pos != 0 and not live[j]:                                       # window end: flat at the open
            px = O[j] if pos == 1 else O[j] + S[j]
            ei[m] = e0; xi[m] = j; pn[m] = (px - ent) * pos; m += 1; pos = 0
            continue
        if pos == 0:
            if live[j] and (j == 0 or not live[j - 1]):                     # window start: go long at the ask
                pos = 1; ent = O[j] + S[j]; e0 = j; stop = O[j] - D[j]
            continue
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop)                                       # sell stop fills at the bid
                ei[m] = e0; xi[m] = j; pn[m] = px - ent; m += 1
                pos = -1; ent = px; e0 = j; stop = px + S[j] + D[j]        # new short, buy stop above (ask terms)
            else:
                stop = max(stop, H[j] - D[j])
        else:
            if H[j] + S[j] >= stop:
                px = max(O[j] + S[j], stop)                                # buy stop fills at the ask
                ei[m] = e0; xi[m] = j; pn[m] = ent - px; m += 1
                pos = 1; ent = px; e0 = j; stop = px - S[j] - D[j]
            else:
                stop = min(stop, L[j] + S[j] + D[j])
    return ei[:m], xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]].copy()
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; a1 = M.atr(B).values
    hm = T.hour.values * 60 + T.minute.values
    day = T.normalize()
    wd = T.day_of_week.values < 5
    base = wd & (hm >= 90) & (hm < 1410)
    ny = wd & (hm >= 930) & (hm < 1080)
    gate = base & (a1 >= 8 * S)
    a3 = end - pd.Timedelta(days=91)
    ndays = len(np.unique(day[base]))
    say(f"gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {ndays} trading days, median spread ${np.median(S) * usd:.2f}, median ATR(M1) ${np.nanmedian(a1) * usd:.2f}; $ per 0.01 lot")
    say(f"{'variant':34s} {'trades':>7} {'/day':>6} {'win%':>5} {'PF':>5} {'yr1':>5} {'yr2':>5} | {'net$':>8} {'12m$':>8} {'3m$':>7} | {'maxDD':>7} {'wDay':>6} | {'spread paid$':>12}")
    for wname, live in (("01:30-23:30", base), ("NY 15:30-18:00", ny), ("gate>=8 only", gate)):
        for lab, Dv in [(f"${x}", np.full(len(O), x)) for x in (0.3, 0.5, 1.0, 2.0, 3.0, 5.0)] + \
                       [(f"{k}xATR", np.nan_to_num(k * a1, nan=1.0)) for k in (0.5, 1.0, 2.0, 3.0)]:
            ei, xi, pn = sar(O, H, L, S, Dv, live)
            if len(pn) < 20: continue
            p = pn * usd; te = T[xi]
            dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
            spread = (S[ei].sum() + S[xi].sum()) / 2 * usd
            y1 = p[te < mid]; y2 = p[te >= mid]
            say(f"{wname + ' gap ' + lab:34s} {len(p):7d} {len(p) / ndays:6.1f} {100 * (p > 0).mean():5.0f} {pf(p):5.2f} {pf(y1):5.2f} {pf(y2):5.2f} | "
                f"{p.sum():+8.0f} {y2.sum():+8.0f} {p[te >= a3].sum():+7.0f} | {dd:+7.0f} {dp.min():+6.0f} | {spread:12.0f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
