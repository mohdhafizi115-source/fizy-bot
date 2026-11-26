# Round 171: the round 170b gold M15 rule (trendline break + break of the nearest unbroken S/R) on ALL 30 symbols
# (owner: "kecik nya untung, kalau apply dekat semua forex sekali ok?").
# Data: the broker's M5 export (m5data, bid OHLC + spread per bar). M15 bars are built from M5; exits are walked on
# M5 bars (SL first when SL and TP fall in the same bar; sells use ask = bid + that bar's spread).
# Rule (buy shown, sell mirrored): online fractal swings n (a swing at bar i is known after bar i+n closes);
# falling line through the 2 latest swing highs; an M15 close above it (previous close not) = TL break;
# resistance = the nearest unbroken swing high above that close (last 50 swings); wait up to W = 120 M15 bars for a
# close above it, cancelled by a close back below the line; enter at the next M15 open at the ask.
# SL 1.5 ATR(14, M15) or beyond the 10-bar extreme, TP 2R / 3R, out after 16 M15 bars (4 h), one position per
# symbol, no entries 23:45-01:30 server. 0.01 lot; $ from the export's tick value, scaled so XAUUSD = $1 per $1
# move at 0.01 lot (handles a cent account's US-cent tick values). Random-direction twin at the same fills.
# Last 3 months / the 3 months before (by the data's end).
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import scalp_all as SA
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
print("symbols in meta:", len(meta), sorted(meta)[:40], flush=True)

def usd_unit(mt): return mt["tick_value"] / mt["tick_size"] * 0.01   # account money per 1.0 price move at 0.01 lot
scale = 1.0
if "XAUUSD" in meta:
    g = usd_unit(meta["XAUUSD"]); scale = 1.0 / g if g > 0 else 1.0
print(f"money scale (XAUUSD normalised to $1 per $1 at 0.01 lot): {scale:.4f}", flush=True)

def m15(d):
    k = d.index.asi8 // (900 * 10**9)
    g = d.groupby(k)
    b = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "s": g.s.first()})
    b.index = pd.to_datetime(b.index.values * 900, unit="s").as_unit("ns")
    return b

def signals(B, n, W):
    h, l, c, atr = B["h"], B["l"], B["c"], B["atr"]; mins = B["mins"]; N = len(c)
    sh, sl, out, pend = [], [], [], []
    uh = ul = -1
    def line(i1, i2, v, x): return v[i2] + (v[i2] - v[i1]) / (i2 - i1) * (x - i2)
    def unb(v, k, j, up):
        seg = v[k + 1:j + 1]
        return seg.size == 0 or ((seg.max() < v[k]) if up else (seg.min() > v[k]))
    for j in range(2 * n + 1, N):
        i = j - n
        if h[i] == h[i - n:i + n + 1].max() and h[i] > h[i - n:i].max(): sh.append(i)
        if l[i] == l[i - n:i + n + 1].min() and l[i] < l[i - n:i].min(): sl.append(i)
        ok = 90 <= mins[j] < 1425
        if len(sh) >= 2:
            i1, i2 = sh[-2], sh[-1]
            if h[i2] < h[i1] and uh != i2 and j - 1 > i2 and c[j] > line(i1, i2, h, j) and c[j - 1] <= line(i1, i2, h, j - 1):
                uh = i2
                cand = [h[k] for k in sh[-50:] if h[k] > c[j] and unb(h, k, j, True)]
                if not cand:
                    if ok: out.append((j, 1))
                else: pend.append((j, 1, i1, i2, min(cand)))
        if len(sl) >= 2:
            i1, i2 = sl[-2], sl[-1]
            if l[i2] > l[i1] and ul != i2 and j - 1 > i2 and c[j] < line(i1, i2, l, j) and c[j - 1] >= line(i1, i2, l, j - 1):
                ul = i2
                cand = [l[k] for k in sl[-50:] if l[k] < c[j] and unb(l, k, j, False)]
                if not cand:
                    if ok: out.append((j, -1))
                else: pend.append((j, -1, i1, i2, max(cand)))
        if pend:
            keep = []
            for p in pend:
                jb, d, i1, i2, lev = p
                if j <= jb: keep.append(p); continue
                if j - jb > W: continue
                L0 = line(i1, i2, h if d == 1 else l, j)
                if (d == 1 and c[j] < L0) or (d == -1 and c[j] > L0): continue
                if (d == 1 and c[j] > lev) or (d == -1 and c[j] < lev):
                    if ok: out.append((j, d))
                    continue
                keep.append(p)
            pend = keep
    return out

def run(B, M, sig, slm, tpR, unit, rnd=None):
    h, l, c, atr, bt = B["h"], B["l"], B["c"], B["atr"], B["t"]
    mt, mo, mh, ml, mc, ms = M
    rng = np.random.default_rng(rnd) if rnd is not None else None
    res = []; busy = -1; NB = len(c)
    for (j, d) in sig:
        if j + 1 >= NB: continue
        t0 = bt[j + 1]
        m0 = np.searchsorted(mt, t0)
        if m0 >= len(mt) or m0 <= busy: continue
        if rng is not None: d = 1 if rng.random() < 0.5 else -1
        if slm == "atr": dist = 1.5 * atr[j]
        else:
            dist = (c[j] - l[max(0, j - 9):j + 1].min() + 0.1 * atr[j]) if d == 1 else (h[max(0, j - 9):j + 1].max() - c[j] + 0.1 * atr[j])
            dist = max(dist, 0.5 * atr[j])
        if not dist > 0: continue
        m1 = np.searchsorted(mt, t0 + 16 * 900 * 10**9)
        m1 = max(min(m1, len(mt)), m0 + 1)
        if d == 1:
            e = mo[m0] + ms[m0]; slp, tpp = e - dist, e + tpR * dist
            lo, hi = ml[m0:m1], mh[m0:m1]
            a = np.flatnonzero(lo <= slp); b = np.flatnonzero(hi >= tpp)
        else:
            e = mo[m0]; slp, tpp = e + dist, e - tpR * dist
            lo, hi = ml[m0:m1] + ms[m0:m1], mh[m0:m1] + ms[m0:m1]
            a = np.flatnonzero(hi >= slp); b = np.flatnonzero(lo <= tpp)
        ka = a[0] if len(a) else 10**9; kb = b[0] if len(b) else 10**9
        if ka <= kb and ka < 10**9: x, k = slp, ka
        elif kb < 10**9: x, k = tpp, kb
        else:
            k = m1 - 1 - m0; x = mc[m1 - 1] if d == 1 else mc[m1 - 1] + ms[m1 - 1]
        res.append((t0, d * (x - e) * unit))
        busy = m0 + k
    return res

rows = []
for sym in sorted(meta):
    path = os.path.join(DATA, sym + ".csv")
    if not os.path.exists(path): continue
    mtd = meta[sym]
    d = SA.load(path, mtd["point"]); d.index = pd.DatetimeIndex(d.index).as_unit("ns")
    d = d[d.index >= "2026-04-01"]
    if len(d) < 5000: print(sym, "too few bars", len(d)); continue
    unit = usd_unit(mtd) * scale
    M = (d.index.values.astype("int64"), d.o.values, d.h.values, d.l.values, d.c.values, d.s.values)
    b = m15(d)
    pc = np.r_[b.c.values[0], b.c.values[:-1]]
    tr = np.maximum(b.h.values - b.l.values, np.maximum(abs(b.h.values - pc), abs(b.l.values - pc)))
    B = dict(h=b.h.values, l=b.l.values, c=b.c.values, atr=pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values,
             t=b.index.values.astype("int64"), mins=(b.index.hour * 60 + b.index.minute).values)
    end = d.index[-1]; a3 = (end - pd.Timedelta(days=91)).value; a6 = (end - pd.Timedelta(days=182)).value
    for n in (7, 8, 10, 12):
        sig = signals(B, n, 120)
        for slm in ("atr", "swing"):
            for tpR in (2, 3):
                r = run(B, M, sig, slm, tpR, unit)
                rr = run(B, M, sig, slm, tpR, unit, rnd=1)
                for (t, p) in r: rows.append(dict(sym=sym, n=n, sl=slm, tp=tpR, t=t, p=p, rnd=0, w=2 if t >= a3 else (1 if t >= a6 else 0)))
                for (t, p) in rr: rows.append(dict(sym=sym, n=n, sl=slm, tp=tpR, t=t, p=p, rnd=1, w=2 if t >= a3 else (1 if t >= a6 else 0)))
    print(sym, "done, med spread", round(float(np.median(d.s.values)), 6), "unit $", round(unit, 4), flush=True)

D = pd.DataFrame(rows); D = D[D.w > 0]
D["day"] = pd.to_datetime(D.t, unit="ns").dt.normalize()
def st(q):
    if len(q) == 0: return "   0 trades"
    p = q.sort_values("t").p.values; eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    wd = q.groupby("day").p.sum().min()
    return f"{len(p):4d} trades win {100*(p>0).mean():3.0f}% net ${p.sum():+7.0f} DD ${min(dd,0):+6.0f} worst day ${wd:+5.0f}"
print("\nPOOLED, all symbols except XAUUSD / BTCUSD (forex only) and with them, last 3 months | previous 3 months | random twin last / prev net")
for (n, slm, tp), q in D.groupby(["n", "sl", "tp"]):
    for lab, f in (("FOREX", ~q.sym.isin(["XAUUSD", "BTCUSD"])), ("ALL", q.sym == q.sym), ("GOLD", q.sym == "XAUUSD")):
        x = q[f & (q.rnd == 0)]; z = q[f & (q.rnd == 1)]
        print(f"n {n:2d} SL {slm:5s} TP {tp}R {lab:5s} | {st(x[x.w==2])} | {st(x[x.w==1])} | rand ${z[z.w==2].p.sum():+6.0f} / ${z[z.w==1].p.sum():+6.0f}")
print("\nPER SYMBOL, n 10 SL atr TP 3R: last 3 months net / previous net (trades)")
q = D[(D.n == 10) & (D.sl == "atr") & (D.tp == 3) & (D.rnd == 0)]
for s, g in q.groupby("sym"):
    print(f"  {s:8s} ${g[g.w==2].p.sum():+6.0f} ({(g.w==2).sum():3d}) / ${g[g.w==1].p.sum():+6.0f} ({(g.w==1).sum():3d})")
pos = q.groupby("sym").apply(lambda g: (g[g.w==2].p.sum() > 0) and (g[g.w==1].p.sum() > 0))
print("symbols positive in both windows:", int(pos.sum()), "of", len(pos))
