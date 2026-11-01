"""Gold before the LBMA auctions (10:30 and 15:00 London): robustness of the round-7 finding that gold tends to
fall in the 15 minutes before the 10:30 auction. Sell at T_in, buy back at T_out (London time), every trading day.
Cost: the entry bar's spread (MT5 export). Per trade in $ per 0.01 lot ($1 per $1 move)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
d = FL.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
print("XAUUSD, sell before the auction, buy back at T_out ($ per 0.01 lot, after spread)")
for t_in, t_out in ((600, 630), (610, 630), (615, 630), (620, 630), (625, 630), (615, 625), (615, 635), (615, 645), (630, 645),
                    (870, 900), (885, 900), (895, 900), (900, 915)):
    I = FL.window_trades(d, "Europe/London", t_in, t_out, side=-1)
    FL.report(f"sell {t_in // 60}:{t_in % 60:02d} -> {t_out // 60}:{t_out % 60:02d} London", I, 1.0)
I = FL.window_trades(d, "Europe/London", 615, 630, side=-1)
print("\nsell 10:15 -> 10:30 by weekday: " + ", ".join(f"{n}: {len(g)} PF {FL.f2(FL.pf(g.net.values))} ${g.net.sum():+.0f}"
      for n, g in I.groupby(I.index.day_name())))
mon = I.net.groupby(I.index.to_period("M")).sum()
q = I.net.groupby(I.index.to_period("Q")).sum()
print(f"winning months {(mon > 0).sum()}/{len(mon)}, winning quarters {(q > 0).sum()}/{len(q)}, mean spread ${I.sp.mean():.2f}, "
      f"stdev of the 15-min move ${I.gross.std():.2f}, worst trade ${I.net.min():.2f}, best ${I.net.max():.2f}")
eq = I.net.cumsum(); print(f"max drawdown ${(eq - eq.cummax()).min():.0f} per 0.01 lot, total ${I.net.sum():+.0f}")
# with a stop: what if a protective stop of k x ATR(M5) is used (exit at the stop if touched)
for k in (1.0, 2.0, 3.0):
    c1 = d.c.shift(); tr = np.maximum(d.h - d.l, np.maximum((d.h - c1).abs(), (d.l - c1).abs())); atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    loc = d.index.tz_convert("Europe/London"); hm = loc.hour * 60 + loc.minute
    out = []
    for i in np.where(hm == 615)[0]:
        if i + 3 >= len(d) or hm[i + 3] != 630:
            continue
        e = d.o.values[i]; sl = e + k * atr.values[i]; ex = d.o.values[i + 3]
        for j in range(i, i + 3):
            if d.h.values[j] >= sl:
                ex = sl; break
        out.append(e - ex - d.s.values[i])
    out = np.array(out)
    print(f"stop {k:.0f} ATR(M5): {len(out)} trades, PF {FL.f2(FL.pf(out))}, mean ${out.mean():+.2f}, stopped {np.mean(out < -k * 0.5):.0%} (approx)")
