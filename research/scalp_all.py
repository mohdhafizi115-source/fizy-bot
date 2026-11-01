"""Round 5: new scalping techniques on the broker's own M5 history, all 30 instruments (1 Nov 2026).

Data: JustMarkets demo M5 bars exported by mt5/ExportM5.mq5 (gold, BTC and 28 forex pairs). Times are server time
(Europe/Athens, GMT+2/+3). Costs: the bar's own spread (MT5 export, in points) at the fill bar, once per trade;
a stress test charges 1.5x that spread. No commission, no swap (all rules are flat by 23:00 server).
Every order is simulated bar by bar on the path O-L-H-C (up bar) or O-H-L-C (down bar); a stop gapped through fills
at the open; a stop order fills at its price or the open if it gaps.

Rules were fixed before the first run. None of them was tested in rounds 1-4.
  SQZ   TTM Squeeze (J. Carter): BB(20,2) inside Keltner(20, 1.5 ATR) for >= 6 bars, then the squeeze fires; trade
        the sign of the momentum line (20-bar linear regression of close - mean(Donchian mid, SMA 20)) if it is
        rising in that direction. Next open; SL 1.5 ATR; TP 2R; max 24 bars.
  BOX   Intraday compression breakout (the London-breakout idea at any hour): the last 12 bars' range <= 0.5x its
        5-day average. OCO stops 0.05 ATR beyond the box, SL at the other side, TP 2R, orders valid 12 bars,
        max 36 bars, one box per 12 bars, 02:00-21:00, box >= 4x the median spread.
  ORB5L / ORB5N  5-minute opening-range breakout (Zarattini & Aziz 2023) at London 10:00 / New York 16:30 server:
        trade the direction of the first 5-minute bar at the next open, SL at that bar's other end, TP 10R, exit
        at session end (London 18:30, New York 23:00). Skip dojis and stops < 3x spread.
  ORB15L / ORB15N  15-minute opening range at the same opens: OCO stops 0.05 ATR beyond the first 3 bars'
        range, valid 2 hours, SL at the other side, TP 2R, same session ends. Range >= 4x spread.
  STO   Stochastic (5,3,3) + EMA 200 pullback: close and EMA 50 on the EMA 200 side, %K crosses %D out of
        <20 (buy) / >80 (sell). Next open; SL beyond the 5-bar extreme - 0.2 ATR (at least 0.5 ATR); TP 1.5R;
        max 36 bars; 03:00-22:00.
  VWAP  VWAP trend pullback: daily VWAP (tick volume) rising over 24 bars, EMA 50 above it, previous close above
        it, the bar dips to VWAP and closes above it -> buy (sell mirrored). SL bar extreme - 0.3 ATR; TP 2R;
        max 36 bars; 10:00-22:00; at most 2 per direction per day.
  SOUP  Turtle Soup (L. Raschke): a new 20-bar low whose previous 20-bar low is >= 4 bars old, and the bar closes
        back above that previous low -> buy next open (sell mirrored). SL sweep extreme - 0.1 ATR; TP 2R;
        max 24 bars; 03:00-22:00.
  JUDAS Asia-range false break: Asia range 03:00-08:00; between 08:00 and 12:00 the first break of a side that
        closes back inside within 3 bars -> fade it at the next open, SL beyond the sweep extreme + 0.1 ATR,
        TP the other side of the Asia range (skip if < 1R); one per day; flat 21:00.
  NIGHT Night scalper (forex EA classic): 21:00-23:30 and 01:15-03:00 server, close beyond BB(20,2) with RSI(14)
        > 70 / < 30 -> fade at the next open, TP the SMA 20 at the signal, SL 2 ATR, max 12 bars, flat 23:50 /
        03:30.
  PSAR  Parabolic SAR (0.02, 0.2) flip + EMA 200 side + MACD above/below its signal. Next open; SL at the SAR
        (0.5-3 ATR); TP 1.5R; max 36 bars; 03:00-22:00.
Check of the live setups on the same broker data:
  LIVE_RSI2  H1 RSI(2) < 10 / > 90 with the SMA 200, SL 2 ATR(H1), exit at the next open after a close beyond
        the SMA 5, entry skipped if the spread > 0.3 ATR (swap ignored).
  LIVE_NR7   D1 NR7: OCO stops at yesterday's high/low, SL at the other side, exit at the next day's open.
Pass rule for one instrument and rule (fixed in advance): >= 150 trades, PF(R) >= 1.15, both halves PF >= 1.05,
stress PF >= 1.05, last 12 months positive.
  RAND  chance baseline: random entries (about 3 a day), random direction, SL 1.5 ATR, TP 1.5R, max 24 bars.
"""
import os, sys, glob, time
import numpy as np, pandas as pd

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def say(s=""):
    print(s, flush=True)


# ---------------------------------------------------------------- data
def load_meta(path):
    meta = {}
    for ln in open(path, encoding="latin-1"):
        p = ln.strip().split(",")
        if len(p) >= 12 and p[0] != "base":
            try:
                meta[p[0]] = dict(sym=p[1], digits=int(p[2]), point=float(p[3]), tick_size=float(p[4]),
                                  tick_value=float(p[5]), bars=int(p[8]), first=p[9], last=p[10], med_sp=int(p[11]))
            except ValueError:
                pass
    return meta


def load(path, point):
    df = pd.read_csv(path)
    df = df.drop_duplicates("t").sort_values("t")
    d = pd.DataFrame({"o": df.o.values, "h": df.h.values, "l": df.l.values, "c": df.c.values,
                      "v": df.v.values.astype(float), "s": df.s.values.astype(float) * point},
                     index=pd.to_datetime(df.t.values, unit="s"))
    med = np.median(d.s.values[d.s.values > 0]) if (d.s.values > 0).any() else point
    d.loc[d.s <= 0, "s"] = med
    return d


def prep(d):
    o, h, l, c = d.o, d.h, d.l, d.c
    c1 = c.shift()
    tr = np.maximum(h - l, np.maximum((h - c1).abs(), (l - c1).abs()))
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    for n in (20, 50, 200):
        d[f"e{n}"] = c.ewm(span=n, adjust=False).mean()
    d["sma20"] = c.rolling(20).mean()
    d["sd20"] = c.rolling(20).std(ddof=0)
    d["hm"] = d.index.hour * 60 + d.index.minute
    d["date"] = d.index.normalize()
    return d


def daily(d):
    g = d.groupby("date")
    D = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "s": g.s.median()})
    c1 = D.c.shift()
    D["tr"] = np.maximum(D.h - D.l, np.maximum((D.h - c1).abs(), (D.l - c1).abs()))
    D["atr"] = D.tr.rolling(14).mean()
    return D


def hourly(d):
    r = d.resample("1h")
    H = pd.DataFrame({"o": r.o.first(), "h": r.h.max(), "l": r.l.min(), "c": r.c.last(), "s": r.s.median()}).dropna()
    return H


# ---------------------------------------------------------------- simulator
def sim(o, h, l, c, sp, sigs, flat):
    """sigs: list of dicts with k0 (first bar the order is live), kind mkt/stop/oco, dir, P (stop price),
    P2/sl2 (sell leg of an oco), sl, tp or tp_r, exp (last bar the order is live), maxb, xl/xs exit flags,
    end (bar index at which to flatten at the open). Returns a list of trades."""
    n = len(o)
    out = []
    busy = -1
    for g in sigs:
        k0 = g["k0"]
        if k0 <= busy or k0 >= n:
            continue
        kind = g["kind"]
        end = min(g.get("end", n), n)
        exp = min(g.get("exp", k0), n - 1)
        pos = None
        k = k0
        # ---- pending / fill
        while k <= exp and k < end:
            if flat[k]:
                break
            a = o[k]
            path = (o[k], l[k], h[k], c[k]) if c[k] >= o[k] else (o[k], h[k], l[k], c[k])
            fill = None
            if kind == "mkt":
                fill, dr, sl, seg = a, g["dir"], g["sl"], 0
            else:
                for si in range(3):
                    x, y = path[si], path[si + 1]
                    # buy leg
                    if (kind == "oco" or g["dir"] == 1):
                        P = g["P"]
                        if si == 0 and x >= P:
                            fill, dr, sl, seg = x, 1, g["sl"], si; break
                        if y >= P > x:
                            fill, dr, sl, seg = P, 1, g["sl"], si; break
                    if (kind == "oco" or g["dir"] == -1):
                        P = g["P2"] if kind == "oco" else g["P"]
                        sl_ = g["sl2"] if kind == "oco" else g["sl"]
                        if si == 0 and x <= P:
                            fill, dr, sl, seg = x, -1, sl_, si; break
                        if y <= P < x:
                            fill, dr, sl, seg = P, -1, sl_, si; break
            if fill is not None:
                risk = (fill - sl) * dr
                if risk <= 0:
                    fill = None
                    break
                tp = g.get("tp")
                if g.get("tp_r"):
                    tp = fill + dr * g["tp_r"] * risk
                if tp is not None and (tp - fill) * dr <= 0:
                    fill = None
                    break
                pos = dict(k=k, dir=dr, e=fill, sl=sl, tp=tp, risk=risk, sp=sp[k], seg=seg)
                break
            k += 1
        if pos is None:
            busy = max(busy, min(k, exp))
            continue
        # ---- position
        dr, sl, tp, e = pos["dir"], pos["sl"], pos["tp"], pos["e"]
        xl, xs = g.get("xl"), g.get("xs")
        maxb = g.get("maxb", 10 ** 9)
        k = pos["k"]
        first = True
        ex = None
        why = ""
        while k < n:
            if not first:
                if k - pos["k"] >= maxb or flat[k] or k >= end:
                    ex, why = o[k], "time"; break
                if (dr == 1 and xl is not None and xl[k - 1]) or (dr == -1 and xs is not None and xs[k - 1]):
                    ex, why = o[k], "exit"; break
                if (o[k] - sl) * dr <= 0:
                    ex, why = o[k], "SL"; break
                if tp is not None and (o[k] - tp) * dr >= 0:
                    ex, why = o[k], "TP"; break
            path = (o[k], l[k], h[k], c[k]) if c[k] >= o[k] else (o[k], h[k], l[k], c[k])
            s0 = pos["seg"] if first else 0
            for si in range(s0, 3):
                x, y = path[si], path[si + 1]
                if first and si == s0:
                    x = e
                if dr == 1:
                    if y < x and y <= sl:
                        ex, why = sl, "SL"; break
                    if y > x and tp is not None and y >= tp:
                        ex, why = tp, "TP"; break
                else:
                    if y > x and y >= sl:
                        ex, why = sl, "SL"; break
                    if y < x and tp is not None and y <= tp:
                        ex, why = tp, "TP"; break
            if ex is not None:
                break
            first = False
            k += 1
        if ex is None:
            ex, why, k = c[n - 1], "end", n - 1
        out.append((pos["k"], dr, (ex - e) * dr, pos["sp"], pos["risk"], why))
        busy = k
    return out


# ---------------------------------------------------------------- rules (M5)
def linreg_end(y, n):
    x = np.arange(n, dtype=float); xb = x.mean(); sxx = ((x - xb) ** 2).sum()
    w = 1.0 / n + (x - xb) * (n - 1 - xb) / sxx
    out = np.full(len(y), np.nan)
    v = np.convolve(np.nan_to_num(y), w[::-1], mode="valid")
    out[n - 1:] = v
    return out


def rules_m5(d, med_sp):
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    A = d.atr.values; hm = d.hm.values; n = len(d)
    dates = d.date.values
    e20, e50, e200, sma, sd = d.e20.values, d.e50.values, d.e200.values, d.sma20.values, d.sd20.values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    flat23 = (hm >= 23 * 60) | newday
    R = {}
    win = lambda a, b: (hm >= a * 60) & (hm < b * 60)
    W322 = win(3, 22)

    def mk(i, dr, sl, tp_r, maxb, **kw):
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, tp_r=tp_r, exp=i + 1, maxb=maxb)
        g.update(kw); return g

    # SQZ
    bbu, bbl = sma + 2 * sd, sma - 2 * sd
    a20 = pd.Series(np.maximum(h - l, 0)).rolling(20).mean().values  # simple ATR(20) proxy for the Keltner width
    kcu, kcl = sma + 1.5 * a20, sma - 1.5 * a20
    on = (bbu < kcu) & (bbl > kcl)
    run = np.zeros(n, int)
    for i in range(1, n):
        run[i] = run[i - 1] + 1 if on[i] else 0
    hh = pd.Series(h).rolling(20).max().values; ll = pd.Series(l).rolling(20).min().values
    mom = linreg_end(c - ((hh + ll) / 2 + sma) / 2, 20)
    sig = []
    for i in np.where((~on) & np.r_[False, run[:-1] >= 6] & win(2, 22))[0]:
        if i < 250 or i >= n - 1 or np.isnan(mom[i]):
            continue
        dr = 1 if (mom[i] > 0 and mom[i] > mom[i - 1]) else (-1 if (mom[i] < 0 and mom[i] < mom[i - 1]) else 0)
        if dr:
            sig.append(mk(i, dr, c[i] - dr * 1.5 * A[i], 2.0, 24))
    R["SQZ"] = (sig, flat23)

    # BOX
    hh12 = pd.Series(h).rolling(12).max().values; ll12 = pd.Series(l).rolling(12).min().values
    r12 = hh12 - ll12
    avg = pd.Series(r12).rolling(1440, min_periods=500).mean().shift(12).values
    sig = []; last = -100
    cand = np.where((r12 <= 0.5 * avg) & win(2, 21))[0]
    for i in cand:
        if i < 250 or i - last < 12 or r12[i] < 4 * med_sp:
            continue
        last = i
        b = 0.05 * A[i]
        sig.append(dict(k0=i + 1, kind="oco", dir=0, P=hh12[i] + b, sl=ll12[i], P2=ll12[i] - b, sl2=hh12[i],
                        tp_r=2.0, exp=i + 12, maxb=36))
    R["BOX"] = (sig, flat23)

    # ORB5 / ORB15
    for tag, t0, tend in (("L", 600, 1110), ("N", 990, 1380)):
        flat_s = (hm >= tend) | newday
        s5, s15 = [], []
        for i in np.where(hm == t0)[0]:
            if i < 250 or i + 3 >= n or dates[i + 3] != dates[i]:
                continue
            rg = h[i] - l[i]
            if rg > 0 and abs(c[i] - o[i]) >= 0.1 * rg:
                dr = 1 if c[i] > o[i] else -1
                sl = l[i] if dr == 1 else h[i]
                if abs(c[i] - sl) >= 3 * med_sp:
                    s5.append(mk(i, dr, sl, 10.0, 10 ** 6))
            j = i + 2
            if hm[j] != t0 + 10:
                continue
            H3, L3 = h[i:j + 1].max(), l[i:j + 1].min()
            if H3 - L3 < 4 * med_sp:
                continue
            b = 0.05 * A[j]
            s15.append(dict(k0=j + 1, kind="oco", dir=0, P=H3 + b, sl=L3, P2=L3 - b, sl2=H3, tp_r=2.0, exp=j + 24, maxb=10 ** 6))
        R["ORB5" + tag] = (s5, flat_s)
        R["ORB15" + tag] = (s15, flat_s)

    # STO
    ll5 = pd.Series(l).rolling(5).min().values; hh5 = pd.Series(h).rolling(5).max().values
    raw = 100 * (c - ll5) / np.where(hh5 - ll5 > 0, hh5 - ll5, np.nan)
    K = pd.Series(raw).rolling(3).mean().values; Dd = pd.Series(K).rolling(3).mean().values
    sig = []
    upx = (K > Dd) & np.r_[False, (K[:-1] <= Dd[:-1]) & (K[:-1] < 20) & (Dd[:-1] < 20)]
    dnx = (K < Dd) & np.r_[False, (K[:-1] >= Dd[:-1]) & (K[:-1] > 80) & (Dd[:-1] > 80)]
    for i in np.where((upx & (c > e200) & (e50 > e200)) | (dnx & (c < e200) & (e50 < e200)))[0]:
        if i < 250 or i >= n - 1 or not W322[i]:
            continue
        dr = 1 if upx[i] else -1
        sl = (ll5[i] - 0.2 * A[i]) if dr == 1 else (hh5[i] + 0.2 * A[i])
        if abs(c[i] - sl) < 0.5 * A[i]:
            sl = c[i] - dr * 0.5 * A[i]
        sig.append(mk(i, dr, sl, 1.5, 36))
    R["STO"] = (sig, flat23)

    # VWAP
    tp_ = (h + l + c) / 3; v = d.v.values.copy(); v[v <= 0] = 1
    grp = np.cumsum(newday)
    cv = pd.Series(tp_ * v).groupby(grp).cumsum().values; cvol = pd.Series(v).groupby(grp).cumsum().values
    vw = cv / cvol
    sig = []; cnt = {}
    vw24 = np.r_[np.full(24, np.nan), vw[:-24]]; g24 = np.r_[np.full(24, -1), grp[:-24]]
    vw1 = np.r_[np.nan, vw[:-1]]; c1 = np.r_[np.nan, c[:-1]]
    vb = (vw > vw24) & (e50 > vw) & (c1 > vw1) & (l <= vw) & (vw < c)
    vs = (vw < vw24) & (e50 < vw) & (c1 < vw1) & (h >= vw) & (vw > c)
    for i in np.where((vb | vs) & (hm >= 600) & (hm < 1320) & (g24 == grp))[0]:
        if i < 250 or i >= n - 1:
            continue
        dr = 1 if vb[i] else -1
        key = (grp[i], dr)
        if cnt.get(key, 0) >= 2:
            continue
        cnt[key] = cnt.get(key, 0) + 1
        sl = (l[i] - 0.3 * A[i]) if dr == 1 else (h[i] + 0.3 * A[i])
        sig.append(mk(i, dr, sl, 2.0, 36))
    R["VWAP"] = (sig, flat23)

    # SOUP
    pl = pd.Series(l).shift(1).rolling(20).min().values; ph = pd.Series(h).shift(1).rolling(20).max().values
    from numpy.lib.stride_tricks import sliding_window_view as swv
    agel = np.full(n, -1.0); ageh = np.full(n, -1.0)
    agel[20:] = 19 - swv(l[:-1], 20).argmin(axis=1)[:n - 20]
    ageh[20:] = 19 - swv(h[:-1], 20).argmax(axis=1)[:n - 20]
    sig = []
    bl = (l < pl) & (c > pl) & (agel >= 3)
    bs = (h > ph) & (c < ph) & (ageh >= 3)
    for i in np.where((bl | bs) & W322)[0]:
        if i < 250 or i >= n - 1:
            continue
        dr = 1 if bl[i] else -1
        sl = (l[i] - 0.1 * A[i]) if dr == 1 else (h[i] + 0.1 * A[i])
        sig.append(mk(i, dr, sl, 2.0, 24))
    R["SOUP"] = (sig, flat23)

    # JUDAS
    sig = []
    flat21 = (hm >= 21 * 60) | newday
    day_idx = pd.Series(np.arange(n)).groupby(grp)
    for _, idx in day_idx:
        idx = idx.values
        hmd = hm[idx]
        asia = idx[(hmd >= 180) & (hmd < 480)]
        lon = idx[(hmd >= 480) & (hmd < 720)]
        if len(asia) < 40 or len(lon) < 10 or asia[0] < 250:
            continue
        AH, AL = h[asia].max(), l[asia].min()
        done = False
        for p, i in enumerate(lon):
            if done:
                break
            for dr, brk in ((-1, h[i] > AH), (1, l[i] < AL)):
                if not brk:
                    continue
                ext = h[i] if dr == -1 else l[i]
                for j in lon[p:p + 4]:
                    ext = max(ext, h[j]) if dr == -1 else min(ext, l[j])
                    inside = c[j] < AH if dr == -1 else c[j] > AL
                    if inside and j + 1 < n:
                        sl = ext + 0.1 * A[j] if dr == -1 else ext - 0.1 * A[j]
                        tp = AL if dr == -1 else AH
                        if abs(tp - c[j]) >= abs(c[j] - sl):
                            sig.append(dict(k0=j + 1, kind="mkt", dir=dr, sl=sl, tp=tp, exp=j + 1, maxb=10 ** 6))
                        break
                done = True
                break
    R["JUDAS"] = (sig, flat21)

    # NIGHT
    dl = np.diff(c, prepend=c[0])
    up = pd.Series(np.clip(dl, 0, None)).ewm(alpha=1 / 14, adjust=False).mean().values
    dn = pd.Series(np.clip(-dl, 0, None)).ewm(alpha=1 / 14, adjust=False).mean().values
    rsi = 100 - 100 / (1 + up / np.where(dn > 0, dn, np.nan))
    wA = (hm >= 1260) & (hm < 1410); wB = (hm >= 75) & (hm < 180)
    flatN = ((hm >= 1430) | ((hm >= 210) & (hm < 1260))) | newday
    sig = []
    for i in np.where((wA | wB) & (((c > bbu) & (rsi > 70)) | ((c < bbl) & (rsi < 30))))[0]:
        if i < 250 or i >= n - 1:
            continue
        dr = -1 if c[i] > bbu[i] else 1
        sig.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c[i] - dr * 2 * A[i], tp=sma[i], exp=i + 1, maxb=12))
    R["NIGHT"] = (sig, flatN)

    # PSAR
    ps = np.zeros(n); up_ = True; af = 0.02; ep = h[0]; ps[0] = l[0]
    for i in range(1, n):
        p = ps[i - 1] + af * (ep - ps[i - 1])
        if up_:
            p = min(p, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < p:
                up_, p, ep, af = False, ep, l[i], 0.02
            elif h[i] > ep:
                ep, af = h[i], min(af + 0.02, 0.2)
        else:
            p = max(p, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > p:
                up_, p, ep, af = True, ep, h[i], 0.02
            elif l[i] < ep:
                ep, af = l[i], min(af + 0.02, 0.2)
        ps[i] = p
    below = ps < c
    macd = pd.Series(c).ewm(span=12, adjust=False).mean().values - pd.Series(c).ewm(span=26, adjust=False).mean().values
    msig = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    sig = []
    fl_up = below & np.r_[False, ~below[:-1]]; fl_dn = (~below) & np.r_[False, below[:-1]]
    for i in np.where(((fl_up & (c > e200) & (macd > msig)) | (fl_dn & (c < e200) & (macd < msig))) & W322)[0]:
        if i < 250 or i >= n - 1:
            continue
        dr = 1 if fl_up[i] else -1
        dist = abs(c[i] - ps[i])
        dist = min(max(dist, 0.5 * A[i]), 3 * A[i])
        sig.append(mk(i, dr, c[i] - dr * dist, 1.5, 36))
    R["PSAR"] = (sig, flat23)

    # RAND: chance baseline (no edge by construction): random bars 03:00-22:00 (about 3 a day), random direction,
    # SL 1.5 ATR, TP 1.5R, max 24 bars. Its pass count shows how many passes luck alone gives.
    rng = np.random.default_rng(12345)
    sig = []
    for i in np.where(W322 & (rng.random(n) < 3 / 228))[0]:
        if i < 250 or i >= n - 1:
            continue
        dr = 1 if rng.random() < 0.5 else -1
        sig.append(mk(i, dr, c[i] - dr * 1.5 * A[i], 1.5, 24))
    R["RAND"] = (sig, flat23)
    return R


def live_rsi2(H):
    o, h, l, c, s = (H[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(H)
    cs = pd.Series(c)
    s200 = cs.rolling(200).mean().values; s5 = cs.rolling(5).mean().values
    c1 = cs.shift()
    tr = np.maximum(H.h - H.l, np.maximum((H.h - c1.values).abs(), (H.l - c1.values).abs())).values
    A = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    dl = np.diff(c, prepend=c[0])
    up = pd.Series(np.clip(dl, 0, None)).ewm(alpha=0.5, adjust=False).mean().values
    dn = pd.Series(np.clip(-dl, 0, None)).ewm(alpha=0.5, adjust=False).mean().values
    rsi = 100 - 100 / (1 + up / np.where(dn > 0, dn, np.nan))
    sig = []
    for i in range(210, n - 1):
        if s[i] > 0.3 * A[i]:
            continue
        dr = 1 if (c[i] > s200[i] and rsi[i] < 10) else (-1 if (c[i] < s200[i] and rsi[i] > 90) else 0)
        if dr:
            sig.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c[i] - dr * 2 * A[i], tp=None, exp=i + 1, maxb=10 ** 6,
                            xl=c > s5, xs=c < s5))
    return sig, np.zeros(n, bool)


def live_nr7(D):
    o, h, l, c = (D[x].values for x in ("o", "h", "l", "c"))
    rg = h - l; n = len(D)
    sig = []
    for i in range(7, n - 1):
        if rg[i] > 0 and rg[i] <= rg[i - 6:i].min():
            sig.append(dict(k0=i + 1, kind="oco", dir=0, P=h[i], sl=l[i], P2=l[i], sl2=h[i], tp=None, exp=i + 1, maxb=1))
    return sig, np.zeros(n, bool)


# ---------------------------------------------------------------- stats
def pf(x):
    g = x[x > 0].sum(); b = -x[x < 0].sum()
    return g / b if b > 0 else (np.inf if g > 0 else np.nan)


def f2(x):
    return "  inf" if x == np.inf else ("  nan" if x != x else f"{x:5.2f}")


def main():
    meta = load_meta(os.path.join(DATA, "meta.txt"))
    files = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    say(f"Round 5 scalping research on broker M5 data: {len(files)} instruments")
    rows = []          # all trades
    info = {}
    for f in files:
        base = os.path.basename(f)[:-4]
        m = meta.get(base)
        if not m:
            continue
        d = load(f, m["point"])
        if len(d) < 20000:
            say(f"{base}: only {len(d)} bars, skipped"); continue
        d = prep(d)
        med_sp = float(np.median(d.s.values))
        usd = m["tick_value"] / m["tick_size"] * 0.01 if m["tick_size"] > 0 else 0.0   # $ per 1.0 price move, 0.01 lot
        days = d.date.nunique()
        info[base] = dict(bars=len(d), days=days, first=str(d.index[0])[:10], last=str(d.index[-1])[:10], med_sp=med_sp,
                          usd=usd, mid=d.index[len(d) // 2], end=d.index[-1])
        o, h, l, c, sp = (d[x].values for x in ("o", "h", "l", "c", "s"))
        R = rules_m5(d, med_sp)
        for rule, (sig, flat) in R.items():
            for (k, dr, pnl, s_, risk, why) in sim(o, h, l, c, sp, sig, flat):
                rows.append((base, rule, d.index[k], dr, pnl, s_, risk, why))
        H = hourly(d)
        sig, flat = live_rsi2(H)
        for (k, dr, pnl, s_, risk, why) in sim(*(H[x].values for x in ("o", "h", "l", "c", "s")), sig, flat):
            rows.append((base, "LIVE_RSI2", H.index[k], dr, pnl, s_, risk, why))
        D = daily(d)
        sig, flat = live_nr7(D)
        for (k, dr, pnl, s_, risk, why) in sim(*(D[x].values for x in ("o", "h", "l", "c", "s")), sig, flat):
            rows.append((base, "LIVE_NR7", D.index[k], dr, pnl, s_, risk, why))
        say(f"  {base:7s} {m['sym']:9s} {len(d):7d} bars {info[base]['first']} .. {info[base]['last']}, median spread "
            f"{med_sp:.5g}, {time.time() - T0:5.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "rule", "t", "dir", "pnl", "sp", "risk", "why"])
    T["net"] = T.pnl - T.sp
    T["R"] = T.net / T.risk
    T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = T.net * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [1 if t >= info[s]["mid"] else 0 for s, t in zip(T.sym, T.t)]
    T["last12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    T["year"] = T.t.dt.year
    ndays = np.median([v["days"] for v in info.values()])
    say(f"\nmedian trading days per instrument: {ndays:.0f}; cost = bar spread at the fill; R = net / initial risk")
    say("\n== All instruments together (R units; $ = per 0.01 lot at today's tick values) ==")
    say("rule        trades  /day  win%   PF  half1 half2 stress last12R  avgR   net$     syms PF>1  pass")
    passes = []
    for rule, g in T.groupby("rule", sort=False):
        per = []
        for s, x in g.groupby("sym"):
            P, P1, P2, PS = pf(x.R.values), pf(x[x.half == 0].R.values), pf(x[x.half == 1].R.values), pf(x.Rs.values)
            l12 = x[x.last12].R.sum()
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
            per.append((s, len(x), P, P1, P2, PS, l12, x.R.sum(), x.usd.sum(), len(x) / info[s]["days"], ok))
            if ok:
                passes.append((rule, s, len(x), P, P1, P2, PS, l12, x.usd.sum(), len(x) / info[s]["days"]))
        npos = sum(1 for p in per if p[2] > 1)
        say(f"{rule:10s} {len(g):7d} {len(g) / ndays:5.1f} {100 * (g.R > 0).mean():5.1f} {f2(pf(g.R.values))} "
            f"{f2(pf(g[g.half == 0].R.values))} {f2(pf(g[g.half == 1].R.values))} {f2(pf(g.Rs.values))} "
            f"{g[g.last12].R.sum():7.0f} {g.R.mean():+5.3f} {g.usd.sum():8.0f}  {npos:3d}/{len(per):2d}  "
            f"{sum(p[-1] for p in per):3d}")
    say("\n== Per instrument: PF(R) by rule (trades in brackets for the totals row) ==")
    rules = list(dict.fromkeys(T.rule))
    say("sym     " + " ".join(f"{r[:7]:>7s}" for r in rules))
    for s in sorted(info):
        line = f"{s:7s} "
        for r in rules:
            x = T[(T.sym == s) & (T.rule == r)]
            line += f"{f2(pf(x.R.values)) if len(x) >= 20 else '    -':>7s} " if True else ""
        say(line)
    say("\n== Instrument + rule pairs that pass (>=150 trades, PF>=1.15, halves>=1.05, stress>=1.05, last 12m > 0) ==")
    say(f"{len(passes)} of {len(rules) * len(info)} pairs pass")
    say("rule       sym      trades  /day    PF  half1 half2 stress last12R    net$")
    for p in sorted(passes, key=lambda p: -p[3]):
        say(f"{p[0]:10s} {p[1]:7s} {p[2]:7d} {p[9]:5.2f} {f2(p[3])} {f2(p[4])} {f2(p[5])} {f2(p[6])} {p[7]:7.1f} {p[8]:8.0f}")
    say("\n== By year, PF(R), all instruments ==")
    yrs = sorted(T.year.unique())
    say("rule       " + " ".join(f"{y:>6d}" for y in yrs))
    for rule, g in T.groupby("rule", sort=False):
        say(f"{rule:10s} " + " ".join(f"{f2(pf(g[g.year == y].R.values)):>6s}" for y in yrs))
    say("\n== Gold and BTC detail (per 0.01 lot) ==")
    for s in ("XAUUSD", "BTCUSD"):
        if s not in info:
            continue
        say(f"{s}: {info[s]['first']} .. {info[s]['last']}, median spread {info[s]['med_sp']:.3g}")
        for rule, x in T[T.sym == s].groupby("rule", sort=False):
            yr = " ".join(f"{y}:{f2(pf(x[x.year == y].R.values))}" for y in sorted(x.year.unique()))
            mo = x.groupby(x.t.dt.to_period("M")).usd.sum()
            say(f"  {rule:10s} {len(x):5d} tr {len(x) / info[s]['days']:4.1f}/day PF {f2(pf(x.R.values))} net ${x.usd.sum():7.0f} "
                f"months+ {int((mo > 0).sum())}/{len(mo)} | {yr}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
