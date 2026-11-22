"""Round 161b: the round 161 BTC MART basket with NEW baskets on SATURDAY and SUNDAY only (owner 22 Nov: "pasang yang kau
kata akaun tak meletup bulan lepas. run hanya pada hari sabtu dan ahad saja btc ni"). An open basket keeps adding and keeps
its TP on weekdays (no SL). Same simulator as round 161 (weekday mask inverted), $1000 starts every 2nd weekday."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btcmart161 as R
import scalp_all as SA
import wti104 as W

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
W.DATA = DATA
mt, sw = W.read_meta("BTCUSD")
usd = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
d = d[d.index >= a6 - pd.Timedelta(days=2)]
O, H, L, C, SP = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
T = d.index
DAY = T.normalize().values.astype("datetime64[D]").astype(np.int64)
WD = T.dayofweek.values.astype(np.int64)
WE = np.where(WD >= 5, 0, 5).astype(np.int64)          # inverted: the sim skips new baskets where the value >= 5
ix = lambda t: int(np.searchsorted(T.values, np.datetime64(t)))
i_a6, i_a3, i_end = ix(a6), ix(a3), len(T)
starts = [s for s in pd.date_range(a6.normalize(), end.normalize() - pd.Timedelta(days=10), freq="B")][::2]
si = [ix(s) for s in starts]
R.say(f"ROUND 161b  BTC MART, new baskets SAT+SUN only, last 3 months {a3:%Y-%m-%d} .. {end:%Y-%m-%d} / previous {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}")
R.say(f"{'S':>5} {'TP$':>5} {'days':>5} | last: bask   net$ blown 1st  worstfl maxL | prev: bask   net$ blown 1st  worstfl maxL | $1000 starts blown")
for S in (200.0, 300.0, 400.0, 500.0, 600.0):
    for Tgt in (3.0, S * usd):
        if Tgt == S * usd and abs(Tgt - 3.0) < 1e-9: continue
        for lab, wd, flag in (("SatSu", WE, True), ("7d", WD, False)):
            a = R.sim(O, H, L, C, SP, DAY, wd, i_a3, i_end, S, S, Tgt, usd, flag, 1000.0)
            b = R.sim(O, H, L, C, SP, DAY, wd, i_a6, i_a3, S, S, Tgt, usd, flag, 1000.0)
            nbl = sum(1 for i in si if R.sim(O, H, L, C, SP, DAY, wd, i, i_end, S, S, Tgt, usd, flag, 1000.0)[3] >= 0)
            fa = T[a[3]].strftime("%m-%d") if a[3] >= 0 else "-"; fb = T[b[3]].strftime("%m-%d") if b[3] >= 0 else "-"
            R.say(f"{S:5.0f} {Tgt:5.2f} {lab:>5} | {a[0]:5d} {a[1]:+7.0f} {a[2]:3d} {fa:>5} {a[4]:7.0f} {a[5]:4d} | "
                  f"{b[0]:5d} {b[1]:+7.0f} {b[2]:3d} {fb:>5} {b[4]:7.0f} {b[5]:4d} | {nbl:2d} / {len(si)}")
