"""Round 106 (13 Nov 2026): NEW gold scalping families on the broker's own M1 data, last 2 years.
Owner: "bro, balik semula pada gold. apa lagi teknik scalp yang boleh di pasang? aku nak kau cari yang baru".
Data: a fresh gold M1 export (tf=M1, symbols=XAUUSD, from 2024.09.01); M5 / M15 / H1 are resampled from it.
Only families NOT run before in this project (see CLAUDE.md rounds 15-105):
  F1  session VWAP bands (tick-volume weighted, anchored at London 08:00 and New York 09:30): fade +-K sd back to the VWAP,
      or follow a close beyond +-K sd
  F2  absorption: a high-tick-volume M1 bar with a small range at a 20-bar high / low, fade or follow
  F3  sweep and reclaim of the previous H1 / H4 / M15 block high / low: price runs beyond it, an M1 close back inside within
      W bars -> fade the sweep; TP the other side of the block or 2R
  F4  H1-open magnet: in minutes 30-50 of the hour, price >= k ATR(M5) from the hour's open -> fade to the open (or follow)
  F5  initial balance (first 60 min of New York 09:30 / London 08:00): close beyond it -> follow; a 0.5 / 1.0 x IB extension
      -> fade back to the IB edge (limit)
  F6  M5 / M15 inside-bar OCO breakout in the killzone (09-12 / 14-17 server), SL other side of the mother bar, TP 1R / 2R
  F7  three-timeframe pullback: M15 EMA 20 slope + M5 close on the same side of its EMA 20 + M1 RSI(3) crossing < 20 / > 80
  F8  volatility contraction: ATR5 / ATR60 of M1 true range < x, then a close out of the 15-bar range -> follow
  F9  standalone M5 displacement FVG: a >= 1.5 ATR(M5) bar that leaves a gap, limit at the gap top / middle, SL under the
      displacement bar, TP 2R / 3R
  F10 London-to-New-York continuation on gold: at New York 09:30 follow / fade the move since London 08:00, out 22:00
  F11 Monday gap fade
Every trade has a RANDOM-direction twin and an ALWAYS-BUY twin (btc103.Book), costs = the bar's real spread, rollover entries
dropped, everything intraday.  $ per 0.01 lot.  Pass rule: >= 150 trades, PF >= 1.15, both years >= 1.05, stress >= 1.05,
last 12 months > 0, PF >= both twins + 0.10."""
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
try:
    from numba import njit
except Exception:
    njit = None
jit = (lambda f: njit(cache=False)(f)) if njit else (lambda f: f)


@jit
def scan_limit(L, H, S, a, b, lvl, dr):
    """first bar in [a, b) where a buy limit (dr 1, ask low <= lvl) / sell limit (dr -1, bid high >= lvl) fills, else -1"""
    for j in range(a, min(b, len(L))):
        if dr == 1 and L[j] + S[j] <= lvl: return j
        if dr == -1 and H[j] >= lvl: return j
    return -1


@jit
def scan_oco(O, H, L, S, a, b, up, dn):
    """first stop of an OCO pair to trigger in [a, b): returns (bar, dir, fill price) or (-1, 0, 0)"""
    for j in range(a, min(b, len(O))):
        bu = H[j] + S[j] >= up; se = L[j] <= dn
        if bu and se:
            return -1, 0, 0.0          # both in one bar: ambiguous, skip
        if bu: return j, 1, max(O[j] + S[j], up)
        if se: return j, -1, min(O[j], dn)
    return -1, 0, 0.0


@jit
def sweep_loop(H, L, C, blk, ph, pl, thr, wmax):
    """per M1 bar: price breaks the previous block's low by >= thr, then an M1 close back above it within wmax bars -> buy
    (mirror at the high). One signal per side per block. Returns arrays (bar, dir, extreme)."""
    n = len(C); out_i = []; out_d = []; out_x = []
    cur = -1; bl = -1; bh = -1; mnl = 0.0; mxh = 0.0; usedb = False; useds = False
    for j in range(n):
        if blk[j] != cur:
            cur = blk[j]; bl = -1; bh = -1; usedb = False; useds = False
        if ph[j] != ph[j] or thr[j] != thr[j]: continue
        if bl == -1 and L[j] <= pl[j] - thr[j]:
            bl = j; mnl = L[j]
        elif bl != -1:
            mnl = min(mnl, L[j])
        if bh == -1 and H[j] >= ph[j] + thr[j]:
            bh = j; mxh = H[j]
        elif bh != -1:
            mxh = max(mxh, H[j])
        if bl != -1 and not usedb and j - bl <= wmax and C[j] > pl[j]:
            out_i.append(j); out_d.append(1); out_x.append(mnl); usedb = True
        if bh != -1 and not useds and j - bh <= wmax and C[j] < ph[j]:
            out_i.append(j); out_d.append(-1); out_x.append(mxh); useds = True
    return np.array(out_i, dtype=np.int64), np.array(out_d, dtype=np.int64), np.array(out_x)


def rsi(c, n):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().values; ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + au / np.maximum(ad, 1e-12))


def main():
    sym = "XAUUSD"
    mt, sw = W.read_meta(sym)
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=40)][["o", "h", "l", "c", "s", "v"]].copy()
    step = int(np.median(np.diff(Bw.index.values[:5000]).astype("timedelta64[s]").astype(int)))
    say(f"GOLD ({mt['sym']}): {len(Bw):,} bars of {step // 60} min, {Bw.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; $ per 1.00 at 0.01 lot "
        f"{usd:.2f}; median spread ${float(Bw.s[Bw.index >= start].median()) * usd:.3f}")
    if step != 60: raise SystemExit("needs an M1 export")
    bk = M.Book(Bw[["o", "h", "l", "c", "s"]], usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    V = np.maximum(Bw.v.values.astype(float), 1.0)
    T = Bw.index; ns = T.asi8; n = len(Bw)
    day = T.normalize()
    a1 = M.atr(Bw).values
    M5 = M.resample(Bw, 5); a5f = M.atr(M5)
    a5 = pd.Series(a5f.values, index=M5.index + pd.Timedelta(minutes=5)).reindex(T, method="ffill").values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    res = []

    def go(name, sg, one=True):
        if sg is None or len(sg) == 0: return
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1)]
        if len(sg) == 0: return
        x = M.line(name, bk.run(sg, one), mid, end)
        if x: res.append(x); M.show(x)

    def mk_entry(ii, dr):
        return np.where(dr == 1, O[ii] + S[ii], O[ii])

    gate = lambda j, g: (a1[j] >= g * S[j]) if g else np.ones(len(j), bool)
    dates = pd.DatetimeIndex(day.unique())

    # ---------------------------------------------------------------- F1 session VWAP
    say("\n-- F1 session VWAP bands (anchored London 08:00 / New York 09:30, tick-volume weighted)"); say(M.HDR)
    a_l = W.ldn_to_server(dates, 8, 0); a_n = W.ny_to_server(dates, 9, 30)
    a_e = dates + pd.Timedelta(minutes=1410)
    st = np.sort(np.r_[a_l.dropna().values, a_n.dropna().values]).astype("datetime64[ns]")
    nd = np.r_[st[1:], st[-1:]]
    nd = np.minimum(nd, (pd.DatetimeIndex(st).normalize() + pd.Timedelta(minutes=1410)).values)
    seg = np.searchsorted(st, T.values, side="right") - 1
    ok = (seg >= 0) & (T.values < nd[np.maximum(seg, 0)])
    seg = np.where(ok, seg, -1)
    tp_ = (H + L + C) / 3
    g = pd.DataFrame({"seg": seg, "v": V, "pv": V * tp_, "pv2": V * tp_ * tp_})
    g.loc[g.seg < 0, ["v", "pv", "pv2"]] = 0
    cv = g.groupby("seg").v.cumsum().values; cpv = g.groupby("seg").pv.cumsum().values; cpv2 = g.groupby("seg").pv2.cumsum().values
    cnt = g.groupby("seg").cumcount().values
    vw = cpv / np.maximum(cv, 1e-9); sd = np.sqrt(np.maximum(cpv2 / np.maximum(cv, 1e-9) - vw * vw, 0))
    vw[seg < 0] = np.nan; sd[seg < 0] = np.nan; sd[cnt < 15] = np.nan
    segend = np.searchsorted(T.values, nd[np.maximum(seg, 0)])
    for K in (1.5, 2.0, 2.5, 3.0):
        up_ = C > vw + K * sd; dn_ = C < vw - K * sd
        upx = up_ & ~np.r_[False, up_[:-1]]; dnx = dn_ & ~np.r_[False, dn_[:-1]]
        for mode in ("fade", "follow"):
            for gg in (0, 8):
                for exitm in ("vwap", "60m") if mode == "fade" else ("1R", "60m"):
                    j = np.where((upx | dnx) & (seg >= 0))[0]; j = j[gate(j, gg)]
                    ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
                    dr = np.where(upx[j], 1, -1) * (-1 if mode == "fade" else 1)
                    e = mk_entry(ii, dr)
                    if mode == "fade":
                        tpd = (vw[j] - e) * dr if exitm == "vwap" else np.full(len(ii), np.nan)
                        sl = sd[j] * 1.0
                    else:
                        sl = np.abs(e - vw[j]); tpd = sl if exitm == "1R" else np.full(len(ii), np.nan)
                    x = np.minimum(np.minimum(ii + 60, segend[j]), exb(ii)); x = np.maximum(x, ii + 1)
                    sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": tpd, "x": x})
                    if mode == "fade" and exitm == "vwap": sg = sg[sg.tp > 0]
                    go(f"F1 VWAP {mode} {K}sd gate {gg} exit {exitm}", sg)

    # ---------------------------------------------------------------- F2 absorption
    say("\n-- F2 absorption: tick volume >= m x its 60-bar mean, range <= 0.5 ATR(M1), at a 20-bar high / low"); say(M.HDR)
    vm = pd.Series(V).shift(1).rolling(60).mean().values
    hh20 = pd.Series(H).shift(1).rolling(20).max().values; ll20 = pd.Series(L).shift(1).rolling(20).min().values
    for mult in (3, 5):
        for mode in ("fade", "follow"):
            for slm, tpm in ((1.0, 1.0), (2.0, 2.0), (1.0, np.nan)):
                cond = (V >= mult * vm) & ((H - L) <= 0.5 * a1) & (a1 >= 8 * S)
                hi = cond & (H >= hh20); lo = cond & (L <= ll20) & ~hi
                j = np.where(hi | lo)[0]; ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
                dr = np.where(hi[j], -1, 1) * (1 if mode == "fade" else -1)
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slm * a1[j], "tp": tpm * a1[j],
                                   "x": np.minimum(ii + 30, exb(ii))})
                go(f"F2 absorb vol {mult}x {mode} SL {slm} TP {tpm} ATR 30m", sg)

    # ---------------------------------------------------------------- F3 sweep & reclaim of the previous block
    say("\n-- F3 sweep beyond the previous M15 / H1 / H4 block high / low, M1 close back inside within W bars -> fade"); say(M.HDR)
    for P in (15, 60, 240):
        blk = ns // (P * 60 * 10 ** 9)
        df = pd.DataFrame({"b": blk, "h": H, "l": L})
        agg = df.groupby("b").agg(h=("h", "max"), l=("l", "min"))
        prevb = agg.shift(1)
        prevb = prevb[(agg.index.to_series().diff() == 1).values]          # only a directly preceding block
        ph = prevb.h.reindex(blk).values; pl = prevb.l.reindex(blk).values
        bend = np.searchsorted(blk, blk + 1)                                   # first bar of the next block
        for k in (0.1, 0.3):
            for wmax in (3, 10):
                thr = k * a5
                si, sdir, sx = sweep_loop(H, L, C, blk, ph, pl, thr, wmax)
                if not len(si): continue
                ii = si + 1; okk = ii < n - 1; si, sdir, sx, ii = si[okk], sdir[okk], sx[okk], ii[okk]
                e = mk_entry(ii, sdir)
                sl = np.abs(e - (sx - sdir * 0.1 * a5[si]))
                for tpm in ("other", "2R", "1R"):
                    if tpm == "other": tpd = np.where(sdir == 1, ph[si] - e, e - pl[si])
                    elif tpm == "2R": tpd = 2 * sl
                    else: tpd = sl.copy()
                    for gg in (0, 8):
                        sg = pd.DataFrame({"i": ii, "d": sdir, "ep": np.nan, "sl": sl, "tp": tpd,
                                           "x": np.minimum(ii + max(P, 30), exb(ii)), "g": gate(si, gg)})
                        sg = sg[sg.g & (sg.tp > 0)].drop(columns="g")
                        go(f"F3 sweep M{P} k {k} W {wmax} TP {tpm} gate {gg}", sg)

    # ---------------------------------------------------------------- F4 H1-open magnet
    say("\n-- F4 H1-open magnet: minutes 30-50 of the hour, close >= k ATR(M5) from the hour open (first time) -> fade / follow"); say(M.HDR)
    hb = ns // (3600 * 10 ** 9)
    first = np.r_[True, hb[1:] != hb[:-1]]
    hopen = pd.Series(np.where(first, O, np.nan)).ffill().values
    nxt = np.searchsorted(hb, hb + 1)
    mnt = T.minute.values
    for k in (1.0, 1.5, 2.0, 3.0):
        far = np.abs(C - hopen) >= k * a5
        win = (mnt >= 30) & (mnt <= 50) & far
        dfw = pd.DataFrame({"hb": hb, "w": win})
        firstw = win & (dfw.groupby("hb").w.cumsum().values == 1)
        j = np.where(firstw)[0]; ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
        side = np.sign(C[j] - hopen[j]).astype(int)
        for mode in ("fade", "follow"):
            for gg in (0, 8):
                dr = -side if mode == "fade" else side
                e = mk_entry(ii, dr); dist = np.abs(e - hopen[j])
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": dist if mode == "fade" else dist,
                                   "tp": dist if mode == "fade" else dist, "x": np.maximum(np.minimum(nxt[j], exb(ii)), ii + 1),
                                   "g": gate(j, gg)})
                sg = sg[sg.g].drop(columns="g")
                go(f"F4 hour-open {mode} k {k} gate {gg} 1:1 out at hour end", sg)
                if mode == "fade":
                    sg2 = sg.copy(); sg2["sl"] = sg2.sl * 0.5
                    go(f"F4 hour-open fade k {k} gate {gg} SL 0.5x TP open", sg2)

    # ---------------------------------------------------------------- F5 initial balance
    say("\n-- F5 initial balance (first 60 min): follow a close beyond it / fade a 0.5-1.0 x extension back to the edge"); say(M.HDR)
    for nm, conv, hh_, mm_ in (("NY 09:30", W.ny_to_server, 9, 30), ("LDN 08:00", W.ldn_to_server, 8, 0)):
        a0 = conv(dates, hh_, mm_).dropna()
        ia = np.searchsorted(T.values, a0.values); ib = np.searchsorted(T.values, (a0 + pd.Timedelta(minutes=60)).values)
        ic = np.searchsorted(T.values, (a0 + pd.Timedelta(minutes=300)).values)
        rows_f, rows_x = [], {0.5: [], 1.0: []}
        for s0, s1, s2 in zip(ia, ib, ic):
            if s1 - s0 < 50 or s1 >= n - 2 or T[s0].normalize() != T[min(s1, n - 1)].normalize(): continue
            ih, il = H[s0:s1].max(), L[s0:s1].min(); w = ih - il
            if w <= 0: continue
            s2 = min(s2, n - 1)
            seg_c = C[s1:s2]
            k_up = np.where(seg_c > ih)[0]; k_dn = np.where(seg_c < il)[0]
            ku = k_up[0] if len(k_up) else 10 ** 9; kd = k_dn[0] if len(k_dn) else 10 ** 9
            if min(ku, kd) < 10 ** 9:
                jj = s1 + min(ku, kd); dr = 1 if ku < kd else -1
                rows_f.append((jj + 1, dr, w, ih, il))
            for E in (0.5, 1.0):
                lu = scan_limit(L, H, S, s1, s2, ih + E * w, -1); ld = scan_limit(L, H, S, s1, s2, il - E * w, 1)
                cand = [(lu, -1, ih + E * w), (ld, 1, il - E * w)]
                cand = [c_ for c_ in cand if c_[0] >= 0]
                if cand:
                    jj, dr, lv = min(cand)
                    rows_x[E].append((jj, dr, lv, w))
        if rows_f:
            f = np.array(rows_f); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int); w = f[:, 2]
            ok_ = ii < n - 1; ii, dr, w, f = ii[ok_], dr[ok_], w[ok_], f[ok_]
            e = mk_entry(ii, dr); midp = (f[:, 3] + f[:, 4]) / 2
            for tpn, tpd in (("1R", np.abs(e - midp)), ("IB width", w), ("none 120m", np.full(len(ii), np.nan))):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": np.abs(e - midp), "tp": tpd,
                                   "x": np.minimum(ii + 120, exb(ii)) if tpn.startswith("none") else exb(ii)})
                go(f"F5 IB {nm} follow, SL IB mid, TP {tpn}", sg)
        for E, rr in rows_x.items():
            if not rr: continue
            f = np.array(rr); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int); lv = f[:, 2]; w = f[:, 3]
            for slm in (0.25, 0.5):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": lv, "sl": slm * w, "tp": E * w, "x": np.minimum(ii + 120, exb(ii))})
                go(f"F5 IB {nm} fade {E}x extension, TP IB edge, SL {slm} IB", sg)

    # ---------------------------------------------------------------- F6 inside-bar OCO in the killzone
    say("\n-- F6 M5 / M15 inside-bar OCO in the killzone (09-12 / 14-17 server), SL other side of the mother bar"); say(M.HDR)
    for m in (5, 15):
        X = M.resample(Bw, m); xa = M.atr(X).values
        xh, xl = X.h.values, X.l.values
        ins = np.r_[False, (xh[1:] < xh[:-1]) & (xl[1:] > xl[:-1])]
        tclose = X.index + pd.Timedelta(minutes=m)
        hr_ = tclose.hour + tclose.minute / 60
        kz = ((hr_ >= 9) & (hr_ < 12)) | ((hr_ >= 14) & (hr_ < 17))
        for mwin in (2, 4):
            rows = []
            for k in np.where(ins & kz)[0]:
                mh, ml = xh[k - 1], xl[k - 1]
                if mh - ml < 0.5 * xa[k - 1]: continue
                a = int(np.searchsorted(T.values, tclose[k].to_datetime64())); b = a + mwin * m
                j, dr, fp = scan_oco(O, H, L, S, a, b, mh, ml)
                if j >= 0: rows.append((j, dr, fp, mh - ml, mh, ml))
            if not rows: continue
            f = np.array(rows); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int); fp = f[:, 2]
            sl = np.where(dr == 1, fp - f[:, 5], f[:, 4] - fp)
            for tpr in (1.0, 2.0):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": fp, "sl": sl, "tp": tpr * sl, "x": np.minimum(ii + 120, exb(ii))})
                go(f"F6 inside bar M{m} OCO {mwin} bars TP {tpr}R", sg)

    # ---------------------------------------------------------------- F7 three-timeframe pullback
    say("\n-- F7 M15 EMA 20 slope + M5 close vs its EMA 20 + M1 RSI(3) cross -> with the trend; SL 1 ATR(M5)"); say(M.HDR)
    M15 = M.resample(Bw, 15); e15 = M15.c.ewm(span=20, adjust=False).mean()
    slope = pd.Series((e15 - e15.shift(4)).values, index=M15.index + pd.Timedelta(minutes=15)).reindex(T, method="ffill").values
    e5 = M5.c.ewm(span=20, adjust=False).mean()
    above5 = pd.Series(np.sign(M5.c - e5).values, index=M5.index + pd.Timedelta(minutes=5)).reindex(T, method="ffill").values
    r3 = rsi(C, 3)
    for lv in (20, 10):
        bx = (r3 < lv) & (np.r_[100.0, r3[:-1]] >= lv) & (slope > 0) & (above5 > 0)
        sx = (r3 > 100 - lv) & (np.r_[0.0, r3[:-1]] <= 100 - lv) & (slope < 0) & (above5 < 0)
        for gg in (0, 8):
            j = np.where(bx | sx)[0]; j = j[gate(j, gg)]; ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
            dr = np.where(bx[j], 1, -1)
            for tpm, hold in ((1.5, 30), (1.0, 30), (np.nan, 60)):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": a5[j], "tp": tpm * a5[j], "x": np.minimum(ii + hold, exb(ii))})
                go(f"F7 MTF pullback RSI3 {lv} gate {gg} TP {tpm} ATR {hold}m", sg)

    # ---------------------------------------------------------------- F8 volatility contraction breakout
    say("\n-- F8 volatility contraction: ATR5 / ATR60 of M1 TR < x, then a close out of the 15-bar range -> follow"); say(M.HDR)
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    rat = pd.Series(tr).rolling(5).mean().values / pd.Series(tr).rolling(60).mean().values
    hh15 = pd.Series(H).shift(1).rolling(15).max().values; ll15 = pd.Series(L).shift(1).rolling(15).min().values
    for xr in (0.4, 0.5, 0.6):
        pre = np.r_[np.nan, rat[:-1]] < xr
        bx = pre & (C > hh15); sx = pre & (C < ll15)
        for gg in (0, 8):
            j = np.where(bx | sx)[0]; j = j[gate(j, gg)]; ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
            dr = np.where(bx[j], 1, -1); e = mk_entry(ii, dr)
            sl = np.where(dr == 1, e - ll15[j], hh15[j] - e)
            for tpr in (1.0, 2.0):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": tpr * sl, "x": np.minimum(ii + 60, exb(ii))})
                go(f"F8 contraction < {xr} gate {gg} TP {tpr}R", sg)

    # ---------------------------------------------------------------- F9 M5 displacement FVG
    say("\n-- F9 M5 displacement FVG: bar >= 1.5 ATR(M5) leaving a gap; limit in the gap, SL under the displacement bar"); say(M.HDR)
    xo, xh, xl, xc = M5.o.values, M5.h.values, M5.l.values, M5.c.values; xa = a5f.values
    for kk_ in (1.5, 2.0):
        bull = np.zeros(len(M5), bool); bear = np.zeros(len(M5), bool)
        bull[2:] = (xl[2:] > xh[:-2]) & ((xc[1:-1] - xo[1:-1]) >= kk_ * xa[1:-1])
        bear[2:] = (xh[2:] < xl[:-2]) & ((xo[1:-1] - xc[1:-1]) >= kk_ * xa[1:-1])
        for where in ("top", "mid"):
            rows = []
            for k in np.where(bull | bear)[0]:
                dr = 1 if bull[k] else -1
                top, bot = (xl[k], xh[k - 2]) if dr == 1 else (xh[k], xl[k - 2])
                lvl = top if where == "top" else (top + bot) / 2
                stop = (xl[k - 1] - 0.1 * xa[k - 1]) if dr == 1 else (xh[k - 1] + 0.1 * xa[k - 1])
                a = int(np.searchsorted(T.values, (M5.index[k] + pd.Timedelta(minutes=5)).to_datetime64()))
                j = scan_limit(L, H, S, a, a + 60, lvl, dr)
                if j >= 0: rows.append((j, dr, lvl, abs(lvl - stop)))
            if not rows: continue
            f = np.array(rows); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int)
            for tpr in (2.0, 3.0):
                sg = pd.DataFrame({"i": ii, "d": dr, "ep": f[:, 2], "sl": f[:, 3], "tp": tpr * f[:, 3], "x": np.minimum(ii + 120, exb(ii))})
                go(f"F9 FVG M5 disp {kk_} ATR limit {where} TP {tpr}R", sg)

    # ---------------------------------------------------------------- F10 London-to-NY continuation
    say("\n-- F10 at New York 09:30 follow / fade the move since London 08:00 if >= k x the 14-day mean daily range; out 22:00"); say(M.HDR)
    D = SA.daily(SA.prep(Bw[["o", "h", "l", "c", "s", "v"]].copy()))
    drng = (D.h - D.l).rolling(14).mean().shift(1)
    a_l = W.ldn_to_server(dates, 8, 0); a_n = W.ny_to_server(dates, 9, 30)
    okd = ~(a_l.isna() | a_n.isna())
    il_ = np.searchsorted(T.values, a_l[okd].values); in_ = np.searchsorted(T.values, a_n[okd].values)
    rr_ = drng.reindex(dates[okd]).values
    for k in (0.2, 0.35, 0.5):
        for mode in ("follow", "fade"):
            rows = []
            for s0, s1, rg in zip(il_, in_, rr_):
                if s1 >= n - 2 or s0 >= s1 or not np.isfinite(rg): continue
                mv = C[s1 - 1] - O[s0]
                if abs(mv) < k * rg: continue
                dr = int(np.sign(mv)) * (1 if mode == "follow" else -1)
                rows.append((s1, dr, abs(mv)))
            if not rows: continue
            f = np.array(rows); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int)
            x22 = M.exit_bar(Bw, ii, 1320)
            sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 0.5 * f[:, 2], "tp": np.nan, "x": x22})
            go(f"F10 LDN->NY {mode} k {k} SL 0.5 move out 22:00", sg)

    # ---------------------------------------------------------------- F11 Monday gap fade
    say("\n-- F11 Monday gap: fade the gap from Friday's last price, TP the gap fill, SL = gap, out after 4 h"); say(M.HDR)
    wk = T.to_period("W").astype(str).values
    newwk = np.r_[False, wk[1:] != wk[:-1]]
    j = np.where(newwk)[0]
    gap = O[j] - C[j - 1]
    for gmin in (1.0, 3.0):
        sel = np.abs(gap) >= gmin
        jj = j[sel]; gp = gap[sel]
        # the first bar after the rollover filter (01:30 server) is the earliest the Book keeps: enter there
        ent = np.searchsorted(T.values, (T[jj].normalize() + pd.Timedelta(minutes=95)).values)
        ok_ = ent < n - 1; ent, gp, jj = ent[ok_], gp[ok_], jj[ok_]
        dr = np.where(gp > 0, -1, 1); e = mk_entry(ent, dr)
        tpd = (C[jj - 1] - e) * dr
        sg = pd.DataFrame({"i": ent, "d": dr, "ep": np.nan, "sl": np.abs(gp), "tp": tpd, "x": np.minimum(ent + 240, exb(ent))})
        sg = sg[sg.tp > 0]
        go(f"F11 Monday gap >= ${gmin} fade", sg)

    # ---------------------------------------------------------------- summary
    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        say(f"{len(R)} variants with >= {M.MIN_N} trades; PASS {int(R.ok.sum())}")
        say(f"median PF {R.PF.median():.2f}, median random twin {R.rand.median():.2f}, median always-buy twin {R.ab.median():.2f}")
        say("by family: " + "  ".join(f"{f}: {g.PF.median():.2f} (rand {g.rand.median():.2f}, n {len(g)})"
                                      for f, g in R.groupby(R.name.str.split().str[0])))
        say("\nTOP 25 by PF with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(25).iterrows(): M.show(x.to_dict())
        say("\nTOP 15 with both years >= 1.05 and PF >= twins + 0.10 (any n)"); say(M.HDR)
        q = R[(R.y1 >= 1.05) & (R.y2 >= 1.05) & (R.PF >= np.maximum(R.rand, R.ab) + 0.10)]
        for _, x in q.sort_values("PF", ascending=False).head(15).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
