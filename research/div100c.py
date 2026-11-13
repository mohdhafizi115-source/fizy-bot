"""Round 100c (13 Nov 2026): divergence on GOLD ALONE, last 2 years (owner: "jadi gold okay ke tak").
Every round-100 variant on XAUUSD, H1 and H4, with three controls on the SAME entry times:
random direction, ALWAYS BUY (gold's 2025-26 trend), and the signal split into its buys and its sells.
A divergence edge must beat always-buy, and its sells must make money too; if only the buys win and always-buy wins
as much, the profit is the gold trend, not the divergence.  $ per 0.01 lot; 150 trades is not required here
(gold alone cannot reach it on H1 / H4) but every row shows its count.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import div100 as D

say = lambda s="": print(s, flush=True); pf = D.pf


def main():
    meta = SA.load_meta(os.path.join(D.DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(1002)
    D.TFS = (60, 240); D.BUY_CTRL = True
    out, end = D.run("XAUUSD", meta["XAUUSD"], SW.get("XAUUSD"), rg)
    mid = end - pd.Timedelta(days=365); a3, a6 = end - pd.Timedelta(days=91), end - pd.Timedelta(days=182)
    cols = ["t", "net", "r", "rs", "d"]; rows = []
    for key, (a, b, c) in out.items():
        x, xr, xb = (pd.DataFrame(v, columns=cols) for v in (a, b, c))
        if len(x) < 40: continue
        bu, se = x[x.d == 1], x[x.d == -1]
        rows.append(dict(key=" ".join(key), n=len(x), win=100 * (x.r > 0).mean(), PF=pf(x.r.values), y1=pf(x.r[x.t < mid].values),
                         y2=pf(x.r[x.t >= mid].values), usd=x.net.sum(), u12=x.net[x.t >= mid].sum(), u3=x.net[x.t >= a3].sum(),
                         p3=x.net[(x.t >= a6) & (x.t < a3)].sum(), nb=len(bu), pb=pf(bu.r.values), ub=bu.net.sum(), ns=len(se), ps=pf(se.r.values),
                         us=se.net.sum(), rand=pf(xr.r.values), buy=pf(xb.r.values), ubuy=xb.net.sum(),
                         dd=((x.net.cumsum() - x.net.cumsum().cummax()).min()), worst=x.net.min()))
    R = pd.DataFrame(rows)
    say(f"XAUUSD {end - pd.Timedelta(days=730):%Y-%m-%d} .. {end:%Y-%m-%d}; {len(R)} variants with >= 40 trades")
    say(f"gold buy-and-hold over the window: the always-buy twin is the trend; a variant only adds something if PF > always-buy PF")
    say(f"variants beating ALWAYS-BUY by >= 0.10 PF: {(R.PF >= R.buy + 0.10).sum()} of {len(R)}; with sells PF >= 1.0 as well: "
        f"{((R.PF >= R.buy + 0.10) & (R.ps >= 1.0)).sum()}; with >= 100 trades too: {((R.PF >= R.buy + 0.10) & (R.ps >= 1.0) & (R.n >= 100)).sum()}")
    say(f"median PF {R.PF.median():.2f}, median always-buy PF {R.buy.median():.2f}, median random {R.rand.median():.2f}; "
        f"median buys PF {R.pb.median():.2f}, median sells PF {R.ps.median():.2f}")
    hdr = (f"{'variant':48s} {'n':>4} {'win':>3} {'PF':>5} {'yr1':>5} {'yr2':>5} {'net$':>6} {'12m$':>6} {'3m$':>5} {'p3m$':>5} | "
           f"{'buys':>4} {'PF':>5} {'$':>6} | {'sells':>5} {'PF':>5} {'$':>6} | {'RAND':>5} {'BUY':>5} {'buy$':>6} | {'maxDD':>6} {'worst':>5}")
    fm = lambda r: (f"{r.key:48s} {r.n:4d} {r.win:3.0f} {r.PF:5.2f} {r.y1:5.2f} {r.y2:5.2f} {r.usd:+6.0f} {r.u12:+6.0f} {r.u3:+5.0f} {r.p3:+5.0f} | "
                    f"{r.nb:4d} {r.pb:5.2f} {r.ub:+6.0f} | {r.ns:5d} {r.ps:5.2f} {r.us:+6.0f} | {r.rand:5.2f} {r.buy:5.2f} {r.ubuy:+6.0f} | {r.dd:+6.0f} {r.worst:+5.0f}")
    say("\nTOP 30 by PF"); say(hdr)
    for r in R.sort_values("PF", ascending=False).head(30).itertuples(): say(fm(r))
    say("\nTOP 15 by PF minus ALWAYS-BUY PF (what the divergence adds over just buying gold at the same moments)"); say(hdr)
    for r in R.assign(edge=R.PF - R.buy).sort_values("edge", ascending=False).head(15).itertuples(): say(fm(r))


if __name__ == "__main__":
    main()
