"""Round 102b (13 Nov 2026): round 102's SMC models on GOLD ALONE, last 2 years, with an ALWAYS-BUY twin.
Round 102 found every SMC model losing on the 28 forex pairs while gold alone scored PF 1.6-2.3 on its M15/H4 rows.
Gold rose most of these 2 years, so a buy-heavy rule wins for that reason alone: every trade here also has an always-BUY
twin (market buy at the same fill bar, same risk and target in R) and a random-direction twin.
Report: trades, PF, years, stress, last 12 / 3 / previous 3 months in $ (0.01 lot), buys / sells apart, both twins,
max drawdown, worst trade and average risk in $ against the $100 account."""
import os, sys, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smc102 as M
import scalp_all as SA, ind23 as R23

say = M.say; pf = M.pf
M.BUY_CTRL = True


def main():
    meta = SA.load_meta(os.path.join(M.DATA, "meta.txt")); SW = R23.load_swaps()
    A, END = M.run("XAUUSD", meta["XAUUSD"], SW.get("XAUUSD"))
    for c in ("entry", "tp", "typ"): A[c] = A[c].astype(str)
    A = A.sort_values("t", kind="stable").reset_index(drop=True)
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    TFN = {5: "M5/H1", 15: "M15/H4", 60: "H1/D1"}
    FILT = {"typ": ("any", "BOS", "CHoCH"), "sweep": ("any", True), "htf": ("any", True), "disc": ("any", True), "kz": ("any", True)}
    res = []
    for (tf, n, en, tp), g0 in A.groupby(["tf", "n", "entry", "tp"]):
        for combo in itertools.product(*FILT.values()):
            msk = np.ones(len(g0), bool)
            for col, v in zip(FILT.keys(), combo):
                if v != "any": msk &= (g0[col].values == v)
            if msk.sum() < 30: continue
            g = M.busy(g0[msk])
            if len(g) < 30: continue
            r = g.r.values.astype(float); usd = r * g.risk.values; t = g.t; y1 = (t < mid).values; dv = g.d.values
            rb = g.rb.values.astype(float); rr = g.rr.values.astype(float)
            eq = np.cumsum(usd); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
            name = f"{TFN[tf]} n{n} | {en:9s} | TP {tp:9s} | " + " ".join(f"{k}={'Y' if v is True else v}" for k, v in zip(FILT.keys(), combo) if v != "any")
            P, PB, PR = pf(r), pf(rb[~np.isnan(rb)]), pf(rr[~np.isnan(rr)])
            res.append(dict(name=name, n=len(g), PF=P, y1=pf(r[y1]), y2=pf(r[~y1]), st=pf(r - 0.5 * g.sp.values), usd=usd.sum(),
                            u12=usd[~y1].sum(), u3=usd[(t >= a3).values].sum(), p3=usd[((t >= a6) & (t < a3)).values].sum(),
                            buy=pf(r[dv == 1]), nb=int((dv == 1).sum()), sell=pf(r[dv == -1]), ns=int((dv == -1).sum()),
                            ab=PB, rand=PR, dd=dd, worst=usd.min(), risk=g.risk.mean(), n1=int(y1.sum()),
                            ok=len(g) >= 150 and P >= 1.15 and pf(r[y1]) >= 1.05 and pf(r[~y1]) >= 1.05 and usd[~y1].sum() > 0
                               and P >= PB + 0.10 and P >= PR + 0.10 and pf(r[dv == -1]) >= 1.0))
    R = pd.DataFrame(res)
    say(f"GOLD, {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; $ per 0.01 lot; AB = always-buy twin, RAND = random twin")
    say(f"{len(R)} variants with >= 30 trades, {int((R.n >= 150).sum())} with >= 150")
    big = R[R.n >= 100]
    say(f"median PF (>= 100 trades): signal {big.PF.median():.2f}  always-buy {big.ab.median():.2f}  random {big.rand.median():.2f}  "
        f"buys {big.buy.median():.2f}  sells {big.sell.median():.2f}")
    say(f"beat always-buy by >= 0.10: {int((big.PF >= big.ab + 0.10).sum())} of {len(big)}; sells PF >= 1: {int((big.sell >= 1).sum())}")
    say("\nPASS = >= 150 trades, PF >= 1.15, both years >= 1.05, last 12 months > 0, PF >= always-buy + 0.10 and random + 0.10, sells >= 1.0:"
        f" {int(R.ok.sum())}")
    hdr = (f"{'variant':84s} {'n':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'net$':>6} {'12m$':>6} {'3m$':>5} {'p3m$':>5} "
           f"{'buys':>10} {'sells':>10} {'AB':>5} {'RAND':>5} {'maxDD':>5} {'worst':>5} {'risk':>5}")
    fm = lambda r: (f"{r.name:84s} {r.n:4d} {r.PF:5.2f} {r.y1:5.2f} {r.y2:5.2f} {r.st:5.2f} {r.usd:+6.0f} {r.u12:+6.0f} {r.u3:+5.0f} {r.p3:+5.0f} "
                    f"{r.buy:5.2f}({r.nb:3d}) {r.sell:5.2f}({r.ns:3d}) {r.ab:5.2f} {r.rand:5.2f} {r.dd:+5.0f} {r.worst:+5.0f} {r.risk:5.1f} {'PASS' if r.ok else ''}")
    say("\nTOP 30 by PF (>= 100 trades)"); say(hdr)
    for r in big.sort_values("PF", ascending=False).head(30).itertuples(): say(fm(r))
    say("\nTOP 20 by PF minus always-buy (>= 100 trades)"); say(hdr)
    for r in big.assign(ex=big.PF - big.ab).sort_values("ex", ascending=False).head(20).itertuples(): say(fm(r))
    if R.ok.any():
        say("\nALL PASSES"); say(hdr)
        for r in R[R.ok].sort_values("PF", ascending=False).itertuples(): say(fm(r))
    say("\nchosen on YEAR 1 (top 15 by year-1 PF, >= 50 year-1 trades) -> YEAR 2")
    c = R[(R.n1 >= 50)].sort_values("y1", ascending=False).head(15)
    for r in c.itertuples(): say(f"  {r.name:84s} yr1 {r.y1:5.2f} -> yr2 {r.y2:5.2f}  (AB {r.ab:.2f}, sells {r.sell:.2f})")
    say(f"  median year 2 of those {c.y2.median():.2f}; of all {R.y2.median():.2f}")


if __name__ == "__main__":
    main()
