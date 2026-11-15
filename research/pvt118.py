"""Round 118 (15 Nov 2026): "PVT" on gold, judged on the LAST 3 MONTHS with the 3 months before as a repeat check.
Owner: "kau cari kan aku teknik pvt. dengar cerita ini teknik kuno sebelum wujudnya indikator dan teknik ini adalah power".
Two readings of PVT are tested:
  (1) PIVOT POINTS, the floor traders' levels from the previous day's high / low / close (the pre-indicator pit technique):
      P = (H+L+C)/3, R1 = 2P-L, S1 = 2P-H, R2 = P+(H-L), S2 = P-(H-L), R3 = H+2(P-L), S3 = L-2(H-P).
      Rules from the guides (MarketGauge, FXStreet, Dummies, LuxAlgo): bias from the 01:30 open vs P, a P bounce with the bias,
      fade S1 / R1 (and S2 / R2) back to P, break of R1 / S1 to R2 / S2, and a P cross.  Control: the same rules on FAKE pivots
      (all levels shifted by +-0.25 / +-0.5 of yesterday's range) and a random direction for the bias trade.
  (2) PRICE VOLUME TREND, the indicator: PVT += tick volume x (c - c1) / c1, traded on its cross of its own SMA on M15 / H1, with
      and without an EMA 50 side filter; SL k x ATR(14), exit on the opposite cross or 23:30.  Control: random direction.
Gold M1, 0.01 lot, entries 01:30-23:30 server, everything out at 23:30."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit


@jit
def sim(O, H, L, S, st, en, kind, dr, lev, sl, tp, usd):
    """kind 0 market at O[st], 1 limit at lev, 2 stop at lev; active st..en-1; exit SL / TP / O[en].  tp <= 0 means no TP."""
    n = len(st); pn = np.zeros(n); xi = np.full(n, -1, np.int64)
    for k in range(n):
        j0 = st[k]; j1 = en[k]; d = dr[k]; f = -1; ent = 0.0
        for j in range(j0, j1):
            if kind[k] == 0:
                f = j; ent = O[j] + S[j] if d == 1 else O[j]; break
            a_l = L[j] + S[j]; a_h = H[j] + S[j]
            if kind[k] == 1:
                if d == 1 and a_l <= lev[k]: f = j; ent = min(O[j] + S[j], lev[k]); break
                if d == -1 and H[j] >= lev[k]: f = j; ent = max(O[j], lev[k]); break
            else:
                if d == 1 and a_h >= lev[k]: f = j; ent = max(O[j] + S[j], lev[k]); break
                if d == -1 and L[j] <= lev[k]: f = j; ent = min(O[j], lev[k]); break
        if f < 0: continue
        if (d == 1 and sl[k] >= ent) or (d == -1 and sl[k] <= ent): continue
        out = 0.0; done = False
        for j in range(f, j1):
            if d == 1:
                if L[j] <= sl[k]: out = (min(O[j], sl[k]) if j > f else sl[k]) - ent; done = True; break
                if j > f and tp[k] > 0 and H[j] >= tp[k]: out = max(O[j], tp[k]) - ent; done = True; break
            else:
                if H[j] + S[j] >= sl[k]: out = ent - (max(O[j] + S[j], sl[k]) if j > f else sl[k]); done = True; break
                if j > f and tp[k] > 0 and L[j] + S[j] <= tp[k]: out = ent - min(O[j] + S[j], tp[k]); done = True; break
        if not done:
            out = (O[j1] - ent) if d == 1 else (ent - (O[j1] + S[j1]))
        pn[k] = out * usd; xi[k] = f
    return pn, xi


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= a6 - pd.Timedelta(days=40)]
    O, H, L, C, S, V = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s", "v"))
    T = B.index; N = len(O)
    hm = (T.hour.values * 60 + T.minute.values)
    day = T.normalize(); dow = T.day_of_week.values
    say(f"PVT / PIVOTS on XAUUSD, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat check {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    say(f"median spread ${np.median(S) * usd:.2f}")

    # day table: start (first bar >= 01:30), eod (first bar >= 23:30 or last bar)
    idx = np.arange(N)
    df = pd.DataFrame({"i": idx, "d": day, "hm": hm, "h": H, "l": L, "c": C, "o": O, "dow": dow})
    g = df.groupby("d")
    D = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "dow": g.dow.first(), "last": g.i.max()})
    D["st"] = df[df.hm >= 90].groupby("d").i.min()
    D["eo"] = df[df.hm >= 1410].groupby("d").i.min()
    D["eod"] = D.eo.fillna(D["last"]).astype(int)
    D = D[(D.dow < 5)].dropna(subset=["st"])
    D["st"] = D.st.astype(int)
    D["ph"] = D.h.shift(); D["pl"] = D.l.shift(); D["pc"] = D.c.shift()
    D = D.dropna(subset=["ph"])
    D = D[D.index >= a6 - pd.Timedelta(days=3)]
    D["open"] = O[D.st.values]

    def lv(shift):
        ph, pl, pc = D.ph.values, D.pl.values, D.pc.values
        rg = ph - pl; ph = ph + shift * rg; pl = pl + shift * rg; pc = pc + shift * rg
        P = (ph + pl + pc) / 3
        return dict(P=P, R1=2 * P - pl, S1=2 * P - ph, R2=P + (ph - pl), S2=P - (ph - pl), R3=ph + 2 * (P - pl), S3=pl - 2 * (ph - P))

    hdr = (f"{'variant':44s} | {'trd':>4} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'wTrd':>5} | "
           f"{'prev3m trd':>10} {'PF':>5} {'net$':>6}")

    def report(nm, st, en, kind, dr, lev, sl, tp):
        if len(st) == 0: say(f"{nm:44s} |    0"); return
        a = [np.asarray(x) for x in (st, en, kind, dr, lev, sl, tp)]
        a[0] = a[0].astype(np.int64); a[1] = a[1].astype(np.int64); a[2] = a[2].astype(np.int64); a[3] = a[3].astype(np.int64)
        a[4:] = [x.astype(float) for x in a[4:]]
        p, xi = sim(O, H, L, S, *a, usd)
        pS, xS = sim(O, H, L, S * 1.5, *a, usd)
        ok = xi >= 0; te = T[xi[ok]]; p = p[ok]; teS = T[xS[xS >= 0]]; pS = pS[xS >= 0]
        m = te >= a3; m2 = (te >= a6) & (te < a3)
        x = p[m]
        if len(x) == 0: say(f"{nm:44s} |    0 | {m2.sum():10d} {pf(p[m2]):5.2f} {p[m2].sum():+6.0f}"); return
        dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        say(f"{nm:44s} | {len(x):4d} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {pf(pS[teS >= a3]):5.2f} {x.sum():+6.0f} {min(ddn, 0):+5.0f} "
            f"{dp.min():+5.0f} {x.min():+5.0f} | {m2.sum():10d} {pf(p[m2]):5.2f} {p[m2].sum():+6.0f}")

    st = D.st.values; eod = D.eod.values; op = D.open.values; nD = len(D)
    one = np.ones(nD, np.int64)

    def pivots(tag, shift, rng=None):
        X = lv(shift)
        P, R1, S1, R2, S2, R3, S3 = (X[k] for k in ("P", "R1", "S1", "R2", "S2", "R3", "S3"))
        bias = np.where(op > P, 1, -1)
        if rng is not None: bias = rng.choice([-1, 1], nD)
        # 1 bias at 01:30 market, SL S1 / R1, TP R1 / S1 or none
        sl = np.where(bias == 1, S1, R1); tp = np.where(bias == 1, R1, S1)
        report(f"{tag} BIAS mkt SL S1/R1 TP R1/S1", st, eod, 0 * one, bias, op, sl, tp)
        report(f"{tag} BIAS mkt SL S1/R1 no TP", st, eod, 0 * one, bias, op, sl, 0 * tp)
        if rng is not None: return
        # 2 P bounce with the bias: limit at P
        report(f"{tag} P BOUNCE lim SL S1/R1 TP R1/S1", st, eod, one, bias, P, sl, tp)
        report(f"{tag} P BOUNCE lim SL S1/R1 no TP", st, eod, one, bias, P, sl, 0 * tp)
        # 3 P cross against the open (buy stop at P when open below), SL S1/R1, TP R1/S1
        cb = -bias
        report(f"{tag} P CROSS stop SL S1/R1 TP R1/S1", st, eod, 2 * one, cb, P, np.where(cb == 1, S1, R1), np.where(cb == 1, R1, S1))
        # 4 fade S1 / R1 back to P, SL S2 / R2 (both sides, each its own setup)
        s2 = np.r_[st, st]; e2 = np.r_[eod, eod]; k1 = np.r_[one, one]; dd = np.r_[one, -one]
        report(f"{tag} FADE S1/R1 SL S2/R2 TP P", s2, e2, k1, dd, np.r_[S1, R1], np.r_[S2, R2], np.r_[P, P])
        report(f"{tag} FADE S1/R1 SL S2/R2 TP P, bias side", s2[np.r_[bias == 1, bias == -1]], e2[np.r_[bias == 1, bias == -1]],
               k1[np.r_[bias == 1, bias == -1]], dd[np.r_[bias == 1, bias == -1]], np.r_[S1, R1][np.r_[bias == 1, bias == -1]],
               np.r_[S2, R2][np.r_[bias == 1, bias == -1]], np.r_[P, P][np.r_[bias == 1, bias == -1]])
        report(f"{tag} FADE S2/R2 SL S3/R3 TP S1/R1", s2, e2, k1, dd, np.r_[S2, R2], np.r_[S3, R3], np.r_[S1, R1])
        # 5 break R1 / S1 to R2 / S2, SL P
        report(f"{tag} BREAK R1/S1 SL P TP R2/S2", s2, e2, 2 * k1, dd, np.r_[R1, S1], np.r_[P, P], np.r_[R2, S2])
        report(f"{tag} BREAK R1/S1 SL P no TP", s2, e2, 2 * k1, dd, np.r_[R1, S1], np.r_[P, P], 0 * np.r_[R2, S2])
        mid1 = np.r_[(R1 + P) / 2, (S1 + P) / 2]
        report(f"{tag} BREAK R1/S1 SL mid(P,R1) TP R2/S2", s2, e2, 2 * k1, dd, np.r_[R1, S1], mid1, np.r_[R2, S2])

    say("\n=== (1) PIVOT POINTS (previous server day H / L / C) ===\n" + hdr)
    pivots("REAL", 0.0)
    for sh in (-0.5, -0.25, 0.25, 0.5):
        say(""); pivots(f"FAKE{sh:+.2f}", sh)
    say("")
    for sd in (1, 2, 3):
        pivots(f"RANDDIR{sd}", 0.0, np.random.default_rng(sd))

    # (2) Price Volume Trend
    say("\n=== (2) PRICE VOLUME TREND (tick volume) ===\n" + hdr)
    b = pd.DataFrame({"o": O, "h": H, "l": L, "c": C, "v": V, "i": idx}, index=T)
    eod_of = pd.Series(D.eod.values, index=D.index)
    for tf in ("15min", "1h"):
        R = b.resample(tf, label="left", closed="left").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
                                                             v=("v", "sum"), i=("i", "first")).dropna()
        c1 = R.c.shift()
        tr = np.maximum(R.h - R.l, np.maximum((R.h - c1).abs(), (R.l - c1).abs()))
        R["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
        R["pvt"] = (R.v * (R.c - c1) / c1).fillna(0).cumsum()
        R["e50"] = R.c.ewm(span=50, adjust=False).mean()
        R["e200"] = R.c.ewm(span=200, adjust=False).mean()
        nxt_i = R.i.shift(-1).values
        Rd = R.index.normalize(); Rhm = R.index.hour * 60 + R.index.minute
        for n in (13, 21, 50):
            sig = R.pvt.rolling(n).mean()
            above = (R.pvt > sig).astype(int).values
            cross = np.r_[0, np.diff(above)]  # +1 up, -1 down
            for filt in ("none", "ema50", "ema200"):
                for k_sl in (1.5, 3.0):
                    sts, ens, drs, sls = [], [], [], []
                    cidx = np.where(cross != 0)[0]
                    for q, j in enumerate(cidx):
                        if j + 1 >= len(R) or not np.isfinite(nxt_i[j]): continue
                        dday = Rd[j]
                        if dday not in eod_of.index or Rhm[j] < 75 or Rhm[j] >= 1395: continue
                        dirn = 1 if cross[j] > 0 else -1
                        if filt == "ema50" and np.sign(R.c.values[j] - R.e50.values[j]) != dirn: continue
                        if filt == "ema200" and np.sign(R.c.values[j] - R.e200.values[j]) != dirn: continue
                        s0 = int(nxt_i[j]); e0 = int(eod_of[dday])
                        if s0 >= e0: continue
                        if q + 1 < len(cidx) and cidx[q + 1] + 1 < len(R) and np.isfinite(nxt_i[cidx[q + 1]]):
                            e0 = min(e0, int(nxt_i[cidx[q + 1]]))
                        if s0 >= e0: continue
                        ent = O[s0] + (S[s0] if dirn == 1 else 0)
                        sts.append(s0); ens.append(e0); drs.append(dirn); sls.append(ent - dirn * k_sl * R.atr.values[j])
                    sts = np.array(sts); z = np.zeros(len(sts))
                    nm = f"PVT {tf:5s} x SMA{n:<3d} {filt:6s} SL {k_sl:.1f}ATR"
                    report(nm, sts, ens, np.zeros(len(sts), int), drs, z, sls, z)
                    if filt == "none" and k_sl == 1.5:
                        rd = np.random.default_rng(n).choice([-1, 1], len(sts))
                        ents = O[sts.astype(int)] + np.where(rd == 1, S[sts.astype(int)], 0) if len(sts) else z
                        atrj = np.abs(np.array(sls) - (O[sts.astype(int)] + np.where(np.array(drs) == 1, S[sts.astype(int)], 0))) if len(sts) else z
                        report(nm.replace("none  ", "RANDOM"), sts, ens, np.zeros(len(sts), int), rd, z, ents - rd * atrj, z)


if __name__ == "__main__":
    main()
