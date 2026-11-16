"""Round 133: trade lists of the live GOLD modules (not FLIP) on M1 bars built from the owner's real XAUUSD ticks.
Each function returns rows (mod, t_entry, t_exit, d, entry, net$) at 0.01 lot ($1 per $1 of price). Server time."""
import numpy as np, pandas as pd
D = pd.read_pickle("xau_m1.pkl")
T = D.index; O, H, L, C, SP = (D[k].values for k in ("o", "h", "l", "c", "spread"))
N = len(D); MIN = (T.hour * 60 + T.minute).values; DAY = T.normalize(); WD = T.dayofweek.values
def walk(i, d, e, sl, tp, iend, trail=None):
    """walk bars from i (entry bar, entry at its open) to iend (exit at its open)."""
    for z in range(i, min(iend, N)):
        s = SP[z]
        if d == 1:
            if L[z] <= sl: return z, (min(O[z], sl) if z > i else sl)
            if tp and H[z] >= tp: return z, (max(O[z], tp) if z > i else tp)
        else:
            if H[z] + s >= sl: return z, (max(O[z] + s, sl) if z > i else sl)
            if tp and L[z] + s <= tp: return z, (min(O[z] + s, tp) if z > i else tp)
        if trail: sl = trail(z, sl)
    z = min(iend, N - 1); return z, (O[z] if d == 1 else O[z] + SP[z])
def rec(R, mod, i, z, d, e, x): R.append((mod, T[i], T[z], d, e, (x - e) * d))
# daily bars (server days)
DD = D.groupby(DAY).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
DD = DD[DD.index.dayofweek < 5]
tr = np.maximum(DD.h - DD.l, np.maximum((DD.h - DD.c.shift()).abs(), (DD.l - DD.c.shift()).abs()))
ATRD = tr.rolling(14).mean().shift(1)          # last 14 completed D1 bars
day_idx = {d: np.flatnonzero((DAY == d)) for d in DD.index}
def first_at(ix, m):
    j = ix[MIN[ix] >= m]; return j[0] if len(j) else None
def ATB():
    R = []
    for d, ix in day_idx.items():
        a = ATRD.get(d); i0 = first_at(ix, 90); ie = first_at(ix, 1410)
        if a != a or i0 is None or ie is None: continue
        op = O[i0]; up, dn = op + 0.25 * a, op - 0.25 * a
        for z in range(i0, ie):
            if H[z] + SP[z] >= up: zz, x = walk(z, 1, max(up, O[z] + SP[z]), up - 0.125 * a, 0, ie); rec(R, "ATB", z, zz, 1, max(up, O[z] + SP[z]), x); break
            if L[z] <= dn: zz, x = walk(z, -1, min(dn, O[z]), dn + 0.125 * a, 0, ie); rec(R, "ATB", z, zz, -1, min(dn, O[z]), x); break
    return R
def ORB():
    R = []
    for d, ix in day_idx.items():
        a = ATRD.get(d); r = ix[(MIN[ix] >= 60) & (MIN[ix] < 240)]; i0 = first_at(ix, 240); ie = first_at(ix, 1410)
        if a != a or len(r) < 60 or i0 is None or ie is None: continue
        hi, lo = H[r].max(), L[r].min(); sl = 0.25 * a
        for side in (1, -1):
            for z in range(i0, ie):
                if side == 1 and H[z] + SP[z] >= hi:
                    e = max(hi, O[z] + SP[z]); zz, x = walk(z, 1, e, e - sl, e + 2 * sl, ie); rec(R, "ORB", z, zz, 1, e, x); break
                if side == -1 and L[z] <= lo:
                    e = min(lo, O[z]); zz, x = walk(z, -1, e, e + sl, e - 2 * sl, ie); rec(R, "ORB", z, zz, -1, e, x); break
    return R
def CMX():
    R = []
    ny = T.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT").tz_convert("America/New_York")
    nm = (ny.hour * 60 + ny.minute).values
    trm = np.maximum(H - L, np.maximum(np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])))
    atr = pd.Series(trm).ewm(alpha=1 / 14, adjust=False).mean().values
    for i in np.flatnonzero(nm == 8 * 60 + 20):
        if i + 6 >= N or WD[i] > 4: continue
        d = 1 if C[i] > O[i] else (-1 if C[i] < O[i] else 0)
        if d == 0 or SP[i + 1] > atr[i]: continue
        e = O[i + 1] + (SP[i + 1] if d == 1 else 0); zz, x = walk(i + 1, d, e, e - d * atr[i], 0, i + 6); rec(R, "CMX", i + 1, zz, d, e, x)
    return R
def GAU():
    R = []
    ld = T.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT").tz_convert("Europe/London")
    lm = (ld.hour * 60 + ld.minute).values
    trm = np.maximum(H - L, np.maximum(np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])))
    atr1 = pd.Series(trm).ewm(alpha=1 / 14, adjust=False).mean().values
    M5 = D.resample("5min").agg({"h": "max", "l": "min", "c": "last"}).dropna()
    t5 = np.maximum(M5.h - M5.l, np.maximum((M5.h - M5.c.shift()).abs(), (M5.l - M5.c.shift()).abs()))
    a5 = t5.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    for i in np.flatnonzero(lm == 615):
        if WD[i] > 4: continue
        a = a5.asof(T[i]); e = O[i]
        ie = i + 30; lo = [L[i]]
        def tr(z, sl):
            lo[0] = min(lo[0], L[z])
            if lm[z] >= 629: sl = min(sl, lo[0] + atr1[z])
            return sl
        zz, x = walk(i, -1, e, e + 2 * a, 0, ie, tr); rec(R, "GAU", i, zz, -1, e, x)
    return R
def KUMO():
    R = []
    h1 = D.resample("1h").agg({"o": "first", "h": "max", "l": "min", "c": "last", "spread": "median"}).dropna()
    hh = lambda n: h1.h.rolling(n).max(); ll = lambda n: h1.l.rolling(n).min()
    ten = (hh(9) + ll(9)) / 2; kij = (hh(26) + ll(26)) / 2
    sa = ((ten + kij) / 2).shift(26); sb = ((hh(52) + ll(52)) / 2).shift(26)
    top = np.maximum(sa, sb).values; bot = np.minimum(sa, sb).values
    t_ = np.maximum(h1.h - h1.l, np.maximum((h1.h - h1.c.shift()).abs(), (h1.l - h1.c.shift()).abs()))
    atr = t_.ewm(alpha=1 / 14, adjust=False).mean().values
    c = h1.c.values; tn = ten.values; kj = kij.values; ti = h1.index; hm = (ti.hour * 60 + ti.minute)
    busy = None; k = 60
    while k < len(h1) - 1:
        if hm[k] < 90 or hm[k] > 1320 or np.isnan(top[k]) or np.isnan(top[k - 1]): k += 1; continue
        d = 1 if (c[k] > top[k] and c[k - 1] <= top[k - 1] and tn[k] > kj[k]) else (-1 if (c[k] < bot[k] and c[k - 1] >= bot[k - 1] and tn[k] < kj[k]) else 0)
        if d == 0: k += 1; continue
        i = T.searchsorted(ti[k + 1]);
        if i >= N: break
        e = O[i] + (SP[i] if d == 1 else 0)
        sl = bot[k] - 0.2 * atr[k] if d == 1 else top[k] + 0.2 * atr[k]
        if abs(e - sl) < 0.5 * atr[k]: sl = e - d * 0.5 * atr[k]
        tp = e + d * 20; x = None; j = k + 1
        while j < len(h1) and j <= k + 48:
            a0 = T.searchsorted(ti[j]); a1 = T.searchsorted(ti[j] + pd.Timedelta(hours=1))
            zz, xx = walk(a0, d, e, sl, tp, a1)
            if zz < a1 - 0 and (xx != (O[min(a1, N - 1)] if d == 1 else O[min(a1, N - 1)] + SP[min(a1, N - 1)])): x = xx; break
            inside = bot[j] <= c[j] <= top[j]
            if inside or j == k + 48: zz = min(a1, N - 1); x = O[zz] + (SP[zz] if d == -1 else 0); break
            j += 1
        if x is None: break
        rec(R, "KUMO", i, zz, d, e, x)
        k = j + 1
    return R
def m15():
    M = D.resample("15min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "spread": "median"}).dropna()
    return M
def CRS():
    R = []; M = m15(); c = M.c
    def rsi(x, n):
        dlt = x.diff(); up = dlt.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-dlt.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        return 100 - 100 / (1 + up / dn.replace(0, 1e-12))
    st = np.zeros(len(c)); cv = c.values
    for i in range(1, len(cv)):
        st[i] = (st[i - 1] + 1 if st[i - 1] > 0 else 1) if cv[i] > cv[i - 1] else ((st[i - 1] - 1 if st[i - 1] < 0 else -1) if cv[i] < cv[i - 1] else 0)
    roc = c.pct_change()
    pr = roc.rolling(100).apply(lambda w: (w[:-1] < w[-1]).mean() * 100, raw=True)
    crsi = ((rsi(c, 3) + rsi(pd.Series(st, index=c.index), 2) + pr) / 3).values
    ema = c.ewm(span=200, adjust=False).mean().values
    t_ = np.maximum(M.h - M.l, np.maximum((M.h - M.c.shift()).abs(), (M.l - M.c.shift()).abs()))
    atr = t_.ewm(alpha=1 / 14, adjust=False).mean().values
    ti = M.index; busy = T[0]
    for k in range(300, len(M) - 1):
        hm = ti[k + 1].hour * 60 + ti[k + 1].minute
        if ti[k + 1].dayofweek > 4 or hm < 90 or hm >= 1410 or ti[k + 1] < busy: continue
        d = 1 if (crsi[k] < 10 <= crsi[k - 1] and cv[k] > ema[k]) else (-1 if (crsi[k] > 90 >= crsi[k - 1] and cv[k] < ema[k]) else 0)
        if d == 0: continue
        i = T.searchsorted(ti[k + 1]); e = O[i] + (SP[i] if d == 1 else 0)
        end = min(ti[k + 1] + pd.Timedelta(minutes=120), ti[k + 1].normalize() + pd.Timedelta(minutes=1410))
        ie = T.searchsorted(end); zz, x = walk(i, d, e, e - d * 1.5 * atr[k], 0, ie); rec(R, "CRS", i, zz, d, e, x); busy = T[zz]
    return R
def BAS():
    R = []
    h1 = D.resample("1h").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    rng = (h1.h - h1.l).rolling(14).mean()
    days = list(DD.index)
    for n_, d in enumerate(days[:-1]):
        b = h1[(h1.index.normalize() == d) & (h1.index.hour == 23)]
        if not len(b): continue
        bh, bl = b.h.iloc[0], b.l.iloc[0]; ht = bh - bl
        if ht < 0.4 * rng.asof(b.index[0]): continue
        o_, c_ = DD.loc[d, "o"], DD.loc[d, "c"]
        side = 1 if c_ < o_ else (-1 if c_ > o_ else 0)
        if side == 0: continue
        lvl = bh if side == 1 else bl; sl = (bl - 0.1 * ht) if side == 1 else (bh + 0.1 * ht)
        armed = False; done = False
        for d2 in days[n_ + 1: n_ + 6]:
            ix = day_idx[d2]; i0 = first_at(ix, 90); ie = first_at(ix, 1410); ic = first_at(ix, 1380)
            if i0 is None or ie is None: continue
            for z in range(i0, ic if ic is not None else ie):
                if not armed:
                    if (side == 1 and C[z] > lvl) or (side == -1 and C[z] < lvl): armed = True
                    continue
                if side == 1 and L[z] + SP[z] <= lvl:
                    e = min(lvl, O[z] + SP[z]); s2 = sl - SP[z]; zz, x = walk(z, 1, e, s2, 0, ie); rec(R, "BAS", z, zz, 1, e, x); done = True; break
                if side == -1 and H[z] >= lvl:
                    e = max(lvl, O[z]); s2 = sl + SP[z]; zz, x = walk(z, -1, e, s2, 0, ie); rec(R, "BAS", z, zz, -1, e, x); done = True; break
            if done: break
            dc = DD.loc[d2, "c"]
            if (side == 1 and dc < bl) or (side == -1 and dc > bh): break
    return R
def ALL():
    out = []
    for f in (ATB, ORB, CMX, GAU, KUMO, CRS, BAS): out += f()
    return pd.DataFrame(out, columns=["mod", "t", "tx", "d", "e", "net"]).assign(sym="XAUUSD")
if __name__ == "__main__":
    X = ALL(); X.to_pickle("gold133.pkl")
    end = T[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9)
    for m, g in X.groupby("mod"):
        for lab, lo, hi in (("last3", a3, end), ("prev3", a6, a3)):
            v = g[(g.t >= lo) & (g.t < hi)].net.values
            print(f"{m:5s} {lab} n {len(v):4d} PF {pf(v):5.2f} net {v.sum():+7.0f}")
