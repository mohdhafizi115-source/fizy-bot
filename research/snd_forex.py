"""Out-of-sample check of the SnD (supply & demand zone) rules on Yahoo H1 data, 2 years, all pairs + gold.
Runs inside GitHub Actions. Writes status/research.txt. Execution on H1 candles; spread 1 pip forex /
2 pips gold; swap ignored."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
from snd import snd
from ms_forex_data import yahoo_h1

VARIANTS = {
    "A H1 zones, H4 trend, 2R, dep 2, legout 1.5": dict(ztf="1h", trend=True, rr=2.0, dep=2.0, legout_atr=1.5),
    "B H1 zones, no trend, 1.5R, dep 3, legout 1.2": dict(ztf="1h", trend=False, rr=1.5, dep=3.0, legout_atr=1.2),
    "C H1 zones, H4 trend, 1.5R, dep 2, legout 1.2": dict(ztf="1h", trend=True, rr=1.5, dep=2.0, legout_atr=1.2),
    "D H4 zones, H4 trend, 2R, dep 2, legout 1.5": dict(ztf="4h", trend=True, rr=2.0, dep=2.0, legout_atr=1.5),
}

out, allr = [], {k: [] for k in VARIANTS}
for name in S.symbol_list():
    S.set_symbol(name)
    try:
        df = yahoo_h1(name)
    except Exception as e:
        out.append(f"{name}: data error {e}"); continue
    df.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in df.index])
    df = df[~df.index.duplicated()].sort_index()
    df["spread"] = S.CUR["spread"]
    line = f"{name:7s} {len(df):5d} H1 {df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d} |"
    for k, kw in VARIANTS.items():
        tr = snd(df, swap=False, **kw)
        if len(tr):
            r = tr.R.values; allr[k] += [(name, t.open, t.R) for t in tr.itertuples()]
            gp, gl = r[r > 0].sum(), -r[r < 0].sum()
            line += f" {k[:1]}: n={len(r)} R={r.sum():+.1f} PF={(gp / gl if gl else 99):.2f} |"
        else:
            line += f" {k[:1]}: n=0 |"
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
    a, b = d[d.open < half].R.values, d[d.open >= half].R.values
    pf = lambda x: (x[x > 0].sum() / -x[x < 0].sum()) if (x < 0).any() else 99
    fx = d[~d.sym.str.startswith("XAU")]
    pos_pairs = (fx.groupby("sym").R.sum() > 0).mean() * 100
    summ.append(f"ALL {k}: trades {len(r)}, win {np.mean(r > 0) * 100:.0f}%, total {r.sum():+.1f}R, PF {gp / gl if gl else 99:.2f}, "
                f"max DD {dd:.1f}R, PF first half {pf(a):.2f} / second half {pf(b):.2f}, forex pairs positive {pos_pairs:.0f}%")
os.makedirs("status", exist_ok=True)
with open("status/research.txt", "w") as f:
    f.write("SnD zone strategy on Yahoo H1 data, 2 years (spread 1 pip forex / 2 pips gold, swap ignored)\n")
    f.write("\n".join(summ) + "\n\n" + "\n".join(out) + "\n")
print("\n".join(summ))
