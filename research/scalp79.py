"""Round 79 (10 Nov 2026): a second search for a frequent gold M1 scalper, judged on the last 3 months
(owner: "cuba carikan aku scalping gold m1 yang bagus dan trade banyak kali. test dalam 3 bulan" ... "aku kata cari").

Round 74 covered the textbook families (EMA cross, BB+RSI, RSI2, Stoch, breakout, pullback, momentum, 1-bar spike
fade).  This round tries only what has NOT been run on gold M1 before:
  A  multi-bar drop fade      close fell >= k ATR over the last 2 / 3 bars (buy; also both sides)
  B  spike fade, new exits    the live rule (1-bar >= 2 ATR, gate 8) with breakeven stops, other holds, NY only, k 1.5 NY
  C  up-spike follow          buy after an UP bar >= k ATR, +/- H1 trend up
  D  dip in an H1 uptrend     H1 EMA 20 > EMA 50 and M1 RSI oversold (buy); mirror for sells in an H1 downtrend
  E  pin bar                  lower wick >= w ATR and a close in the top third (buy); mirror
  F  Keltner re-entry         a close back inside EMA 20 +/- 2 ATR after a close outside
  G  session VWAP band        close beyond VWAP +/- 2 sd of the session's deviation, then the first bar closing back
  H  quiet -> burst           ATR14 / ATR100 < 0.7 and a bar >= 2 ATR: follow it
  J  3-bar reversal           3 closes down then a close above the previous high (buy); mirror
  L  spike + RSI              1-bar down spike with RSI(14) < 30, immediate (no wick wait)
One position at a time, entry at the next bar's open, spread charged once, entries 01:30-22:00 server, flat 23:45.
$ per 0.01 lot.  PASS (the round 74 frame): >= 3 trades a day, each of the last 3 months positive, PF >= 1.15 over
the 3 months, and the 3 months before positive.  Every pass is then shown over 12 months, with a RANDOM-TIME control
(the same number of entries, same directions, at random eligible bars: gold rose, so "buy anything" must be beaten).
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    X = DT.bars(d, "1min"); del d
    X = X[X.index >= X.index[-1] - pd.Timedelta(days=400)]
    end = X.index[-1]
    edges = [end - pd.Timedelta(days=30 * i) for i in range(6, -1, -1)]
    y1 = end - pd.Timedelta(days=365)
    O, H, L, C = (X[c].values.astype(float) for c in ("o", "h", "l", "c"))
    S = X.s.values.astype(float); T = X.index; n = len(C)
    hm = T.hour.values * 60 + T.minute.values; wd = T.dayofweek.values
    day = T.normalize().values
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    a1 = np.r_[np.nan, atr[:-1]]
    a100 = pd.Series(tr).rolling(100).mean().shift(1).values
    gate = a1 / np.where(S > 0, S, np.nan)
    rng = H - L; body = C - O
    ok = (hm >= 90) & (hm < 1320) & (wd < 5)
    dC = np.diff(C, prepend=C[0])
    def rsi(p):
        up = pd.Series(np.maximum(dC, 0)).ewm(alpha=1 / p, adjust=False).mean()
        dn = pd.Series(np.maximum(-dC, 0)).ewm(alpha=1 / p, adjust=False).mean()
        return (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    r14, r7 = rsi(14), rsi(7)
    e20 = pd.Series(C).ewm(span=20, adjust=False).mean().values
    h1 = pd.Series(C, index=T).resample("1h").last().dropna()
    hup = (h1.ewm(span=20, adjust=False).mean() > h1.ewm(span=50, adjust=False).mean()).shift(1).reindex(T, method="ffill").values
    hup = np.where(pd.isna(hup), False, hup).astype(bool); hdn = ~hup
    # session VWAP (typical price x tick volume is not in the bars: use an equal-weight session mean) and its deviation
    tp_ = (H + L + C) / 3
    g = pd.Series(tp_).groupby(day)
    vw = g.expanding().mean().reset_index(level=0, drop=True).values
    dev = C - vw
    sd = pd.Series(dev).groupby(day).expanding().std().reset_index(level=0, drop=True).values
    say(f"XAUUSD M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; last 3 months from {edges[3]:%d %b}, repeat check from {edges[0]:%d %b}")

    def sim(sig, slm, tpm, hold, sl_mode="atr", be=0.0):
        """sig -1/0/+1 at the close of bar k -> trade from the open of k+1.  be: move the SL to entry after +be ATR."""
        res = []; busy = -1
        for k in np.where((sig != 0) & ok)[0]:
            if k <= busy or k + 1 >= n: continue
            dr = int(sig[k]); e = O[k + 1]; a = atr[k]
            if not np.isfinite(a) or a <= 0: continue
            sl = e - dr * slm * a if sl_mode == "atr" else ((L[k] - slm * a) if dr == 1 else (H[k] + slm * a))
            if (e - sl) * dr <= 0: continue
            tp = e + dr * tpm * a if tpm else None
            x = None; q = k + 1; moved = False
            while q < n:
                if q - (k + 1) >= hold or hm[q] >= 1425 or day[q] != day[k + 1]:
                    x = O[q] if q > k + 1 else C[q]; break
                if dr == 1:
                    if L[q] <= sl: x = min(O[q], sl) if q > k + 1 else sl; break
                    if tp is not None and H[q] >= tp: x = max(O[q], tp) if q > k + 1 else tp; break
                    if be and not moved and H[q] >= e + be * a: sl = e; moved = True      # effective from the next bar
                else:
                    if H[q] >= sl: x = max(O[q], sl) if q > k + 1 else sl; break
                    if tp is not None and L[q] <= tp: x = min(O[q], tp) if q > k + 1 else tp; break
                    if be and not moved and L[q] <= e - be * a: sl = e; moved = True
                q += 1
            if x is None: continue
            res.append((T[k + 1], ((x - e) * dr - S[k + 1]) * usd)); busy = q
        return pd.DataFrame(res, columns=["t", "net"])

    rows = []; keep = {}
    def rec(name, sig, *a, **kw):
        sig = np.where(np.isfinite(gate), sig, 0)
        R = sim(sig, *a, **kw)
        if len(R) < 30: return
        m = [R[(R.t >= edges[i]) & (R.t < edges[i + 1])].net.sum() for i in range(6)]
        l3 = R[R.t >= edges[3]]; p3 = R[(R.t >= edges[0]) & (R.t < edges[3])]; yy = R[R.t >= y1]
        if len(l3) < 10: return
        pf = l3.net[l3.net > 0].sum() / max(-l3.net[l3.net < 0].sum(), 1e-9)
        per_day = len(l3) / max(1, l3.t.dt.normalize().nunique())
        per_day_all = len(l3) / 64.0                                   # per trading day of the 3 months, quiet days included
        wday = l3.groupby(l3.t.dt.normalize()).net.sum().min()
        ok_ = per_day_all >= 3 and min(m[3:]) > 0 and pf >= 1.15 and p3.net.sum() > 0
        rows.append([name, per_day_all, 100 * (l3.net > 0).mean(), pf, m[3], m[4], m[5], l3.net.sum(), p3.net.sum(), wday, yy.net.sum(), "PASS" if ok_ else ""])
        keep[name] = (sig, a, kw)

    down = body < 0; up = body > 0
    g8 = gate >= 8
    # ---- A multi-bar drop fade
    for m_ in (2, 3):
        mv = C - np.r_[[np.nan] * m_, C[:-m_]]
        for k_ in (2.5, 3.0, 3.5, 4.0):
            for gg, gn in ((g8, "gate8"), (gate >= 6, "gate6")):
                s = np.where((mv <= -k_ * a1) & gg, 1, 0)
                rec(f"A {m_}-bar drop >= {k_} ATR fade BUY {gn} SL 0.2 ATR under the bar, no TP, 45 min", s, 0.2, 0, 45, sl_mode="bar")
                rec(f"A {m_}-bar drop >= {k_} ATR fade BUY {gn} SL 1 ATR, TP 1.5 ATR, 30 min", s, 1.0, 1.5, 30)
                b = np.where((np.abs(mv) >= k_ * a1) & gg, -np.sign(mv), 0)
                rec(f"A {m_}-bar move >= {k_} ATR fade BOTH {gn} SL 1 ATR, TP 1.5 ATR, 30 min", b, 1.0, 1.5, 30)
    # ---- B the live spike fade with new exits / sessions
    spk = np.where((rng >= 2.0 * a1) & down & g8, 1, 0)
    rec("B LIVE spike fade k2 gate8 SL 0.2 ATR, no TP, 45 min (reference)", spk, 0.2, 0, 45, sl_mode="bar")
    for be in (0.5, 1.0, 2.0):
        rec(f"B spike fade k2 gate8 + breakeven after +{be} ATR, 45 min", spk, 0.2, 0, 45, sl_mode="bar", be=be)
    for hold in (20, 90, 180):
        rec(f"B spike fade k2 gate8 hold {hold} min", spk, 0.2, 0, hold, sl_mode="bar")
    for slm in (0.5, 1.0):
        rec(f"B spike fade k2 gate8 SL {slm} ATR under the bar, 45 min", spk, slm, 0, 45, sl_mode="bar")
    ny = (hm >= 930) & (hm < 1320)
    for k_ in (1.5, 1.75, 2.0):
        rec(f"B spike fade k{k_} gate8 NY session only, 45 min", np.where((rng >= k_ * a1) & down & g8 & ny, 1, 0), 0.2, 0, 45, sl_mode="bar")
        rec(f"B spike fade k{k_} gate8 H1 uptrend only, 45 min", np.where((rng >= k_ * a1) & down & g8 & hup, 1, 0), 0.2, 0, 45, sl_mode="bar")
        rec(f"B spike fade k{k_} gate10, 45 min", np.where((rng >= k_ * a1) & down & (gate >= 10), 1, 0), 0.2, 0, 45, sl_mode="bar")
    # ---- C up-spike follow
    for k_ in (1.5, 2.0, 2.5):
        us = (rng >= k_ * a1) & up & g8
        rec(f"C up spike k{k_} gate8 FOLLOW buy, SL under the bar, no TP, 45 min", np.where(us, 1, 0), 0.2, 0, 45, sl_mode="bar")
        rec(f"C up spike k{k_} gate8 FOLLOW buy in an H1 uptrend, SL 1 ATR, TP 2 ATR, 45 min", np.where(us & hup, 1, 0), 1.0, 2.0, 45)
        ds = (rng >= k_ * a1) & down & g8
        rec(f"C down spike k{k_} gate8 FOLLOW sell in an H1 downtrend, SL 1 ATR, TP 2 ATR, 45 min", np.where(ds & hdn, -1, 0), 1.0, 2.0, 45)
    # ---- D dip in an H1 trend
    for rr, nm, lo in ((r14, "RSI14", 25), (r14, "RSI14", 20), (r7, "RSI7", 15), (r7, "RSI7", 10)):
        x1 = np.r_[np.nan, rr[:-1]]
        for gg, gn in ((g8, "gate8"), (np.ones(n, bool), "no gate")):
            s = np.where((rr < lo) & ~(x1 < lo) & hup & gg, 1, np.where((rr > 100 - lo) & ~(x1 > 100 - lo) & hdn & gg, -1, 0))
            rec(f"D {nm} < {lo} in an H1 uptrend (mirror) {gn} SL 1 ATR, TP 2 ATR, 45 min", s, 1.0, 2.0, 45)
            rec(f"D {nm} < {lo} in an H1 uptrend (mirror) {gn} SL 2 ATR, no TP, 45 min", s, 2.0, 0, 45)
            rec(f"D {nm} < {lo} BUY only, H1 uptrend {gn} SL 1 ATR, TP 2 ATR, 45 min", np.where(s == 1, 1, 0), 1.0, 2.0, 45)
    # ---- E pin bar
    lw = np.minimum(O, C) - L; uw = H - np.maximum(O, C)
    for w in (1.0, 1.5, 2.0):
        for gg, gn in ((g8, "gate8"), (gate >= 5, "gate5")):
            pb = (lw >= w * a1) & (C >= L + 0.67 * rng) & gg
            ps = (uw >= w * a1) & (C <= L + 0.33 * rng) & gg
            rec(f"E pin bar wick >= {w} ATR BUY {gn} SL under the wick, no TP, 45 min", np.where(pb, 1, 0), 0.1, 0, 45, sl_mode="bar")
            rec(f"E pin bar wick >= {w} ATR BOTH {gn} SL beyond the wick, TP 2 ATR, 45 min", np.where(pb, 1, np.where(ps, -1, 0)), 0.1, 2.0, 45, sl_mode="bar")
    # ---- F Keltner re-entry
    for kk in (2.0, 3.0):
        lo_ = e20 - kk * atr; hi_ = e20 + kk * atr
        out_lo = np.r_[False, (C < lo_)[:-1]]; out_hi = np.r_[False, (C > hi_)[:-1]]
        for gg, gn in ((g8, "gate8"), (np.ones(n, bool), "no gate")):
            s = np.where(out_lo & (C >= lo_) & gg, 1, np.where(out_hi & (C <= hi_) & gg, -1, 0))
            rec(f"F Keltner {kk} ATR re-entry BOTH {gn} SL 1 ATR, TP at 1.5 ATR, 30 min", s, 1.0, 1.5, 30)
            rec(f"F Keltner {kk} ATR re-entry BUY {gn} SL under the bar, no TP, 45 min", np.where(s == 1, 1, 0), 0.2, 0, 45, sl_mode="bar")
    # ---- G session VWAP band
    for z in (2.0, 2.5, 3.0):
        zz = dev / np.where(sd > 0, sd, np.nan)
        z1 = np.r_[np.nan, zz[:-1]]
        for gg, gn in ((g8, "gate8"), (np.ones(n, bool), "no gate")):
            s = np.where((z1 <= -z) & (zz > z1) & up & gg, 1, np.where((z1 >= z) & (zz < z1) & down & gg, -1, 0))
            rec(f"G session mean -{z} sd then an up close, BOTH {gn} SL 1 ATR, TP 2 ATR, 45 min", s, 1.0, 2.0, 45)
            rec(f"G session mean -{z} sd then an up close, BUY {gn} SL 1.5 ATR, no TP, 60 min", np.where(s == 1, 1, 0), 1.5, 0, 60)
    # ---- H quiet -> burst
    for q_ in (0.6, 0.7, 0.8):
        s = np.where((a1 / a100 < q_) & (rng >= 2.0 * a1), np.sign(body), 0)
        rec(f"H quiet (ATR14/ATR100 < {q_}) then a 2 ATR bar: FOLLOW, SL 1 ATR, TP 2 ATR, 30 min", s, 1.0, 2.0, 30)
        rec(f"H quiet (ATR14/ATR100 < {q_}) then a 2 ATR bar: FADE, SL 1 ATR, TP 2 ATR, 30 min", -s, 1.0, 2.0, 30)
    # ---- J 3-bar reversal
    dn3 = (dC < 0) & np.r_[False, (dC < 0)[:-1]] & np.r_[False, False, (dC < 0)[:-2]]
    up3 = (dC > 0) & np.r_[False, (dC > 0)[:-1]] & np.r_[False, False, (dC > 0)[:-2]]
    h1_ = np.r_[np.nan, H[:-1]]; l1_ = np.r_[np.nan, L[:-1]]
    for gg, gn in ((g8, "gate8"), (gate >= 5, "gate5")):
        s = np.where(np.r_[False, dn3[:-1]] & (C > h1_) & gg, 1, np.where(np.r_[False, up3[:-1]] & (C < l1_) & gg, -1, 0))
        rec(f"J 3 closes down then a close above the last high (mirror) {gn} SL beyond the bar, TP 2 ATR, 30 min", s, 0.2, 2.0, 30, sl_mode="bar")
        rec(f"J the same, BUY only {gn} SL under the bar, no TP, 45 min", np.where(s == 1, 1, 0), 0.2, 0, 45, sl_mode="bar")
    # ---- L spike + RSI, immediate
    for k_ in (1.5, 2.0):
        for lo in (30, 35):
            rec(f"L down spike k{k_} gate8 with RSI14 < {lo}, 45 min", np.where((rng >= k_ * a1) & down & g8 & (r14 < lo), 1, 0), 0.2, 0, 45, sl_mode="bar")
            rec(f"L down spike k{k_} gate6 with RSI14 < {lo}, 45 min", np.where((rng >= k_ * a1) & down & (gate >= 6) & (r14 < lo), 1, 0), 0.2, 0, 45, sl_mode="bar")

    rows.sort(key=lambda r: -r[7])
    say(f"\n{len(rows)} variants, sorted by the last 3 months' net. /day counts every trading day of the 3 months.")
    say(f"{'variant':86s} {'/day':>5} {'win%':>4} {'PF3m':>5} | {'m1':>6} {'m2':>6} {'m3':>6} | {'3 mths':>7} {'prev 3m':>7} {'worst d':>7} {'12 mths':>8}")
    for r in rows:
        if r[7] > 0 or r[11]:
            say(f"{r[0]:86s} {r[1]:5.1f} {r[2]:4.0f} {r[3]:5.2f} | {r[4]:+6.0f} {r[5]:+6.0f} {r[6]:+6.0f} | {r[7]:+7.0f} {r[8]:+7.0f} {r[9]:+7.0f} {r[10]:+8.0f} {r[11]}")
    neg = [r for r in rows if r[7] <= 0]
    say(f"... and {len(neg)} variants that lost over the last 3 months (worst {min((r[7] for r in rows)):+.0f}).")
    passes = [r for r in rows if r[11]]
    say(f"\n{len(passes)} of {len(rows)} PASS (>= 3 a day, 3 months each positive, PF >= 1.15, previous 3 months positive).")
    say(f"positive last 3 months AND previous 3 months, any trade rate: {sum(1 for r in rows if r[7] > 0 and r[8] > 0)} of {len(rows)}")
    # ---- random-time control for every pass and for the best 10 by 3-month net
    say("\nRANDOM-TIME CONTROL (20 draws: the same number of entries and directions at random eligible bars, same exit):")
    rg = np.random.default_rng(79)
    elig = np.where(ok & np.isfinite(gate) & np.isfinite(atr))[0]
    for r in (passes + [x for x in rows[:10] if not x[11]]):
        sig, a, kw = keep[r[0]]
        idx = np.where((sig != 0) & ok)[0]
        if len(idx) == 0: continue
        tot = []
        for _ in range(20):
            s2 = np.zeros(n, int)
            s2[rg.choice(elig, size=len(idx), replace=False)] = sig[idx]
            R = sim(s2, *a, **kw)
            tot.append(R[R.t >= edges[3]].net.sum())
        tot = np.array(tot)
        say(f"  {r[0][:80]:80s} real {r[7]:+6.0f} | random mean {tot.mean():+6.0f}, best {tot.max():+6.0f}, {100 * (tot >= r[7]).mean():3.0f}% of draws as good")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
