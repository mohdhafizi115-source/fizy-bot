"""NR7 breakout deep check on gold (GC=F) and BTC (BTC-USD) daily, plus a few FX majors for contrast:
by year, both halves, last 3 years, and neighbouring settings (hold 1/2/3/5 days, NR4/NR7/NR10,
stop at the other side vs. 1 ATR, an inside-day filter). Same engine and costs as newtech.py."""
import os, sys
import numpy as np, pandas as pd
src = open(os.path.join(os.path.dirname(__file__), "newtech.py")).read().split("try:\n    daily = {}")[0]
ns = {"__file__": __file__}; exec(src, ns)
say, yahoo, run, atr = ns["say"], ns["yahoo"], ns["run"], ns["atr"]


def nr_trades(d, n, k=7, hold=1, stop="side", inside=False):
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    rng = d.high - d.low
    nr = (rng == rng.rolling(k).min()).values
    A = atr(d).values
    res = []
    for i in range(20, len(d) - 1):
        if not nr[i] or h[i] <= l[i] or (inside and not (h[i] <= h[i - 1] and l[i] >= l[i - 1])):
            continue
        bsl = l[i] if stop == "side" else h[i] - A[i]
        ssl = h[i] if stop == "side" else l[i] + A[i]
        k1 = i + 1
        path = [o[k1], l[k1], h[k1], c[k1]] if c[k1] >= o[k1] else [o[k1], h[k1], l[k1], c[k1]]
        first = None
        for a_, b_ in zip(path[:-1], path[1:]):
            if max(a_, b_) >= h[i]:
                first = dict(type="stop", dir=1, price=h[i], sl=bsl, exp=1, maxb=hold); break
            if min(a_, b_) <= l[i]:
                first = dict(type="stop", dir=-1, price=l[i], sl=ssl, exp=1, maxb=hold); break
        if first is None:
            continue
        r = run(d.iloc[i:i + hold + 3], {0: first}, n)
        res += [(t, R) for t, R in r[:1]]
    return res


def show(label, rows):
    if not rows:
        say(f"  {label}: no trades"); return
    s = pd.Series([R for _, R in rows], index=[t for t, _ in rows])
    pf = s[s > 0].sum() / -s[s < 0].sum()
    h1, h2 = s[s.index < s.index[len(s) // 2]], s[s.index >= s.index[len(s) // 2]]
    pfh = lambda x: x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
    l3 = s[s.index >= pd.Timestamp("2023-11-01", tz="UTC")]
    say(f"  {label:38s} {len(s):4d} trades, win {np.mean(s > 0) * 100:.0f}%, PF {pf:.2f}, {s.sum():+6.1f}R (avg {s.mean():+.3f}R), "
        f"halves PF {pfh(h1):.2f} / {pfh(h2):.2f}, last 3y {len(l3)}t {l3.sum():+.1f}R PF {pfh(l3):.2f}")


for n in ("XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY"):
    try:
        d = yahoo(n, "1d")
    except Exception as e:
        say(f"{n}: data error {e}"); continue
    say(f"\n{n}: {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d}")
    base = nr_trades(d, n)
    show("NR7, stop other side, hold 1 day (base)", base)
    s = pd.Series([R for _, R in base], index=[t for t, _ in base])
    say("   by year: " + ", ".join(f"{y} {g.sum():+.1f}R" for y, g in s.groupby(s.index.year)))
    for kw, lab in ((dict(hold=2), "hold 2 days"), (dict(hold=3), "hold 3 days"), (dict(hold=5), "hold 5 days"),
                    (dict(k=4), "NR4"), (dict(k=10), "NR10"), (dict(stop="atr"), "stop 1 ATR beyond entry"),
                    (dict(inside=True), "NR7 + inside day")):
        show(lab, nr_trades(d, n, **kw))
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("NR7 breakout deep check\n" + "\n".join(ns["out"]) + "\n")
