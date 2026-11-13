"""Round 101 (13 Nov 2026): gold H1 HIDDEN CCI divergence (round 100c's best family) - better SL and invalidation
filters.  Owner: "aku rasa sl kena lebih perbaiki, untuk validkan divergence pasti ada punca untuk membatalkan valid
setup, mungkin perlu beberapa indikator".  XAUUSD only, last 2 years, H1 bars, spread + swaps, 0.01 lot.

Base signal (round 100): fractal pivots (n 3 / 5) on H1 lows / highs found online, two pivots 5-60 bars apart, price
higher low + CCI(20) lower low (buy; sell mirrored), entry after a close beyond the swing within 3 bars (E1), TP 2R / 3R,
48-bar cap.
SL modes: pivot + spread (round 100) / k x ATR(14, H1) from the entry / the pivot SL tightened to at most k ATR /
the pivot SL but the setup skipped when the $ risk > cap.
Invalidation filters (a setup is cancelled when the filter says no), each alone, then the best pairs chosen on YEAR 1
and judged on YEAR 2: ADX(14) >= 20 / 25 (a trend to continue), H4 close on the trade's side of the H4 EMA 50, H1 EMA 50
slope with the trade, RSI(14) on the trade's side of 50, RSI not stretched (< 70 buy / > 30 sell), MACD histogram with
the trade, close on the trade's side of the mid BB, close within 1.5 ATR of the EMA 50, tick volume above its 20-bar
mean, CCI at the second pivot beyond -100 / +100, price pivots at least 0.5 ATR apart.
Controls on the same entries: random direction and ALWAYS BUY (gold's uptrend).
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import div100 as D

DATA = D.DATA
say = lambda s="": print(s, flush=True); pf = D.pf
HOLD = 48


def adx14(h, l, c):
    c1 = np.r_[c[0], c[:-1]]; h1 = np.r_[h[0], h[:-1]]; l1 = np.r_[l[0], l[:-1]]
    up, dn = h - h1, l1 - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    w = lambda a: pd.Series(a).ewm(alpha=1 / 14, adjust=False).mean().values
    atr = w(tr); pdi = 100 * w(pdm) / np.maximum(atr, 1e-12); ndi = 100 * w(ndm) / np.maximum(atr, 1e-12)
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return w(dx)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(101)
    mt = meta["XAUUSD"]; sw = SW.get("XAUUSD"); usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = d[["o", "h", "l", "c", "s", "v"]].copy(); del d
    end = B.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3, a6 = end - pd.Timedelta(days=91), end - pd.Timedelta(days=182)
    g = B.resample("60min", label="left", closed="left")
    X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
    X["v"] = g.v.sum().reindex(X.index).fillna(0).values; X["s"] = g.s.median().reindex(X.index).values
    X = X[X.index >= start - pd.Timedelta(days=200)]
    O, H, L, C, S, V = (X[k].values.astype(float) for k in ("o", "h", "l", "c", "s", "v"))
    T = X.index; N = len(X); day = T.normalize().values; wd = T.day_of_week.values; hm = T.hour.values * 60 + T.minute.values
    OS, e200, atr = D.oscs(X); cci, rsi, mh = OS["CCI"], OS["RSI"], OS["MACDh"]
    e50 = D.ema(C, 50); adx = adx14(H, L, C)
    bbm = pd.Series(C).rolling(20).mean().values; vm = pd.Series(V).rolling(20).mean().values
    g4 = B.resample("240min", label="left", closed="left")
    c4 = g4.c.last().dropna(); e4 = pd.Series(D.ema(c4.values, 50), index=c4.index)
    cl4 = (c4.index + pd.Timedelta(hours=4)).values
    valid = T >= start

    # ---- signals: (k1 = confirmation bar, side, pivot extreme, feature dict)
    sigs = {}
    for n in (3, 5):
        pl, ph = D.pivots(L, n, True), D.pivots(H, n, False)
        out = []
        for side, piv, P, sg in ((1, pl, L, 1), (-1, ph, H, -1)):
            js = np.where(piv)[0]
            for a in range(1, len(js)):
                j2 = js[a]; k = j2 + n; j1 = js[a - 1]
                if k >= N - 1 or not valid[k] or not (5 <= j2 - j1 <= 60) or np.isnan(cci[j1]) or np.isnan(cci[j2]): continue
                p_lower = (P[j2] - P[j1]) * sg < 0; o_lower = (cci[j2] - cci[j1]) * sg < 0
                if p_lower or not o_lower or P[j2] == P[j1]: continue          # hidden only: price HL, CCI LL (bull)
                lvl = H[j2:k + 1].max() if side == 1 else L[j2:k + 1].min(); k1 = -1
                for q in range(k + 1, min(k + 4, N - 1)):
                    if (side == 1 and C[q] > lvl) or (side == -1 and C[q] < lvl): k1 = q; break
                if k1 < 0: continue
                i4 = np.searchsorted(cl4, (T[k1] + pd.Timedelta(hours=1)).to_datetime64(), side="right") - 1
                f = {
                    "ADX>=20": adx[k1] >= 20, "ADX>=25": adx[k1] >= 25,
                    "H4 close vs EMA50": i4 >= 0 and (c4.values[i4] - e4.values[i4]) * side > 0,
                    "H1 EMA50 slope": (e50[k1] - e50[k1 - 5]) * side > 0,
                    "RSI side of 50": (rsi[k1] - 50) * side > 0,
                    "RSI not stretched": rsi[k1] < 70 if side == 1 else rsi[k1] > 30,
                    "MACD hist with trade": mh[k1] * side > 0,
                    "close side of mid BB": (C[k1] - bbm[k1]) * side > 0,
                    "within 1.5 ATR of EMA50": abs(C[k1] - e50[k1]) <= 1.5 * atr[k1],
                    "volume > 20-bar mean": V[k1] > vm[k1],
                    "CCI pivot beyond 100": cci[j2] * side < -100,
                    "pivots >= 0.5 ATR apart": abs(P[j2] - P[j1]) >= 0.5 * atr[k1],
                    "EMA200 trend": (C[k1] - e200[k1]) * side > 0,
                }
                out.append((k1, side, P[j2], atr[k1], f))
        out.sort(key=lambda r: r[0]); sigs[n] = out

    def sim(sg, slm, tpR, mode, cap=None):
        res = []; busy = -1
        for (k1, side, pext, a, f) in sg:
            i = k1 + 1
            if i >= N or i <= busy or hm[i] < 90: continue
            e0 = O[i] + (S[i] if side == 1 else 0)
            pdist = (e0 - (pext - S[i])) * side if side == 1 else ((pext + S[i]) - e0)
            if slm[0] == "pivot": dist = pdist
            elif slm[0] == "atr": dist = slm[1] * a
            else: dist = min(pdist, slm[1] * a)                              # "tight"
            if dist <= S[i] or (cap and dist * usd > cap): continue
            d_ = side if mode == "sig" else (1 if mode == "buy" else (1 if rg.random() < 0.5 else -1))
            e = O[i] + (S[i] if d_ == 1 else 0); sl = e - d_ * dist; tp = e + d_ * tpR * dist
            x = None; z = i; nights = 0
            while z < N:
                if z > i and day[z] != day[z - 1]: nights += 3 if (sw and 1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
                if z - i >= HOLD: x = O[z] + (S[z] if d_ == -1 else 0); break
                if d_ == 1:
                    if L[z] <= sl: x = min(O[z], sl) if z > i else sl; break
                    if H[z] >= tp: x = tp if z == i or O[z] < tp else O[z]; break
                else:
                    if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; break
                    if L[z] + S[z] <= tp: x = tp if z == i or O[z] + S[z] > tp else O[z] + S[z]; break
                z += 1
            if x is None: break
            swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
            net = (x - e) * d_ * usd + swp
            res.append((T[i], net, net / (dist * usd), d_, dist * usd)); busy = z
        return pd.DataFrame(res, columns=["t", "net", "r", "d", "risk"])

    def row(name, sg, slm, tpR, cap=None):
        x = sim(sg, slm, tpR, "sig", cap)
        if len(x) < 15: return None
        xr, xb = sim(sg, slm, tpR, "rand", cap), sim(sg, slm, tpR, "buy", cap)
        eq = x.net.cumsum()
        return dict(name=name, n=len(x), win=100 * (x.r > 0).mean(), PF=pf(x.net.values), y1=pf(x.net[x.t < mid].values),
                    y2=pf(x.net[x.t >= mid].values), n1=int((x.t < mid).sum()), usd=x.net.sum(), u12=x.net[x.t >= mid].sum(),
                    u3=x.net[x.t >= a3].sum(), p3=x.net[(x.t >= a6) & (x.t < a3)].sum(), pb=pf(x.net[x.d == 1].values),
                    ps=pf(x.net[x.d == -1].values), ns=int((x.d == -1).sum()), rand=pf(xr.net.values), buy=pf(xb.net.values),
                    dd=(eq - eq.cummax()).min(), worst=x.net.min(), risk=x.risk.mean())
    hdr = (f"{'variant':58s} {'n':>3} {'win':>3} {'PF$':>5} {'yr1':>5} {'yr2':>5} {'net$':>6} {'12m$':>6} {'3m$':>5} {'p3m$':>5} "
           f"{'buyPF':>5} {'sellPF':>6}({'n':>2}) {'RAND':>5} {'BUY':>5} {'maxDD':>6} {'worst':>5} {'risk$':>5}")
    fm = lambda r: (f"{r['name']:58s} {r['n']:3d} {r['win']:3.0f} {r['PF']:5.2f} {r['y1']:5.2f} {r['y2']:5.2f} {r['usd']:+6.0f} {r['u12']:+6.0f} "
                    f"{r['u3']:+5.0f} {r['p3']:+5.0f} {r['pb']:5.2f} {r['ps']:6.2f}({r['ns']:2d}) {r['rand']:5.2f} {r['buy']:5.2f} "
                    f"{r['dd']:+6.0f} {r['worst']:+5.0f} {r['risk']:5.1f}")
    say(f"XAUUSD H1 hidden CCI divergence, {start:%Y-%m-%d} .. {end:%Y-%m-%d}; PF in $ (0.01 lot); signals n3 {len(sigs[3])}, n5 {len(sigs[5])}")

    # ---- 1. SL modes on the four round-100 bases
    SLS = [("pivot", ("pivot",), None)] + [(f"ATR x{k}", ("atr", k), None) for k in (1.0, 1.5, 2.0, 2.5, 3.0)] + \
          [(f"pivot tightened to <= {k} ATR", ("tight", k), None) for k in (1.0, 1.5, 2.0)] + \
          [(f"pivot, skip if risk > ${c}", ("pivot",), c) for c in (10, 15, 20, 30)]
    say("\n1. SL MODES (no filter)"); say(hdr)
    sl_rows = []
    for n in (3, 5):
        for tp in (2, 3):
            for sn, slm, cap in SLS:
                r = row(f"n{n} TP{tp}R | SL {sn}", sigs[n], slm, tp, cap)
                if r: r.update(nn=n, tp=tp, sl=sn, slm=slm, cap=cap); sl_rows.append(r); say(fm(r))
            say()
    SR = pd.DataFrame(sl_rows)
    # choose the SL on year 1 (median year-1 PF of the four bases)
    by = SR.groupby("sl").agg(y1=("y1", "median"), y2=("y2", "median"), worst=("worst", "min"), n=("n", "median")).sort_values("y1", ascending=False)
    say("SL modes ranked by median YEAR-1 PF over the 4 bases -> their median year 2:")
    for sn, r in by.iterrows(): say(f"  {sn:36s} yr1 {r.y1:5.2f} -> yr2 {r.y2:5.2f}   worst trade {r.worst:+5.0f}  trades ~{r.n:.0f}")
    best_sl = by.index[0]; bs = SR[SR.sl == best_sl].iloc[0]
    say(f"chosen on year 1: SL = {best_sl}")

    # ---- 2. invalidation filters, alone, with the pivot SL and with the chosen SL
    FN = list(sigs[3][0][4].keys())
    fl_rows = []
    for sln, slm, cap in (("pivot", ("pivot",), None), (best_sl, bs.slm, bs.cap)):
        say(f"\n2. INVALIDATION FILTERS alone, SL {sln}"); say(hdr)
        for n in (3, 5):
            for tp in (2, 3):
                base = row(f"n{n} TP{tp}R | SL {sln} | no filter", sigs[n], slm, tp, cap)
                if base: say(fm(base))
                for fn in FN:
                    sg = [s for s in sigs[n] if s[4][fn]]
                    r = row(f"n{n} TP{tp}R | SL {sln} | {fn}", sg, slm, tp, cap)
                    if r: r.update(nn=n, tp=tp, sl=sln, f=fn, base1=base["y1"] if base else 0, base2=base["y2"] if base else 0); fl_rows.append(r); say(fm(r))
                say()
    F = pd.DataFrame(fl_rows)
    F["d1"] = F.y1 - F.base1; F["d2"] = F.y2 - F.base2
    agg = F.groupby(["sl", "f"]).agg(d1=("d1", "median"), d2=("d2", "median"), n=("n", "median")).reset_index()
    for sln in agg.sl.unique():
        say(f"\nfilters by median YEAR-1 gain over no-filter (SL {sln}) -> their median YEAR-2 gain:")
        for r in agg[agg.sl == sln].sort_values("d1", ascending=False).itertuples():
            say(f"  {r.f:28s} yr1 {r.d1:+5.2f} -> yr2 {r.d2:+5.2f}   trades ~{r.n:.0f}")

    # ---- 3. pairs of the year-1 top 5 filters, chosen on year 1, judged on year 2
    for sln, slm, cap in (("pivot", ("pivot",), None), (best_sl, bs.slm, bs.cap)):
        top = agg[agg.sl == sln].sort_values("d1", ascending=False).f.head(5).tolist()
        say(f"\n3. PAIRS of the year-1 top-5 filters, SL {sln}: {top}"); say(hdr)
        pr = []
        for a in range(len(top)):
            for b in range(a + 1, len(top)):
                for n in (3, 5):
                    for tp in (2, 3):
                        sg = [s for s in sigs[n] if s[4][top[a]] and s[4][top[b]]]
                        r = row(f"n{n} TP{tp}R | {top[a]} + {top[b]}", sg, slm, tp, cap)
                        if r: pr.append(r)
        P = pd.DataFrame(pr)
        if len(P):
            for r in P.sort_values("y1", ascending=False).head(12).to_dict("records"): say(fm(r))
            say(f"  pairs chosen on year 1 (top 12) -> median year-2 PF {P.sort_values('y1', ascending=False).head(12).y2.median():.2f}; "
                f"all pairs median year-2 PF {P.y2.median():.2f}")


if __name__ == "__main__":
    main()
