"""Detail check of the day-trade rules (research/daytrade.py) on chosen instruments: halves, stress, last 12 months,
years and trades a day. Used on 2 Nov 2026 to confirm USDJPY PDHL / NY_CONT before adding them, and to see why
gold's Williams k 0.7 no longer passes on the export that ends 2 Nov 2026."""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYMS = ("XAUUSD", "USDJPY", "EURJPY", "GBPJPY")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    pf, f2 = SA.pf, SA.f2
    for s in SYMS:
        d5 = SA.load(os.path.join(DATA, s + ".csv"), meta[s]["point"])
        B15, BH, D = DT.bars(d5, "15min"), DT.bars(d5, "1h"), DT.daily(d5)
        days = d5.index.normalize().nunique()
        mid, end = d5.index[len(d5) // 2], d5.index[-1]
        print(f"\n{s}: {d5.index[0].date()} .. {end.date()}, {days} days")
        for rule, (tf, sig, flat) in DT.rules(B15, BH, D).items():
            if rule not in ("WILL70", "WILL50", "PDHL", "NY_CONT"):
                continue
            B = B15 if tf == "M15" else BH
            arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
            res = SA.sim(*arr, sig, flat)
            T = pd.DataFrame(res, columns=["k", "dir", "pnl", "sp", "risk", "why"])
            T["t"] = B.index[T.k.values]
            R = ((T.pnl - T.sp) / T.risk).values
            RS = ((T.pnl - 1.5 * T.sp) / T.risk).values
            h = (T.t >= mid).values
            l12 = (T.t >= end - pd.Timedelta(days=365)).values
            yrs = " ".join(f"{y % 100}:{f2(pf(R[(T.t.dt.year == y).values]))}" for y in sorted(T.t.dt.year.unique()))
            ok = len(T) >= 150 and pf(R) >= 1.15 and pf(R[~h]) >= 1.05 and pf(R[h]) >= 1.05 and pf(RS) >= 1.05 and R[l12].sum() > 0
            print(f"  {rule:8s} {len(T):5d} trades ({len(T) / days:.2f}/day) PF {f2(pf(R))} halves {f2(pf(R[~h]))} {f2(pf(R[h]))} "
                  f"stress {f2(pf(RS))} last 12 months {R[l12].sum():+.1f}R (PF {f2(pf(R[l12]))}) long PF {f2(pf(R[T.dir.values == 1]))} "
                  f"short PF {f2(pf(R[T.dir.values == -1]))} {'PASS' if ok else 'fail'} | {yrs}")


if __name__ == "__main__":
    main()
