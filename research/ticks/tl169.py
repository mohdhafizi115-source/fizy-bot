# Round 169: TRENDLINE techniques on gold, real ticks (owner: "carikan aku teknik trendline bro dan aku nak tahu result").
# Bars M5 / M15 / H1 built from the owner's XAUUSD.m ticks (bid OHLC, ask OHLC per minute).
# Online fractal swings n 3 / 5 (a swing at bar i is known only after bar i+n closes).
# Line = the two latest confirmed swing highs (falling = resistance) or lows (rising = support).
#   BREAK : close beyond the line (previous close not beyond) -> follow, one trade per line.
#   BOUNCE: wick reaches the line (within 0.1 ATR) and closes back on its side -> trade off it, one per line.
#   RETEST: within 10 bars after a BREAK, price comes back within 0.2 ATR of the line and closes away -> follow.
# Entry next bar open at the real ask / bid, SL 1.5 ATR or beyond the last 10 bars' extreme - 0.1 ATR,
# TP 1R / 2R / 3R, out after 48 bars; exits on M1 bid / ask (SL first when both in one minute);
# one position at a time per cell; no entries 23:45-01:30 server; 0.01 lot ($1 per $1).
# Every cell has a random-direction twin at the same fills. Last 3 months / the 3 before.
import numpy as np, pandas as pd, sys
z = np.load("xau.npz"); t = z["t"]; b = z["b"]; a = z["a"]
mi = t // 60000; st = np.flatnonzero(np.r_[True, mi[1:] != mi[:-1]])
M_t = mi[st] * 60000
M_bo = b[st] / 100.0; M_ao = a[st] / 100.0
M_bh = np.maximum.reduceat(b, st) / 100.0; M_bl = np.minimum.reduceat(b, st) / 100.0
M_ah = np.maximum.reduceat(a, st) / 100.0; M_al = np.minimum.reduceat(a, st) / 100.0
M_bc = b[np.r_[st[1:] - 1, len(b) - 1]] / 100.0
M_ac = a[np.r_[st[1:] - 1, len(a) - 1]] / 100.0
del z, t, b, a, mi, st
NM = len(M_t)
end = pd.Timestamp(M_t[-1], unit="ms"); a3 = end - pd.Timedelta(days=91); a6 = a3 - pd.Timedelta(days=91)
A3 = a3.value // 10**6; A6 = a6.value // 10**6
print(f"M1 bars {NM}, {pd.Timestamp(M_t[0], unit='ms'):%d %b %Y} .. {end:%d %b %Y}; last 3 m from {a3:%d %b}, previous from {a6:%d %b}", flush=True)

def bars(sec):
    k = M_t // (sec * 1000); s = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    o = M_bo[s]; h = np.maximum.reduceat(M_bh, s); l = np.minimum.reduceat(M_bl, s); c = M_bc[np.r_[s[1:] - 1, NM - 1]]
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    ema = pd.Series(c).ewm(span=200, adjust=False).mean().values
    return dict(s=s, o=o, h=h, l=l, c=c, atr=atr, ema=ema, t=M_t[s])

def signals(B, n, kind, filt):
    h, l, c, atr, ema, tt = B["h"], B["l"], B["c"], B["atr"], B["ema"], B["t"]; N = len(c)
    sh, sl = [], []                      # confirmed swings (index)
    out = []                             # (signal bar, dir, sl_swing)
    used_h = used_l = -1                 # line id = index of its 2nd swing, one trade per line
    brk = []                             # pending retests: (bar of break, dir, i1, i2, isHigh)
    for j in range(2 * n + 1, N):
        i = j - n                        # bar i becomes a confirmed swing at the close of j
        if h[i] == h[i - n:i + n + 1].max() and h[i] > h[i - n:i].max(): sh.append(i)
        if l[i] == l[i - n:i + n + 1].min() and l[i] < l[i - n:i].min(): sl.append(i)
        mins = (tt[j] // 60000) % 1440
        ok_time = 90 <= mins < 1425
        fu = (not filt) or c[j] > ema[j]; fd = (not filt) or c[j] < ema[j]
        def line(i1, i2, v, x): return v[i2] + (v[i2] - v[i1]) / (i2 - i1) * (x - i2)
        if len(sh) >= 2:
            i1, i2 = sh[-2], sh[-1]
            if h[i2] < h[i1]:            # falling resistance
                L0, L1 = line(i1, i2, h, j), line(i1, i2, h, j - 1)
                if kind in ("break", "retest") and used_h != i2 and c[j] > L0 and c[j - 1] <= L1 and j - 1 > i2:
                    used_h = i2
                    if kind == "break" and ok_time and fu: out.append((j, 1))
                    if kind == "retest": brk.append((j, 1, i1, i2, True))
                if kind == "bounce" and used_h != i2 and j > i2 + 1 and h[j] >= L0 - 0.1 * atr[j] and c[j] < L0 and c[j - 1] < L1:
                    used_h = i2
                    if ok_time and fd: out.append((j, -1))
        if len(sl) >= 2:
            i1, i2 = sl[-2], sl[-1]
            if l[i2] > l[i1]:            # rising support
                L0, L1 = line(i1, i2, l, j), line(i1, i2, l, j - 1)
                if kind in ("break", "retest") and used_l != i2 and c[j] < L0 and c[j - 1] >= L1 and j - 1 > i2:
                    used_l = i2
                    if kind == "break" and ok_time and fd: out.append((j, -1))
                    if kind == "retest": brk.append((j, -1, i1, i2, False))
                if kind == "bounce" and used_l != i2 and j > i2 + 1 and l[j] <= L0 + 0.1 * atr[j] and c[j] > L0 and c[j - 1] > L1:
                    used_l = i2
                    if ok_time and fu: out.append((j, 1))
        if kind == "retest" and brk:
            keep = []
            for (jb, d, i1, i2, ish) in brk:
                if j <= jb: keep.append((jb, d, i1, i2, ish)); continue
                if j - jb > 10: continue
                v = h if ish else l; L0 = line(i1, i2, v, j)
                if d == 1 and l[j] <= L0 + 0.2 * atr[j] and c[j] > L0:
                    if ok_time and fu: out.append((j, 1))
                    continue
                if d == -1 and h[j] >= L0 - 0.2 * atr[j] and c[j] < L0:
                    if ok_time and fd: out.append((j, -1))
                    continue
                if (d == 1 and c[j] < L0) or (d == -1 and c[j] > L0): continue   # failed break
                keep.append((jb, d, i1, i2, ish))
            brk = keep
    return out

def trade(m0, d, dist, tpR, mend, stress):
    """entry at M1 index m0 open, direction d, stop distance dist ($); returns (pnl $, exit M1 index)"""
    if d == 1:
        e = M_ao[m0]; sp = M_ao[m0] - M_bo[m0]; e += 0.5 * sp * (stress - 1)
        sl, tp = e - dist, e + tpR * dist
        lo = M_bl[m0:mend]; hi = M_bh[m0:mend]
        hs = np.flatnonzero(lo <= sl); ht = np.flatnonzero(hi >= tp)
        ks = hs[0] if len(hs) else 10**9; kt = ht[0] if len(ht) else 10**9
        if ks <= kt and ks < 10**9: return sl - e, m0 + ks
        if kt < 10**9: return tp - e, m0 + kt
        x = M_bc[mend - 1] - 0.5 * sp * (stress - 1); return x - e, mend - 1
    e = M_bo[m0]; sp = M_ao[m0] - M_bo[m0]; e -= 0.5 * sp * (stress - 1)
    sl, tp = e + dist, e - tpR * dist
    hi = M_ah[m0:mend]; lo = M_al[m0:mend]
    hs = np.flatnonzero(hi >= sl); ht = np.flatnonzero(lo <= tp)
    ks = hs[0] if len(hs) else 10**9; kt = ht[0] if len(ht) else 10**9
    if ks <= kt and ks < 10**9: return e - sl, m0 + ks
    if kt < 10**9: return e - tp, m0 + kt
    x = M_ac[mend - 1] + 0.5 * sp * (stress - 1); return e - x, mend - 1

def run(B, sig, slm, tpR, rnd=None, stress=1.0):
    s, h, l, atr = B["s"], B["h"], B["l"], B["atr"]; NB = len(s)
    res = []; busy = -1
    rng = np.random.default_rng(rnd) if rnd is not None else None
    for (j, d) in sig:
        if j + 1 >= NB: continue
        m0 = s[j + 1]
        if m0 <= busy: continue
        if rng is not None: d = 1 if rng.random() < 0.5 else -1
        if slm == "atr": dist = 1.5 * atr[j]
        else:
            ref = c = B["c"][j]
            dist = (c - l[max(0, j - 9):j + 1].min() + 0.1 * atr[j]) if d == 1 else (h[max(0, j - 9):j + 1].max() - c + 0.1 * atr[j])
            dist = max(dist, 0.5 * atr[j])
        mend = s[j + 49] if j + 49 < NB else NM
        p, mx = trade(m0, d, dist, tpR, mend, stress); busy = mx
        res.append((M_t[m0], p))
    return res

def stats(res, lo, hi):
    r = [(tt, p) for tt, p in res if lo <= tt < hi]
    if not r: return dict(n=0, pf=0, net=0, dd=0, wd=0, win=0)
    p = np.array([x[1] for x in r]); g = p[p > 0].sum(); ls = -p[p < 0].sum()
    eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    days = pd.Series(p, index=pd.to_datetime([x[0] for x in r], unit="ms").normalize()).groupby(level=0).sum()
    return dict(n=len(p), pf=g / ls if ls > 0 else 99, net=p.sum(), dd=min(dd, 0), wd=days.min(), win=100 * (p > 0).mean())

E = M_t[-1] + 1
print("TF   n kind    EMA200 SL  TP | LAST 3 MONTHS: trades win PF stress net DD worstDay rand | PREVIOUS 3: trades PF net rand", flush=True)
rows = []
for tfn, sec in (("M5", 300), ("M15", 900), ("H1", 3600)):
    B = bars(sec)
    for n in (3, 5):
        for kind in ("break", "bounce", "retest"):
            for filt in (False, True):
                sig = signals(B, n, kind, filt)
                for slm in ("atr", "swing"):
                    for tpR in (1, 2, 3):
                        r = run(B, sig, slm, tpR); rs = run(B, sig, slm, tpR, stress=1.5)
                        rr = [run(B, sig, slm, tpR, rnd=k) for k in (1, 2)]
                        x = stats(r, A3, E); y = stats(r, A6, A3); xs = stats(rs, A3, E)
                        xr = [stats(q, A3, E)["pf"] for q in rr]; yr = [stats(q, A6, A3)["pf"] for q in rr]
                        ys = stats(rs, A6, A3)
                        ok = x["n"] >= 30 and x["pf"] >= 1.15 and xs["pf"] >= 1.05 and x["net"] > 0
                        flag = " PASS" if ok else ""
                        if ok and y["pf"] >= 1.15: flag += "+REPEAT"
                        if ok and max(xr) >= x["pf"]: flag += " (random as good)"
                        line = (f"{tfn:3s} {n} {kind:6s} {'EMA' if filt else '-  ':3s} {slm:5s} {tpR}R | {x['n']:4d} {x['win']:3.0f}% PF {x['pf']:4.2f} st {xs['pf']:4.2f} "
                                f"net {x['net']:+7.0f} DD {x['dd']:+6.0f} wd {x['wd']:+5.0f} rand {xr[0]:4.2f}/{xr[1]:4.2f} | "
                                f"{y['n']:4d} PF {y['pf']:4.2f} net {y['net']:+7.0f} rand {yr[0]:4.2f}/{yr[1]:4.2f}{flag}")
                        print(line, flush=True)
                        rows.append(dict(tf=tfn, n=n, kind=kind, filt=filt, sl=slm, tp=tpR, n3=x["n"], pf3=x["pf"], pf3s=xs["pf"], net3=x["net"],
                                         dd3=x["dd"], wd3=x["wd"], r3=max(xr), n6=y["n"], pf6=y["pf"], net6=y["net"], r6=max(yr), pass_=ok))
D = pd.DataFrame(rows)
print("\nSUMMARY")
print(f"cells {len(D)}, median PF last 3 m {D.pf3.median():.2f} (random twins {D.r3.median():.2f}), previous {D.pf6.median():.2f} (random {D.r6.median():.2f})")
for k in ("break", "bounce", "retest"):
    q = D[D.kind == k]; print(f"  {k:6s}: median PF {q.pf3.median():.2f} / {q.pf6.median():.2f}, cells PF>=1.15 in both windows {((q.pf3>=1.15)&(q.pf6>=1.15)&(q.n3>=30)).sum()}")
for tf in ("M5", "M15", "H1"):
    q = D[D.tf == tf]; print(f"  {tf:3s}: median PF {q.pf3.median():.2f} / {q.pf6.median():.2f}")
both = D[(D.pass_) & (D.pf6 >= 1.15) & (D.n6 >= 30)]
print(f"pass last 3 m: {D.pass_.sum()}, also PF>=1.15 the 3 months before: {len(both)}, of which beat both random twins in both windows: {((both.pf3>both.r3)&(both.pf6>both.r6)).sum()}")
print(both.sort_values("pf3", ascending=False).head(15).to_string(index=False))
