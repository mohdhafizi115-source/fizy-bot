"""Out-of-sample check of the market structure strategy on Deriv data for all pairs + gold.
Runs inside GitHub Actions (Deriv is reachable there). Writes status/research.txt."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
import bt
bt.swap_cost = lambda t0, t1, dr: 0.0          # forex swap unknown here: ignored (noted in the report)
from ms import market_structure

VARIANTS = {
    "H4/H1 TP 2R": dict(),
    "H4/H1 TP swing": dict(tp_mode="swing"),
    "H4/M15 TP 2R": dict(etf="15min"),
}
VARIANTS["H4/H1 TP 2R"] = dict(tp_mode="rr", rr=2.0)
VARIANTS["H4/M15 TP 2R"] = dict(etf="15min", tp_mode="rr", rr=2.0)

out, allr = [], {k: [] for k in VARIANTS}
for name in S.symbol_list():
    S.set_symbol(name)
    try:
        df = S.fetch_deriv(name, need=16000, max_pages=25)
    except Exception as e:
        out.append(f"{name}: data error {e}"); continue
    df.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in df.index])
    df = df[~df.index.duplicated()].sort_index()
    df["spread"] = S.CUR["spread"]
    line = f"{name:7s} {len(df):5d} candles {df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d} |"
    for k, kw in VARIANTS.items():
        tr = market_structure(df, **kw)
        if len(tr):
            r = tr.R.values; allr[k] += [(name, t.open, t.R) for t in tr.itertuples()]
            gp, gl = r[r > 0].sum(), -r[r < 0].sum()
            line += f" {k}: n={len(r)} R={r.sum():+.1f} PF={(gp / gl if gl else 99):.2f} |"
        else:
            line += f" {k}: n=0 |"
    out.append(line); print(line, flush=True)
    time.sleep(1)
summ = []
for k, rows in allr.items():
    if not rows:
        continue
    d = pd.DataFrame(rows, columns=["sym", "open", "R"]).sort_values("open")
    r = d.R.values; gp, gl = r[r > 0].sum(), -r[r < 0].sum()
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    half = d.open.quantile(0.5)
    a, b = d[d.open < half].R, d[d.open >= half].R
    pos_pairs = (d.groupby("sym").R.sum() > 0).mean() * 100
    summ.append(f"ALL {k}: trades {len(r)}, win {np.mean(r > 0) * 100:.0f}%, total {r.sum():+.1f}R, PF {gp / gl if gl else 99:.2f}, "
                f"max DD {dd:.1f}R, first half {a.sum():+.1f}R / second half {b.sum():+.1f}R, pairs positive {pos_pairs:.0f}%")
os.makedirs("status", exist_ok=True)
with open("status/research.txt", "w") as f:
    f.write("Market structure strategy on Deriv M15 data (spread 1 pip forex / 2 pips gold, swap ignored)\n")
    f.write("\n".join(summ) + "\n\n" + "\n".join(out) + "\n")
print("\n".join(summ))
