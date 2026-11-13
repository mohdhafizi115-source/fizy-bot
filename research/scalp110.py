"""Round 110 (14 Nov 2026): popular TradingView scalping indicators never tested in this project, gold M1 / M5 / M15.
Owner: "aku nak kau cari scalping bro. faham la sikit. m1 m5 m15!".
Data: gold M1 export run 43450356142 (from 2024-09), last 2 years; M5 / M15 resampled.  All entries at the open of the
first M1 bar after the signal bar closes; costs = the real spread; rollover entries dropped; out by 23:30 server.
  FLIP systems (always-in style: enter on a flip, exit on the next flip or a cap; disaster SL 2 x ATR of the frame):
     UT Bot Alerts (key 1 / 2 / 3, ATR 10), QQE (14, 5, 4.236), SSL channel (10), Hull MA 20 / 55 slope, KAMA (10, 2, 30)
     slope, Vortex 14, TRIX 15 / 9, Fisher transform 10 slope; each also with a Choppiness(14) < 50 trend filter
  EVENT systems (SL 1.5 x ATR of the frame, fixed hold): Squeeze Momentum release (BB 20,2 inside KC 20,1.5, LazyBear),
     Waddah Attar explosion (MACD 20/40 delta x150 > BB width and > dead zone), Stoch RSI 14/14/3/3 K-D cross out of
     20 / 80, Connors RSI(3,2,100) < 10 / > 90 (with and without the EMA 200 side), Laguerre RSI (0.5 / 0.7) cross of
     0.2 / 0.8, Fisher transform turning from beyond +-1.5
Every trade has a random-direction and an always-buy twin.  $ per 0.01 lot.  Pass rule as always."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()
jit = G.jit


@jit
def ut_bot(C, A, key):
    n = len(C); tr = np.zeros(n); pos = np.zeros(n, np.int64)
    tr[0] = C[0]
    for i in range(1, n):
        nl = key * A[i]; p = tr[i - 1]
        if C[i] > p and C[i - 1] > p: tr[i] = max(p, C[i] - nl)
        elif C[i] < p and C[i - 1] < p: tr[i] = min(p, C[i] + nl)
        elif C[i] > p: tr[i] = C[i] - nl
        else: tr[i] = C[i] + nl
        if C[i - 1] < p and C[i] > p: pos[i] = 1
        elif C[i - 1] > p and C[i] < p: pos[i] = -1
        else: pos[i] = pos[i - 1]
    return pos


@jit
def kama(C, n, fast, slow):
    k = np.zeros(len(C)); k[:n] = C[:n]
    f = 2.0 / (fast + 1); s = 2.0 / (slow + 1)
    for i in range(n, len(C)):
        ch = abs(C[i] - C[i - n]); vol = 0.0
        for q in range(i - n + 1, i + 1): vol += abs(C[q] - C[q - 1])
        er = ch / vol if vol > 0 else 0.0
        sc = (er * (f - s) + s) ** 2
        k[i] = k[i - 1] + sc * (C[i] - k[i - 1])
    return k


@jit
def laguerre(C, g):
    n = len(C); out = np.full(n, 0.5)
    l0 = l1 = l2 = l3 = C[0]
    for i in range(n):
        p0, p1, p2 = l0, l1, l2
        l0 = (1 - g) * C[i] + g * p0
        l1 = -g * l0 + p0 + g * l1
        l2 = -g * l1 + p1 + g * l2
        l3 = -g * l2 + p2 + g * l3
        cu = 0.0; cd = 0.0
        if l0 >= l1: cu += l0 - l1
        else: cd += l1 - l0
        if l1 >= l2: cu += l1 - l2
        else: cd += l2 - l1
        if l2 >= l3: cu += l2 - l3
        else: cd += l3 - l2
        out[i] = cu / (cu + cd) if cu + cd > 0 else 0.5
    return out


@jit
def qqe_trend(rma, dar):
    n = len(rma); lb = np.zeros(n); sb = np.zeros(n); tr = np.zeros(n, np.int64)
    for i in range(1, n):
        nl = rma[i] - dar[i]; ns = rma[i] + dar[i]
        lb[i] = max(lb[i - 1], nl) if (rma[i - 1] > lb[i - 1] and rma[i] > lb[i - 1]) else nl
        sb[i] = min(sb[i - 1], ns) if (rma[i - 1] < sb[i - 1] and rma[i] < sb[i - 1]) else ns
        if rma[i - 1] <= sb[i - 1] and rma[i] > sb[i - 1]: tr[i] = 1
        elif rma[i - 1] >= lb[i - 1] and rma[i] < lb[i - 1]: tr[i] = -1
        else: tr[i] = tr[i - 1]
    return tr


@jit
def fisher(hl2, hh, ll):
    n = len(hl2); v = np.zeros(n); f = np.zeros(n)
    for i in range(1, n):
        rng = hh[i] - ll[i]
        x = 0.66 * ((hl2[i] - ll[i]) / rng - 0.5) + 0.67 * v[i - 1] if rng > 0 else v[i - 1]
        x = min(max(x, -0.999), 0.999); v[i] = x
        f[i] = 0.5 * np.log((1 + x) / (1 - x)) + 0.5 * f[i - 1]
    return f


def ema(x, n): return pd.Series(x).ewm(span=n, adjust=False).mean().values
def rma(x, n): return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values
def sma(x, n): return pd.Series(x).rolling(n).mean().values


def wma(x, n):
    w = np.arange(1, n + 1, dtype=float)
    return pd.Series(x).rolling(n).apply(lambda a: np.dot(a, w) / w.sum(), raw=True).values


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    au = rma(np.where(d > 0, d, 0.0), n); ad = rma(np.where(d < 0, -d, 0.0), n)
    return 100 - 100 / (1 + au / np.maximum(ad, 1e-12))


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=30)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    O, S = bk.O, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    res = []

    def go(name, sg, one=True):
        if sg is None or len(sg) == 0: return
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.d != 0)]
        if len(sg) < 20: return
        x = M.line(name, bk.run(sg, one), mid, end)
        if x:
            x["tf"] = name.split()[0]; x["sys"] = name.split()[1]; res.append(x); M.show(x)

    for tf in (1, 5, 15):
        X = Bw if tf == 1 else M.resample(Bw, tf)
        o, h, l, c = (X[k].values.astype(float) for k in ("o", "h", "l", "c"))
        xa = M.atr(X).values
        at = np.searchsorted(tv, (X.index + pd.Timedelta(minutes=tf)).values.astype("datetime64[ns]"))   # M1 entry bar for each frame bar
        gate_ok = (a1[np.maximum(at - 1, 0)] >= 8 * S[np.maximum(at - 1, 0)]) if tf == 1 else np.ones(len(X), bool)
        cap = {1: 60, 5: 240, 15: 480}[tf]
        hold = {1: (15, 30), 5: (30, 60), 15: (60, 120)}[tf]
        # choppiness
        c1 = np.r_[c[0], c[:-1]]
        trr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
        chop = 100 * np.log10(pd.Series(trr).rolling(14).sum().values /
                              np.maximum(pd.Series(h).rolling(14).max().values - pd.Series(l).rolling(14).min().values, 1e-9)) / np.log10(14)
        say(f"\n{'=' * 20} M{tf}: {len(X):,} bars {'=' * 20}"); say(M.HDR)

        # ---------------- state (flip) systems
        st = {}
        for key in (1.0, 2.0, 3.0): st[f"UTBot{key:.0f}"] = ut_bot(c, rma(trr, 10), key)
        r14 = rsi(c, 14); rm = ema(r14, 5); ar = np.abs(np.diff(rm, prepend=rm[0])); dar = ema(ema(ar, 27), 27) * 4.236
        st["QQE"] = qqe_trend(rm, dar)
        sh, sl_ = sma(h, 10), sma(l, 10)
        ssl = np.zeros(len(c), np.int64); cur = 0
        upm = c > sh; dnm = c < sl_
        hl = np.where(upm, 1, np.where(dnm, -1, 0)); s_ = pd.Series(hl).replace(0, np.nan).ffill().fillna(0).values.astype(np.int64)
        st["SSL10"] = s_
        for hn in (20, 55):
            half = wma(c, hn // 2); full = wma(c, hn)
            hma = wma(2 * half - full, int(np.sqrt(hn)))
            st[f"HMA{hn}"] = np.sign(np.diff(hma, prepend=np.nan)).astype(float)
        km = kama(c, 10, 2, 30); st["KAMA"] = np.sign(np.diff(km, prepend=km[0]))
        vp = np.abs(h - np.r_[l[0], l[:-1]]); vm = np.abs(l - np.r_[h[0], h[:-1]])
        trs = pd.Series(trr).rolling(14).sum().values
        st["VORTEX"] = np.sign(pd.Series(vp).rolling(14).sum().values / trs - pd.Series(vm).rolling(14).sum().values / trs)
        lc = np.log(c); tx = ema(ema(ema(lc, 15), 15), 15); trix = np.diff(tx, prepend=tx[0]) * 1e4
        st["TRIX"] = np.sign(trix - ema(trix, 9))
        hl2 = (h + l) / 2
        fi = fisher(hl2, pd.Series(hl2).rolling(10).max().values, pd.Series(hl2).rolling(10).min().values)
        st["FISHER"] = np.sign(np.diff(fi, prepend=0.0))
        for nm, s in st.items():
            s = np.nan_to_num(np.asarray(s, float)).astype(np.int64)
            prev = np.r_[0, s[:-1]]
            k = np.where((s != prev) & (prev != 0) & (s != 0))[0]
            k = k[(k > 300) & (at[k] < n - 2)]
            if len(k) < 30: continue
            ii = at[k]; dr = s[k]
            nxt = np.r_[ii[1:], n - 1]
            x = np.maximum(np.minimum(np.minimum(nxt, ii + cap), exb(ii)), ii + 1)
            base = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 2.0 * xa[k], "tp": np.nan, "x": x, "g": gate_ok[k], "ch": chop[k]})
            go(f"M{tf} {nm} flip", base.drop(columns=["g", "ch"]), one=False)
            go(f"M{tf} {nm} flip CHOP<50", base[base.ch < 50].drop(columns=["g", "ch"]), one=False)
            if tf == 1: go(f"M{tf} {nm} flip gate8", base[base.g].drop(columns=["g", "ch"]), one=False)

        # ---------------- event systems
        ev = {}
        bbm, bbs = sma(c, 20), pd.Series(c).rolling(20).std(ddof=0).values
        kcr = sma(trr, 20)
        sqz = (bbm - 2 * bbs > bbm - 1.5 * kcr) & (bbm + 2 * bbs < bbm + 1.5 * kcr)
        val = c - ((pd.Series(h).rolling(20).max().values + pd.Series(l).rolling(20).min().values) / 2 + bbm) / 2
        val = ema(val, 5)
        rel = (~sqz) & np.r_[False, sqz[:-1]]
        ev["SQUEEZE"] = np.where(rel & (val > 0), 1, np.where(rel & (val < 0), -1, 0))
        macd = ema(c, 20) - ema(c, 40); t1 = np.diff(macd, prepend=macd[0]) * 150
        e1 = 4 * bbs; dz = rma(trr, 100) * 3.7
        wb = (t1 > 0) & (t1 > e1) & (t1 > dz); ws = (t1 < 0) & (-t1 > e1) & (-t1 > dz)
        ev["WAE"] = np.where(wb & ~np.r_[False, wb[:-1]], 1, np.where(ws & ~np.r_[False, ws[:-1]], -1, 0))
        rr = rsi(c, 14); lo = pd.Series(rr).rolling(14).min().values; hi = pd.Series(rr).rolling(14).max().values
        stk = sma(sma(100 * (rr - lo) / np.maximum(hi - lo, 1e-9), 3), 3); std_ = sma(stk, 3)
        cup = (stk > std_) & (np.r_[0, stk[:-1]] <= np.r_[0, std_[:-1]]) & (np.r_[50, stk[:-1]] < 20)
        cdn = (stk < std_) & (np.r_[0, stk[:-1]] >= np.r_[0, std_[:-1]]) & (np.r_[50, stk[:-1]] > 80)
        ev["STOCHRSI"] = np.where(cup, 1, np.where(cdn, -1, 0))
        dd = np.diff(c, prepend=c[0]); streak = np.zeros(len(c))
        for i in range(1, len(c)):
            streak[i] = (streak[i - 1] + 1 if streak[i - 1] > 0 else 1) if dd[i] > 0 else ((streak[i - 1] - 1 if streak[i - 1] < 0 else -1) if dd[i] < 0 else 0)
        roc = pd.Series(dd / np.r_[c[0], c[:-1]])
        prank = roc.rolling(100).apply(lambda a: (a[:-1] < a[-1]).mean() * 100, raw=True).values
        crsi = (rsi(c, 3) + rsi(streak, 2) + prank) / 3
        e200 = ema(c, 200)
        cb = (crsi < 10) & (np.r_[50, crsi[:-1]] >= 10); cs = (crsi > 90) & (np.r_[50, crsi[:-1]] <= 90)
        ev["CONNORS"] = np.where(cb, 1, np.where(cs, -1, 0))
        ev["CONNORS-EMA200"] = np.where(cb & (c > e200), 1, np.where(cs & (c < e200), -1, 0))
        for g_ in (0.5, 0.7):
            lr = laguerre(c, g_); lp = np.r_[0.5, lr[:-1]]
            ev[f"LAGUERRE{g_}"] = np.where((lp <= 0.2) & (lr > 0.2), 1, np.where((lp >= 0.8) & (lr < 0.8), -1, 0))
        fp = np.r_[0.0, fi[:-1]]; fpp = np.r_[0.0, 0.0, fi[:-2]]
        ev["FISHER-EXT"] = np.where((fpp < -1.5) & (fi > fp) & (fp <= fpp), 1, np.where((fpp > 1.5) & (fi < fp) & (fp >= fpp), -1, 0))
        for nm, e in ev.items():
            k = np.where(e != 0)[0]; k = k[(k > 300) & (at[k] < n - 2)]
            if len(k) < 30: continue
            ii = at[k]; dr = e[k].astype(int)
            for hd in hold:
                base = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 1.5 * xa[k], "tp": np.nan, "x": np.minimum(ii + hd, exb(ii)), "g": gate_ok[k]})
                go(f"M{tf} {nm} {hd}m", base.drop(columns="g"))
                if tf == 1: go(f"M{tf} {nm} {hd}m gate8", base[base.g].drop(columns="g"))
                base2 = base.copy(); base2["tp"] = 1.5 * xa[k]
                go(f"M{tf} {nm} {hd}m TP1R", base2.drop(columns="g"))

    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        say(f"{len(R)} variants; PASS {int(R.ok.sum())}; median PF {R.PF.median():.2f}, random {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
        say("by timeframe: " + "  ".join(f"{f}: {g.PF.median():.2f} (rand {g.rand.median():.2f}, n {len(g)}, trades/wk {g.wk.median():.0f})" for f, g in R.groupby("tf")))
        say("by system: " + "  ".join(f"{f}: {g.PF.median():.2f}" for f, g in R.groupby("sys")))
        say("\nTOP 25 by PF with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(25).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
