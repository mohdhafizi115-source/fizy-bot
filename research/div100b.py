"""Round 100b (13 Nov 2026): robustness of the only divergence family that passed round 100:
H4 REGULAR RSI divergence with the first RSI pivot in its zone (< 30 buy / > 70 sell) and a confirmation close beyond
the swing within 3 bars (E1); SL beyond the second pivot + spread, TP 1 / 2 / 3R, 48-bar cap, swaps; 28 forex + XAUUSD,
last 2 years.  Every neighbour of every setting, a random-direction twin, gold and forex apart, $ drawdown and worst day
(by entry day, 0.01 lot, all 29 symbols together), and how many symbols end positive.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import div100 as D

DATA = D.DATA
say = lambda s="": print(s, flush=True)
T0 = time.time(); pf = D.pf
BASE = dict(tf=240, rsi=14, zone=(30, 70), n=3, conf=3, gap=(5, 60))
VAR = [("BASE H4 RSI14 zone 30/70 n3 conf3 gap5-60", {})]
VAR += [(f"timeframe {m // 60}h", {"tf": m}) for m in (120, 180, 360, 480)]
VAR += [(f"RSI {r}", {"rsi": r}) for r in (9, 11, 17, 21)]
VAR += [(f"zone {a}/{100 - a}", {"zone": (a, 100 - a)}) for a in (20, 25, 35, 40)]
VAR += [("no zone (any regular)", {"zone": (101, -1)})]
VAR += [(f"pivot n{k}", {"n": k}) for k in (2, 4, 5)]
VAR += [(f"confirm within {c} bar(s)", {"conf": c}) for c in (1, 2, 5, 8)]
VAR += [(f"pivot gap {a}-{b}", {"gap": (a, b)}) for a, b in ((3, 60), (5, 30), (10, 60), (5, 100))]


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(1001)
    D.OSC = ("RSI",); END = None
    say(f"{'variant':44s} {'TP':>3} {'n':>4} {'win':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'12mR':>6} {'3mR':>5} {'p3mR':>5} | "
        f"{'net$':>6} {'gold$':>6} {'gPF':>5} {'fx$':>6} {'fxPF':>5} {'maxDD':>6} {'wDay':>5} {'sym+':>4}/{'sym':<3} | {'RAND':>5}")
    for name, ch in VAR:
        p = dict(BASE, **ch)
        D.TFS = (p["tf"],); D.RSI_N = p["rsi"]; D.ZONE = dict(D.ZONE, RSI=p["zone"]); D.NS = (p["n"],); D.CONFW = p["conf"]; D.GAP = p["gap"]
        res = {}
        for sym in D.SYMS:
            if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
            out, end = D.run(sym, meta[sym], SW.get(sym), rg); END = end if END is None else max(END, end)
            want = "no filter" if p["zone"][0] > 100 else "zone"
            for key, (a, b) in out.items():
                if key[3] != "REG" or key[4] != want or key[5] != "E1": continue
                res.setdefault(key[6], [[], []]); res[key[6]][0] += [r + (sym,) for r in a]; res[key[6]][1] += [r + (sym,) for r in b]
        mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
        for tp in ("TP 1R", "TP 2R", "TP 3R"):
            if tp not in res: continue
            x = pd.DataFrame(res[tp][0], columns=["t", "net", "r", "rs", "d", "sym"]); xr = pd.DataFrame(res[tp][1], columns=["t", "net", "r", "rs", "d", "sym"])
            if not len(x): continue
            P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values)
            g, f = x[x.sym == "XAUUSD"], x[x.sym != "XAUUSD"]
            dd = x.groupby(x.t.dt.normalize()).net.sum(); eq = dd.cumsum(); mdd = (eq - eq.cummax()).min()
            l12 = x.r[x.t >= mid].sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
            bs = x.groupby("sym").r.sum()
            say(f"{name:44s} {tp[3:]:>3} {len(x):4d} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} {l12:+6.1f} "
                f"{x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+5.1f} | {x.net.sum():+6.0f} {g.net.sum():+6.0f} {pf(g.r.values):5.2f} "
                f"{f.net.sum():+6.0f} {pf(f.r.values):5.2f} {mdd:+6.0f} {dd.min():+5.0f} {(bs > 0).sum():4d}/{len(bs):<3d} | {PR:5.2f} {'PASS' if ok else ''}")
        say()
    # per-symbol detail for the base, TP 3R and TP 1R
    D.TFS = (240,); D.RSI_N = 14; D.ZONE = dict(D.ZONE, RSI=(30, 70)); D.NS = (3,); D.CONFW = 3; D.GAP = (5, 60)
    det = {}
    for sym in D.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        out, end = D.run(sym, meta[sym], SW.get(sym), rg)
        for key, (a, b) in out.items():
            if key[3] == "REG" and key[4] == "zone" and key[5] == "E1": det.setdefault(key[6], []).extend(r + (sym,) for r in a)
    for tp in ("TP 1R", "TP 3R"):
        x = pd.DataFrame(det[tp], columns=["t", "net", "r", "rs", "d", "sym"])
        say(f"BASE {tp}, by symbol (trades, R, $):  " + ", ".join(f"{s} {len(v)} {v.r.sum():+.1f}R {v.net.sum():+.0f}$" for s, v in x.groupby("sym")))
        say(f"BASE {tp}, buys {pf(x.r[x.d == 1].values):.2f} ({(x.d == 1).sum()}), sells {pf(x.r[x.d == -1].values):.2f} ({(x.d == -1).sum()}); "
            f"by quarter R: " + " ".join(f"{q}:{v.r.sum():+.1f}" for q, v in x.groupby(x.t.dt.to_period('Q'))))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
