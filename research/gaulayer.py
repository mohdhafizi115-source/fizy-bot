"""Gold auction scalp with layers (2 Nov 2026): the owner asked to add 0.01 lot every 10 pips ($1.00) against the
entry of the live LBMA pre-auction sell ("setiap kali bergerak lawan entry dalam 10 pip tambah layer lagi 0.01").

Base trade (live module FizyGAU): sell 0.01 lot at the 10:15 London M5 open, SL = entry + 2 x ATR(M5, 14), close at the
10:30 open. Layers: one more 0.01-lot sell each time the price rises STEP above the last layer (entry + STEP,
entry + 2 STEP, ...) while the level is below the SL; all layers share the SL and the 10:30 exit. Bars are walked on
the O-H-L-C path (O-L-H-C for up bars). Every layer pays its bar's spread; stress = 1.5x spread.
STEP $1.00 is the request (10 pips, 1 pip = $0.10); $0.50 and $2.00 are shown for comparison; "single" = the live
trade. Per basket in $ for 0.01 lot per layer ($1 per $1 move).
The usual pass rule on baskets (>= 150, PF >= 1.15, both halves >= 1.05, stress >= 1.05, last 12 months positive);
a layered version is only worth it if it also earns more per $ of drawdown than the single trade.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def main():
    meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
    d = FL.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
    o, h, l, c, s = (d[x].values for x in ("o", "h", "l", "c", "s"))
    c1 = d.c.shift()
    tr = np.maximum(d.h - d.l, np.maximum((d.h - c1).abs(), (d.l - c1).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    loc = d.index.tz_convert("Europe/London")
    hm = loc.hour * 60 + loc.minute
    starts = [i for i in np.where(hm == 615)[0] if i + 3 < len(d) and hm[i + 3] == 630 and np.isfinite(atr[i])]
    print(f"XAUUSD {d.index[0].date()} .. {d.index[-1].date()}: {len(starts)} auction mornings, median ATR(M5) ${np.median(atr[starts]):.2f}")
    print(f"{'variant':10s} {'baskets':>7s} {'layers avg/max':>14s} {'win%':>5s} {'PF':>5s} {'half1':>5s} {'half2':>5s} {'stress':>6s} "
          f"{'total$':>7s} {'$/basket':>8s} {'maxDD$':>7s} {'worst$':>7s} {'last12$':>7s} {'profit/DD':>9s} pass")
    t_all = d.index[starts]
    mid, end = t_all[len(t_all) // 2], t_all[-1]
    base_ratio = None
    for name, step in (("single", None), ("$0.50", 0.5), ("$1.00", 1.0), ("$2.00", 2.0)):
        net, nets, nl = [], [], []
        for i in starts:
            e = o[i]
            sl = e + 2 * atr[i]
            lv = [(e, s[i])]                                    # (sell price on the bid, spread paid)
            ex = None
            for j in range(i, i + 3):
                path = (o[j], l[j], h[j], c[j]) if c[j] >= o[j] else (o[j], h[j], l[j], c[j])
                for a, b in zip(path[:-1], path[1:]):
                    if b <= a:
                        continue
                    if step:                                    # rising: add layers at the levels crossed
                        while True:
                            nxt = lv[-1][0] + step
                            if nxt >= sl or b < nxt:
                                break
                            lv.append((nxt, s[j]))
                    if b >= sl:
                        ex = sl; break
                if ex is not None:
                    break
            if ex is None:
                ex = o[i + 3]
            g = sum(p - ex for p, _ in lv)
            cost = sum(sp for _, sp in lv)
            net.append(g - cost); nets.append(g - 1.5 * cost); nl.append(len(lv))
        net, nets, nl = np.array(net), np.array(nets), np.array(nl)
        first = (t_all < mid)
        eq = np.cumsum(net)
        dd = (eq - np.maximum.accumulate(eq)).min()
        l12 = net[t_all >= end - pd.Timedelta(days=365)].sum()
        P, P1, P2, PS = FL.pf(net), FL.pf(net[first]), FL.pf(net[~first]), FL.pf(nets)
        ok = len(net) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        ratio = net.sum() / -dd if dd < 0 else np.inf
        if base_ratio is None:
            base_ratio = ratio
        print(f"{name:10s} {len(net):7d} {nl.mean():7.2f}/{nl.max():<6d} {100 * (net > 0).mean():5.1f} {FL.f2(P)} {FL.f2(P1)} {FL.f2(P2)} "
              f"{FL.f2(PS):>6s} {net.sum():+7.0f} {net.mean():+8.2f} {dd:7.0f} {net.min():7.2f} {l12:+7.0f} {ratio:9.2f} "
              f"{'PASS' if ok else 'fail'}{' (better per $ of drawdown than single)' if ok and name != 'single' and ratio > base_ratio else ''}")
        by = pd.Series(net, index=t_all).groupby(t_all.year).sum()
        print(f"{'':10s} by year $: " + " ".join(f"{y}:{v:+.0f}" for y, v in by.items()))


if __name__ == "__main__":
    main()
