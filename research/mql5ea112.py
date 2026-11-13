"""Round 112 (14 Nov 2026): free MQL5 gold EAs (Code Base + Market free list), rebuilt from their published rules.
Owner: "cari teknik dekat mql5 bro, free version banyak".  Only the rules each page states are used; where a page gives no
number, a small grid of sensible values is tried.  Trailing stops are not simulated (the Book has fixed SL / TP / time).
Data: gold M1 export run 43450356142, last 2 years; frames resampled; entry at the next M1 open (stop orders at their
level); real spread; rollover dropped; out by 23:30 server.  Every trade has random-direction and always-buy twins.
  SAFE   ExMachina / ASQ Safe Scalping (Code Base 70052 / 71189), M5 / M15: EMA 150 vs 510, EMA gap > k ATR, close above
         both, close > the 20-bar high + 0.1 ATR, RSI 40-65 (sells 35-60), close > previous close, 08-20 server, optional
         H1 EMA 50 / 200; SL / TP 225 / 250 points (a user comment) or ATR multiples
  ORB    GOLD_ORB (github yulz008), H1 range of the first 1 / 3 H1 candles from 01:00 server, buy stop at the high and
         sell stop at the low (one each a day), SL 400 / TP 1200 points, or 0.5 / 1.5 x ATR14(D1)
  LUMEN  Lumen Golden Breakout (Market 185267), H1 / M15: close beyond the 30-bar high / low with the EMA 200 trend,
         ATR stop (1.5 / 2.5), long-only and both sides
  CANDLE Gold Candle Bot (Market 129105), M1 / M5: a large bar (>= 1.5 / 2 ATR) then a small bar (<= 0.5 ATR), trade the
         small bar's direction (and the large bar's), SL / TP 1 ATR
  SESS   The Impossible Gold (Market 169680), M5: the 01:30-08:00 range broken by a close with a 0.1 ATR buffer 08-17
         server, scored by ADX > 20, EMA 20 / 50, ATR > its 50-bar mean, RSI 30-70 (all four, or none)
  SWING  Super Scalping EA Gold Tick Scalper (Market 175365), M5: stop orders at confirmed fractal swing highs / lows
         (n 3 / 5), expiry 6 / 12 bars, 08-20 server
  EMA    Gold Scalpers EA (Market 184515), M5 / M15: EMA 9 / 21 cross on the EMA 50 side, hard SL
  TREND  Gold Smart Trend EA (Market 153635), M15 / H1: close on the SMA 200 side and RSI 14 crossing 50 (55 / 45)"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import scalp110 as S1
import scalp111 as S2

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()
jit = G.jit
ema, rma, sma, rsi = S1.ema, S1.rma, S1.sma, S1.rsi


@jit
def scan_stop(O, H, L, S, a, b, lvl, dr):
    """first bar in [a, b) where a buy stop (ask high >= lvl) / sell stop (bid low <= lvl) fills: (bar, price) or (-1, 0)"""
    for j in range(a, min(b, len(O))):
        if dr == 1 and H[j] + S[j] >= lvl: return j, max(O[j] + S[j], lvl)
        if dr == -1 and L[j] <= lvl: return j, min(O[j], lvl)
    return -1, 0.0


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01; pt = mt["point"]
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), pt)
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=60)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    res = []
    say(f"gold point {pt}; 225 points = ${225 * pt:.2f}")

    def go(name, sg, one=True):
        if sg is None or len(sg) == 0: return
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.d != 0)]
        if len(sg) < 20: return
        x = M.line(name, bk.run(sg, one), mid, end)
        if x:
            x["fam"] = name.split()[0]; res.append(x); M.show(x)

    F = {}
    for tf in (1, 5, 15, 60):
        X = Bw if tf == 1 else M.resample(Bw, tf)
        o, h, l, c = (X[k].values.astype(float) for k in ("o", "h", "l", "c"))
        at = np.searchsorted(tv, (X.index + pd.Timedelta(minutes=tf)).values.astype("datetime64[ns]"))
        F[tf] = dict(X=X, o=o, h=h, l=l, c=c, xa=M.atr(X).values, at=at, hr=X.index.hour.values, idx=X.index)

    def mk(tf, k, dr, sl, tp=None, hold=None):
        f = F[tf]; ii = f["at"][k]
        ok = ii < n - 2; ii, k, dr = ii[ok], k[ok], np.asarray(dr)[ok]
        sl = np.asarray(sl)[ok] if np.ndim(sl) else np.full(len(ii), sl)
        tpv = (np.asarray(tp)[ok] if np.ndim(tp) else np.full(len(ii), tp)) if tp is not None else np.full(len(ii), np.nan)
        x = exb(ii) if hold is None else np.minimum(ii + hold, exb(ii))
        return pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": tpv, "x": x})

    def first(cond):
        cond = np.nan_to_num(cond).astype(bool)
        return cond & ~np.r_[False, cond[:-1]]

    # ------------------------------------------------ SAFE (ExMachina / ASQ Safe Scalping)
    say("\n-- SAFE: ExMachina / ASQ Safe Scalping"); say(M.HDR)
    h1 = F[60]; e50h, e200h = ema(h1["c"], 50), ema(h1["c"], 200)
    h1bias = pd.Series(np.sign(e50h - e200h), index=h1["idx"] + pd.Timedelta(minutes=60))
    for tf in (5, 15):
        f = F[tf]; c, h, l, xa = f["c"], f["h"], f["l"], f["xa"]
        e150, e510, r = ema(c, 150), ema(c, 510), rsi(c, 14)
        hh = pd.Series(h).rolling(20).max().shift(1).values; ll = pd.Series(l).rolling(20).min().shift(1).values
        cp = np.r_[c[0], c[:-1]]; sess = (f["hr"] >= 8) & (f["hr"] < 20)
        hb = h1bias.reindex(f["idx"] + pd.Timedelta(minutes=tf), method="ffill").values
        for kg in (0.5, 1.0):
            b = (e150 > e510) & (e150 - e510 > kg * xa) & (c > e150) & (c > e510) & (c > hh + 0.1 * xa) & (r >= 40) & (r <= 65) & (c > cp) & sess
            s = (e150 < e510) & (e510 - e150 > kg * xa) & (c < e150) & (c < e510) & (c < ll - 0.1 * xa) & (r >= 35) & (r <= 60) & (c < cp) & sess
            for htf in (False, True):
                bb, ss = (b & (hb > 0), s & (hb < 0)) if htf else (b, s)
                k = np.where(first(bb) | first(ss))[0]; dr = np.where(bb[k], 1, -1)
                tag = f"M{tf} gap{kg}{' H1' if htf else ''}"
                go(f"SAFE {tag} SL225/TP250pts", mk(tf, k, dr, 225 * pt, 250 * pt))
                go(f"SAFE {tag} SL1.5/TP1.5ATR", mk(tf, k, dr, 1.5 * xa[k], 1.5 * xa[k]))
                go(f"SAFE {tag} SL1.5/TP3ATR", mk(tf, k, dr, 1.5 * xa[k], 3.0 * xa[k]))

    # ------------------------------------------------ ORB (GOLD_ORB)
    say("\n-- ORB: GOLD_ORB first H1 candle(s) range, stop orders"); say(M.HDR)
    day = T.normalize(); D = Bw.groupby(day).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    pc = D.c.shift(); tr = np.maximum(D.h - D.l, np.maximum((D.h - pc).abs(), (D.l - pc).abs()))
    datr = tr.rolling(14).mean().shift(1)
    days = D.index[D.index >= start]
    for nh in (1, 3):
        rows = {("pts", 1): [], ("pts", -1): [], ("atr", 1): [], ("atr", -1): []}
        for dd in days:
            if dd.dayofweek >= 5: continue
            a = np.searchsorted(tv, (dd + pd.Timedelta(hours=1)).to_datetime64()); b = np.searchsorted(tv, (dd + pd.Timedelta(hours=1 + nh)).to_datetime64())
            e = np.searchsorted(tv, (dd + pd.Timedelta(minutes=1410)).to_datetime64())
            if b - a < 20 * nh or e <= b: continue
            hi, lo = H[a:b].max(), L[a:b].min(); A = datr.get(dd, np.nan)
            for dr, lvl in ((1, hi), (-1, lo)):
                j, fp = scan_stop(O, H, L, S, b, e, lvl, dr)
                if j < 0: continue
                rows[("pts", dr)].append((j, dr, fp, 400 * pt, 1200 * pt))
                if np.isfinite(A): rows[("atr", dr)].append((j, dr, fp, 0.5 * A, 1.5 * A))
        for ex in ("pts", "atr"):
            rr = rows[(ex, 1)] + rows[(ex, -1)]
            if not rr: continue
            df = pd.DataFrame(rr, columns=["i", "d", "ep", "sl", "tp"]); df["x"] = exb(df.i.values)
            lab = "SL400/TP1200pts" if ex == "pts" else "SL0.5/TP1.5 ATR(D1)"
            go(f"ORB range{nh}h {lab} both", df, one=False)
            go(f"ORB range{nh}h {lab} long", df[df.d == 1], one=False)

    # ------------------------------------------------ LUMEN (30-bar breakout with EMA 200)
    say("\n-- LUMEN: 30-bar close breakout with EMA 200 trend, ATR stop"); say(M.HDR)
    for tf in (15, 60):
        f = F[tf]; c, h, l, xa = f["c"], f["h"], f["l"], f["xa"]; e2 = ema(c, 200)
        hh = pd.Series(h).rolling(30).max().shift(1).values; ll = pd.Series(l).rolling(30).min().shift(1).values
        b = first((c > hh) & (c > e2)); s = first((c < ll) & (c < e2))
        for side in ("long", "both"):
            k = np.where(b | (s if side == "both" else False))[0]; dr = np.where(b[k], 1, -1)
            for slk in (1.5, 2.5):
                go(f"LUMEN M{tf} {side} SL{slk}ATR to 23:30", mk(tf, k, dr, slk * xa[k]))
                go(f"LUMEN M{tf} {side} SL{slk}ATR TP{2 * slk}", mk(tf, k, dr, slk * xa[k], 2 * slk * xa[k]))

    # ------------------------------------------------ CANDLE (large bar then small bar)
    say("\n-- CANDLE: large bar then small bar"); say(M.HDR)
    for tf in (1, 5):
        f = F[tf]; o, c, h, l, xa = f["o"], f["c"], f["h"], f["l"], f["xa"]
        rng = h - l; xp = np.r_[np.nan, xa[:-1]]; rp = np.r_[np.nan, rng[:-1]]; bodyp = np.r_[0, (c - o)[:-1]]
        gate = (a1[np.maximum(f["at"] - 1, 0)] >= 8 * S[np.maximum(f["at"] - 1, 0)]) if tf == 1 else np.ones(len(c), bool)
        for kb in (1.5, 2.0):
            ok = (rp >= kb * xp) & (rng <= 0.5 * xp) & (c != o)
            k = np.where(ok)[0]
            for mode in ("small", "large"):
                dr = np.sign(c - o)[k] if mode == "small" else np.sign(bodyp)[k]
                dr = dr.astype(int)
                sg = mk(tf, k, dr, 1.0 * xa[k], 1.0 * xa[k], hold=60)
                go(f"CANDLE M{tf} big{kb} follow-{mode} SL/TP1ATR", sg)
                if tf == 1: go(f"CANDLE M{tf} big{kb} follow-{mode} SL/TP1ATR gate8", sg[gate[k[f['at'][k] < n - 2]]])

    # ------------------------------------------------ SESS (The Impossible Gold)
    say("\n-- SESS: 01:30-08:00 range breakout 08-17 with ADX / EMA / ATR / RSI score"); say(M.HDR)
    f = F[5]; c, h, l, xa, idx = f["c"], f["h"], f["l"], f["xa"], f["idx"]
    adx = S2.adx(h, l, c, 14); e20, e50 = ema(c, 20), ema(c, 50); r = rsi(c, 14); am = sma(xa, 50)
    hm = idx.hour.values * 60 + idx.minute.values; dk = idx.normalize()
    rng_df = pd.DataFrame({"h": h, "l": l, "d": dk})[(hm >= 90) & (hm < 480)].groupby("d").agg(h=("h", "max"), l=("l", "min"))
    rh = rng_df.h.reindex(dk).values; rl = rng_df.l.reindex(dk).values
    win = (hm >= 480) & (hm < 1020)
    for scored in (False, True):
        b = win & (c > rh + 0.1 * xa); s = win & (c < rl - 0.1 * xa)
        if scored:
            sc = (adx > 20) & (xa > am) & (r > 30) & (r < 70)
            b &= sc & (e20 > e50); s &= sc & (e20 < e50)
        # first break per side per day
        kb_ = pd.Series(np.where(b)[0]).groupby(dk[b]).first().values if b.any() else np.array([], int)
        ks_ = pd.Series(np.where(s)[0]).groupby(dk[s]).first().values if s.any() else np.array([], int)
        k = np.r_[kb_, ks_].astype(int); dr = np.r_[np.ones(len(kb_)), -np.ones(len(ks_))].astype(int)
        for slk, tpk in ((1.5, 2.0), (2.0, 3.0)):
            go(f"SESS M5 {'scored' if scored else 'plain'} SL{slk}/TP{tpk}ATR", mk(5, k, dr, slk * xa[k], tpk * xa[k]))

    # ------------------------------------------------ SWING (stop orders at fractal swings)
    say("\n-- SWING: stop orders at confirmed fractal swings"); say(M.HDR)
    f = F[5]; c, h, l, xa, at, hr = f["c"], f["h"], f["l"], f["xa"], f["at"], f["hr"]
    for nf in (3, 5):
        hs = pd.Series(h); ls = pd.Series(l)
        ph = (hs == hs.rolling(2 * nf + 1, center=True).max()).values; pl = (ls == ls.rolling(2 * nf + 1, center=True).min()).values
        for exp_ in (6, 12):
            for slk, tpk in ((1.0, 1.5), (1.5, 3.0)):
                rows = []
                for p in np.where(ph | pl)[0]:
                    q = p + nf                                             # confirmation bar
                    if q >= len(c) - 1 or not (8 <= hr[q] < 20): continue
                    a = at[q]; b = min(a + exp_ * 5, n - 1)
                    if a >= n - 2: continue
                    for dr, lvl in (((1, h[p]),) if ph[p] else ()) + (((-1, l[p]),) if pl[p] else ()):
                        if (dr == 1 and c[q] >= lvl) or (dr == -1 and c[q] <= lvl): continue
                        j, fp = scan_stop(O, H, L, S, a, b, lvl, dr)
                        if j >= 0: rows.append((j, dr, fp, slk * xa[q], tpk * xa[q]))
                if rows:
                    df = pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp"]); df["x"] = exb(df.i.values)
                    go(f"SWING M5 n{nf} exp{exp_} SL{slk}/TP{tpk}ATR", df)

    # ------------------------------------------------ EMA (9 / 21 cross with EMA 50) and TREND (SMA 200 + RSI 50)
    say("\n-- EMA 9/21 cross on the EMA 50 side; TREND SMA 200 side + RSI cross"); say(M.HDR)
    for tf in (5, 15):
        f = F[tf]; c, xa = f["c"], f["xa"]; e9, e21, e5 = ema(c, 9), ema(c, 21), ema(c, 50)
        up = (e9 > e21) & (np.r_[0, e9[:-1]] <= np.r_[0, e21[:-1]]); dn = (e9 < e21) & (np.r_[0, e9[:-1]] >= np.r_[0, e21[:-1]])
        b, s = up & (c > e5), dn & (c < e5)
        k = np.where(b | s)[0]; dr = np.where(b[k], 1, -1)
        go(f"EMA M{tf} 9/21+50 SL1.5/TP2ATR", mk(tf, k, dr, 1.5 * xa[k], 2.0 * xa[k]))
        go(f"EMA M{tf} 9/21+50 SL1.5ATR to 23:30", mk(tf, k, dr, 1.5 * xa[k]))
    for tf in (15, 60):
        f = F[tf]; c, xa = f["c"], f["xa"]; s2 = sma(c, 200); r = rsi(c, 14); rp = np.r_[50, r[:-1]]
        for lo, hi in ((50, 50), (55, 45)):
            b = (c > s2) & (r > lo) & (rp <= lo); s = (c < s2) & (r < hi) & (rp >= hi)
            k = np.where(b | s)[0]; dr = np.where(b[k], 1, -1)
            go(f"TREND M{tf} RSI{lo}/{hi} SL1.5/TP3ATR", mk(tf, k, dr, 1.5 * xa[k], 3.0 * xa[k]))

    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        say(f"{len(R)} variants; PASS {int(R.ok.sum())}; median PF {R.PF.median():.2f}, random {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
        say("by EA: " + "  ".join(f"{f}: {g.PF.median():.2f} (best {g.PF.max():.2f}, n {len(g)})" for f, g in R.groupby("fam")))
        say("\nTOP 20 by PF with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(20).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
