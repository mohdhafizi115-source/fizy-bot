"""Round 113b (14 Nov 2026): round 113's best stop-and-reverse cells with the owner's daily target.
Owner: "kau buat ea ikut pf yang paling tinggi. dapat 25$ terus stop ea ni".  Same simulation as flip113.py, plus: once
today's realised P&L (server day, 0.01 lot) reaches +$25, the position is closed and the EA stays flat until the next day.
Also a $100 account run: refilled to $100 every time equity (realised) falls to $0, counting the blow-ups."""
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
jit = G.jit


@jit
def sar_t(O, H, L, S, D, live, dayid, usd, target):
    n = len(O); xi = np.zeros(n, np.int64); pn = np.zeros(n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; dpnl = 0.0; done = False
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + S[j]
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0; dpnl += p
            continue
        if pos == 0:
            if live[j] and not done and (j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]):
                pos = 1; ent = O[j] + S[j]; stop = O[j] - D[j]
            continue
        hit = False
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); p = (px - ent) * usd; hit = True
                pos = -1; ent = px; stop = px + S[j] + D[j]
            else:
                stop = max(stop, H[j] - D[j])
        else:
            if H[j] + S[j] >= stop:
                px = max(O[j] + S[j], stop); p = (ent - px) * usd; hit = True
                pos = 1; ent = px; stop = px - S[j] - D[j]
            else:
                stop = min(stop, L[j] + S[j] + D[j])
        if hit:
            xi[m] = j; pn[m] = p; m += 1; dpnl += p
            if dpnl >= target:
                done = True                                               # the reversed position is closed at the next bar's open
    return xi[:m], pn[:m]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365); a3 = end - pd.Timedelta(days=91)
    B = d[d.index >= start][["o", "h", "l", "c", "s"]].copy()
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; a1 = M.atr(B).values
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = (T.normalize().values.astype("datetime64[D]").astype(np.int64))
    base = wd & (hm >= 90) & (hm < 1410); gate = base & (a1 >= 8 * S)
    ndays = len(np.unique(dayid[base]))
    say(f"{'variant':40s} {'trades':>7} {'PF':>5} {'yr1':>5} {'yr2':>5} | {'net$':>7} {'12m$':>7} {'3m$':>6} | {'maxDD':>6} {'wDay':>6} | {'days +25':>8} {'blow-ups $100':>13} {'last blow-up':>12}")
    for wname, live in (("all day", base), ("gate>=8", gate)):
        for gap in (3.0, 5.0, 8.0):
            for tgt in (1e9, 25.0):
                xi, p = sar_t(O, H, L, S, np.full(len(O), gap), live, dayid, usd, tgt)
                te = T[xi]
                dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
                bal = 100.0; blow = 0; last = "-"
                for t_, v in zip(te, p):
                    bal += v
                    if bal <= 0: blow += 1; bal = 100.0; last = f"{t_:%Y-%m-%d}"
                say(f"{wname + f' gap ${gap:g}' + (' target $25' if tgt < 1e8 else ''):40s} {len(p):7d} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} | "
                    f"{p.sum():+7.0f} {p[te >= mid].sum():+7.0f} {p[te >= a3].sum():+6.0f} | {dd:+6.0f} {dp.min():+6.0f} | {int((dp >= 25).sum()):8d} {blow:13d} {last:>12}")
    say(f"{ndays} trading days")


if __name__ == "__main__":
    main()
