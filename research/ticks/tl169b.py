# Round 169b: robustness of the one trendline family that held (H1, swing n 3, BREAK, SL 1.5 ATR, TP 1-3R).
import sys; sys.argv = ["x"]
exec(open("tl169.py").read().split("E = M_t[-1] + 1")[0])
E = M_t[-1] + 1
def side(res, sig, d):  # keep only trades whose signal direction is d (same order as executed)
    return res
print("TF n TP | last 3 m trades PF net DD | prev PF net | buys PF | sells PF  (last 3 m / prev)")
for tfn, sec in (("M30", 1800), ("H1", 3600), ("H2", 7200), ("H4", 14400)):
    B = bars(sec)
    for n in (2, 3, 4, 5):
        sig = signals(B, n, "break", False)
        for tpR in (1, 2, 3):
            out = []
            for lab, sg in (("all", sig), ("buy", [s for s in sig if s[1] == 1]), ("sell", [s for s in sig if s[1] == -1])):
                r = run(B, sg, "atr", tpR); x = stats(r, A3, E); y = stats(r, A6, A3); out.append((x, y))
            (x, y), (xb, yb), (xs, ys) = out
            print(f"{tfn:3s} {n} {tpR}R | {x['n']:3d} PF {x['pf']:4.2f} net {x['net']:+5.0f} DD {x['dd']:+5.0f} wd {x['wd']:+4.0f} | {y['n']:3d} PF {y['pf']:4.2f} net {y['net']:+5.0f} | "
                  f"buy {xb['n']:3d} {xb['pf']:4.2f} / {yb['pf']:4.2f} | sell {xs['n']:3d} {xs['pf']:4.2f} / {ys['pf']:4.2f}", flush=True)
