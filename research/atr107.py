"""Round 107 (13 Nov 2026): ATR-based techniques on gold, broker M1 data, last 2 years.  Owner: "cari teknik atr bro".
Data: gold M1 export run 43406389671 (from 2024-09-01); M5 / M15 / H1 / D1 built from it.  Families:
  A1 ATR exhaustion: today's range (from 01:30 server) reaches X x ATR14(D1) at a new high / low -> fade it or follow it
  A2 ATR bands from today's open: open +- k x ATR14(D1); first touch -> breakout follow (stop order) or fade (limit), out 23:30
  A3 Chandelier exit flip on M5 / M15 (highest high of n - m ATR(n) / lowest low + m ATR): trade each flip, exit on the
     opposite flip, a 4 h cap or 23:30; SL at the chandelier line
  A4 Keltner channel (EMA 20 +- m ATR 14) on M5 / M15: first close beyond -> follow (SL the EMA) or fade (TP the EMA)
  A5 big candle on M15 / H1: |body| >= k ATR14 of its own timeframe -> follow or fade at the next M1 open
  A6 ATR expansion: ATR5 / ATR50 of M5 crosses above x after being <= 1.0 within the last 12 bars -> follow / fade the
     last 6-bar move
Every trade has a random-direction and an always-buy twin (btc103.Book), costs = the bar's spread, rollover entries dropped,
intraday only.  $ per 0.01 lot.  Pass rule: >= 150 trades, PF >= 1.15, both years >= 1.05, stress >= 1.05, last 12 months
> 0, PF >= both twins + 0.10."""
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
def chandelier(H, L, C, A, n, m):
    """state +1 / -1 after each closed bar, and the active stop line; a flip happens on a close through the line"""
    k = len(C); st = np.zeros(k, np.int64); line = np.full(k, np.nan); s = 0
    for i in range(n, k):
        hh = H[i - n + 1:i + 1].max(); ll = L[i - n + 1:i + 1].min()
        ls = hh - m * A[i]; ss = ll + m * A[i]
        if s >= 0 and C[i] < ls: s = -1
        elif s <= 0 and C[i] > ss: s = 1
        st[i] = s; line[i] = ls if s == 1 else ss
    return st, line


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=60)][["o", "h", "l", "c", "s", "v"]].copy()
    bk = M.Book(Bw[["o", "h", "l", "c", "s"]], usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    say(f"GOLD M1 {len(Bw):,} bars {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; median spread ${float(np.median(S)) * usd:.3f}")
    res = []

    def go(name, sg, one=True):
        if sg is None or len(sg) == 0: return
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.i >= 0)]
        if len(sg) == 0: return
        x = M.line(name, bk.run(sg, one), mid, end)
        if x: res.append(x); M.show(x)

    mk = lambda ii, dr: np.where(dr == 1, O[ii] + S[ii], O[ii])
    gate = lambda j, g: (a1[j] >= g * S[j]) if g else np.ones(len(j), bool)

    # daily ATR (previous completed days only) and the trading-day windows 01:30 .. 23:30 server
    day = T.normalize()
    D = pd.DataFrame({"h": Bw.h.values, "l": Bw.l.values, "c": Bw.c.values, "d": day}).groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    c1 = D.c.shift()
    tr = np.maximum(D.h - D.l, np.maximum((D.h - c1).abs(), (D.l - c1).abs()))
    datr = tr.rolling(14).mean().shift(1)
    days = D.index[D.index >= start.normalize()]
    s0 = np.searchsorted(tv, (days + pd.Timedelta(minutes=90)).values)
    s1 = np.searchsorted(tv, (days + pd.Timedelta(minutes=1410)).values)
    A = datr.reindex(days).values
    say(f"median ATR14(D1) ${np.nanmedian(A) * usd:.1f}; median ATR14(M1) ${np.nanmedian(a1) * usd:.2f}")

    # ---------------------------------------------------------------- A1 exhaustion
    say("\n-- A1 ATR exhaustion: today's range reaches X x ATR(D1) at a new extreme -> fade / follow; SL / TP in ATR(D1)"); say(M.HDR)
    for X in (0.6, 0.8, 1.0, 1.2):
        rows = []
        for a, b, AA in zip(s0, s1, A):
            if not np.isfinite(AA) or b - a < 30: continue
            hh = np.maximum.accumulate(H[a:b]); ll = np.minimum.accumulate(L[a:b])
            k = np.where(hh - ll >= X * AA)[0]
            if not len(k): continue
            k = k[0]; j = a + k
            side = 1 if H[j] >= hh[k] else -1          # the bar that completed the range made a new high (+1) or low (-1)
            rows.append((j, side, AA, b))
        if not rows: continue
        f = np.array(rows); j = f[:, 0].astype(np.int64); side = f[:, 1].astype(int); AA = f[:, 2]; bb = f[:, 3].astype(np.int64)
        ii = j + 1
        for mode in ("fade", "follow"):
            dr = -side if mode == "fade" else side
            for slm, tpm, hold in ((0.2, 0.2, 120), (0.3, 0.3, 120), (0.2, np.nan, 120), (0.3, np.nan, 240), (0.15, 0.3, 120)):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slm * AA, "tp": tpm * AA, "x": np.minimum(ii + hold, bb)})
                go(f"A1 range {X} ATR {mode} SL {slm} TP {tpm} {hold}m", sg)

    # ---------------------------------------------------------------- A2 bands from today's open
    say("\n-- A2 open +- k x ATR(D1): first touch -> breakout (stop, SL the open) or fade (limit, TP the open, SL k/2 beyond)"); say(M.HDR)
    for kk in (0.25, 0.4, 0.6, 0.8):
        rb, rf = [], []
        for a, b, AA in zip(s0, s1, A):
            if not np.isfinite(AA) or b - a < 30: continue
            o = O[a]; up, dn = o + kk * AA, o - kk * AA
            j, dr, fp = G.scan_oco(O, H, L, S, a, b, up, dn)
            if j >= 0: rb.append((j, dr, fp, o, b, AA))
            ju = G.scan_limit(L, H, S, a, b, up, -1); jd = G.scan_limit(L, H, S, a, b, dn, 1)
            c_ = [(x_, d_, lv) for x_, d_, lv in ((ju, -1, up), (jd, 1, dn)) if x_ >= 0]
            if c_:
                x_, d_, lv = min(c_); rf.append((x_, d_, lv, o, b, AA))
        if rb:
            f = np.array(rb); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int); fp = f[:, 2]; o = f[:, 3]; bb = f[:, 4].astype(np.int64)
            sl = np.abs(fp - o)
            for tpn, tpd in (("none, out 23:30", np.full(len(ii), np.nan)), ("1R", sl), ("2R", 2 * sl)):
                go(f"A2 open band {kk} ATR breakout TP {tpn}", pd.DataFrame({"i": ii, "d": dr, "ep": fp, "sl": sl, "tp": tpd, "x": bb}))
            sg = pd.DataFrame({"i": ii, "d": dr, "ep": fp, "sl": 0.5 * sl, "tp": np.nan, "x": bb})
            go(f"A2 open band {kk} ATR breakout SL half way to open", sg)
        if rf:
            f = np.array(rf); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int); lv = f[:, 2]; o = f[:, 3]; bb = f[:, 4].astype(np.int64); AA = f[:, 5]
            dist = np.abs(lv - o)
            for slm in (0.5, 1.0):
                go(f"A2 open band {kk} ATR fade, TP open, SL {slm} x band", pd.DataFrame({"i": ii, "d": dr, "ep": lv, "sl": slm * dist, "tp": dist, "x": bb}))

    # ---------------------------------------------------------------- A3 chandelier flip
    say("\n-- A3 Chandelier exit flip (n, m ATR) on M5 / M15: trade the flip, exit on the opposite flip / 4 h / 23:30"); say(M.HDR)
    for tf in (5, 15):
        X = M.resample(Bw, tf)
        for nn, mm in ((22, 3.0), (22, 2.0), (14, 3.0), (14, 2.0)):
            XA = M.atr(X, nn).values
            st, ln = chandelier(X.h.values, X.l.values, X.c.values, XA, nn, mm)
            flip = np.where((st != 0) & (np.r_[0, st[:-1]] != 0) & (st != np.r_[0, st[:-1]]))[0]
            if len(flip) < 2: continue
            tclose = X.index[flip] + pd.Timedelta(minutes=tf)
            ii = np.searchsorted(tv, tclose.values); ok = ii < n - 1; flip, ii = flip[ok], ii[ok]
            dr = st[flip].astype(int)
            nxt = np.r_[ii[1:], n - 1]                                     # the next flip closes this one
            e = mk(ii, dr); sl = np.abs(e - ln[flip])
            for gg in (0, 8):
                for cap in (240, 60):
                    x = np.minimum(np.minimum(nxt, ii + cap), exb(ii)); x = np.maximum(x, ii + 1)
                    sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": np.nan, "x": x, "g": gate(np.maximum(ii - 1, 0), gg)})
                    go(f"A3 chandelier M{tf} n {nn} m {mm} gate {gg} cap {cap}m", sg[sg.g].drop(columns="g"))

    # ---------------------------------------------------------------- A4 Keltner channel
    say("\n-- A4 Keltner (EMA 20 +- m ATR14) on M5 / M15: first close beyond -> follow (SL EMA) / fade (TP EMA, SL 1 ATR)"); say(M.HDR)
    for tf in (5, 15):
        X = M.resample(Bw, tf); XA = M.atr(X).values; e20 = X.c.ewm(span=20, adjust=False).mean().values; xc = X.c.values
        for mm in (1.5, 2.0, 2.5, 3.0):
            up = xc > e20 + mm * XA; dn = xc < e20 - mm * XA
            upx = up & ~np.r_[False, up[:-1]]; dnx = dn & ~np.r_[False, dn[:-1]]
            k = np.where(upx | dnx)[0]
            tclose = X.index[k] + pd.Timedelta(minutes=tf)
            ii = np.searchsorted(tv, tclose.values); ok = ii < n - 1; k, ii = k[ok], ii[ok]
            side = np.where(upx[k], 1, -1)
            for gg in (0, 8):
                gm = gate(np.maximum(ii - 1, 0), gg)
                for mode in ("follow", "fade"):
                    dr = side if mode == "follow" else -side
                    e = mk(ii, dr)
                    for hold in (60, 120):
                        if mode == "follow":
                            sl = np.abs(e - e20[k]); tp = np.full(len(ii), np.nan)
                        else:
                            sl = XA[k] * 1.0; tp = np.abs(e - e20[k])
                        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": tp, "x": np.minimum(ii + hold, exb(ii))})
                        go(f"A4 Keltner M{tf} {mm} ATR {mode} gate {gg} {hold}m", sg[gm])

    # ---------------------------------------------------------------- A5 big candle M15 / H1
    say("\n-- A5 big candle: |body| >= k ATR14 of its timeframe -> follow / fade at the next M1 open"); say(M.HDR)
    for tf in (15, 60):
        X = M.resample(Bw, tf); XA = M.atr(X).values; body = (X.c - X.o).values
        for kk in (1.5, 2.0, 2.5):
            k = np.where(np.abs(body) >= kk * XA)[0]
            tclose = X.index[k] + pd.Timedelta(minutes=tf)
            ii = np.searchsorted(tv, tclose.values); ok = ii < n - 1; k, ii = k[ok], ii[ok]
            side = np.sign(body[k]).astype(int)
            for mode in ("follow", "fade"):
                dr = side if mode == "follow" else -side
                e = mk(ii, dr)
                if mode == "follow":
                    far = np.where(dr == 1, X.l.values[k], X.h.values[k]); sl = np.abs(e - (far - dr * 0.1 * XA[k]))
                    sl2 = 0.5 * np.abs(body[k])
                else:
                    ext = np.where(dr == 1, X.l.values[k], X.h.values[k]); sl = np.abs(e - (ext - dr * 0.25 * XA[k]))
                    sl2 = 0.5 * XA[k]
                for hold in (60, 120, 240):
                    go(f"A5 big M{tf} {kk} ATR {mode} SL bar {hold}m", pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))}))
                go(f"A5 big M{tf} {kk} ATR {mode} tight SL 120m", pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl2, "tp": np.nan, "x": np.minimum(ii + 120, exb(ii))}))

    # ---------------------------------------------------------------- A6 ATR expansion
    say("\n-- A6 ATR expansion on M5: ATR5/ATR50 crosses above x after <= 1.0 in the last 12 bars -> follow / fade the 6-bar move"); say(M.HDR)
    X = M.resample(Bw, 5); xc = X.c.values
    c1_ = X.c.shift()
    trx = np.maximum(X.h - X.l, np.maximum((X.h - c1_).abs(), (X.l - c1_).abs())).values
    r = pd.Series(trx).rolling(5).mean().values / pd.Series(trx).rolling(50).mean().values
    a50 = pd.Series(trx).rolling(50).mean().values
    calm = pd.Series(r <= 1.0).rolling(12).max().shift(1).fillna(0).values.astype(bool)
    for xr in (1.5, 2.0, 2.5):
        cx = (r >= xr) & np.r_[True, r[:-1] < xr] & calm
        k = np.where(cx)[0]; k = k[k >= 6]
        tclose = X.index[k] + pd.Timedelta(minutes=5)
        ii = np.searchsorted(tv, tclose.values); ok = ii < n - 1; k, ii = k[ok], ii[ok]
        side = np.sign(xc[k] - xc[k - 6]).astype(int)
        for mode in ("follow", "fade"):
            dr = side if mode == "follow" else -side
            for slm, hold in ((1.0, 60), (2.0, 60), (2.0, 120)):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slm * a50[k], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))})
                go(f"A6 expansion {xr}x {mode} SL {slm} ATR50 {hold}m", sg[sg.d != 0])

    # ---------------------------------------------------------------- summary
    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        say(f"{len(R)} variants with >= {M.MIN_N} trades; PASS {int(R.ok.sum())}")
        say(f"median PF {R.PF.median():.2f}, random twin {R.rand.median():.2f}, always-buy twin {R.ab.median():.2f}")
        say("by family: " + "  ".join(f"{f}: {g.PF.median():.2f} (rand {g.rand.median():.2f}, n {len(g)})" for f, g in R.groupby(R.name.str.split().str[0])))
        say("\nTOP 25 by PF with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(25).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
