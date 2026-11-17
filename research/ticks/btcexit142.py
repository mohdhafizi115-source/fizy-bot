# Round 142: exits for BTC-STO (live: SL 1.5 ATR(M5), no TP, out after 240 min) on the M5 export of round 133.
# Breakeven, trailing (from closed bars only), TP, longer holds. Last 3 months / the 3 before, 0.01 lot.
# Within a bar the stop is checked before the bar can move the trail (pessimistic); TP filled at its level.
import os, sys
DATA = sys.argv[1]; sys.argv = ["x", DATA]
sys.path.insert(0, "/home/claude/fizy-bot/research")
import numpy as np, pandas as pd
import scalp_all as SA
meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
mt = meta["BTCUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s")); T = d.index; N = len(d)
tr = np.maximum(H - L, np.maximum(np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])))
atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
e20 = pd.Series(C).ewm(span=20, adjust=False).mean().values
ll = pd.Series(L).rolling(5).min(); hh = pd.Series(H).rolling(5).max()
k = ((pd.Series(C) - ll) / (hh - ll) * 100).rolling(3).mean().values; dd_ = pd.Series(k).rolling(3).mean().values
H4 = d.resample("4h").agg({"c": "last"}).dropna(); tr4 = np.sign(H4.c.ewm(span=20, adjust=False).mean() - H4.c.ewm(span=50, adjust=False).mean())
tr4.index = tr4.index + pd.Timedelta(hours=4); trd = tr4.reindex(T, method="ffill").values
lmin3 = pd.Series(L).rolling(3).min().values; hmax3 = pd.Series(H).rolling(3).max().values
sig = []
for i in range(60, N - 1):
    if not (7 <= T[i].hour < 19): continue
    up = k[i] > dd_[i] and k[i - 1] <= dd_[i - 1] and min(k[i - 1], dd_[i - 1]) < 20 and C[i] > O[i] and trd[i] > 0 and lmin3[i] <= e20[i]
    dn = k[i] < dd_[i] and k[i - 1] >= dd_[i - 1] and max(k[i - 1], dd_[i - 1]) > 80 and C[i] < O[i] and trd[i] < 0 and hmax3[i] >= e20[i]
    if up or dn: sig.append((i, 1 if up else -1))

def run(sl=1.5, hold=48, be=None, beoff=0.1, trA=None, trD=None, tp=None, sm=1.0):
    out = []; busy = -1
    for i, s_ in sig:
        if i <= busy: continue
        j = i + 1; a = atr[i]; e = O[j] + (S[j] * sm if s_ == 1 else 0)
        stop = e - s_ * sl * a; R = sl * a; best = e; x = None; z = j
        tpl = e + s_ * tp * R if tp else None
        for z in range(j, min(j + hold, N)):
            # bar extremes in the trade's favour; a short exits on the ask
            lo = L[z] if s_ == 1 else H[z] + S[z] * sm
            hi = H[z] if s_ == 1 else L[z] + S[z] * sm
            if (s_ == 1 and lo <= stop) or (s_ == -1 and lo >= stop):
                op = O[z] if s_ == 1 else O[z] + S[z] * sm
                x = (min(op, stop) if s_ == 1 else max(op, stop)) if z > j else stop; break
            if tpl is not None and ((s_ == 1 and hi >= tpl) or (s_ == -1 and hi <= tpl)): x = tpl; break
            # update after the bar closes (closed-bar trail)
            best = max(best, hi) if s_ == 1 else min(best, hi)
            prof = (best - e) * s_
            if be is not None and prof >= be * a:
                ns = e + s_ * beoff * a
                stop = max(stop, ns) if s_ == 1 else min(stop, ns)
            if trA is not None and prof >= trA * a:
                ns = best - s_ * trD * a
                stop = max(stop, ns) if s_ == 1 else min(stop, ns)
        if x is None:
            z = min(j + hold, N - 1); x = O[z] if s_ == 1 else O[z] + S[z] * sm
        out.append((T[j], (x - e) * s_ * usd)); busy = z
    return pd.DataFrame(out, columns=["t", "p"])

end = T[-1]; A3 = end - pd.Timedelta(days=91); A6 = A3 - pd.Timedelta(days=91)
def st(df):
    if len(df) == 0: return "  0"
    w = df.p[df.p > 0].sum(); l = -df.p[df.p < 0].sum(); eq = df.p.cumsum()
    dd = (eq - eq.cummax().clip(lower=0)).min(); day = df.groupby(df.t.dt.date).p.sum().min()
    return f"{len(df):4d} win {100*(df.p>0).mean():3.0f}% PF {w/max(l,1e-9):5.2f} net {df.p.sum():+6.0f} DD {dd:+5.0f} wday {day:+4.0f} bigwin {df.p.max():+4.0f}"
def row(lab, **kw):
    df = run(**kw); dfs = run(sm=1.5, **kw)
    a = df[df.t >= A3]; b = df[(df.t >= A6) & (df.t < A3)]
    sa = dfs[dfs.t >= A3]; ws = sa.p[sa.p > 0].sum(); ls = -sa.p[sa.p < 0].sum()
    print(f"{lab:34s} | last {st(a)} stress {ws/max(ls,1e-9):4.2f} | prev {st(b)}")
print(f"BTC-STO exits, windows {A3:%d %b}-{end:%d %b} / {A6:%d %b}-{A3:%d %b}, 0.01 lot")
row("LIVE SL1.5 4h", )
for h in (24, 96, 144): row(f"hold {h*5//60}h", hold=h)
for be in (0.5, 1.0, 1.5, 2.0): row(f"BE at +{be} ATR (+0.1)", be=be)
for tp in (1.0, 1.5, 2.0, 3.0): row(f"TP {tp}R", tp=tp)
for A in (1.0, 1.5, 2.0, 3.0):
    for D in (0.75, 1.0, 1.5, 2.0): row(f"trail from +{A} ATR, {D} behind", trA=A, trD=D)
for A, D in ((1.5, 1.0), (2.0, 1.5)):
    for h in (96, 144): row(f"trail +{A}/{D} hold {h*5//60}h", trA=A, trD=D, hold=h)
row("BE +1 + trail +2/1.5", be=1.0, trA=2.0, trD=1.5)
row("BE +1.5 + TP 3R", be=1.5, tp=3.0)
