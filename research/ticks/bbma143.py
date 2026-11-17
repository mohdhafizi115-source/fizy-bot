# Round 143: the owner's BBMA + CB1 rule on gold M15 (17-18 Nov; owner: "test ea bbma + cb1 break").
# BUY (SELL mirrored):
#   H4  : the last closed H4 candle closes above LWMA 5 and LWMA 10 of the H4 highs (the "MA5/10 high"), even in a downtrend.
#   CB1 : an M15 close above the nearest unbroken swing high (fractal), done by ordinary candles ("soft": the break candle is
#         not a big candle (body < 1 ATR) and not a bullish engulfing) - or any break ("any").
#   CSAK: within W M15 candles after the CB1, one candle opens below and closes above EMA 50, mid BB 20 and LWMA 5 / 10 high.
#   Entry: BUY LIMIT in the MA5/10 LOW zone (top of LWMA 5 / 10 of the lows), re-set every M15 bar, valid V candles.
#   SL beyond the swing low since the CB1 (or 1.5 ATR), TP 1 / 2 / 3 R, the upper BB, or none (8 h exit).
# Fills / exits on M5 bars (SL first when a bar touches both), one position at a time, 0.01 lot, gold $1 per $1.
# Controls: CSAK alone (no CB1), no H4 filter, and a RANDOM-direction twin at the same fill time with the same risk / TP.
import os, sys
DATA = sys.argv[1]
sys.path.insert(0, "/home/claude/fizy-bot/research")
import numpy as np, pandas as pd
import scalp_all as SA
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
H4MODES = os.environ.get("H4MODES", "on1,on3,on6,off").split(",")
RNDM = os.environ.get("RNDM", "on6,off").split(","); CTRL = os.environ.get("CTRL", "on6,off").split(",")
SYMS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["XAUUSD"]

def lwma(x, n):
    w = np.arange(1, n + 1, dtype=float)
    return x.rolling(n).apply(lambda a: np.dot(a, w) / w.sum(), raw=True)

def build(sym):
    mt = meta[sym]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    m = d.resample("15min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "s": "median"}).dropna()
    c = m.c
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    m["mid"] = mid; m["up"] = mid + 2 * sd; m["dn"] = mid - 2 * sd
    m["e50"] = c.ewm(span=50, adjust=False).mean()
    m["h5"] = lwma(m.h, 5); m["h10"] = lwma(m.h, 10); m["l5"] = lwma(m.l, 5); m["l10"] = lwma(m.l, 10)
    tr = np.maximum(m.h - m.l, np.maximum((m.h - c.shift()).abs(), (m.l - c.shift()).abs()))
    m["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    h4 = d.resample("4h").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    hb = (h4.c > np.maximum(lwma(h4.h, 5), lwma(h4.h, 10))).astype(int) - (h4.c < np.minimum(lwma(h4.l, 5), lwma(h4.l, 10))).astype(int)
    # round 143b: H4 momentum = an H4 close beyond its BB 20,2 in the last nb closed H4 candles, no opposite one since,
    # optionally with the H4 trend (EMA 50 above / below EMA 90)
    hc = h4.c; hm = hc.rolling(20).mean(); hs = hc.rolling(20).std(ddof=0)
    mu = (hc > hm + 2 * hs).astype(int); md = (hc < hm - 2 * hs).astype(int)
    last = pd.Series(np.where(mu == 1, 1, np.where(md == 1, -1, np.nan)), index=hc.index).ffill().fillna(0)
    tr50 = np.sign(hc.ewm(span=50, adjust=False).mean() - hc.ewm(span=90, adjust=False).mean())
    for nb in (3, 6, 12):
        ru = mu.rolling(nb).max(); rd = md.rolling(nb).max()
        for tf, tt in (("m", None), ("mt", tr50)):
            u = ((ru == 1) & (last == 1)); dn_ = ((rd == 1) & (last == -1))
            if tt is not None: u = u & (tt > 0); dn_ = dn_ & (tt < 0)
            for nm, ser in ((f"h4u_{tf}{nb}", u), (f"h4d_{tf}{nb}", dn_)):
                z = ser.astype(float); z.index = z.index + pd.Timedelta(hours=4)
                m[nm] = z.reindex(m.index, method="ffill").fillna(0).values
    for nb in (1, 3, 6):                                               # a buy (sell) close in the last nb closed H4 candles
        up_ = (hb == 1).astype(float).rolling(nb).max(); dn_ = (hb == -1).astype(float).rolling(nb).max()
        x = (up_ - dn_); x.index = x.index + pd.Timedelta(hours=4)     # known once the H4 candle has closed
        x = x.reindex(m.index, method="ffill").fillna(0).values
        m[f"h4_{nb}"] = x
        m[f"h4u_{nb}"] = up_.set_axis(up_.index + pd.Timedelta(hours=4)).reindex(m.index, method="ffill").fillna(0).values
        m[f"h4d_{nb}"] = dn_.set_axis(dn_.index + pd.Timedelta(hours=4)).reindex(m.index, method="ffill").fillna(0).values
    return d, m, usd

def signals(m, cb1mode, W, need_cb1=True):
    """list of (csak bar index, dir, cb1 bar index)"""
    O, H, L, C, A = (m[k].values for k in ("o", "h", "l", "c", "atr"))
    hi4 = np.maximum.reduce([m.mid.values, m.e50.values, m.h5.values, m.h10.values])
    lo4 = np.minimum.reduce([m.mid.values, m.e50.values, m.l5.values, m.l10.values])
    hi4s = np.maximum.reduce([m.mid.values, m.e50.values, m.l5.values, m.l10.values])     # sell CSAK: below EMA50 + mid + MA5/10 low
    lo4b = np.minimum.reduce([m.mid.values, m.e50.values, m.h5.values, m.h10.values])
    n = len(m); n2 = 2
    sh = np.nan; sl_ = np.nan; last_up = -10 ** 9; last_dn = -10 ** 9; out = []
    for i in range(60, n):
        # fractal confirmed at i (pivot at i - n2)
        p = i - n2
        if H[p] == H[p - n2:i + 1].max(): sh = H[p]
        if L[p] == L[p - n2:i + 1].min(): sl_ = L[p]
        body = abs(C[i] - O[i]); big = body >= 1.0 * A[i]
        if not np.isnan(sh) and C[i] > sh and C[i - 1] <= sh:
            eng = C[i] > O[i] and C[i - 1] < O[i - 1] and C[i] >= O[i - 1] and O[i] <= C[i - 1]
            if cb1mode == "any" or not (big or eng): last_up = i
            sh = np.nan
        if not np.isnan(sl_) and C[i] < sl_ and C[i - 1] >= sl_:
            eng = C[i] < O[i] and C[i - 1] > O[i - 1] and C[i] <= O[i - 1] and O[i] >= C[i - 1]
            if cb1mode == "any" or not (big or eng): last_dn = i
            sl_ = np.nan
        if O[i] < lo4b[i] and C[i] > hi4[i] and (not need_cb1 or 0 < i - last_up <= W): out.append((i, 1, last_up))
        if O[i] > hi4s[i] and C[i] < lo4[i] and (not need_cb1 or 0 < i - last_dn <= W): out.append((i, -1, last_dn))
    return out

def simulate(d, m, usd, sig, h4mode, entry, V, slmode, tp, rng=None, extra=0.0):
    """returns list of (fill time, pnl $)"""
    t5 = d.index.values; O5, H5, L5, C5, S5 = (d[k].values for k in ("o", "h", "l", "c", "s"))
    mi = m.index.values; idx15 = {t: k for k, t in enumerate(mi)}
    res = []; busy = np.datetime64("1970-01-01")
    for i, s_, cb in sig:
        if h4mode != "off":
            key = h4mode[2:]
            ok = m[f"h4u_{key}"].values[i] if s_ == 1 else m[f"h4d_{key}"].values[i]
            if not ok: continue
        if i + 1 >= len(m): continue
        t_open = mi[i] + np.timedelta64(15, "m")                         # the CSAK has closed
        if t_open < busy: continue
        a = m.atr.values[i]
        lo0 = max(cb - 12, 0) if cb > 0 else max(i - 12, 0)
        if slmode == "swing":
            stop = (m.l.values[lo0:i + 1].min() - 0.1 * a) if s_ == 1 else (m.h.values[lo0:i + 1].max() + 0.1 * a)
        # walk M5 bars after the CSAK
        j = np.searchsorted(t5, t_open); end_wait = t_open + np.timedelta64(15 * V, "m")
        fill = None
        while j < len(t5) and t5[j] < end_wait:
            k15 = idx15.get(t5[j] - (t5[j] - mi[0]) % np.timedelta64(15, "m"))
            kz = (k15 - 1) if k15 is not None else i                     # last CLOSED M15 bar
            kz = max(kz, i)
            if entry == "mkt": lvl = None
            elif s_ == 1: lvl = max(m.l5.values[kz], m.l10.values[kz]) if entry == "ztop" else 0.5 * (m.l5.values[kz] + m.l10.values[kz])
            else: lvl = min(m.h5.values[kz], m.h10.values[kz]) if entry == "ztop" else 0.5 * (m.h5.values[kz] + m.h10.values[kz])
            sp = S5[j]
            if lvl is None: fill = (j, O5[j] + (sp if s_ == 1 else 0)); break
            if s_ == 1 and L5[j] + sp <= lvl: fill = (j, min(lvl, O5[j] + sp)); break
            if s_ == -1 and H5[j] >= lvl: fill = (j, max(lvl, O5[j])); break
            if s_ == 1 and slmode == "swing" and C5[j] < stop: break     # setup invalid before the fill
            if s_ == -1 and slmode == "swing" and C5[j] + sp > stop: break
            j += 1
        if fill is None: continue
        j, e = fill
        d_ = s_
        if rng is not None: d_ = 1 if rng.random() < 0.5 else -1
        sp = S5[j]
        if rng is not None: e = O5[j] + (sp if d_ == 1 else 0)
        if slmode == "swing" and rng is None: R = (e - stop) * s_
        elif slmode == "swing": R = abs(e - ((m.l.values[lo0:i + 1].min() - 0.1 * a) if s_ == 1 else (m.h.values[lo0:i + 1].max() + 0.1 * a)))
        else: R = 1.5 * a
        if R <= sp: continue
        st = e - d_ * R
        if tp == "bb": tgt = m.up.values[i] if d_ == 1 else m.dn.values[i]
        elif tp == "none": tgt = None
        else: tgt = e + d_ * float(tp) * R
        if tgt is not None and (tgt - e) * d_ <= 0: tgt = None
        cap = t5[j] + np.timedelta64(8 if tp == "none" else 24, "h")
        x = None; z = j
        for z in range(j, len(t5)):
            if t5[z] >= cap: x = O5[z] + (0 if d_ == 1 else S5[z]); break
            bl = L5[z] if d_ == 1 else H5[z] + S5[z]                    # adverse extreme in exit price
            bh = H5[z] if d_ == 1 else L5[z] + S5[z]
            if (d_ == 1 and bl <= st) or (d_ == -1 and bl >= st):
                x = st if z > j else st; break
            if tgt is not None and ((d_ == 1 and bh >= tgt) or (d_ == -1 and bh <= tgt)): x = tgt; break
        if x is None: x = C5[-1]
        res.append((pd.Timestamp(t5[j]), ((x - e) * d_ - extra * sp) * usd, d_)); busy = t5[z]
    return res

def st(r, lo, hi):
    p = np.array([x[1] for x in r if lo <= x[0] < hi]); tt = [x[0] for x in r if lo <= x[0] < hi]
    if len(p) == 0: return "  0 trades"
    w = p[p > 0].sum(); l = -p[p < 0].sum(); eq = np.cumsum(p); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    day = pd.Series(p, index=pd.DatetimeIndex(tt).normalize()).groupby(level=0).sum().min()
    return f"{len(p):3d} trades win {100*(p>0).mean():3.0f}% PF {min(w/max(l,1e-9),99):5.2f} net {p.sum():+6.0f} DD {dd:+5.0f} wday {day:+4.0f}"

for sym in SYMS:
    d, m, usd = build(sym)
    END = m.index[-1]; A3 = END - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
    print(f"\nH4 candles closing beyond MA5/10 high / low: {int((m.h4_1>0).sum()/16)} / {int((m.h4_1<0).sum()/16)} H4 bars of {len(m)//16}")
    print(f"\n{sym} M15  last 3 months {A3:%d %b}-{END:%d %b} | previous {A6:%d %b}-{A3:%d %b}  (0.01 lot)")
    def row(lab, sig, h4, entry, V, slm, tp, rnd=False):
        r = simulate(d, m, usd, sig, h4, entry, V, slm, tp)
        rs = simulate(d, m, usd, sig, h4, entry, V, slm, tp, extra=0.5)
        a = [x for x in rs if x[0] >= A3]; w = sum(x[1] for x in a if x[1] > 0); l = -sum(x[1] for x in a if x[1] < 0)
        s = f"{lab:46s} | {st(r, A3, END + pd.Timedelta(days=1))} stress {min(w/max(l,1e-9),99):4.2f} | {st(r, A6, A3)}"
        if rnd:
            pf = []
            for seed in range(5):
                rr = simulate(d, m, usd, sig, h4, entry, V, slm, tp, rng=np.random.default_rng(seed))
                for lo_, hi_ in ((A3, END + pd.Timedelta(days=1)), (A6, A3)):
                    p = np.array([x[1] for x in rr if lo_ <= x[0] < hi_]); pf.append(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9))
            s += f" | random dir {min(pf[0::2]):.2f}-{max(pf[0::2]):.2f} / {min(pf[1::2]):.2f}-{max(pf[1::2]):.2f}"
        print(s)
        return r
    for cbm in ("soft", "any"):
        for W in (8, 16):
            sig = signals(m, cbm, W)
            nb = sum(1 for x in sig if x[1] == 1); print(f"-- CB1 {cbm}, CSAK within {W} candles: {len(sig)} signals ({nb} buy / {len(sig)-nb} sell) before the H4 filter")
            for h4 in H4MODES:
                for entry, V in (("ztop", 8), ("zmid", 8), ("mkt", 1)):
                    for tp in ("1", "2", "3", "bb", "none"):
                        if (entry, V) != ("ztop", 8) and tp not in ("2", "none"): continue
                        row(f"H4 {h4:3s} {entry} {V:2d}c SL swing TP {tp}", sig, h4, entry, V, "swing", tp, rnd=(h4 in RNDM and entry == "ztop" and V == 8 and tp in ("2", "none")))
                row(f"H4 {h4:3s} ztop 8c SL 1.5ATR TP 2", sig, h4, "ztop", 8, "atr", "2")
    print("-- control: CSAK alone (no CB1)")
    sig0 = signals(m, "any", 8, need_cb1=False)
    for h4 in CTRL:
        for tp in ("2", "none"): row(f"no CB1 H4 {h4} ztop 8c SL swing TP {tp}", sig0, h4, "ztop", 8, "swing", tp)
