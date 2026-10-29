"""Out-of-sample check of the Fib + trend line rules (BabyPips) on Yahoo H1 data, 2 years, all pairs + gold.
Runs inside GitHub Actions. Writes status/research.txt. Execution on H1 candles; spread 1 pip forex /
2 pips gold; swap ignored."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S
from fibtl import fib_tl
from ms_forex_data import yahoo_h1

VARIANTS = {
    "A L3, SL swing, TP 2R, no trend, leg 1.5 ATR": dict(L=3, sl_mode="swing", tp_mode="2r", trend=False, min_leg=1.5),
    "B L3, SL bounce bar, TP swing high, no trend, leg 1.5 ATR": dict(L=3, sl_mode="bar", tp_mode="high", trend=False, min_leg=1.5),
    "C L3, SL bounce bar, TP swing high, H4 trend, leg 1.5 ATR": dict(L=3, sl_mode="bar", tp_mode="high", trend=True, min_leg=1.5),
    "D L5, SL swing, TP 2R, no trend, leg 1.5 ATR": dict(L=5, sl_mode="swing", tp_mode="2r", trend=False, min_leg=1.5),
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
        tr = fib_tl(df, swap=False, **kw)
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
    f.write("Fib + trend line strategy (BabyPips) on Yahoo H1 data, 2 years (spread 1 pip forex / 2 pips gold, swap ignored)\n")
    f.write("\n".join(summ) + "\n\n" + "\n".join(out) + "\n")
print("\n".join(summ))
