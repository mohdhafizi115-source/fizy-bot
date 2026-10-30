"""Robustness of the London Silver Bullet (research/scalp2.py SB_LDN) on Deriv XAUUSD 5m: neighbouring
settings (TP, minimum gap, entry at the gap edge or its middle, window) and the result by month."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import scalp2 as X
out = X.out
def deriv_slow():
    got = {}; end = "latest"
    for p in range(45):
        js = X.S._deriv_call({"ticks_history": "frxXAUUSD", "style": "candles", "granularity": 300, "count": 5000, "end": end})
        if js.get("error"):
            X.say(f"  deriv page {p}: {js['error'].get('message')}"); break
        rows = js.get("candles") or []
        new = [r for r in rows if int(r["epoch"]) not in got]
        for r in rows:
            got[int(r["epoch"])] = r
        if not rows or not new:
            break
        end = min(int(r["epoch"]) for r in rows) - 1
        time.sleep(1.5)
    df = pd.DataFrame([got[e] for e in sorted(got)])
    df.index = pd.to_datetime(df["epoch"].astype(int), unit="s", utc=True)
    df = df[["open", "high", "low", "close"]].astype(float); df["volume"] = 1.0
    return df
for src, loader, sp in (("Deriv XAUUSD 5m", deriv_slow, 0.25), ("Yahoo GC=F 5m", X.yahoo5, 0.30)):
    try:
        d = X.indicators(loader())
    except Exception as e:
        X.say(f"{src}: data error {e}"); continue
    days = d.ch_day.nunique(); mid_t = d.index[len(d) // 2]
    X.say(f"\n{src}: {len(d)} candles {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d} ({days} days)")
    rows = []
    for w0, w1 in ((3, 4), (2, 4), (3, 5), (2, 3)):
        for tp in (1.5, 2.0, 3.0):
            for gap in (0.1, 0.2, 0.3):
                for ce in (False, True):
                    sig, flat = X.sig_sb(d, w0, w1, False, tp_r=tp, gap=gap, ce=ce)
                    tr = X.run(d, sig, sp, flat)
                    if not len(tr):
                        continue
                    x = tr.pnl.values
                    rows.append(dict(win=f"{w0:02d}-{w1:02d}", tp=tp, gap=gap, entry="mid" if ce else "edge", n=len(tr),
                                     pf=X.pf(x), net=x.sum(), h1=X.pf(tr[tr.t < mid_t].pnl.values), h2=X.pf(tr[tr.t >= mid_t].pnl.values)))
    r = pd.DataFrame(rows)
    X.say(f"  {len(r)} settings: PF > 1 in {np.mean(r.pf > 1) * 100:.0f}%, both halves > 1 in {np.mean((r.h1 > 1) & (r.h2 > 1)) * 100:.0f}%, "
          f"median PF {r.pf.median():.2f}")
    for w, g in r.groupby("win"):
        X.say(f"   window {w} NY: median PF {g.pf.median():.2f}, PF>1 in {np.mean(g.pf > 1) * 100:.0f}%, median net ${g.net.median():+.0f}")
    for k in ("tp", "gap", "entry"):
        X.say("   by " + k + ": " + ", ".join(f"{v}: PF {g.pf.median():.2f}" for v, g in r[r.win == "03-04"].groupby(k)))
    sig, flat = X.sig_sb(d, 3, 4, False)
    tr = X.run(d, sig, sp, flat)
    mon = tr.groupby(tr.t.dt.strftime("%Y-%m")).pnl.agg(["count", "sum"])
    X.say("   base SB_LDN by month: " + ", ".join(f"{m} {int(c)}t ${s:+.0f}" for m, (c, s) in mon.iterrows()))
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("London Silver Bullet robustness\n" + "\n".join(out) + "\n")
