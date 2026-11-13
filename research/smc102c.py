"""Round 102c (13 Nov 2026): robustness of round 102b's gold family (M15 setup / H4 bias, BOS, killzone, limit at the OB / OTE,
TP 2R / 3R / liquidity), gold alone, last 2 years.  Each check changes ONE thing and keeps the rest:
  1. the entry timeframe: M5 / M10 / M15 / M20 / M30 / H1 (an island fails here)
  2. the killzone: London 09-12 + NY 14-17 (live definition), London only, NY only, all day, and FAKE hours 02-05 + 19-22 server
  3. order life 10 / 30 / 60 bars, hold 6 / 12 / 24 h, SL buffer 0 / 0.1 / 0.25 / 0.5 ATR
  4. the centre rule by quarter and month, buys / sells, both twins (always-buy, random)
Every row: the 30 cells entry (5) x TP (3) x swing n (3, 5) with BOS + killzone: median PF and how many pass, then the centre cell
M15/H4 n5 OB top TP 3R and its n3 twin."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smc102 as M
import scalp_all as SA, ind23 as R23

say = M.say; pf = M.pf
M.BUY_CTRL = True
KZ = {"LDN+NY": lambda h: ((h >= 9) & (h < 12)) | ((h >= 14) & (h < 17)), "LDN": lambda h: (h >= 9) & (h < 12),
      "NY": lambda h: (h >= 14) & (h < 17), "all day": lambda h: h >= 0, "FAKE": lambda h: ((h >= 2) & (h < 5)) | ((h >= 19) & (h < 22))}
meta = SA.load_meta(os.path.join(M.DATA, "meta.txt")); SW = R23.load_swaps()


def cells(A, END, kz="LDN+NY", typ="BOS"):
    mid = END - pd.Timedelta(days=365); out = []
    for (tf, n, en, tp), g0 in A.groupby(["tf", "n", "entry", "tp"]):
        g = g0[KZ[kz](g0.hr.values)]
        if typ != "any": g = g[g.typ.values == typ]
        g = M.busy(g)
        if len(g) < 30: continue
        r = g.r.values.astype(float); y1 = (g.t < mid).values; usd = r * g.risk.values; dv = g.d.values
        rb, rr = g.rb.values.astype(float), g.rr.values.astype(float)
        P, PB, PR = pf(r), pf(rb[~np.isnan(rb)]), pf(rr[~np.isnan(rr)])
        eq = np.cumsum(usd); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        ok = (len(g) >= 150 and P >= 1.15 and pf(r[y1]) >= 1.05 and pf(r[~y1]) >= 1.05 and pf(r - 0.5 * g.sp.values) >= 1.05
              and usd[~y1].sum() > 0 and P >= max(PB, PR) + 0.10)
        out.append(dict(tf=tf, n=n, en=en, tp=tp, N=len(g), PF=P, y1=pf(r[y1]), y2=pf(r[~y1]), usd=usd.sum(), u12=usd[~y1].sum(),
                        buy=pf(r[dv == 1]), sell=pf(r[dv == -1]), ab=PB, rand=PR, dd=dd, worst=usd.min(), ok=ok, g=g))
    return pd.DataFrame(out)


def line(lab, C, tf):
    c = C[C.tf == tf] if len(C) else C
    if not len(c): say(f"  {lab:34s} no cells"); return
    cen = c[(c.en == "OB top") & (c.tp == "3R")]
    s = f"  {lab:34s} cells {len(c):2d}  PF median {c.PF.median():4.2f}  pass {int(c.ok.sum()):2d}  trades median {int(c.N.median()):4d}  AB {c.ab.median():4.2f}  RAND {c.rand.median():4.2f} |"
    for r in cen.sort_values("n").itertuples():
        s += f" n{r.n}: {r.N:3d} PF {r.PF:4.2f} ({r.y1:4.2f}/{r.y2:4.2f}) ${r.usd:+5.0f} sells {r.sell:4.2f}"
    say(s)


def go(pairs, **kw):
    M.PAIRS = pairs
    for k, v in kw.items(): setattr(M, k, v)
    A, END = M.run("XAUUSD", meta["XAUUSD"], SW.get("XAUUSD"))
    for c in ("entry", "tp", "typ"): A[c] = A[c].astype(str)
    A = A.sort_values("t", kind="stable").reset_index(drop=True)
    M.WAIT, M.HOLD_H, M.SLBUF = 30, None, 0.1
    return A, END


def main():
    say("GOLD, last 2 years; cells = 5 entries x 3 TPs x n 3/5 with BOS + killzone; centre = OB top TP 3R; (yr1/yr2); $ per 0.01 lot")
    say("\n1. ENTRY TIMEFRAME (bias H4 unless named), hold 48 bars")
    A, END = go(((5, 240), (10, 240), (15, 240), (20, 240), (30, 240), (60, 240)))
    C = cells(A, END)
    for (tf, hm) in ((5, 240), (10, 240), (15, 240), (20, 240), (30, 240), (60, 240)):
        line(f"M{tf}/H4" if tf < 60 else "H1/H4", C, tf)
    say("\n2. KILLZONE (M15/H4)")
    A, END = go(((15, 240),))
    for kz in KZ: line(kz, cells(A, END, kz), 15)
    line("LDN+NY, BOS or CHoCH", cells(A, END, "LDN+NY", "any"), 15)
    line("LDN+NY, CHoCH only", cells(A, END, "LDN+NY", "CHoCH"), 15)
    say("\n3. ORDER LIFE / HOLD / SL BUFFER (M15/H4, LDN+NY)")
    for lab, kw in (("order life 10 bars", dict(WAIT=10)), ("order life 60 bars", dict(WAIT=60)), ("hold 6 h", dict(HOLD_H=6)),
                    ("hold 12 h (= 48 bars, base)", dict(HOLD_H=12)), ("hold 24 h", dict(HOLD_H=24)), ("SL buffer 0 ATR", dict(SLBUF=0.0)),
                    ("SL buffer 0.25 ATR", dict(SLBUF=0.25)), ("SL buffer 0.5 ATR", dict(SLBUF=0.5))):
        A2, E2 = go(((15, 240),), **kw); line(lab, cells(A2, E2), 15)
    say("\n4. THE CENTRE RULE M15/H4 BOS + LDN+NY killzone + limit at the OB top + TP 3R, by quarter (R) and month")
    C = cells(A, END)
    for n in (3, 5):
        r = C[(C.tf == 15) & (C.en == "OB top") & (C.tp == "3R") & (C.n == n)]
        if not len(r): continue
        r = next(r.itertuples()); g = r.g.copy(); g["usd"] = g.r * g.risk
        q = g.groupby(g.t.dt.to_period("Q")).agg(R=("r", "sum"), n=("r", "size"), usd=("usd", "sum"))
        mo = g.groupby(g.t.dt.to_period("M")).usd.sum()
        say(f"  n{n}: {r.N} trades, PF {r.PF:.2f}, yr {r.y1:.2f}/{r.y2:.2f}, ${r.usd:+.0f}, 12m ${r.u12:+.0f}, buys {r.buy:.2f}, sells {r.sell:.2f}, "
            f"AB {r.ab:.2f}, RAND {r.rand:.2f}, max DD ${r.dd:.0f}, worst ${r.worst:.0f}, avg risk ${g.risk.mean():.1f}, "
            f"months positive {(mo > 0).sum()}/{len(mo)}, worst month ${mo.min():.0f}")
        say("     " + "  ".join(f"{p}: {v.R:+.1f}R/{v.n}" for p, v in q.iterrows()))
        say(f"     longest losing run {max((len(x) for x in ''.join('L' if v <= 0 else 'W' for v in g.r).split('W')), default=0)} trades; "
            f"trades a week {r.N / 104:.1f}")


if __name__ == "__main__":
    main()
