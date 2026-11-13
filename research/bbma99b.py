"""Round 99b (13 Nov 2026): the live reversal CSAK (v2.21, SL 2 ATR(M15), no TP, 8 h) - why it loses often, and caps.
Owner: "modul csak m15 ni, kenapa banyak loss? kata stabil" after its first 5 live trades all hit the SL (13 Nov: BUY EURUSD,
GBPUSD, AUDUSD and SELL USDJPY twice - every one of them a bet against the US dollar).
Measures on the last 2 years (data run 43201971006): win rate, losing streaks, how often several open trades are the same
currency bet, and the result with per-currency caps, gold only and forex only."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bbma99 as B

say = B.say; pf = B.pf
T0 = time.time()


def streaks(x):
    w = (x.sort_values("t").net.values > 0)
    best = cur = 0; runs = []
    for v in w:
        if not v: cur += 1
        else:
            if cur: runs.append(cur)
            cur = 0
        best = max(best, cur)
    if cur: runs.append(cur)
    runs = np.array(runs) if runs else np.array([0])
    return best, int((runs >= 5).sum()), int((runs >= 8).sum())


def main():
    meta = B.SA.load_meta(os.path.join(B.DATA, "meta.txt")); SW = B.R23.load_swaps(); rg = np.random.default_rng(99)
    B.B97.CTX_ONLY = True
    name = [n for n, _ in B.V if n.startswith("SL 2.0 ATR")][0]
    ch = dict(B.V)[name]
    ALL, RND = [], []; END = None
    for sym in B.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(B.DATA, sym + ".csv")): continue
        cx = B.B97.run(sym, meta[sym], SW.get(sym), rg); END = cx["end"] if END is None else max(END, cx["end"])
        ks, dr = cx["ks"], cx["dr"]
        exa = np.where(dr == 1, cx["roll"](cx["exd"], 8)[ks - 1], cx["roll"](cx["exu"], 8)[ks - 1])
        m = (cx["h4pos"] <= -0.5) & (exa == 1) & (cx["spr"] <= 0.20)
        p = dict(B.C, **ch)
        for rand, acc in ((False, ALL), (True, RND)):
            df = B.sim(cx, SW.get(sym), meta[sym], m, p, rand, rg)
            if len(df): acc.append(df.assign(sym=sym))
    X = pd.concat(ALL); XR = pd.concat(RND)
    hdr = (f"{'variant':44s} {'n':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'IS':>5} {'OOS':>5} | {'12m R':>6} {'3m R':>5} {'p3m':>5} | "
           f"{'net $':>6} {'gold':>5} {'fx':>5} {'maxDD':>6} {'wDay':>5} {'opn':>3} | {'RAND':>5}")
    say(f"live rule = '{name}', window {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}\n")
    say(hdr)
    fx = X[X.sym != "XAUUSD"]; g = X[X.sym == "XAUUSD"]
    rows = [("LIVE (29 symbols, no cap)", X, XR), ("  forex only (28)", fx, XR[XR.sym != "XAUUSD"]), ("  gold only", g, XR[XR.sym == "XAUUSD"])]
    for cn, kw in (("max 1 per currency", {"ccy": 1}), ("max 2 per currency", {"ccy": 2}), ("max 3 open", {"mx": 3}), ("max 1 open", {"mx": 1})):
        rows.append(("  " + cn, B.cap(X, **kw), B.cap(XR, **kw)))
    rows.append(("  forex max 1 per currency + gold", pd.concat([B.cap(fx, ccy=1), g]), XR))
    for nm, x, xr in rows:
        B.line(nm, x, xr, END)
    say("\nlosing streaks (by entry time, all symbols together): longest / runs of >= 5 losses / runs of >= 8")
    for nm, x, _ in rows:
        b, r5, r8 = streaks(x); say(f"  {nm:44s} longest {b:3d}   >=5: {r5:3d}   >=8: {r8:3d}   trades {len(x)}")
    # how often trades that are open together are the same bet on one currency (e.g. BUY EURUSD + BUY GBPUSD + SELL USDJPY = short USD x3)
    say("\nclusters: at each entry, how many trades already open lean the same way on one of its two currencies")
    Xs = X.sort_values("t"); opn = []; same = []
    for row in Xs.itertuples():
        opn = [o for o in opn if o[0] > row.t]
        b, q = row.sym[:3], row.sym[3:]
        k = 0
        for tx, s, d in opn:
            if (s[:3] == b and d == row.d) or (s[3:] == q and d == row.d) or (s[3:] == b and d == -row.d) or (s[:3] == q and d == -row.d): k += 1
        same.append(k); opn.append((row.tx, row.sym, row.d))
    Xs = Xs.assign(same=same)
    for lo, hi in ((0, 0), (1, 1), (2, 3), (4, 99)):
        y = Xs[(Xs.same >= lo) & (Xs.same <= hi)]
        if len(y): say(f"  {lo}-{hi} same-way trades already open: {len(y):4d} trades ({100 * len(y) / len(Xs):3.0f}%), win {100 * (y.net > 0).mean():3.0f}%, PF {pf(y.r.values):.2f}, net ${y.net.sum():+.0f}")
    say(f"\nper symbol, net $ (2 years, 0.01 lot):")
    ps = X.groupby("sym").net.agg(["count", "sum"]).sort_values("sum")
    say("  " + "  ".join(f"{s}:{int(r['count'])}/{r['sum']:+.0f}" for s, r in ps.iterrows()))
    say(f"  symbols positive: {int((ps['sum'] > 0).sum())} of {len(ps)}")
    say(f"\naverage loss ${X.net[X.net < 0].mean():.2f}, average win ${X.net[X.net > 0].mean():.2f}; forex avg loss ${fx.net[fx.net < 0].mean():.2f}, "
        f"avg win ${fx.net[fx.net > 0].mean():.2f}; gold avg loss ${g.net[g.net < 0].mean():.2f}, avg win ${g.net[g.net > 0].mean():.2f}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
