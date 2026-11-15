"""Round 120b (15 Nov 2026): MODIFY the BTCUSD M5 infographic scalp until it holds in BOTH 3-month windows.  Owner: "cuba kau modified".
Grid on top of round 120: trend none / H1 EMA20-50 / H4 EMA20-50 / H1 EMA50-200; Stoch (5,3,3) cross out of 20/80 or 30/70; RSI 50 on /
off; pullback to EMA 20 on / off; session all days / weekdays / 07-19 server; SL 1 / 1.5 / 2 x ATR(14, M5) from the entry; exit TP 1R /
2R / 3R / no TP with a 2 h or 4 h time exit; every trade also capped at 24 h, swap charged.  A cell must be positive in the 3 months
before (the choosing window) AND in the last 3 months; the whole grid is re-run with a RANDOM direction on the same entries to count how
many cells pass both windows by luck.  BTCUSD M1 from 2026-04-01 (data of round 120), 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
from btcm5_120 import ema, rsi

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit
SWL, SWS = -0.85, -0.56


@jit
def sim2(O, H, L, S, dayid, eidx, edir, sld, tpr, maxb, usd):
    n = len(eidx); pn = np.zeros(n); xi = np.full(n, -1, np.int64); last = -1; N = len(O)
    for k in range(n):
        j0 = eidx[k]
        if j0 <= last or j0 >= N - 2: continue
        d = edir[k]
        ent = O[j0] + S[j0] if d == 1 else O[j0]
        sl = ent - d * sld[k]; tp = ent + d * sld[k] * tpr if tpr > 0 else 0.0
        pnl = 0.0; done = False; j = j0; jend = min(j0 + maxb, N - 1)
        while j < jend:
            if j > j0 and dayid[j] != dayid[j - 1]:
                pnl += SWL if d == 1 else SWS
            if d == 1:
                if L[j] <= sl: pnl += (min(O[j], sl) - ent) * usd; done = True; break
                if tpr > 0 and H[j] >= tp: pnl += (tp - ent) * usd; done = True; break
            else:
                if H[j] + S[j] >= sl: pnl += (ent - max(O[j] + S[j], sl)) * usd; done = True; break
                if tpr > 0 and L[j] + S[j] <= tp: pnl += (ent - tp) * usd; done = True; break
            j += 1
        if not done:
            pnl += ((O[j] - ent) if d == 1 else (ent - O[j] - S[j])) * usd
        pn[k] = pnl; xi[k] = j0; last = j
    return pn, xi


def main():
    mt, sw = W.read_meta("BTCUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=25)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    say(f"BTCUSD M5 SCALP MODIFIED, choose on {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}, check on {a3:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot")
    agg = dict(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    m5 = d.resample("5min", label="left", closed="left").agg(**agg).dropna()
    c5 = m5.c
    e20 = ema(c5, 20).values; r = rsi(c5).values
    c1 = c5.shift(); tr = np.maximum(m5.h - m5.l, np.maximum((m5.h - c1).abs(), (m5.l - c1).abs()))
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().values
    ll = m5.l.rolling(5).min(); hh = m5.h.rolling(5).max()
    k = ((c5 - ll) / (hh - ll) * 100).rolling(3).mean().values; dd = pd.Series(k).rolling(3).mean().values
    k1 = np.roll(k, 1); d1 = np.roll(dd, 1)
    o, c, l, h = m5.o.values, c5.values, m5.l.values, m5.h.values
    lmin3 = pd.Series(l).rolling(3).min().values; hmax3 = pd.Series(h).rolling(3).max().values
    trends = {"none": np.zeros(len(m5))}
    for nm, fr, per, a, b in (("H1 20/50", "1h", pd.Timedelta(hours=1), 20, 50), ("H4 20/50", "4h", pd.Timedelta(hours=4), 20, 50),
                              ("H1 50/200", "1h", pd.Timedelta(hours=1), 50, 200)):
        X = d.resample(fr, label="left", closed="left").agg(**agg).dropna()
        t = np.sign(ema(X.c, a) - ema(X.c, b)); t.index = X.index + per
        trends[nm] = t.reindex(m5.index + pd.Timedelta(minutes=5), method="ffill").values
    pos = pd.Series(np.arange(len(T)), index=T)
    nxt = pos.reindex(m5.index + pd.Timedelta(minutes=5), method="bfill").values
    hr = m5.index.hour.values; wd = m5.index.day_of_week.values < 5
    sess = {"all": np.ones(len(m5), bool), "weekdays": wd, "07-19": (hr >= 7) & (hr < 19)}
    exits = [(1.0, 1440, "TP1R"), (2.0, 1440, "TP2R"), (3.0, 1440, "TP3R"), (0.0, 120, "2h"), (0.0, 240, "4h")]
    rows = []; rnd = np.random.default_rng(7)
    for tn, trd in trends.items():
        for lv in (20, 30):
            ux = (k > dd) & (k1 <= d1) & (np.minimum(k1, d1) < lv); dx = (k < dd) & (k1 >= d1) & (np.maximum(k1, d1) > 100 - lv)
            for ru in (True, False):
                for pb in (True, False):
                    for sn, sm in sess.items():
                        B = ux & (c > o) & sm & ((trd > 0) if tn != "none" else True)
                        Sx = dx & (c < o) & sm & ((trd < 0) if tn != "none" else True)
                        if ru: B = B & (r > 50); Sx = Sx & (r < 50)
                        if pb: B = B & (lmin3 <= e20); Sx = Sx & (hmax3 >= e20)
                        sig = np.where(B, 1, np.where(Sx, -1, 0))
                        idx = np.where((sig != 0) & np.isfinite(nxt) & np.isfinite(atr))[0]
                        if len(idx) < 40: continue
                        ei = nxt[idx].astype(np.int64); ed = sig[idx].astype(np.int64); er = rnd.choice([-1, 1], len(ed)).astype(np.int64)
                        for slk in (1.0, 1.5, 2.0):
                            sld = atr[idx] * slk
                            for tpr, mb, en in exits:
                                for tag, dirs in (("REAL", ed), ("RAND", er)):
                                    p, xi = sim2(O, H, L, S, dayid, ei, dirs, sld, tpr, mb, usd)
                                    ok = xi >= 0; te = T[xi[ok]]; p = p[ok]
                                    m = te >= a3; m2 = (te >= a6) & (te < a3)
                                    rows.append(dict(tag=tag, name=f"{tn} st{lv} rsi{'Y' if ru else 'N'} pb{'Y' if pb else 'N'} {sn} SL{slk}ATR {en}",
                                                     n1=int(m2.sum()), pf1=pf(p[m2]), net1=p[m2].sum(), n2=int(m.sum()), pf2=pf(p[m]), net2=p[m].sum(),
                                                     idx=(ei, dirs, sld, tpr, mb)))
    R = pd.DataFrame(rows)
    for tag in ("REAL", "RAND"):
        X = R[(R.tag == tag) & (R.n1 >= 30) & (R.n2 >= 30)]
        both = X[(X.pf1 >= 1.15) & (X.pf2 >= 1.15)]
        say(f"{tag}: {len(X)} cells with >= 30 trades in both windows; PF >= 1.15 in both: {len(both)} ({100 * len(both) / max(len(X), 1):.1f}%); "
            f"median PF choose / check {X.pf1.median():.2f} / {X.pf2.median():.2f}; corr(PF choose, PF check) {X.pf1.corr(X.pf2):+.2f}")
    X = R[(R.tag == "REAL") & (R.n1 >= 30) & (R.n2 >= 30)].copy()
    say("\nchosen on the PREVIOUS 3 months only (top 15 by PF there), then their LAST 3 months:")
    say(f"{'cell':62s} | {'prev n':>6} {'PF':>5} {'net$':>6} | {'last n':>6} {'PF':>5} {'net$':>6}")
    for _, x in X.sort_values("pf1", ascending=False).head(15).iterrows():
        say(f"{x['name']:62s} | {x.n1:6d} {x.pf1:5.2f} {x.net1:+6.0f} | {x.n2:6d} {x.pf2:5.2f} {x.net2:+6.0f}")
    say("\nbest by the WORSE of the two windows (top 15):")
    X["mn"] = np.minimum(X.pf1, X.pf2)
    top = X.sort_values("mn", ascending=False).head(15)
    for _, x in top.iterrows():
        say(f"{x['name']:62s} | {x.n1:6d} {x.pf1:5.2f} {x.net1:+6.0f} | {x.n2:6d} {x.pf2:5.2f} {x.net2:+6.0f}")
    x = top.iloc[0]; ei, dirs, sld, tpr, mb = x["idx"]
    p, xi = sim2(O, H, L, S, dayid, ei, dirs, sld, tpr, mb, usd); ok = xi >= 0; te = T[xi[ok]]; p = p[ok]; dr = dirs[ok]
    pS, xS = sim2(O, H, L, S * 1.5, dayid, ei, dirs, sld, tpr, mb, usd); okS = xS >= 0
    m = te >= a3; x2 = p[m]
    dp = pd.Series(x2, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
    say(f"\nbest cell detail, last 3 months: {len(x2)} trades, win {100 * (x2 > 0).mean():.0f}%, PF {pf(x2):.2f}, stress {pf(pS[okS][T[xS[okS]] >= a3]):.2f}, "
        f"net {x2.sum():+.0f}, DD {(eq - eq.cummax()).min():+.0f}, worst day {dp.min():+.0f}, buys {pf(x2[dr[m] == 1]):.2f} / sells {pf(x2[dr[m] == -1]):.2f}")
    for nm, sub in (("its 10 neighbours (same family, one setting changed)", None),):
        pass


if __name__ == "__main__":
    main()
