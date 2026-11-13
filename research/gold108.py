"""Round 108 (13 Nov 2026): more gold scalps, NEW families only, short holds (5-30 minutes).
Owner: "cari scalping gold lagi bro. lain dari semua ni dan bukan pegang seharian atau berjam jam".
Data: one M1 export with gold and its neighbours (XAUUSD + XAGUSD, EURUSD, USDJPY and US indices where the broker has them),
from 2024-09; judged on the last 2 years.  Families (none run before in this project):
  L1 cross-asset spike lead: a 1-minute spike of k ATR on silver / EURUSD / USDJPY / an index while gold has not moved
     (|gold bar| < 0.5 ATR) -> trade gold the way that asset leads it (sign learned on year 1 only), hold 5-15 min
     (round 16 was a plain M5 lead-lag; this is spike-triggered on M1)
  L2 first minutes of an opening: London 08:00, NY data 08:30, COMEX 08:20, NY 09:30 and Tokyo 09:00 - follow or fade the
     move of the first 1 / 2 / 5 minutes, hold 5-30 min (round 33 scanned fixed-direction time windows, not this)
  L3 tick-volume at a 30-bar extreme: a new 30-bar high / low on weak volume (< 0.5x its 30-bar mean) -> fade; on strong
     volume (> 2x) -> follow; hold 10 / 20 min
  L4 micro double top / bottom on M1: a retest within 0.3 ATR of a 10-40-bar-old swing after a >= 1 ATR pullback, closing
     back away -> fade, TP the neckline or 20 min
  L5 big-wick rejection: a wick of >= k ATR with the close in the far 30% of the range -> trade away from the wick, 10-30 min
  L6 burst then stall: a 3-bar move of >= 3 ATR followed by a bar of < 0.5 ATR -> follow / fade, 10 min
Every trade has a random-direction and an always-buy twin (btc103.Book), real spread, rollover dropped.  $ per 0.01 lot."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()
OTHERS = ["XAGUSD", "EURUSD", "USDJPY", "US30", "US500", "NAS100", "USTEC", "US100", "DXY", "USDX", "GER40", "DE40"]


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=20)][["o", "h", "l", "c", "s", "v"]].copy()
    bk = M.Book(Bw[["o", "h", "l", "c", "s"]], usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    V = np.maximum(Bw.v.values.astype(float), 1.0)
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    say(f"GOLD M1 {n:,} bars {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, median spread ${np.median(S) * usd:.2f}, median ATR(M1) ${np.nanmedian(a1) * usd:.2f}")
    y1mask = T < mid
    res = []

    def go(name, sg):
        if sg is None or len(sg) == 0: return
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.d != 0)]
        if len(sg) == 0: return
        x = M.line(name, bk.run(sg), mid, end)
        if x:
            x["fam"] = name.split()[0]; res.append(x); M.show(x)

    mk = lambda ii, dr: np.where(dr == 1, O[ii] + S[ii], O[ii])
    nxt = lambda j: (j + 1)[(j + 1) < n - 1]

    # ---------------------------------------------------------------- L1 cross-asset spike lead
    say("\n-- L1 cross-asset 1-minute spike while gold has not moved -> gold the way the asset leads it"); say(M.HDR)
    gr = (C - O)
    for sym in OTHERS:
        p = os.path.join(DATA, sym + ".csv")
        if not os.path.exists(p): continue
        try: mx, _ = W.read_meta(sym)
        except SystemExit: continue
        X = SA.load(p, mx["point"])
        X = X[~X.index.duplicated()].reindex(T)
        ok = X.c.notna().values
        xa = M.atr(X.ffill()).values
        xr = (X.c - X.o).values
        # lead-lag measured on year 1: sign of corr(asset bar t, gold bars t+1..t+5)
        fut = pd.Series(C).shift(-5).values - C
        m1 = ok & y1mask & np.isfinite(xr) & np.isfinite(fut)
        cc = np.corrcoef(xr[m1], fut[m1])[0, 1] if m1.sum() > 1000 else 0
        c0 = np.corrcoef(xr[m1], gr[m1])[0, 1] if m1.sum() > 1000 else 0
        m2 = ok & ~y1mask & np.isfinite(xr) & np.isfinite(fut)
        cc2 = np.corrcoef(xr[m2], fut[m2])[0, 1] if m2.sum() > 1000 else 0
        sgn = 1 if c0 >= 0 else -1                                            # same-minute co-movement decides the expected way
        say(f"   {sym}: {int(ok.sum()):,} matched bars; corr(same minute) {c0:+.3f}; corr(asset bar, gold next 5 min) year 1 {cc:+.4f} / year 2 {cc2:+.4f}")
        for k in (2.0, 3.0, 4.0):
            for gmax in (0.5, 0.25):
                spike = ok & (np.abs(xr) >= k * xa) & (np.abs(gr) < gmax * a1) & (a1 >= 8 * S)
                j = np.where(spike)[0]; ii = nxt(j); j = ii - 1
                dr = (np.sign(xr[j]) * sgn).astype(int)
                for hold in (5, 15):
                    sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 1.5 * a1[j], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))})
                    go(f"L1 {sym} spike {k} ATR gold<{gmax} hold {hold}m", sg)

    # ---------------------------------------------------------------- L2 first minutes of an opening
    say("\n-- L2 opening minutes: follow / fade the first m minutes' move, hold h"); say(M.HDR)
    dates = pd.DatetimeIndex(T.normalize().unique())
    tky = lambda ds, hh, mm: (pd.DatetimeIndex(ds) + pd.Timedelta(hours=hh, minutes=mm)).tz_localize("Asia/Tokyo").tz_convert("Europe/Athens").tz_localize(None)
    opens = (("London 08:00", W.ldn_to_server(dates, 8, 0)), ("COMEX 08:20 NY", W.ny_to_server(dates, 8, 20)),
             ("NY data 08:30", W.ny_to_server(dates, 8, 30)), ("NY 09:30", W.ny_to_server(dates, 9, 30)), ("Tokyo 09:00", tky(dates, 9, 0)))
    for nm, ts in opens:
        ts = ts.dropna(); ts = ts[ts.dayofweek < 5]
        a = np.searchsorted(tv, ts.values.astype("datetime64[ns]"))
        okk = (a < n - 40) & (np.abs(tv[np.minimum(a, n - 1)] - ts.values.astype("datetime64[ns]")) < np.timedelta64(60, "s"))
        a = a[okk]
        for m in (1, 2, 5):
            mv = C[a + m - 1] - O[a]
            for thr in (0.0, 1.0):
                sel = np.abs(mv) >= thr * a1[a]
                ii = a[sel] + m; side = np.sign(mv[sel]).astype(int)
                for mode in ("follow", "fade"):
                    dr = side if mode == "follow" else -side
                    for hold in (5, 15, 30):
                        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 2.0 * a1[ii - 1], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))})
                        go(f"L2 {nm} first {m}m >= {thr} ATR {mode} {hold}m", sg)

    # ---------------------------------------------------------------- L3 volume at the extreme
    say("\n-- L3 new 30-bar high / low: weak volume -> fade, strong volume -> follow (gate 8)"); say(M.HDR)
    hh = pd.Series(H).shift(1).rolling(30).max().values; ll = pd.Series(L).shift(1).rolling(30).min().values
    vm = pd.Series(V).shift(1).rolling(30).mean().values
    up = (H > hh) & (a1 >= 8 * S); dn = (L < ll) & (a1 >= 8 * S)
    for lab, cond, mode in (("weak <0.5x", V < 0.5 * vm, "fade"), ("weak <0.7x", V < 0.7 * vm, "fade"), ("strong >2x", V > 2 * vm, "follow"),
                            ("strong >3x", V > 3 * vm, "follow"), ("strong >2x", V > 2 * vm, "fade")):
        bu = up & cond; bd = dn & cond & ~bu
        j = np.where(bu | bd)[0]; ii = nxt(j); j = ii - 1
        side = np.where(bu[j], 1, -1); dr = side if mode == "follow" else -side
        ext = np.where(side == 1, H[j], L[j])
        e = mk(ii, dr)
        for hold in (10, 20):
            sl = np.abs(e - (ext + side * 0.5 * a1[j])) if mode == "fade" else 1.5 * a1[j]
            go(f"L3 30-bar break, vol {lab} {mode} {hold}m", pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))}))

    # ---------------------------------------------------------------- L4 micro double top / bottom
    say("\n-- L4 M1 double top / bottom: retest within 0.3 ATR of a 10-40-bar-old swing after a >= 1 ATR pullback"); say(M.HDR)
    sw_h = pd.Series(H).shift(10).rolling(31).max().values            # max of H[j-40 .. j-10]
    sw_l = pd.Series(L).shift(10).rolling(31).min().values
    rec_h = pd.Series(H).shift(1).rolling(9).max().values             # H[j-9 .. j-1]
    rec_l = pd.Series(L).shift(1).rolling(9).min().values
    mid_l = pd.Series(L).shift(1).rolling(39).min().values            # lowest low between (neckline proxy)
    mid_h = pd.Series(H).shift(1).rolling(39).max().values
    for tol in (0.3, 0.6):
        for gg in (0, 8):
            g_ = (a1 >= gg * S) if gg else np.ones(n, bool)
            top = (np.abs(H - sw_h) <= tol * a1) & (rec_h < sw_h - 0.2 * a1) & (sw_h - mid_l >= 1.0 * a1) & (C < (H + L) / 2) & g_
            bot = (np.abs(L - sw_l) <= tol * a1) & (rec_l > sw_l + 0.2 * a1) & (mid_h - sw_l >= 1.0 * a1) & (C > (H + L) / 2) & g_ & ~top
            j = np.where(top | bot)[0]; ii = nxt(j); j = ii - 1
            dr = np.where(top[j], -1, 1); e = mk(ii, dr)
            ext = np.where(dr == -1, np.maximum(H[j], sw_h[j]), np.minimum(L[j], sw_l[j]))
            sl = np.abs(e - (ext - dr * 0.3 * a1[j]))
            neck = np.where(dr == -1, e - mid_l[j], mid_h[j] - e)
            for tpn, tp, hold in (("neckline", neck, 30), ("none", np.full(len(ii), np.nan), 20), ("1R", sl, 30)):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": tp, "x": np.minimum(ii + hold, exb(ii))})
                go(f"L4 double top/bottom tol {tol} gate {gg} TP {tpn}", sg[(sg.tp > 0) | sg.tp.isna()])

    # ---------------------------------------------------------------- L5 big wick rejection
    say("\n-- L5 big-wick rejection: wick >= k ATR, close in the far 30% of the bar -> trade away from the wick"); say(M.HDR)
    rng_ = np.maximum(H - L, 1e-9)
    lw = np.minimum(O, C) - L; uw = H - np.maximum(O, C)
    for k in (1.5, 2.0, 3.0):
        for gg in (0, 8):
            g_ = (a1 >= gg * S) if gg else np.ones(n, bool)
            bl = (lw >= k * a1) & ((C - L) / rng_ >= 0.7) & g_
            br = (uw >= k * a1) & ((H - C) / rng_ >= 0.7) & g_ & ~bl
            j = np.where(bl | br)[0]; ii = nxt(j); j = ii - 1
            dr = np.where(bl[j], 1, -1); e = mk(ii, dr)
            sl = np.abs(e - np.where(dr == 1, L[j] - 0.2 * a1[j], H[j] + 0.2 * a1[j]))
            for hold in (10, 30):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))})
                go(f"L5 wick {k} ATR gate {gg} {hold}m", sg)
                go(f"L5 wick {k} ATR gate {gg} {hold}m BUY side", sg[sg.d == 1])
                go(f"L5 wick {k} ATR gate {gg} {hold}m SELL side", sg[sg.d == -1])

    # ---------------------------------------------------------------- L6 burst then stall
    say("\n-- L6 3-bar burst >= 3 ATR then a stall bar < 0.5 ATR -> follow / fade, 10 min"); say(M.HDR)
    m3 = C - np.r_[np.full(3, np.nan), C[:-3]]
    m3p = np.r_[np.nan, m3[:-1]]                                          # the 3-bar move ending at the previous bar
    a1p = np.r_[np.nan, a1[:-1]]
    for kk in (3.0, 4.0):
        st = (np.abs(m3p) >= kk * a1p) & ((H - L) < 0.5 * a1) & (a1 >= 8 * S)
        j = np.where(st)[0]; ii = nxt(j); j = ii - 1
        side = np.sign(m3p[j]).astype(int)
        for mode in ("follow", "fade"):
            dr = side if mode == "follow" else -side
            for hold in (10, 20):
                go(f"L6 burst {kk} ATR + stall {mode} {hold}m", pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 1.5 * a1[j], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))}))

    # ---------------------------------------------------------------- summary
    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        say(f"{len(R)} variants with >= {M.MIN_N} trades; PASS {int(R.ok.sum())}; median PF {R.PF.median():.2f}, random {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
        say("by family: " + "  ".join(f"{f}: {g.PF.median():.2f} (rand {g.rand.median():.2f}, n {len(g)})" for f, g in R.groupby("fam")))
        say("\nTOP 25 by PF with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(25).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
