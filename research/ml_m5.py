"""Round 6a: Claude's own M5 model (machine learning) on the broker's M5 history, 30 instruments (1 Nov 2026).

Idea: instead of a hand-picked indicator rule, let a gradient-boosting model learn from many M5 features at once
and predict which barrier is hit first in the next hour(s). Strictly walk-forward: the model is trained only on the
24 months before each 3-month test window (every 5th bar), retrained every 3 months, and trades only in the unseen
window.

Data: JustMarkets demo M5 bars (mt5/ExportM5.mq5), server time. Costs: the fill bar's spread (MT5 export), once per
trade; stress test 1.5x spread. Swap ignored (holds <= 3 h).

Features at the close of each M5 bar (all price distances in ATR(14) units, so one model serves all instruments):
  returns over 1/3/6/12/24/48/96/288 bars; distance to EMA 20/50/200; EMA 50 slope; RSI 2 and 14; Bollinger z;
  12- and 48-bar range vs its 5-day mean (compression); ATR vs its 20-day mean and vs the daily ATR; position in
  today's range; distance to today's open, yesterday's high/low, today's Asia (03-08) high/low, daily VWAP;
  last bar body and wicks; tick volume vs its 1-day mean; spread / ATR; time of day; weekday; day of month,
  Gotobi day and month-end flags; currency strength (base minus quote) over 3/12/48 bars built from the 28 pairs;
  the instrument id.
Label (triple barrier): entry at the next open, barriers at +-K x ATR, horizon H bars; which is hit first (or none).
Trade: score = P(up first) - P(down first); trade the sign when |score| is in the top q of the training scores.
One position per instrument at a time. Entries 01:30-22:30 server (BTC all hours).
Settings run: A) K = 1.0, H = 12 (1 hour)   B) K = 2.0, H = 36 (3 hours)
"""
import os, sys, glob, time
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SUB = 5                      # use every 5th bar for training (neighbouring bars are near-duplicates)
TRAIN_MONTHS = 24            # rolling training window
QS = (0.002, 0.005, 0.01, 0.02, 0.05)
CCY = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF")


def say(s=""):
    print(s, flush=True)


def load_meta(path):
    meta = {}
    for ln in open(path, encoding="latin-1"):
        p = ln.strip().split(",")
        if len(p) >= 12 and p[0] != "base":
            try:
                meta[p[0]] = dict(sym=p[1], point=float(p[3]), tick_size=float(p[4]), tick_value=float(p[5]))
            except ValueError:
                pass
    return meta


def load(path, point):
    df = pd.read_csv(path).drop_duplicates("t").sort_values("t")
    d = pd.DataFrame({"o": df.o.values, "h": df.h.values, "l": df.l.values, "c": df.c.values,
                      "v": df.v.values.astype(float), "s": df.s.values.astype(float) * point},
                     index=pd.to_datetime(df.t.values, unit="s"))
    med = np.median(d.s.values[d.s.values > 0]) if (d.s.values > 0).any() else point
    d.loc[d.s <= 0, "s"] = med
    return d


def strength(closes):
    """Currency strength over n bars: mean of the signed, standardised log returns of every pair with that currency."""
    out = {}
    lr = np.log(closes)
    for n in (3, 12, 48):
        z = lr.diff(n)
        z = z / z.rolling(2000, min_periods=300).std()
        S = {}
        for cy in CCY:
            parts = []
            for p in z.columns:
                if p[:3] == cy:
                    parts.append(z[p])
                elif p[3:6] == cy:
                    parts.append(-z[p])
            S[cy] = pd.concat(parts, axis=1).mean(axis=1) if parts else None
        out[n] = S
    return out


def features(d, sym_id, base, st):
    o, h, l, c, v, s = d.o, d.h, d.l, d.c, d.v, d.s
    c1 = c.shift()
    tr = np.maximum(h - l, np.maximum((h - c1).abs(), (l - c1).abs()))
    A = tr.ewm(alpha=1 / 14, adjust=False).mean()
    F = pd.DataFrame(index=d.index)
    for n in (1, 3, 6, 12, 24, 48, 96, 288):
        F[f"r{n}"] = (c - c.shift(n)) / A
    e20, e50, e200 = (c.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    F["d20"], F["d50"], F["d200"] = (c - e20) / A, (c - e50) / A, (c - e200) / A
    F["sl50"] = (e50 - e50.shift(12)) / A
    dl = c.diff()
    for n, a in (("rsi2", 0.5), ("rsi14", 1 / 14)):
        up = dl.clip(lower=0).ewm(alpha=a, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=a, adjust=False).mean()
        F[n] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    sma, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    F["bbz"] = (c - sma) / sd.replace(0, np.nan)
    for n in (12, 48):
        r = h.rolling(n).max() - l.rolling(n).min()
        F[f"cmp{n}"] = r / r.rolling(1440, min_periods=300).mean()
    F["volr"] = A / A.rolling(5760, min_periods=500).mean()
    date = d.index.normalize()
    g = d.groupby(date)
    dhi, dlo, dop = g.h.cummax(), g.l.cummin(), g.o.transform("first")
    F["dpos"] = (c - dlo) / (dhi - dlo).replace(0, np.nan)
    F["dopen"] = (c - dop) / A
    D = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    Dc1 = D.c.shift()
    Dtr = np.maximum(D.h - D.l, np.maximum((D.h - Dc1).abs(), (D.l - Dc1).abs()))
    datr = Dtr.rolling(14).mean().shift(1)
    F["atrd"] = A / pd.Series(date, index=d.index).map(datr).values
    F["pdh"] = (c - pd.Series(date, index=d.index).map(D.h.shift(1)).values) / A
    F["pdl"] = (c - pd.Series(date, index=d.index).map(D.l.shift(1)).values) / A
    hm = d.index.hour * 60 + d.index.minute
    asia = (hm >= 180) & (hm < 480)
    ah = d.h.where(asia).groupby(date).transform("max"); al = d.l.where(asia).groupby(date).transform("min")
    after = hm >= 480
    F["ash"] = np.where(after, (c - ah) / A, np.nan); F["asl"] = np.where(after, (c - al) / A, np.nan)
    tp = (h + l + c) / 3; vv = v.clip(lower=1)
    vw = (tp * vv).groupby(date).cumsum() / vv.groupby(date).cumsum()
    F["vw"] = (c - vw) / A
    F["body"] = (c - o) / A
    F["uw"] = (h - np.maximum(o, c)) / A; F["lw"] = (np.minimum(o, c) - l) / A
    F["vr"] = v / v.rolling(288, min_periods=50).mean()
    F["spr"] = s / A
    F["hs"], F["hc"] = np.sin(2 * np.pi * hm / 1440), np.cos(2 * np.pi * hm / 1440)
    F["dow"] = d.index.dayofweek
    dom = d.index.day
    F["dom"] = dom
    F["gotobi"] = np.isin(dom, (5, 10, 15, 20, 25, 30)).astype(float)
    F["mend"] = (d.index.days_in_month - dom <= 2).astype(float)
    bq = (base[:3], base[3:6])
    for n in (3, 12, 48):
        Sb = st[n].get(bq[0]) if bq[0] in CCY else None
        Sq = st[n].get(bq[1]) if bq[1] in CCY else None
        x = 0
        if Sb is not None:
            x = x + Sb.reindex(d.index).values
        if Sq is not None:
            x = x - Sq.reindex(d.index).values
        F[f"cs{n}"] = x if not np.isscalar(x) else np.nan
    F["sym"] = sym_id
    return F.astype("float32"), A.values, hm


def labels(d, A, K, H):
    """Triple barrier from the next open: +1 up first, -1 down first, 0 none. ret = long return in price."""
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    n = len(d)
    t = d.index.values.astype("datetime64[s]").astype(np.int64)
    lab = np.zeros(n, np.int8); ret = np.full(n, np.nan); xb = np.full(n, -1, np.int64)
    valid = np.zeros(n, bool)
    idx = np.arange(n - H - 1)
    e = o[idx + 1]; up = e + K * A[idx]; dn = e - K * A[idx]
    valid[idx] = (t[idx + H] - t[idx] <= (H + 1) * 300) & np.isfinite(A[idx])
    done = np.zeros(len(idx), bool)
    for j in range(1, H + 1):
        k = idx + j
        hu, hd = h[k] >= up, l[k] <= dn
        both = hu & hd
        upbar = c[k] >= o[k]                      # O-L-H-C: low first on an up bar
        first_dn = (hd & ~hu) | (both & upbar)
        first_up = (hu & ~hd) | (both & ~upbar)
        gap_up = o[k] >= up; gap_dn = o[k] <= dn
        new_up = ~done & (first_up | gap_up) & ~gap_dn
        new_dn = ~done & (first_dn | gap_dn) & ~new_up
        r = np.where(gap_up, o[k] - e, K * A[idx]); lab[idx[new_up]] = 1; ret[idx[new_up]] = r[new_up]; xb[idx[new_up]] = k[new_up]
        r = np.where(gap_dn, o[k] - e, -K * A[idx]); lab[idx[new_dn]] = -1; ret[idx[new_dn]] = r[new_dn]; xb[idx[new_dn]] = k[new_dn]
        done |= new_up | new_dn
    rest = ~done
    ret[idx[rest]] = c[idx[rest] + H] - e[rest]; xb[idx[rest]] = idx[rest] + H
    return lab, ret, xb, valid


def pf(x):
    g = x[x > 0].sum(); b = -x[x < 0].sum()
    return g / b if b > 0 else (np.inf if g > 0 else np.nan)


def f2(x):
    return "  inf" if x == np.inf else ("  nan" if x != x else f"{x:5.2f}")


def main():
    meta = load_meta(os.path.join(DATA, "meta.txt"))
    files = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    raw = {}
    for f in files:
        b = os.path.basename(f)[:-4]
        if b in meta:
            d = load(f, meta[b]["point"])
            if len(d) >= 20000:
                raw[b] = d
    syms = sorted(raw)
    fx = [s for s in syms if s[:3] in CCY and s[3:6] in CCY]
    st = {n: {} for n in (3, 12, 48)}
    if len(fx) >= 4:
        closes = pd.concat({s: raw[s].c for s in fx}, axis=1).sort_index().ffill()
        st = strength(closes)
    say(f"Round 6a M5 model: {len(syms)} instruments, {len(fx)} forex pairs for currency strength, {time.time() - T0:.0f} s")
    for (K, H, tag) in ((1.0, 12, "A K1.0 H12"), (2.0, 36, "B K2.0 H36")):
        say(f"\n######## setting {tag}")
        Xs, info = [], {}
        for i, s in enumerate(syms):
            d = raw[s]
            F, A, hm = features(d, i, s, st)
            lab, ret, xb, valid = labels(d, A, K, H)
            ok = valid & (lab >= -1)
            if s != "BTCUSD":
                ok &= (hm >= 90) & (hm < 1350)
            F["lab"] = lab; F["ret"] = ret; F["xb"] = xb; F["risk"] = K * A
            F["sp"] = np.r_[d.s.values[1:], d.s.values[-1]]        # spread of the fill bar
            F["ok"] = ok; F["pos"] = np.arange(len(d))
            F["usd"] = meta[s]["tick_value"] / meta[s]["tick_size"] * 0.01 if meta[s]["tick_size"] > 0 else 0
            Xs.append(F)
            info[s] = dict(days=d.index.normalize().nunique())
        X = pd.concat(Xs)
        X = X[X.ok]
        X["t"] = X.index
        X = X.sort_values("t")
        fcols = [c for c in X.columns if c not in ("lab", "ret", "xb", "risk", "sp", "ok", "pos", "usd", "t")
                 and np.isfinite(X[c].values).any()]
        say(f"rows {len(X):,}, features {len(fcols)}, {time.time() - T0:.0f} s")
        t0, t1 = X.t.min(), X.t.max()
        starts = pd.date_range(t0 + pd.DateOffset(months=12), t1, freq="3MS")
        preds = []
        imp = None
        for k, a in enumerate(starts):
            b = starts[k + 1] if k + 1 < len(starts) else t1 + pd.Timedelta(days=1)
            tr = X[(X.t < a - pd.Timedelta(days=1)) & (X.t >= a - pd.DateOffset(months=TRAIN_MONTHS))].iloc[::SUB]
            te = X[(X.t >= a) & (X.t < b)]
            if len(te) == 0 or len(tr) < 30000:
                continue
            m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=1000,
                                               l2_regularization=1.0, categorical_features=[fcols.index("sym")],
                                               early_stopping=False, random_state=1)
            m.fit(tr[fcols].values, tr.lab.values)
            cl = list(m.classes_)
            p_tr = m.predict_proba(tr[fcols].values); p_te = m.predict_proba(te[fcols].values)
            sc_tr = p_tr[:, cl.index(1)] - p_tr[:, cl.index(-1)]
            sc_te = p_te[:, cl.index(1)] - p_te[:, cl.index(-1)]
            thr = {q: np.quantile(np.abs(sc_tr), 1 - q) for q in QS}
            P = te[["sym", "t", "pos", "xb", "ret", "risk", "sp", "usd", "lab"]].copy(); P["sc"] = sc_te
            for q in QS:
                P[f"q{q}"] = np.abs(sc_te) >= thr[q]
            preds.append(P)
            # direction accuracy on the clear outcomes, for information
            mask = (te.lab.values != 0)
            acc = ((np.sign(sc_te[mask]) == te.lab.values[mask])).mean() if mask.any() else np.nan
            say(f"  fold {a.date()}..{(b - pd.Timedelta(days=1)).date()}: train {len(tr):,} test {len(te):,} "
                f"dir acc {acc:.3f}, {time.time() - T0:.0f} s")
        if not preds:
            say("no folds"); continue
        P = pd.concat(preds)
        P["half"] = (P.t >= P.t.quantile(0.5)).astype(int)
        P["year"] = P.t.dt.year
        ndays = np.median([v["days"] for v in info.values()])
        oos_days = (P.t.max() - P.t.min()).days * 5 / 7
        say(f"out-of-sample {P.t.min().date()} .. {P.t.max().date()} (~{oos_days:.0f} trading days)")
        say("top q   trades  /day/all  win%    PF  half1 half2 stress  avgR   net$(0.01 lot)  syms PF>1")
        best = None
        for q in QS:
            trades = []
            for sid, g in P[P[f"q{q}"]].groupby("sym"):
                busy = -1
                for row in g.itertuples(index=False):
                    if row.pos <= busy:
                        continue
                    dr = 1 if row.sc > 0 else -1
                    trades.append((int(sid), row.t, dr, dr * row.ret, row.sp, row.risk, row.usd, row.half, row.year))
                    busy = row.xb
            T = pd.DataFrame(trades, columns=["sym", "t", "dir", "pnl", "sp", "risk", "usd", "half", "year"])
            if len(T) == 0:
                continue
            T["R"] = (T.pnl - T.sp) / T.risk; T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk; T["usdn"] = (T.pnl - T.sp) * T.usd
            per = T.groupby("sym").R.apply(lambda x: pf(x.values))
            say(f"{q:6.3f} {len(T):8d} {len(T) / oos_days:8.1f} {100 * (T.R > 0).mean():5.1f} {f2(pf(T.R.values))} "
                f"{f2(pf(T[T.half == 0].R.values))} {f2(pf(T[T.half == 1].R.values))} {f2(pf(T.Rs.values))} "
                f"{T.R.mean():+5.3f} {T.usdn.sum():12.0f}   {(per > 1).sum():2d}/{len(per)}")
            if best is None or pf(T.R.values) > best[1]:
                best = (q, pf(T.R.values), T)
        q, _, T = best
        say(f"\nbest q = {q}: per instrument (trades, PF, half PFs, net $ per 0.01 lot) and by year")
        for sid, x in T.groupby("sym"):
            s = syms[sid]
            say(f"  {s:7s} {len(x):5d} {f2(pf(x.R.values))} {f2(pf(x[x.half == 0].R.values))} {f2(pf(x[x.half == 1].R.values))} "
                f"{x.usdn.sum():8.0f}  " + " ".join(f"{y}:{f2(pf(x[x.year == y].R.values))}" for y in sorted(x.year.unique())))
        say("  all     " + " ".join(f"{y}:{f2(pf(T[T.year == y].R.values))}" for y in sorted(T.year.unique())))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
