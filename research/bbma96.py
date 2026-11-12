"""Round 96 (12 Nov 2026): keep looking for what validates an M15 CSAK: BBMA's own Extreme / MHV context, longer
horizons, and a learned combination of every feature.  Last 2 years, all 30 instruments.

Owner: "aku nak kau cari jugak cara nak valid kan csak m15!".  Round 94 measured 16 features up to 16 M15 candles
ahead and found nothing that beats the spread.  New here:
  1 BBMA context before the CSAK (BUY shown, SELL mirrored), all causal:
      Extreme against  in the last 12 M15 candles, a candle whose LWMA5 or LWMA10 of the lows was below the bottom BB
                       (price was stretched DOWN, the buy CSAK is the turn) - BBMA's reversal "Extreme"
      Extreme with     the same with the highs above the top BB (the CSAK follows a stretched UP move)
      MHV against      an Extreme against 3-20 candles ago, then a candle that touched the bottom BB and closed back
                       inside without a lower low than the Extreme's low (the failed retest, BBMA "MHV")
      H1 / H4 Extreme against / with   the same Extreme test on the last 4 closed H1 / last 3 closed H4 candles
      H4 BB position   (close - H4 mid BB) / half the H4 band, signed (+1 = at the top band in the CSAK direction)
  2 horizons up to 96 M15 candles (24 h): f1 .. f96 = move in the CSAK direction in ATR(M15); a no-SL time exit after N
    candles earns f_N minus the spread (spread/ATR is in the same unit), so "net" columns are that trade
  3 a learned model: gradient boosting on all features (round 94's 16 + the new ones), trained on YEAR 1 to predict the
    32-candle move, then YEAR 2 sorted into deciles of the prediction: does the top decile beat the spread?
Pooled over the 30 instruments; every bucket shown with its year-1 and year-2 value.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import bbma87 as B87
import bbma94 as B94

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()
HZ = (1, 4, 8, 16, 32, 64, 96)


def extremes(X):
    I = B87.ind(X)
    lo5, lo10, hi5, hi10 = (B87.lwma(X[s].values, p) for s, p in (("l", 5), ("l", 10), ("h", 5), ("h", 10)))
    exd = (np.minimum(lo5, lo10) < I.bot.values)                     # stretched down
    exu = (np.maximum(hi5, hi10) > I.top.values)                     # stretched up
    return I, exd, exu


def htf_flags(X, m, nb):
    g = X.resample(f"{m}min", label="left", closed="left")
    Y = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
    I, exd, exu = extremes(Y)
    cly = (Y.index + pd.Timedelta(minutes=m)).values
    k = np.searchsorted(cly, (X.index + pd.Timedelta(minutes=15)).values, side="right") - 1
    rd = pd.Series(exd.astype(float)).rolling(nb, min_periods=1).max().values
    ru = pd.Series(exu.astype(float)).rolling(nb, min_periods=1).max().values
    pos = ((Y.c - I.mid) / ((I.top - I.bot) / 2).replace(0, np.nan)).values
    ok = k >= 0; kk = np.maximum(k, 0)
    return np.where(ok, rd[kk], np.nan), np.where(ok, ru[kk], np.nan), np.where(ok, pos[kk], np.nan)


def measure(meta):
    rows = []; END = None
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        d = SA.load(os.path.join(DATA, sym + ".csv"), meta[sym]["point"])
        B = d[["o", "h", "l", "c", "s", "v"]]
        g = B.resample("15min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        X["v"] = g.v.sum().reindex(X.index).fillna(0).values; X["s"] = g.s.median().reindex(X.index).values
        I, exd, exu = extremes(X); Fm = B94.feats(X)
        o, c, h, l = X.o.values, X.c.values, X.h.values, X.l.values
        bot, top = I.bot.values, I.top.values
        lo, hi = np.minimum(I.mid, I.e50).values, np.maximum(I.mid, I.e50).values
        cb = (o < lo) & (c > hi) & (c <= top); cs = (o > hi) & (c < lo) & (c >= bot)
        end = X.index[-1]; END = end if END is None else max(END, end)
        hm = X.index.hour.values * 60 + X.index.minute.values
        N = len(X)
        ks = np.where((cb | cs) & (hm >= 90) & (hm < 1320) & (X.index >= end - pd.Timedelta(days=730)) & (np.arange(N) < N - 97) & (np.arange(N) > 300))[0]
        dr = np.where(cb[ks], 1, -1); atr = Fm["_atr"][ks]
        r = {"sym": sym, "t": X.index[ks], "dir": dr}
        for hh in HZ: r[f"f{hh}"] = (c[ks + hh] - c[ks]) * dr / atr
        for nm, a in Fm.items():
            if nm == "_atr": continue
            kd = B94.KIND.get(nm, "raw")
            if kd == "pair": r[nm] = np.where(dr == 1, a[0][ks], a[1][ks])
            elif kd == "osc": r[nm] = np.where(dr == 1, a[ks], 100 - a[ks])
            elif kd == "sym": r[nm] = a[ks] * dr
            else: r[nm] = a[ks]
        rd12 = pd.Series(exd.astype(float)).rolling(12, min_periods=1).max().values
        ru12 = pd.Series(exu.astype(float)).rolling(12, min_periods=1).max().values
        r["Extreme against (M15, 12)"] = np.where(dr == 1, rd12[ks - 1], ru12[ks - 1])
        r["Extreme with (M15, 12)"] = np.where(dr == 1, ru12[ks - 1], rd12[ks - 1])
        mhv = np.zeros(len(ks))
        for n_, (k, d_) in enumerate(zip(ks, dr)):
            ex = exd if d_ == 1 else exu
            js = np.where(ex[k - 20:k - 2])[0]
            if len(js) == 0: continue
            j = k - 20 + js[-1]
            if d_ == 1:
                exlow = l[j - 2:j + 1].min()
                seg = np.arange(j + 1, k)
                if ((l[seg] <= bot[seg]) & (c[seg] > bot[seg]) & (l[seg] >= exlow)).any() and l[j + 1:k].min() >= exlow: mhv[n_] = 1
            else:
                exhigh = h[j - 2:j + 1].max()
                seg = np.arange(j + 1, k)
                if ((h[seg] >= top[seg]) & (c[seg] < top[seg]) & (h[seg] <= exhigh)).any() and h[j + 1:k].max() <= exhigh: mhv[n_] = 1
        r["MHV against (M15)"] = mhv
        for m, nb, lab in ((60, 4, "H1"), (240, 3, "H4")):
            fd, fu, pos = htf_flags(X, m, nb)
            r[f"{lab} Extreme against"] = np.where(dr == 1, fd[ks], fu[ks])
            r[f"{lab} Extreme with"] = np.where(dr == 1, fu[ks], fd[ks])
            if lab == "H4": r["H4 BB position"] = pos[ks] * dr
        rows.append(pd.DataFrame(r))
        say(f"{sym}: {len(ks)} CSAKs [{time.time() - T0:.0f} s]")
    D = pd.concat(rows, ignore_index=True)
    D["yr"] = (D.t >= END - pd.Timedelta(days=365)).astype(int)
    return D, END


def line(lab, x, y1, y2):
    spr = x["spread/ATR"].mean()
    cells = " ".join(f"{x[f'f{h}'].mean():+6.3f}" for h in HZ)
    net = " ".join(f"{(x[f'f{h}'] - x['spread/ATR']).mean():+6.3f}" for h in (8, 32, 96))
    return f"{lab:34s} {len(x):6d} | {cells} | spr {spr:5.3f} | net f8/f32/f96 {net} | yr1 f32 {y1.f32.mean():+6.3f} yr2 f32 {y2.f32.mean():+6.3f}"


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    D, END = measure(meta)
    say(f"\n===== {len(D):,} M15 CSAKs, 30 instruments, {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d} =====")
    say("move IN the CSAK direction in ATR(M15) after N M15 candles; 'net' = a no-SL trade closed after N candles, minus one spread")
    say(f"{'bucket':34s} {'n':>6} | " + " ".join(f"{'f' + str(h):>6}" for h in HZ) + " |")
    y1, y2 = D[D.yr == 0], D[D.yr == 1]
    say(line("ALL CSAKs", D, y1, y2))
    for side, sd in (("BUY CSAKs", 1), ("SELL CSAKs", -1)):
        x = D[D.dir == sd]; say(line(side, x, x[x.yr == 0], x[x.yr == 1]))
    say("\n--- BBMA context (1 = present) ---")
    for nm in ("Extreme against (M15, 12)", "Extreme with (M15, 12)", "MHV against (M15)", "H1 Extreme against", "H1 Extreme with",
               "H4 Extreme against", "H4 Extreme with"):
        for v in (1, 0):
            x = D[D[nm] == v]
            if len(x) < 50: continue
            say(line(f"{nm} = {v}", x, x[x.yr == 0], x[x.yr == 1]))
    say("\n--- H4 BB position (signed: +1 = at the H4 band in the CSAK direction, -1 = at the opposite band) ---")
    for a, b in ((-9, -1), (-1, -0.5), (-0.5, 0), (0, 0.5), (0.5, 1), (1, 9)):
        x = D[(D["H4 BB position"] > a) & (D["H4 BB position"] <= b)]
        if len(x) >= 50: say(line(f"({a}, {b}]", x, x[x.yr == 0], x[x.yr == 1]))
    say("\n--- combinations: reversal CSAKs (the only family that held in round 94) ---")
    combos = {
        "M15 Extreme against + MHV": (D["Extreme against (M15, 12)"] == 1) & (D["MHV against (M15)"] == 1),
        "H4 Extreme against": D["H4 Extreme against"] == 1,
        "H4 Extreme against + M15 MHV": (D["H4 Extreme against"] == 1) & (D["MHV against (M15)"] == 1),
        "against H4 trend + prior move against": (D["H4 EMA50vs90"] == -1) & (D["move prior8 ATR"] < -1.2),
        "against H4 + H1 + London": (D["H4 EMA50vs90"] == -1) & (D["H1 vs EMA50"] == -1) & (D["session"] == 1),
        "H4 BB pos <= -0.5 (at the far band)": D["H4 BB position"] <= -0.5,
        "H4 pos <= -0.5 + M15 Extreme against": (D["H4 BB position"] <= -0.5) & (D["Extreme against (M15, 12)"] == 1),
    }
    for nm, m in combos.items():
        x = D[m]
        if len(x) >= 50: say(line(nm, x, x[x.yr == 0], x[x.yr == 1]))
    # ---------- learned model, year 1 -> year 2
    from sklearn.ensemble import HistGradientBoostingRegressor
    cols = [c for c in D.columns if c not in ("sym", "t", "dir", "yr") and not c.startswith("f") or c.startswith("move")]
    cols = [c for c in cols if not (c.startswith("f") and c[1:].isdigit())]
    Xa = D[cols].astype(float).replace([np.inf, -np.inf], np.nan)
    tr, te = D.yr == 0, D.yr == 1
    y = D.f32.clip(-6, 6)
    say(f"\n===== learned model (gradient boosting, {len(cols)} features), trained on YEAR 1 ({tr.sum():,} CSAKs) to predict f32, YEAR 2 out of sample =====")
    for tgt, nm in ((D.f32.clip(-6, 6), "f32"), (D.f96.clip(-10, 10), "f96")):
        mdl = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, random_state=96)
        mdl.fit(Xa[tr], tgt[tr])
        p = mdl.predict(Xa[te]); Z = D[te].assign(p=p)
        Z["dec"] = pd.qcut(Z.p, 10, labels=False, duplicates="drop")
        say(f"\n target {nm}: corr(prediction, realised) in year 2 = {np.corrcoef(p, D.loc[te, nm])[0, 1]:+.3f}")
        say(f" {'decile':>6} {'n':>5} {'pred':>7} {'f8':>7} {'f32':>7} {'f96':>7} {'spr':>6} {'net f32':>8} {'net f96':>8}")
        for dcl, x in Z.groupby("dec"):
            say(f" {int(dcl):6d} {len(x):5d} {x.p.mean():+7.3f} {x.f8.mean():+7.3f} {x.f32.mean():+7.3f} {x.f96.mean():+7.3f} {x['spread/ATR'].mean():6.3f} "
                f"{(x.f32 - x['spread/ATR']).mean():+8.3f} {(x.f96 - x['spread/ATR']).mean():+8.3f}")
        top = Z[Z.dec == Z.dec.max()]
        g = top.groupby("sym").apply(lambda v: (v[nm] - v["spread/ATR"]).mean())
        say(f" top decile by symbol: {int((g > 0).sum())} of {len(g)} symbols net-positive on {nm}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
