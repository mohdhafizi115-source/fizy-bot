"""Out-of-sample check of head and shoulders rules on Yahoo H1 data, 2 years, all pairs + gold.
Runs inside GitHub Actions. Writes status/research.txt. Execution on H1 candles; spread 1 pip forex /
2 pips gold; swap ignored."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
from hs import head_shoulders
from ms_forex_data import yahoo_h1

VARIANTS = {
    "A H1 L3, shoulders within 50%, prior trend, SL shoulder, TP measured": dict(tf="1h", L=3, sym=0.5, trend=True, sl_mode="shoulder", tp_mode="measured"),
    "B H1 L3, shoulders within 50%, no trend filter, SL shoulder, TP 2R": dict(tf="1h", L=3, sym=0.5, trend=False, sl_mode="shoulder", tp_mode="2r"),
    "C H4 L3, shoulders within 50%, prior trend, SL shoulder, TP measured": dict(tf="4h", L=3, sym=0.5, trend=True, sl_mode="shoulder", tp_mode="measured"),
    "D H1 L5, shoulders within 50%, no trend filter, SL head, TP measured": dict(tf="1h", L=5, sym=0.5, trend=False, sl_mode="head", tp_mode="measured"),
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
        tr = head_shoulders(df, swap=False, **kw)
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
    f.write("Head and shoulders on Yahoo H1 data, 2 years (spread 1 pip forex / 2 pips gold, swap ignored)\n")
    f.write("\n".join(summ) + "\n\n" + "\n".join(out) + "\n")
print("\n".join(summ))
