"""Round 104 (13 Nov 2026): WTI scalping on the broker's own data, last 2 years.  Owner: "bro, scalping wti bro".
Data: a fresh M1 export of WTI.m (input tf=M1, symbols=WTI, from 2024.09.01); M5 / M15 are resampled from it.
Part 1 MEASURES what a WTI scalp pays: spread against the M1 / M5 / M15 / H1 ranges, by server hour, and whether short moves
persist or revert (variance ratio by session).  Part 2 TESTS the scalping families, every trade intraday (out by 23:30 server,
no swap), rollover entries dropped, each with a random-direction and an always-buy twin:
  S1 M1 spike fade / follow with the cost gate (gold's M1 edge transplanted)
  S2 M5 big-candle fade / follow (BTC's survivor)
  S3 opening-range breakout: NYMEX pit open 09:00 New York and London 08:00, first 15 / 30 min, OCO, SL other side
  S4 EIA crude inventories (Wednesday 10:30 New York): follow / fade the release candle
  S5 SMC: BOS + limit at the OB top / OTE in the killzone (round 102 rules) on M10 / M15 / M20
  S6 M5 mean reversion: RSI(2) and Bollinger 20,2 fades
  S7 time of day: entry every 30 min x hold 15 / 30 / 60 / 120 min, long / short, picked on year 1, judged on year 2
  S8 Asian range breakout (01:30-09:00 server)
$ per 0.01 lot (10 barrels: $1.00 of WTI move = $10).  Pass rule as always."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()


def read_meta(sym):
    for ln in open(os.path.join(DATA, "meta.txt"), encoding="latin-1"):
        p = ln.strip().split(",")
        if p and p[0] == sym and len(p) >= 12:
            mt = dict(sym=p[1], digits=int(p[2]), point=float(p[3]), tick_size=float(p[4]), tick_value=float(p[5]))
            sw = dict(mode=int(p[12]), long=float(p[13]), short=float(p[14]), d3=int(p[15])) if len(p) >= 16 else None
            return mt, sw
    raise SystemExit(f"{sym} not in the export")


def ny_to_server(dates, hh, mm):
    """New York wall-clock time on each date -> server (Europe/Athens) naive timestamps"""
    t = pd.DatetimeIndex(dates) + pd.Timedelta(hours=hh, minutes=mm)
    return t.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").tz_convert("Europe/Athens").tz_localize(None)


def ldn_to_server(dates, hh, mm):
    t = pd.DatetimeIndex(dates) + pd.Timedelta(hours=hh, minutes=mm)
    return t.tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT").tz_convert("Europe/Athens").tz_localize(None)


def main():
    sym = "WTI"
    mt, sw = read_meta(sym)
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    swl = sw["long"] * mt["point"] if sw and sw["mode"] == 1 else 0.0
    sws = sw["short"] * mt["point"] if sw and sw["mode"] == 1 else 0.0
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    B = d[["o", "h", "l", "c", "s"]].copy()
    step = int(np.median(np.diff(B.index.values[:5000]).astype("timedelta64[s]").astype(int)))
    say(f"WTI ({mt['sym']}): {len(B):,} bars of {step // 60} min, {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; $ per 1.00 at 0.01 lot {usd:.2f}; "
        f"swap long {swl * usd:+.3f} / short {sws * usd:+.3f} a night at 0.01 lot")

    # ---------------- PART 1
    say("\n" + "=" * 30 + " PART 1: WHAT A WTI SCALP PAYS (last 2 years) " + "=" * 30)
    L2 = B[B.index >= start]
    sp = float(L2.s.median()); px = float(L2.c.median())
    say(f"median price {px:.2f}, median spread {sp:.3f} = ${sp * usd:.2f} per 0.01 lot ({100 * sp / px:.3f}% of price)")
    for m, nm in ((1, "M1"), (5, "M5"), (15, "M15"), (60, "H1"), (1440, "D1")):
        X = L2 if m * 60 == step else M.resample(L2, m)
        a = float(M.atr(X).median())
        say(f"  {nm:3s} median ATR ${a * usd:6.2f}, spread = {100 * sp / a:5.1f}% of it")
    hr = L2.index.hour
    a1 = M.atr(L2)
    g = pd.DataFrame({"sp": L2.s * usd, "mv": (L2.h - L2.l) * usd, "r": L2.s / a1, "h": hr}).groupby("h").median()
    say("by server hour: median spread $ / median M1 range $ / spread over ATR(M1)")
    say("  " + "  ".join(f"{h:02d}:{g.sp[h]:.2f}/{g.mv[h]:.2f}/{g.r[h]:.2f}" for h in g.index))
    say("variance ratio of M1 log returns by session (> 1 trends, < 1 reverts), year 1 | year 2")
    lr = np.log(L2.c).diff()
    for nm, h0, h1 in (("Asia 01-09", 1, 9), ("London 09-15", 9, 15), ("NY 15-22", 15, 22)):
        out = []
        for q in (5, 15, 60):
            v = []
            for msk in (L2.index < mid, L2.index >= mid):
                x = lr[msk & (hr >= h0) & (hr < h1)].dropna().values
                v.append(pd.Series(x).rolling(q).sum().dropna().var() / (q * x.var()))
            out.append(f"q{q}: {v[0]:.2f} | {v[1]:.2f}")
        say(f"  {nm:12s} " + "   ".join(out))

    # ---------------- PART 2
    say("\n" + "=" * 30 + " PART 2: SCALPING FAMILIES " + "=" * 30)
    Bw = B[B.index >= start - pd.Timedelta(days=40)]
    bk = M.Book(Bw, usd, swl, sws, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    day = Bw.index.normalize()
    res = []

    def go(name, sig):
        if sig is None or len(sig) == 0: return
        x = M.line(name, bk.run(sig), mid, end)
        if x: res.append(x); M.show(x)

    exb = lambda i: M.exit_bar(Bw, i)
    bars_per = lambda minutes: max(1, minutes * 60 // step)

    say("\n-- S1 M1 spike fade / follow (|bar| >= k ATR(M1), ATR >= gate x spread; next open, SL 0.3 ATR beyond the bar)"); say(M.HDR)
    a = M.atr(Bw).values; body = C - O
    for k_ in (2.0, 2.5, 3.0, 4.0):
        for g_ in (4, 8, 12):
            for mode in ("fade", "follow"):
                for hold in (15, 45):
                    big = (np.abs(body) >= k_ * a) & (a >= g_ * S)
                    ii = np.where(big)[0] + 1; ii = ii[ii < len(Bw) - 1]
                    dr = (np.sign(body[ii - 1]) * (-1 if mode == "fade" else 1)).astype(int)
                    far = np.where(dr == 1, L[ii - 1], H[ii - 1]) if mode == "follow" else np.where(dr == 1, L[ii - 1], H[ii - 1])
                    mk = np.where(dr == 1, O[ii] + S[ii], O[ii])
                    dist = np.abs(mk - (far - dr * 0.3 * a[ii - 1]))
                    sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": dist, "tp": np.nan, "x": np.minimum(ii + bars_per(hold), exb(ii))})
                    go(f"S1 M1 {mode} k {k_} gate {g_} hold {hold}m", sg[sg.d != 0])

    say("\n-- S2 M5 big candle fade / follow (decided on the M5 close, entered on the next M1 bar)"); say(M.HDR)
    M5 = M.resample(Bw, 5); a5 = M.atr(M5).values; b5 = (M5.c - M5.o).values
    for k_ in (2.0, 2.5, 3.0):
        for g_ in (2, 4, 8):
            for mode in ("fade", "follow"):
                big = (np.abs(b5) >= k_ * a5) & (a5 >= g_ * M5.s.values)
                kk = np.where(big)[0]
                if not len(kk): continue
                ii = M.m5_index(Bw, M5.index[kk] + pd.Timedelta(minutes=5)); ok = ii < len(Bw) - 1; kk, ii = kk[ok], ii[ok]
                dr = (np.sign(b5[kk]) * (-1 if mode == "fade" else 1)).astype(int)
                far = np.where(dr == 1, M5.l.values[kk], M5.h.values[kk])
                mk = np.where(dr == 1, O[ii] + S[ii], O[ii])
                dist = np.abs(mk - (far - dr * 0.3 * a5[kk]))
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": dist, "tp": np.nan, "x": np.minimum(ii + bars_per(60), exb(ii))})
                go(f"S2 M5 {mode} k {k_} gate {g_} hold 60m", sg[sg.d != 0])

    say("\n-- S3 opening-range breakout (OCO at the range, SL other side, out 23:30)"); say(M.HDR)
    dates = pd.DatetimeIndex(day.unique())
    for nm, conv, hh, mm in (("NY pit 09:00", ny_to_server, 9, 0), ("London 08:00", ldn_to_server, 8, 0)):
        st0 = conv(dates, hh, mm)
        for rng_min in (15, 30):
            for tpr in (np.nan, 1.0, 2.0):
                rows = []
                for t0 in st0:
                    if pd.isna(t0): continue
                    a_ = np.searchsorted(Bw.index.values, np.datetime64(t0)); b_ = np.searchsorted(Bw.index.values, np.datetime64(t0 + pd.Timedelta(minutes=rng_min)))
                    if b_ - a_ < rng_min * 60 // step * 0.8 or b_ >= len(Bw) - 2: continue
                    hi, lo = H[a_:b_].max(), L[a_:b_].min(); rg = hi - lo
                    if rg <= 2 * S[b_]: continue
                    ex = exb(np.array([b_]))[0]
                    up = np.where(H[b_:ex] >= hi)[0]; dn = np.where(L[b_:ex] + S[b_:ex] <= lo)[0]
                    fu = up[0] if len(up) else 10 ** 9; fd = dn[0] if len(dn) else 10 ** 9
                    if fu == fd == 10 ** 9: continue
                    k = b_ + min(fu, fd); dr = 1 if fu < fd else -1
                    ep = max(hi + S[k], O[k] + S[k]) if dr == 1 else min(lo, O[k])
                    rows.append((k, dr, ep, rg, tpr * rg if tpr == tpr else np.nan, ex))
                if rows: go(f"S3 {nm} first {rng_min}m TP {'none' if tpr != tpr else f'{tpr:.0f}R'}", pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp", "x"]))

    say("\n-- S4 EIA crude inventories (Wednesdays 10:30 New York): the release candle, entered after it"); say(M.HDR)
    wed = dates[dates.day_of_week == 2]
    rel = ny_to_server(wed, 10, 30)
    for after in (5, 15):
        for hold in (15, 30, 60):
            for mode in ("follow", "fade"):
                rows = []
                for t0 in rel:
                    if pd.isna(t0): continue
                    a_ = np.searchsorted(Bw.index.values, np.datetime64(t0)); b_ = np.searchsorted(Bw.index.values, np.datetime64(t0 + pd.Timedelta(minutes=after)))
                    if b_ >= len(Bw) - 2 or a_ >= b_ or abs((Bw.index[a_] - t0).total_seconds()) > 120: continue
                    mv = C[b_ - 1] - O[a_]
                    if mv == 0: continue
                    dr = int(np.sign(mv)) * (1 if mode == "follow" else -1)
                    rows.append((b_, dr, np.nan, max(abs(mv), 4 * S[b_]), np.nan, min(b_ + bars_per(hold), len(Bw) - 1)))
                if rows: go(f"S4 EIA {mode} the first {after}m, hold {hold}m", pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp", "x"]))

    say("\n-- S5 SMC (round 102 rules) on WTI: BOS + limit, killzone 09-12 / 14-17 server, weekdays"); say(M.HDR)
    try:
        import smc102 as SM
        SM.DATA = DATA; SM.PAIRS = ((10, 240), (15, 240), (20, 240)); SM.BUY_CTRL = True
        A, END = SM.run(sym, mt, sw)
        for c_ in ("entry", "tp", "typ"): A[c_] = A[c_].astype(str)
        A = A.sort_values("t", kind="stable")
        kz = (((A.hr >= 9) & (A.hr < 12)) | ((A.hr >= 14) & (A.hr < 17))) & (pd.DatetimeIndex(A.t).day_of_week < 5)
        for tf in (10, 15, 20):
            for n_ in (3, 5):
                for en in ("OB top", "OTE 0.705"):
                    for tp in ("2R", "3R"):
                        gg = SM.busy(A[(A.tf == tf) & (A.n == n_) & (A.entry == en) & (A.tp == tp) & (A.typ == "BOS") & kz])
                        if len(gg) < 20: continue
                        r = dict(n=len(gg), t=pd.DatetimeIndex(gg.t), pnl=(gg.r * gg.risk).values.astype(float), d=gg.d.values,
                                 risk=gg.risk.values.astype(float), swap=np.zeros(len(gg)), sp=(gg.sp * gg.risk).values.astype(float),
                                 rand=(gg.rr * gg.risk).values.astype(float)[~np.isnan(gg.rr.values)], buy=(gg.rb * gg.risk).values.astype(float)[~np.isnan(gg.rb.values)])
                        x = M.line(f"S5 SMC M{tf} n{n_} {en} TP {tp}", r, mid, END)
                        if x: res.append(x); M.show(x)
    except Exception as e:
        say(f"S5 skipped: {e}")

    say("\n-- S6 M5 mean reversion, intraday (exit at the rule, 12 M5 bars or 23:30)"); say(M.HDR)
    c5 = M5.c; dl = c5.diff()
    up_ = dl.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean(); dn_ = (-dl.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    rsi2 = 100 - 100 / (1 + up_ / dn_.replace(0, np.nan)); m20 = c5.rolling(20).mean(); s20 = c5.rolling(20).std(ddof=0)
    for nm, cb, cs in (("RSI2 < 5 / > 95", rsi2 < 5, rsi2 > 95), ("BB 20,2 close outside", c5 < m20 - 2 * s20, c5 > m20 + 2 * s20)):
        for slk in (1.5, 3.0):
            kk = np.where(cb | cs)[0]
            ii = M.m5_index(Bw, M5.index[kk] + pd.Timedelta(minutes=5)); ok = ii < len(Bw) - 1; kk, ii = kk[ok], ii[ok]
            dr = np.where(cb.values[kk], 1, -1)
            tp = np.abs(m20.values[kk] - c5.values[kk]) if "BB" in nm else np.full(len(kk), np.nan)
            sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slk * a5[kk], "tp": tp, "x": np.minimum(ii + bars_per(60), exb(ii))})
            go(f"S6 {nm} SL {slk} ATR(M5)", sg)

    say("\n-- S7 time of day: entry at every :00 / :30 server, hold 15 / 30 / 60 / 120 min, long / short; year 1 picks, year 2 judges")
    sc = []
    for h in range(2, 23):
        for mn in (0, 30):
            tms = dates + pd.Timedelta(hours=h, minutes=mn)
            ii = np.searchsorted(Bw.index.values, tms.values); ok = ii < len(Bw) - 1; ii = ii[ok]
            ii = ii[(Bw.index[ii] - tms[ok]) < pd.Timedelta(minutes=2)]
            if len(ii) < 100: continue
            for hold in (15, 30, 60, 120):
                if h * 60 + mn + hold > 23 * 60 + 30: continue
                xi = np.minimum(ii + bars_per(hold), len(Bw) - 1)
                t = Bw.index[ii]; okw = t >= start
                for dr in (1, -1):
                    ep = O[ii] + (S[ii] if dr == 1 else 0); xp = O[xi] + (S[xi] if dr == -1 else 0)
                    p = (xp - ep) * dr * usd
                    p1, p2 = p[okw & (t < mid)], p[okw & (t >= mid)]
                    if len(p1) < 50: continue
                    t1 = p1.mean() / (p1.std() / np.sqrt(len(p1)) + 1e-12)
                    sc.append((t1, h, mn, hold, dr, pf(p1), pf(p2), p1.sum(), p2.sum()))
    sc.sort(reverse=True)
    for t1, h, mn, hold, dr, P1, P2, s1, s2 in sc[:12]:
        say(f"  {h:02d}:{mn:02d} {'BUY ' if dr == 1 else 'SELL'} hold {hold:3d}m: yr1 t {t1:+.1f} PF {P1:.2f} ${s1:+.0f} -> yr2 PF {P2:.2f} ${s2:+.0f}")
    top = [x for x in sc if x[0] >= 2.5]
    say(f"  {len(sc)} cells; year-1 t >= 2.5: {len(top)}, of those positive in year 2: {sum(1 for x in top if x[8] > 0)}; "
        f"all cells positive in year 2: {sum(1 for x in sc if x[8] > 0)}")

    say("\n-- S8 Asian range breakout 01:30-09:00 server (stop at the high / low, SL other side, out 23:30)"); say(M.HDR)
    for tpr in (np.nan, 1.0, 2.0):
        rows = []
        for dd, grp_idx in pd.Series(np.arange(len(Bw)), index=day).groupby(level=0):
            idx = grp_idx.values; hm = (Bw.index[idx].hour * 60 + Bw.index[idx].minute)
            rg_i = idx[(hm >= 90) & (hm < 540)]; af = idx[(hm >= 540) & (hm < 1380)]
            if len(rg_i) < 300 // (step // 60) or not len(af): continue
            hi, lo = H[rg_i].max(), L[rg_i].min(); rg = hi - lo
            up = np.where(H[af] >= hi)[0]; dn = np.where(L[af] + S[af] <= lo)[0]
            fu = up[0] if len(up) else 10 ** 9; fd = dn[0] if len(dn) else 10 ** 9
            if fu == fd == 10 ** 9 or rg <= 0: continue
            k = af[min(fu, fd)]; dr = 1 if fu < fd else -1
            ep = max(hi + S[k], O[k] + S[k]) if dr == 1 else min(lo, O[k])
            rows.append((k, dr, ep, rg, tpr * rg if tpr == tpr else np.nan, exb(np.array([k]))[0]))
        if rows: go(f"S8 Asia range TP {'none' if tpr != tpr else f'{tpr:.0f}R'}", pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp", "x"]))

    R = pd.DataFrame(res)
    if not len(R): say("no results"); return
    R["fam"] = R.name.str.split(" ").str[0]
    say(f"\nSUMMARY: {int(R.ok.sum())} of {len(R)} WTI variants pass ({int((R.n >= 150).sum())} with >= 150 trades); "
        f"median PF {R.PF.median():.2f}, random twin {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
    for f, g_ in R.groupby("fam"):
        say(f"  {f}: {len(g_):3d} rows  PF median {g_.PF.median():.2f}  best {g_.PF.max():.2f}  rand {g_.rand.median():.2f}  trades/wk median {g_.wk.median():.1f}")
    say("\nTOP 15 by PF (>= 100 trades)"); say(M.HDR)
    for x in R[R.n >= 100].sort_values("PF", ascending=False).head(15).to_dict("records"): M.show(x)
    if R.ok.any():
        say("\nPASSES"); say(M.HDR)
        for x in R[R.ok].sort_values("PF", ascending=False).to_dict("records"): M.show(x)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
