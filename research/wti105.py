"""Round 105 (13 Nov 2026): WTI beyond scalping - first MEASURE how it moves, then test the families its behaviour points
to, on H1 / H4 / D1, last 2 years, with the broker's spread AND swap.  Owner: "kalau scalp tak jalan, cari cara lain bro. ada
lagi tf lain ... cuba la kaji sikit pergerakan dan sifat dia".
Data: a fresh M5 export of WTI from 2023-06 (input tf=M5, symbols=WTI, from=2023.06.01) so D1 indicators have a warm-up.
Part 1 (behaviour): when it moves (by MYT hour and weekday), persistence (variance ratio and autocorrelation on H1 / H4 / D1),
what follows a stretch away from the EMA 50 (H1 / H4) and a big day (D1), Monday gaps, the Wednesday EIA day, narrow days.
Part 2 (strategies): D1 trend (Donchian 20/10, 55/20, EMA 20/50, 20-day momentum), H4 / H1 Donchian and Ichimoku cloud
breakouts (gold's H1 edge), NR7 / inside-day breakout, big-day follow / fade, D1 RSI(2) pullback in the trend, Monday range
breakout, SMC on H1 / H4 (round 102 rules).  Every trade has a random-direction and an always-buy twin.  $ per 0.01 lot."""
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


def main():
    sym = "WTI"
    for ln in open(os.path.join(DATA, "meta.txt"), encoding="latin-1"):
        if ln.startswith(sym + ","): say("meta: " + ln.strip())
    mt, sw = W.read_meta(sym)
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    swl = sw["long"] * mt["point"] if sw and sw["mode"] == 1 else 0.0
    sws = sw["short"] * mt["point"] if sw and sw["mode"] == 1 else 0.0
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    B = d[["o", "h", "l", "c", "s"]].copy()
    say(f"WTI: {len(B):,} M5 bars {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; $ per 1.00 at 0.01 lot {usd:.2f}; swap a night at 0.01 lot: "
        f"long {swl * usd:+.3f}, short {sws * usd:+.3f} (swap mode {sw['mode'] if sw else '?'})")
    H1, H4, D1 = M.resample(B, 60), M.resample(B, 240), M.resample(B, 1440)
    D1 = D1[D1.index.day_of_week < 5]
    L2 = lambda X: X[X.index >= start]
    yr = lambda X: (X.index < mid)

    # ============ PART 1: BEHAVIOUR ============
    say("\n" + "=" * 30 + " PART 1: HOW WTI MOVES (last 2 years) " + "=" * 30)
    h1 = L2(H1); rng = (h1.h - h1.l) * usd; myt = (h1.index + pd.Timedelta(hours=6)).hour
    g = rng.groupby(myt).median()
    say("median H1 range $ (0.01 lot) by MALAYSIA hour (winter): " + "  ".join(f"{h:02d}:{g[h]:.1f}" for h in g.index))
    dd = L2(D1); dr = (dd.h - dd.l) * usd
    say("median D1 range $ by weekday: " + "  ".join(f"{n} {dr[dd.index.day_of_week == k].median():.1f}" for k, n in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri"))))
    say(f"D1 ATR median ${float(M.atr(D1)[D1.index >= start].median()) * usd:.1f}; price {dd.c.iloc[0]:.2f} -> {dd.c.iloc[-1]:.2f} "
        f"(high {dd.h.max():.2f}, low {dd.l.min():.2f})")
    say("\npersistence, year 1 | year 2:")
    for X, nm, qs in ((H1, "H1", (4, 12, 24)), (H4, "H4", (3, 6, 12)), (D1, "D1", (5, 10, 20))):
        x = L2(X); lr = np.log(x.c).diff().dropna(); y1 = lr.index < mid
        out = [f"lag-1 autocorr {lr[y1].autocorr():+.3f} | {lr[~y1].autocorr():+.3f}"]
        for q in qs:
            v = [pd.Series(lr[m].values).rolling(q).sum().dropna().var() / (q * lr[m].var()) for m in (y1, ~y1)]
            out.append(f"VR{q} {v[0]:.2f} | {v[1]:.2f}")
        say(f"  {nm}: " + "   ".join(out))
    say("\nwhat follows a stretch from the EMA 50 (distance in ATR, signed so + = keeps going AWAY), mean move in ATR, year 1 | year 2:")
    for X, nm, fwd in ((H1, "H1", (4, 12)), (H4, "H4", (3, 6))):
        e = X.c.ewm(span=50, adjust=False).mean(); a = M.atr(X); dist = (X.c - e) / a
        for f in fwd:
            mv = (X.c.shift(-f) - X.c) / a * np.sign(dist)
            m = X.index >= start
            row = []
            for lo, hi in ((0, 1), (1, 2), (2, 3), (3, 99)):
                b = m & (dist.abs() >= lo) & (dist.abs() < hi)
                row.append(f"{lo}-{hi if hi < 99 else '+'}: {mv[b & yr(X)].mean():+.2f} | {mv[b & ~yr(X)].mean():+.2f}")
            say(f"  {nm} +{f} bars  " + "   ".join(row))
    say("\nafter a big day (|D1 body| >= k ATR): next day's move in its direction, ATR, year 1 | year 2 (n):")
    a = M.atr(D1); body = D1.c - D1.o; nxt = (D1.c.shift(-1) - D1.o.shift(-1)) / a
    for k in (1.0, 1.5, 2.0):
        b = (body.abs() >= k * a.shift(1)) & (D1.index >= start)
        v = nxt * np.sign(body)
        say(f"  k {k}: {v[b & yr(D1)].mean():+.2f} ({int((b & yr(D1)).sum())}) | {v[b & ~yr(D1)].mean():+.2f} ({int((b & ~yr(D1)).sum())})")
    say("Monday open gap vs Friday close (ATR): " + f"median |gap| {float(((D1.o - D1.c.shift(1)).abs() / a.shift(1))[D1.index.day_of_week == 0].median()):.2f}")
    nr = (D1.h - D1.l); nr7 = nr <= nr.rolling(7).min()
    nx = ((D1.h.shift(-1) - D1.l.shift(-1)) / a)
    say(f"day after an NR7 day: range {nx[nr7 & (D1.index >= start)].mean():.2f} ATR vs all days {nx[D1.index >= start].mean():.2f}")

    # ============ PART 2: STRATEGIES ============
    say("\n" + "=" * 30 + " PART 2: STRATEGIES BY TIMEFRAME " + "=" * 30)
    Bw = B[B.index >= start - pd.Timedelta(days=10)]
    bk = M.Book(Bw, usd, swl, sws, start, mid, end)
    O, S = bk.O, bk.S
    res = []

    def go(name, sg):
        if sg is None or not len(sg): return
        sg = sg[(sg.i >= 0) & (sg.i < len(Bw) - 1)]
        sg = sg[sg.x > sg.i]
        x = M.line(name, bk.run(sg), mid, end)
        if x: res.append(x); M.show(x)

    hmw = (Bw.index.hour * 60 + Bw.index.minute).values

    def idx(times):
        """first M5 bar at or after each time that is outside the 23:45-01:30 rollover"""
        i = np.minimum(M.m5_index(Bw, times), len(Bw) - 1)
        for _ in range(30):
            bad = (hmw[i] < 90) | (hmw[i] >= 1425)
            if not bad.any(): break
            i = np.where(bad, np.minimum(i + 1, len(Bw) - 1), i)
        return i
    M.MIN_N = 8

    def entries_on_close(X, k_arr, dr_arr, sl_arr, tp_arr, x_times):
        """enter on the first M5 bar after bar k of X closes"""
        bar = pd.Timedelta(X.index[1] - X.index[0]) if len(X) > 1 else pd.Timedelta(hours=1)
        tm = X.index[k_arr] + (pd.Timedelta(days=1, minutes=90) if bar >= pd.Timedelta(days=1) else bar)
        return pd.DataFrame({"i": idx(tm), "d": dr_arr, "ep": np.nan, "sl": sl_arr, "tp": tp_arr, "x": idx(x_times)})

    # D1 trend
    say("\n-- T1 D1 trend-following (holds overnight, pays swap)"); say(M.HDR)
    aD = M.atr(D1)
    for ent_n, ex_n in ((20, 10), (55, 20), (10, 5)):
        hiN, loN = D1.h.rolling(ent_n).max().shift(1), D1.l.rolling(ent_n).min().shift(1)
        hiX, loX = D1.h.rolling(ex_n).max().shift(1), D1.l.rolling(ex_n).min().shift(1)
        rows = []; k = 0
        while k < len(D1):
            c = D1.c.iloc[k]; dr = 1 if c > hiN.iloc[k] else (-1 if c < loN.iloc[k] else 0)
            if dr == 0 or D1.index[k] < start - pd.Timedelta(days=5): k += 1; continue
            kx = k + 1
            while kx < len(D1) and not ((dr == 1 and D1.c.iloc[kx] < loX.iloc[kx]) or (dr == -1 and D1.c.iloc[kx] > hiX.iloc[kx])): kx += 1
            rows.append((k, dr, 2 * aD.iloc[k], np.nan, D1.index[min(kx, len(D1) - 1)] + pd.Timedelta(days=1, minutes=95)))
            k = kx
        if rows:
            r = pd.DataFrame(rows, columns=["k", "d", "sl", "tp", "xt"])
            go(f"T1 Donchian {ent_n}/{ex_n} D1, SL 2 ATR", entries_on_close(D1, r.k.values, r.d.values, r.sl.values, r.tp.values, r.xt.values))
    e20, e50 = D1.c.ewm(span=20, adjust=False).mean(), D1.c.ewm(span=50, adjust=False).mean()
    cr = np.sign(e20 - e50).values; ch = np.where(cr[1:] != cr[:-1])[0] + 1
    ks = [k for k in ch if D1.index[k] >= start - pd.Timedelta(days=5)]
    if ks:
        xt = [D1.index[(ch[ch > k][0] if (ch > k).any() else len(D1) - 1)] + pd.Timedelta(days=1, minutes=95) for k in ks]
        go("T1 EMA 20/50 D1 cross, SL 3 ATR", entries_on_close(D1, np.array(ks), cr[ks].astype(int), 3 * aD.values[ks], np.full(len(ks), np.nan), xt))
    for hold in (5, 10):
        mom = np.sign(D1.c - D1.c.shift(20))
        ks = np.arange(20, len(D1), hold); ks = ks[D1.index[ks] >= start - pd.Timedelta(days=5)]
        go(f"T1 20-day momentum, rebalance every {hold} days, SL 3 ATR", entries_on_close(D1, ks, mom.values[ks].astype(int), 3 * aD.values[ks],
           np.full(len(ks), np.nan), D1.index[np.minimum(ks + hold, len(D1) - 1)] + pd.Timedelta(days=1, minutes=95)))

    # H4 / H1 breakouts
    say("\n-- T2 H4 / H1 Donchian and Ichimoku cloud breakouts"); say(M.HDR)
    for X, nm in ((H4, "H4"), (H1, "H1")):
        a = M.atr(X)
        for N in (20, 55):
            up = X.c > X.h.rolling(N).max().shift(1); dn = X.c < X.l.rolling(N).min().shift(1)
            ks = np.where((up | dn) & (X.index >= start))[0]
            for hold in (12, 24):
                go(f"T2 {nm} Donchian {N}, SL 2 ATR, hold {hold} bars", entries_on_close(X, ks, np.where(up.values[ks], 1, -1), 2 * a.values[ks],
                   np.full(len(ks), np.nan), X.index[np.minimum(ks + hold + 1, len(X) - 1)]))
        tk = (X.h.rolling(9).max() + X.l.rolling(9).min()) / 2; kj = (X.h.rolling(26).max() + X.l.rolling(26).min()) / 2
        sa = ((tk + kj) / 2).shift(26); sb = ((X.h.rolling(52).max() + X.l.rolling(52).min()) / 2).shift(26)
        top, bot = np.maximum(sa, sb), np.minimum(sa, sb)
        bu = (X.c > top) & (X.c.shift(1) <= top.shift(1)) & (tk > kj); be = (X.c < bot) & (X.c.shift(1) >= bot.shift(1)) & (tk < kj)
        ks = np.where((bu | be) & (X.index >= start))[0]
        for hold in (12, 48):
            dr = np.where(bu.values[ks], 1, -1)
            slv = np.abs(X.c.values[ks] - np.where(dr == 1, bot.values[ks], top.values[ks])) + 0.2 * a.values[ks]
            go(f"T2 {nm} Kumo breakout, SL beyond the cloud, hold {hold} bars", entries_on_close(X, ks, dr, slv, np.full(len(ks), np.nan),
               X.index[np.minimum(ks + hold + 1, len(X) - 1)]))

    # D1 patterns
    say("\n-- T3 D1 patterns (intraday unless stated)"); say(M.HDR)
    day_open = lambda k: D1.index[k] + pd.Timedelta(days=1, minutes=95)
    day_end = lambda k: D1.index[k] + pd.Timedelta(days=1, hours=23, minutes=30)
    for nm, cond in (("NR7", nr7), ("inside day", (D1.h <= D1.h.shift(1)) & (D1.l >= D1.l.shift(1)))):
        ks = np.where(cond & (D1.index >= start - pd.Timedelta(days=2)))[0]
        rows = []
        for k in ks:
            if k + 1 >= len(D1): continue
            hi, lo = D1.h.iloc[k], D1.l.iloc[k]
            a_ = idx([day_open(k)])[0]; b_ = idx([day_end(k)])[0]
            if b_ <= a_: continue
            up = np.where(bk.H[a_:b_] >= hi)[0]; dn = np.where(bk.L[a_:b_] + S[a_:b_] <= lo)[0]
            fu = up[0] if len(up) else 10 ** 9; fd = dn[0] if len(dn) else 10 ** 9
            if fu == fd == 10 ** 9: continue
            j = a_ + min(fu, fd); dr = 1 if fu < fd else -1
            ep = max(hi + S[j], O[j] + S[j]) if dr == 1 else min(lo, O[j])
            rows.append((j, dr, ep, hi - lo, np.nan, b_))
        if rows: go(f"T3 {nm} breakout next day, SL other side, out 23:30", pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp", "x"]))
    for k_ in (1.5, 2.0):
        b = (body.abs() >= k_ * aD.shift(1)) & (D1.index >= start - pd.Timedelta(days=2))
        ks = np.where(b)[0]; ks = ks[ks + 1 < len(D1)]
        for mode in ("follow", "fade"):
            dr = (np.sign(body.values[ks]) * (1 if mode == "follow" else -1)).astype(int)
            go(f"T3 big day (>= {k_} ATR) {mode} next day", pd.DataFrame({"i": idx([day_open(k) for k in ks]), "d": dr, "ep": np.nan,
               "sl": aD.values[ks], "tp": np.nan, "x": idx([day_end(k) for k in ks])}))
    c = D1.c; dl = c.diff()
    rs = 100 - 100 / (1 + dl.clip(lower=0).ewm(alpha=0.5, adjust=False).mean() / (-dl.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean().replace(0, np.nan))
    e200 = c.ewm(span=100, adjust=False).mean()
    for th in (10, 20):
        bu = (rs < th) & (c > e200); be = (rs > 100 - th) & (c < e200)
        ks = np.where((bu | be) & (D1.index >= start - pd.Timedelta(days=2)))[0]; ks = ks[ks + 1 < len(D1)]
        dr = np.where(bu.values[ks], 1, -1)
        go(f"T3 D1 RSI(2) pullback < {th} with the EMA 100 trend, hold 3 days", pd.DataFrame({"i": idx([day_open(k) for k in ks]), "d": dr, "ep": np.nan,
           "sl": 2 * aD.values[ks], "tp": np.nan, "x": idx([day_open(min(k + 3, len(D1) - 1)) for k in ks])}))

    # SMC on H1 / H4
    say("\n-- T4 SMC (round 102 rules) on H1 / H4, killzone and all day"); say(M.HDR)
    try:
        import smc102 as SM
        SM.DATA = DATA; SM.PAIRS = ((60, 1440), (240, 1440)); SM.BUY_CTRL = True
        A, END = SM.run(sym, mt, sw)
        for c_ in ("entry", "tp", "typ"): A[c_] = A[c_].astype(str)
        A = A.sort_values("t", kind="stable")
        kz = ((A.hr >= 9) & (A.hr < 12)) | ((A.hr >= 14) & (A.hr < 17))
        for tf in (60, 240):
            for n_ in (3, 5):
                for en in ("OB top", "OTE 0.705"):
                    for tp in ("2R", "3R"):
                        for kzn, msk in (("all day", A.hr >= 0), ("killzone", kz)):
                            gg = SM.busy(A[(A.tf == tf) & (A.n == n_) & (A.entry == en) & (A.tp == tp) & (A.typ == "BOS") & msk])
                            if len(gg) < 20: continue
                            r = dict(n=len(gg), t=pd.DatetimeIndex(gg.t), pnl=(gg.r * gg.risk).values.astype(float), d=gg.d.values,
                                     risk=gg.risk.values.astype(float), swap=np.zeros(len(gg)), sp=(gg.sp * gg.risk).values.astype(float),
                                     rand=(gg.rr * gg.risk).values.astype(float)[~np.isnan(gg.rr.values)],
                                     buy=(gg.rb * gg.risk).values.astype(float)[~np.isnan(gg.rb.values)])
                            x = M.line(f"T4 SMC {'H1' if tf == 60 else 'H4'} n{n_} {en} TP {tp} {kzn}", r, mid, END)
                            if x: res.append(x); M.show(x)
    except Exception as e:
        say(f"T4 skipped: {e}")

    R = pd.DataFrame(res)
    R["fam"] = R.name.str.split(" ").str[0]
    say(f"\nSUMMARY: {int(R.ok.sum())} of {len(R)} pass ({int((R.n >= 150).sum())} with >= 150 trades); median PF {R.PF.median():.2f}, random {R.rand.median():.2f}, always-buy {R.ab.median():.2f}")
    for f, g_ in R.groupby("fam"):
        say(f"  {f}: {len(g_):3d} rows  PF median {g_.PF.median():.2f}  best {g_.PF.max():.2f}  rand {g_.rand.median():.2f}  trades/wk median {g_.wk.median():.1f}")
    say("\nTOP 15 by PF (>= 60 trades)"); say(M.HDR)
    for x in R[R.n >= 60].sort_values("PF", ascending=False).head(15).to_dict("records"): M.show(x)
    if R.ok.any():
        say("\nPASSES"); say(M.HDR)
        for x in R[R.ok].sort_values("PF", ascending=False).to_dict("records"): M.show(x)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
