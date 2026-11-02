"""Round 16 (2 Nov 2026): two gold M5 scalping ideas never tested before, on the broker's M5 history.

The owner asked again for gold scalping. 20+ M5 indicator rules, pattern mining and flags all lost (see the project
docs); the only gold scalp that passes is the LBMA pre-auction sell (live). New ideas:
  LEADLAG  does gold follow a move that other markets made in the last M5 bar?
           USD    USD weakness = mean of the standardised M5 returns of EURUSD, -USDJPY, AUDUSD
           GAP    USD weakness minus gold's own standardised return (gold lagging the dollar)
           BTC    BTCUSD's standardised return
           Signal when |x| is in the top 5% / 1% (thresholds from the first half); trade gold at the next M5 open,
           hold 1 / 2 / 3 bars (5-15 minutes).
           Control: the same predictor taken one day earlier (no lead-lag possible).
  TVOL     gold M5 bar with tick volume >= 3x its 50-bar mean: CLIMAX (|body| >= 1 ATR) or ABSORB (|body| <= 0.3 ATR),
           trade at the next open, hold 1 / 2 / 3 bars, follow or fade.
The side is chosen on the first half (gross t >= 3); KEPT if the second half has t >= 2 and PF > 1.1 after the
spread, and the whole period passes the usual rule (>= 150 trades, PF >= 1.15, halves >= 1.05, stress >= 1.05, last
12 months positive). Bars 23:45-01:30 server (rollover) are never traded.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import flows as FL

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def z(r, n=288):
    return r / r.rolling(n).std().shift(1)


def evaluate(name, sig_bool, side_raw, G, rows, mid_i, end_t):
    """sig_bool: bars with a signal; side_raw: +1 / -1 'natural' direction (follow); first half picks follow or fade"""
    o, s = G.o.values, G.s.values
    n = len(G)
    idx = np.where(sig_bool[:n - 4])[0]
    out = []
    for H in (1, 2, 3):
        e, x = idx + 1, idx + 1 + H
        gross = side_raw[idx] * (o[x] - o[e])
        cost = s[e]
        t = G.index[e]
        first = e < mid_i
        if len(gross) < 150 or first.sum() < 50:
            continue
        t1 = FL.tstat(gross[first])
        if not np.isfinite(t1):
            continue
        sd = 1 if t1 > 0 else -1
        g = sd * gross
        net, nets = g - cost, g - 1.5 * cost
        t2 = FL.tstat(g[~first])
        pf_all, pf1, pf2, pfs = SA.pf(net), SA.pf(net[first]), SA.pf(net[~first]), SA.pf(nets)
        l12 = net[t >= end_t - pd.Timedelta(days=365)].sum()
        kept = abs(t1) >= 3 and t2 >= 2 and pf2 > 1.1
        ok = kept and len(net) >= 150 and pf_all >= 1.15 and pf1 >= 1.05 and pf2 >= 1.05 and pfs >= 1.05 and l12 > 0
        days = G.index.normalize().nunique()
        rows.append((name, H, sd, len(net), len(net) / days, abs(t1), t2, net.mean(), pf_all, pf1, pf2, pfs, l12, kept, ok))
    return out


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    L = {}
    for s in ("XAUUSD", "EURUSD", "USDJPY", "AUDUSD", "BTCUSD"):
        L[s] = SA.load(os.path.join(DATA, s + ".csv"), meta[s]["point"])
    idx = L["XAUUSD"].index
    for s in L:
        idx = idx.intersection(L[s].index)
    G = L["XAUUSD"].loc[idx].copy()
    say(f"XAUUSD M5 aligned with EURUSD / USDJPY / AUDUSD / BTCUSD: {len(G)} bars, {G.index[0].date()} .. {G.index[-1].date()}")
    r = {s: np.log(L[s].loc[idx].c).diff() for s in L}
    zz = {s: z(r[s]) for s in L}
    usd = ((zz["EURUSD"] - zz["USDJPY"] + zz["AUDUSD"]) / 3).values
    gap = usd - zz["XAUUSD"].values
    btc = zz["BTCUSD"].values
    hm = G.index.hour * 60 + G.index.minute
    tradable = ~((hm >= 1425) | (hm < 90)) & np.r_[np.diff(G.index.values).astype("timedelta64[m]").astype(int) == 5, False]
    n = len(G)
    mid_i = n // 2
    end_t = G.index[-1]
    rows = []
    for nm, x in (("USD", usd), ("GAP", gap), ("BTC", btc)):
        for lag, tag in ((0, ""), (288, " [control: 1 day earlier]")):
            xx = np.r_[np.full(lag, np.nan), x[:n - lag]] if lag else x
            ax = np.abs(xx)
            for q in (95, 99):
                thr = np.nanpercentile(ax[:mid_i], q)
                sig = (ax >= thr) & tradable & np.isfinite(xx)
                evaluate(f"LEADLAG {nm} top {100 - q}%{tag}", sig, np.sign(np.nan_to_num(xx)), G, rows, mid_i, end_t)
    # tick-volume spikes
    v = G.v.values
    vm = pd.Series(v).rolling(50).mean().shift(1).values
    c1 = G.c.shift()
    tr = np.maximum(G.h - G.l, np.maximum((G.h - c1).abs(), (G.l - c1).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    body = (G.c - G.o).values
    spike = (v >= 3 * vm) & tradable & np.isfinite(atr)
    evaluate("TVOL CLIMAX", spike & (np.abs(body) >= atr), np.sign(body), G, rows, mid_i, end_t)
    evaluate("TVOL ABSORB", spike & (np.abs(body) <= 0.3 * atr), -np.sign(np.nan_to_num(r["XAUUSD"].values)), G, rows, mid_i, end_t)
    say("\nrule                                      hold  side   trades /day  |t1|    t2  net$/trade  PF  half1 half2 stress  last12$  ")
    for (name, H, sd, nt, pd_, t1, t2, avg, P, P1, P2, PS, l12, kept, ok) in rows:
        say(f"{name:42s} {5 * H:3d}m {'FOLLOW' if sd > 0 else 'FADE  '} {nt:6d} {pd_:5.2f} {t1:5.2f} {t2:+5.2f} {avg:+9.3f} "
            f"{SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} {l12:+8.0f}  {'KEPT' if kept else ''} {'PASS' if ok else ''}")
    real = [x for x in rows if "control" not in x[0]]
    ctrl = [x for x in rows if "control" in x[0]]
    say(f"\nreal: {sum(x[13] for x in real)} kept, {sum(x[14] for x in real)} pass of {len(real)} | "
        f"control (1 day earlier): {sum(x[13] for x in ctrl)} kept, {sum(x[14] for x in ctrl)} pass of {len(ctrl)}")
    say("($ per trade = per 0.01 lot of gold after the spread)")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
