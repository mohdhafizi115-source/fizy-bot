"""Round 98 (12 Nov 2026): is round 97's pass real?  Robustness of the reversal CSAK, last 2 years, 30 instruments.

The rule that passed in round 97 (BUY shown, SELL mirrored):
  an M15 CSAK (open below min(mid BB, EMA 50), close above max(mid BB, EMA 50), not above the top BB), 01:30-22:00 server,
  + the last closed H4 candle sits in the LOWER half of its BB band ((close - H4 mid) / half band <= -0.5)
  + an M15 Extreme (LWMA 5 or 10 of the lows below the bottom BB) in the last 8 M15 candles before the CSAK
  + spread at the CSAK <= 0.20 x ATR(14, M15)
  entry next M5 open, SL beyond the 12-candle M15 swing (lowest low up to the CSAK) + spread, NO TP, out after 8 h.
Checks:
  1 one-at-a-time neighbours of every setting (Extreme lookback, H4 position, spread cap, hold, swing length, a TP)
  2 every neighbour also with a random direction on the same entries
  3 the centre rule per symbol, per month, buy / sell, worst day, drawdown and how many positions are open at once
    across all symbols ($ per 0.01 lot each), against a $100 account
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87
import bbma97 as B97

DATA = B97.DATA
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
CENTRE = dict(lb=8, pos=-0.5, spr=0.20, hold=8, sw=12, tp=0)
VARS = [("centre", {})] + [(f"Extreme lookback {v}", {"lb": v}) for v in (4, 6, 10, 12, 16)] + \
       [(f"H4 position <= {v}", {"pos": v}) for v in (-0.3, -0.4, -0.6, -0.7)] + \
       [(f"spread cap {v}", {"spr": v}) for v in (0.10, 0.15, 0.25, 0.30, 9.0)] + \
       [(f"hold {v} h", {"hold": v}) for v in (2, 4, 6, 12, 16, 24)] + \
       [(f"swing {v} candles", {"sw": v}) for v in (4, 8, 16, 24)] + \
       [(f"TP {v}R + 8 h cap", {"tp": v}) for v in (1, 2, 3)]


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(98)
    B97.CTX_ONLY = True
    ALL = {}; END = None
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        cx = B97.run(sym, meta[sym], SW.get(sym), rg); END = cx["end"] if END is None else max(END, cx["end"])
        ks, dr = cx["ks"], cx["dr"]
        for name, ch in VARS:
            p = dict(CENTRE, **ch)
            exa = np.where(dr == 1, cx["roll"](cx["exd"], p["lb"])[ks - 1], cx["roll"](cx["exu"], p["lb"])[ks - 1])
            m = (cx["h4pos"] <= p["pos"]) & (exa == 1) & (cx["spr"] <= p["spr"])
            swl = np.array([cx["l"][max(0, k - p["sw"] + 1):k + 1].min() for k in ks]); swh = np.array([cx["h"][max(0, k - p["sw"] + 1):k + 1].max() for k in ks])
            for rand in (False, True):
                df = cx["sim"](m, "swing", p["tp"], p["hold"], rand, swl, swh)
                if len(df): ALL.setdefault((name, rand), []).append(df.assign(sym=sym))
        say(f"{sym} done [{time.time() - T0:.0f} s]")
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; centre = {CENTRE}")
    say(f"{'variant':26s} {'side':4s} {'n':>5} {'/wk':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'12m R':>6} {'3m R':>5} {'p3m R':>6} | {'sym>1':>6} {'net $':>7} | {'RAND':>5} {'PASS':>4}")
    for name, _ in VARS:
        R = pd.concat(ALL.get((name, False), [pd.DataFrame(columns=["t", "net", "r", "rs", "d", "mae", "tx", "risk", "sym"])]))
        Rr = pd.concat(ALL.get((name, True), [R.iloc[:0]]))
        for side, sd in (("ALL", 0), ("BUY", 1), ("SELL", -1)):
            x = R if sd == 0 else R[R.d == sd]; xr = Rr if sd == 0 else Rr[Rr.d == sd]
            if len(x) < 20: continue
            P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values)
            l12 = x.r[x.t >= mid].sum(); gg = [pf(v.net.values) > 1 for _, v in x.groupby("sym") if len(v) >= 10]
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
            say(f"{name:26s} {side:4s} {len(x):5d} {len(x) / 104:4.1f} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | {l12:+6.1f} "
                f"{x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | {sum(gg):2d}/{len(gg):<3d} {x.net.sum():+7.0f} | {PR:5.2f} {'PASS' if ok else ''}")
        say()
    # ---------- centre in detail
    R = pd.concat(ALL[("centre", False)]).sort_values("t")
    say("===== CENTRE RULE IN DETAIL ($ per 0.01 lot) =====")
    say(f"{'symbol':8s} {'n':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'net $':>7} {'12m $':>7} {'3m $':>6} {'worst $':>7} {'float $':>7} {'avg risk $':>10}")
    for sym, x in R.groupby("sym"):
        say(f"{sym:8s} {len(x):4d} {100 * (x.net > 0).mean():4.0f} {pf(x.net.values):5.2f} {pf(x.net[x.t < mid].values):5.2f} {pf(x.net[x.t >= mid].values):5.2f} "
            f"{x.net.sum():+7.0f} {x.net[x.t >= mid].sum():+7.0f} {x.net[x.t >= a3].sum():+6.0f} {x.net.min():+7.0f} {x.mae.min():+7.0f} {x.risk.mean():10.2f}")
    say("\nby month (all symbols, $): " + " ".join(f"{p.strftime('%y-%m')}:{v:+.0f}" for p, v in R.groupby(R.t.dt.to_period('M')).net.sum().items()))
    pos_m = (R.groupby(R.t.dt.to_period('M')).net.sum() > 0)
    say(f"positive months: {pos_m.sum()} of {len(pos_m)}")
    dd = R.groupby(R.tx.dt.normalize()).net.sum()
    eq = dd.cumsum(); mdd = (eq - eq.cummax()).min()
    say(f"by day: worst day ${dd.min():+.0f}, best ${dd.max():+.0f}; equity max drawdown ${mdd:+.0f} (all 30 symbols at 0.01 lot each)")
    ev = pd.concat([pd.Series(1, index=R.t), pd.Series(-1, index=R.tx)]).sort_index().cumsum()
    say(f"open positions at once across all symbols: max {int(ev.max())}, median {int(ev.median())}")
    for setn, f in (("gold only", R[R.sym == "XAUUSD"]), ("forex only", R[~R.sym.isin(["XAUUSD", "BTCUSD"])])):
        if len(f): say(f"{setn}: {len(f)} trades, PF {pf(f.net.values):.2f}, net ${f.net.sum():+.0f}, 12m ${f.net[f.t >= mid].sum():+.0f}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
