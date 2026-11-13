"""Round 100 (13 Nov 2026): divergence, every common form, on the broker's own data, LAST 2 YEARS, 29 symbols
(the 28 forex pairs + XAUUSD the live portfolio trades; BTCUSD left out).  Owner: "kau boleh cari teknik divergence
yang paling solid? kalau ada cer cuba".

What the guides call the solid versions (LuxAlgo, Capital.com, FXPro, Investing.com, babypips threads):
  REGULAR divergence = reversal: price makes a lower low, the oscillator a higher low (bull; bear mirrored),
                       stronger when the first oscillator low sits in its extreme zone (RSI < 30, Stoch < 20, ...).
  HIDDEN divergence  = trend continuation: price makes a higher low, the oscillator a lower low (bull),
                       traded only with the trend (here: close above EMA 200 for bulls).
  confirmation       = do not enter on the divergence alone; wait for a candle to close beyond the swing.
Oscillators: RSI 14, MACD histogram, MACD line, Stochastic 14,3, CCI 20, Awesome Oscillator, OBV and MFI 14
(tick volume).  Swings: fractal pivots of 3 or 5 bars, detected ONLINE (a pivot exists only n bars later, so the
signal fires at the confirmation bar, never earlier - round 19's look-ahead lesson).  The two pivots must be 5-60
bars apart.  Timeframes M15, H1, H4 (from the M5 export).
Entries: E0 = next open after the pivot is confirmed; E1 = a close beyond the high (bull) / low (bear) of the bars
from the second pivot to the confirmation, within 3 bars, then the next open.
Exits: SL beyond the second pivot's extreme + spread; TP 1R / 2R / 3R; time cap 48 bars of the timeframe; swaps.
Simulated on the timeframe's own bars (SL first when SL and TP fall in one bar: conservative).
Entries with the entry bar opening 00:00-01:30 server are skipped (rollover).
Every variant has a RANDOM-direction twin on the same entries.  Pass rule: >= 150 trades, PF >= 1.15,
both years >= 1.05, stress (1.5x spread) >= 1.05, last 12 months positive, PF >= random + 0.10.
"""
import os, sys, time
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
SYMS = [s for s in B87.SYMS if s != "BTCUSD"]
TFS = (15, 60, 240)
OSC = ("RSI", "MACDh", "MACD", "STOCH", "CCI", "AO", "OBV", "MFI")
ZONE = {"RSI": (30, 70), "STOCH": (20, 80), "CCI": (-100, 100), "MFI": (20, 80), "MACDh": (0, 0), "MACD": (0, 0), "AO": (0, 0)}
HOLD = 48
RSI_N = 14        # round 100b varies these
NS = (3, 5)
GAP = (5, 60)
CONFW = 3
BUY_CTRL = False   # round 100c adds an always-buy twin


def ema(a, n): return pd.Series(a).ewm(span=n, adjust=False).mean().values


def oscs(X):
    o, h, l, c, v = (X[k].values.astype(float) for k in ("o", "h", "l", "c", "v"))
    c1 = np.r_[c[0], c[:-1]]
    d = np.diff(c, prepend=c[0]); up = pd.Series(np.maximum(d, 0)).ewm(alpha=1 / RSI_N, adjust=False).mean().values
    dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1 / RSI_N, adjust=False).mean().values
    rsi = 100 - 100 / (1 + up / np.maximum(dn, 1e-12))
    macd = ema(c, 12) - ema(c, 26); mh = macd - ema(macd, 9)
    ll = pd.Series(l).rolling(14).min().values; hh = pd.Series(h).rolling(14).max().values
    k = pd.Series(100 * (c - ll) / np.maximum(hh - ll, 1e-12)).rolling(3).mean().values
    tp = (h + l + c) / 3; cci = np.full(len(c), np.nan)
    if len(c) >= 20:
        w = swv(tp, 20); m = w.mean(1); md = np.abs(w - m[:, None]).mean(1)
        cci[19:] = (tp[19:] - m) / np.maximum(0.015 * md, 1e-12)
    med = (h + l) / 2; ao = pd.Series(med).rolling(5).mean().values - pd.Series(med).rolling(34).mean().values
    obv = np.cumsum(np.sign(c - c1) * v)
    mf = tp * v; tp1 = np.r_[tp[0], tp[:-1]]
    pos = pd.Series(np.where(tp > tp1, mf, 0)).rolling(14).sum().values; neg = pd.Series(np.where(tp < tp1, mf, 0)).rolling(14).sum().values
    mfi = 100 - 100 / (1 + pos / np.maximum(neg, 1e-12))
    tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    return dict(RSI=rsi, MACDh=mh, MACD=macd, STOCH=k, CCI=cci, AO=ao, OBV=obv, MFI=mfi), ema(c, 200), atr


def pivots(x, n, low):
    """index j is a pivot if x[j] is the strict min (max) of x[j-n..j+n]; known only at bar j+n"""
    N = len(x); out = np.zeros(N, bool)
    if N < 2 * n + 1: return out
    w = swv(x, 2 * n + 1); ctr = w[:, n]
    ext = w.min(1) if low else w.max(1)
    cnt = (w == ext[:, None]).sum(1)
    out[n:N - n] = (ctr == ext) & (cnt == 1)
    return out


def run(sym, mt, sw, rg):
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    B = d[["o", "h", "l", "c", "s", "v"]].copy(); del d
    end = B.index[-1]; start = end - pd.Timedelta(days=730)
    out = {}
    for m in TFS:
        g = B.resample(f"{m}min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
        X["v"] = g.v.sum().reindex(X.index).fillna(0).values; X["s"] = g.s.median().reindex(X.index).values
        X = X[X.index >= start - pd.Timedelta(minutes=m * 1500)]
        O, H, L, C, S = (X[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
        T = X.index; N = len(X); day = T.normalize().values; wd = T.day_of_week.values
        hm = T.hour.values * 60 + T.minute.values
        OS, e200, atr = oscs(X)
        valid = T >= start

        def sim(sig, rand, tpR):
            res = []; busy = -1
            for (k, cd, pext, kk) in sig:
                i = kk + 1
                if i >= N or i <= busy or hm[i] < 90: continue
                e0 = O[i] + (S[i] if cd == 1 else 0)
                sl0 = pext - S[i] if cd == 1 else pext + S[i]
                risk = (e0 - sl0) * cd
                if risk <= S[i]: continue
                d_ = cd if not rand else (1 if rand == "buy" else (1 if rg.random() < 0.5 else -1))   # "buy": always-buy control (round 100c)
                e = O[i] + (S[i] if d_ == 1 else 0); sl = e - d_ * risk; tp = e + d_ * tpR * risk
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
                net = (x - e) * d_ * usd + swp; rk = risk * usd
                res.append((T[i], net, net / rk, (net - 0.5 * S[i] * usd) / rk, d_))
                busy = z
            return res

        for n in NS:
            pl, ph = pivots(L, n, True), pivots(H, n, False)
            for osn in OSC:
                o = OS[osn]; zlo, zhi = ZONE.get(osn, (None, None))
                sigs = {}
                for side, piv, P, sg in ((1, pl, L, 1), (-1, ph, H, -1)):
                    js = np.where(piv)[0]
                    for a in range(1, len(js)):
                        j2 = js[a]; k = j2 + n
                        if k >= N - 1 or not valid[k]: continue
                        j1 = js[a - 1]
                        if not (GAP[0] <= j2 - j1 <= GAP[1]) or np.isnan(o[j1]) or np.isnan(o[j2]): continue
                        # price / oscillator relation in the "bull" sense (sg flips it for bears)
                        p_lower = (P[j2] - P[j1]) * sg < 0           # bull: lower low; bear: higher high
                        o_lower = (o[j2] - o[j1]) * sg < 0
                        if p_lower and not o_lower: typ = "REG"
                        elif (not p_lower) and o_lower and P[j2] != P[j1]: typ = "HID"
                        else: continue
                        if typ == "REG":
                            filt = zlo is not None and ((side == 1 and o[j1] < zlo) or (side == -1 and o[j1] > zhi))
                        else:
                            filt = (side == 1 and C[k] > e200[k]) or (side == -1 and C[k] < e200[k])
                        # entry E1: a close beyond the swing of bars j2..k within 3 bars
                        lvl = H[j2:k + 1].max() if side == 1 else L[j2:k + 1].min(); k1 = -1
                        for q in range(k + 1, min(k + 1 + CONFW, N - 1)):
                            if (side == 1 and C[q] > lvl) or (side == -1 and C[q] < lvl): k1 = q; break
                        for f in (False, True):
                            if f and not filt: continue
                            fl = ("zone" if typ == "REG" else "EMA200 trend") if f else "no filter"
                            if osn == "OBV" and typ == "REG" and f: continue
                            sigs.setdefault((typ, fl, "E0"), []).append((k, side, P[j2], k))
                            if k1 > 0: sigs.setdefault((typ, fl, "E1"), []).append((k, side, P[j2], k1))
                for (typ, fl, en), sg_ in sigs.items():
                    sg_.sort(key=lambda r: r[3])
                    for tpR in (1, 2, 3):
                        key = (f"{'M15' if m == 15 else 'H1' if m == 60 else 'H4'}", f"n{n}", osn, typ, fl, en, f"TP {tpR}R")
                        out[key] = (sim(sg_, False, tpR), sim(sg_, True, tpR)) + ((sim(sg_, "buy", tpR),) if BUY_CTRL else ())
    return out, end


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(100)
    ALL = {}; END = None
    for sym in SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        res, end = run(sym, meta[sym], SW.get(sym), rg); END = end if END is None else max(END, end)
        for k, (a, b, *_) in res.items():
            ALL.setdefault(k, [[], []]); ALL[k][0] += [r + (sym,) for r in a]; ALL[k][1] += [r + (sym,) for r in b]
        say(f"{sym} done [{time.time() - T0:.0f} s]")
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    cols = ["t", "net", "r", "rs", "d", "sym"]
    rows = []
    for key, (a, b) in ALL.items():
        x = pd.DataFrame(a, columns=cols); xr = pd.DataFrame(b, columns=cols)
        if len(x) < 30: continue
        P, P1, P2, PS = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values)
        PR = pf(xr.r.values); l12 = x.r[x.t >= mid].sum()
        g = x[x.sym == "XAUUSD"]
        ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
        rows.append(dict(key=" ".join(key), tf=key[0], osc=key[2], typ=key[3], n=len(x), win=100 * (x.r > 0).mean(), PF=P, y1=P1, y2=P2,
                         st=PS, r12=l12, r3=x.r[x.t >= a3].sum(), p3=x.r[(x.t >= a6) & (x.t < a3)].sum(), usd=x.net.sum(),
                         gold=g.net.sum(), gn=len(g), gpf=pf(g.r.values), rand=PR, ok=ok, n1=int((x.t < mid).sum()), sym_pos=(x.groupby("sym").r.sum() > 0).sum()))
    R = pd.DataFrame(rows)
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; 28 forex + XAUUSD; {len(R)} variants with >= 30 trades; R pooled.")
    say(f"PASS: {int(R.ok.sum())} of {int((R.n >= 150).sum())} variants with >= 150 trades")
    hdr = f"{'variant':52s} {'n':>5} {'win':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'12mR':>7} {'3mR':>6} {'p3mR':>6} {'net$':>7} {'gold$':>6} {'gPF':>5} {'sym+':>4} {'RAND':>5}"
    fm = lambda r: (f"{r.key:52s} {r.n:5d} {r.win:4.0f} {r.PF:5.2f} {r.y1:5.2f} {r.y2:5.2f} {r.st:5.2f} {r.r12:+7.1f} {r.r3:+6.1f} {r.p3:+6.1f} "
                    f"{r.usd:+7.0f} {r.gold:+6.0f} {r.gpf:5.2f} {r.sym_pos:4d} {r.rand:5.2f} {'PASS' if r.ok else ''}")
    big = R[R.n >= 150]
    say("\nmedian PF by timeframe x oscillator x type (variants with >= 150 trades) | random twin median")
    for (tf_, osn, typ), gg in big.groupby(["tf", "osc", "typ"]):
        say(f"  {tf_:3s} {osn:6s} {typ}  rows {len(gg):3d}  PF median {gg.PF.median():.2f}  max {gg.PF.max():.2f}  rand median {gg.rand.median():.2f}")
    say("\nTOP 40 by PF (>= 150 trades)"); say(hdr)
    for r in big.sort_values("PF", ascending=False).head(40).itertuples(): say(fm(r))
    if R.ok.any():
        say("\nALL PASSES"); say(hdr)
        for r in R[R.ok].sort_values("PF", ascending=False).itertuples(): say(fm(r))
    say("\nchosen on YEAR 1 only (top 20 by year-1 PF, >= 75 year-1 trades) -> their year 2:")
    cand = big[big.n1 >= 75].sort_values("y1", ascending=False).head(20)
    for r in cand.itertuples(): say(f"  {r.key:52s} yr1 {r.y1:5.2f} -> yr2 {r.y2:5.2f}  (all {r.PF:.2f}, rand {r.rand:.2f})")
    say(f"  median year-2 PF of those 20: {cand.y2.median():.2f}; median year-2 PF of all: {big.y2.median():.2f}")
    say("\nGOLD alone, top 15 by gold PF (>= 60 gold trades)")
    gg = R[R.gn >= 60].sort_values("gpf", ascending=False).head(15)
    for r in gg.itertuples(): say(f"  {r.key:52s} gold n {r.gn:4d} PF {r.gpf:5.2f} ${r.gold:+6.0f}   (all symbols PF {r.PF:.2f})")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
