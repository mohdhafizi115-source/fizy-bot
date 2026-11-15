"""Round 115f (15 Nov 2026): the missing parts of the owner's "last H1 candle" technique.  Owner: "guna show period separators di h1.
marking seluruh candle last termasuk wick atas bawah. itu la zone kita. tapi aku tak tahu macam mana nak validkan entry pada zon tu sebab
aku dapat rule ni tak habis. tu minta kau bongkar teknik ni".
Base rule = the live v2.32 (FizyBAS): the 23:00 server H1 bar, red day -> BUY at its high, green -> SELL at its low, first return within
5 trading days after a close on the right side, cancelled by a D1 close beyond the far side, SL beyond the base + spread + 0.1 x height,
no TP, out 23:30.  The live fills are split (each split is a partition of the SAME trades, with year 1 / year 2):
  base height / ATR14(H1)        (thin vs thick zone)
  excursion before the return    (how far price ran away from the level, in base heights)
  hours from 01:30 to the fill   and the session of the fill (Asia 01:30-09 / London 09-15:30 / NY 15:30-23 server)
  D1 body / ATR14(D1)            (a small or a big red / green day)
  close location of the base bar inside its own range
  the next day's 01:30 open vs the zone (already on the right side, inside, other side)
TP variants (all else live): the base day's own extreme (buy: the day's high), the base day's open, the base day's mid, 1R / 2R.
Gold M1, last 2 years, 0.01 lot."""
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
def run_f(O, H, L, C, S, hm, eod, dayend, zhi, zlo, zs, ze, zdir, ztp, usd):
    nz = len(zhi); pn = np.zeros(nz); xi = np.full(nz, -1, np.int64); fi = np.full(nz, -1, np.int64); exc = np.zeros(nz)
    for z in range(nz):
        hi = zhi[z]; lo = zlo[z]; ht = hi - lo; want = zdir[z]; j = zs[z]
        if ht <= 0 or want == 0: continue
        side = False; d = 0; ent = 0.0; sl = 0.0; dead = False; far = 0.0
        while j < ze[z]:
            if dayend[j]:
                if (want == 1 and C[j] < lo) or (want == -1 and C[j] > hi): dead = True; break
            if hm[j] < 90 or hm[j] >= 1380: j += 1; continue
            if not side:
                if (want == 1 and C[j] > hi) or (want == -1 and C[j] < lo): side = True
                j += 1; continue
            if want == 1: far = max(far, H[j] - hi)
            else: far = max(far, lo - L[j])
            buf = S[j] + 0.1 * ht
            if want == 1 and L[j] + S[j] <= hi:
                d = 1; ent = min(O[j] + S[j], hi); sl = lo - buf; break
            if want == -1 and H[j] >= lo:
                d = -1; ent = max(O[j], lo); sl = hi + buf; break
            j += 1
        if dead or d == 0: continue
        tp = ztp[z]
        if tp < 0: tp = ent + d * (-tp) * abs(ent - sl)            # negative = R multiple
        if tp != 0 and (tp - ent) * d <= 0: tp = 0.0               # target already behind the entry: no TP
        e = eod[j]; px = 0.0; done = False
        if d == 1 and L[j] <= sl: px = sl; done = True
        if d == -1 and H[j] + S[j] >= sl: px = sl; done = True
        k = j + 1
        while not done and k <= e:
            if d == 1:
                if L[k] <= sl: px = min(O[k], sl); done = True
                elif tp > 0 and H[k] >= tp: px = max(O[k], tp); done = True
            else:
                if H[k] + S[k] >= sl: px = max(O[k] + S[k], sl); done = True
                elif tp > 0 and L[k] + S[k] <= tp: px = min(O[k] + S[k], tp); done = True
            if not done: k += 1
        if not done:
            k = e; px = O[e] if d == 1 else O[e] + S[e]
        pn[z] = (px - ent) * d * usd; xi[z] = k; fi[z] = j; exc[z] = far / ht
    return pn, xi, fi, exc


def wilder(tr, n):
    a = np.full(len(tr), np.nan)
    if len(tr) < n: return a
    a[n - 1] = tr[:n].mean()
    for i in range(n, len(tr)): a[i] = (a[i - 1] * (n - 1) + tr[i]) / n
    return a


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start - pd.Timedelta(days=40)][["o", "h", "l", "c", "s"]]
    O, H, L, C, S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = B.index; N = len(O)
    hm = (T.hour.values * 60 + T.minute.values).astype(np.int64)
    day = T.normalize()
    pos = pd.Series(np.arange(N), index=T)
    lastbar = pos.groupby(day).transform("max").values
    cut = pd.Series(np.where(hm >= 1410, np.arange(N), N + 1), index=T).groupby(day).transform("min").values
    eod = np.minimum(cut, lastbar).astype(np.int64)
    dayend = (np.arange(N) == lastbar)
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["d"] = day
    d1 = b.groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    d1 = d1[d1.index.dayofweek < 5]
    tr = np.maximum(d1.h, d1.c.shift()) - np.minimum(d1.l, d1.c.shift())
    d1["atr"] = wilder(tr.fillna(d1.h - d1.l).values, 14)
    h1 = b.groupby(["d", "hr"]).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    h1r = (h1.h - h1.l).values
    h1["atr"] = pd.Series(h1r).rolling(14).mean().values             # simple ATR of the H1 ranges (enough for a split)
    say(f"BASE TECHNIQUE, the missing parts: gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot, live v2.32 rule unless stated")
    hdr = (f"{'variant / split':44s} {'trades':>6} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5}")

    rows = []
    for dd in days:
        if dd < start or (dd, 23) not in h1.index or dd not in d1.index: continue
        nx = days[days > dd]
        if len(nx) < 1: continue
        D = d1.loc[dd]; col = -1 if D.c < D.o else (1 if D.c > D.o else 0)
        if col == 0: continue
        r = h1.loc[(dd, 23)]
        if r.h <= r.l: continue
        want = -col
        z = dict(day=dd, hi=r.h, lo=r.l, want=want, zs=first_of_day[nx[0]], ze=eod[first_of_day[nx[min(5, len(nx)) - 1]]] + 1,
                 hatr=(r.h - r.l) / r.atr if r.atr > 0 else np.nan, body=abs(D.c - D.o) / D.atr if D.atr > 0 else np.nan,
                 cloc=(r.c - r.l) / (r.h - r.l), dh=D.h, dl=D.l, do=D.o, dmid=(D.h + D.l) / 2)
        # where the next day opens at 01:30 relative to the zone, signed for the trade (+1 = already on the right side)
        nd = nx[0]; sel = (day == nd) & (hm >= 90)
        if sel.any():
            o130 = O[np.argmax(sel)]
            sidev = 1 if (want == 1 and o130 > r.h) or (want == -1 and o130 < r.l) else (0 if r.l <= o130 <= r.h else -1)
        else:
            sidev = 9
        z["open_side"] = sidev
        rows.append(z)
    Z = pd.DataFrame(rows)
    zhi = Z.hi.values; zlo = Z.lo.values; zs = Z.zs.values.astype(np.int64); ze = Z.ze.values.astype(np.int64); zd = Z.want.values.astype(np.int64)

    def stats(nm, p, te, pS=None):
        if len(p) < 15: say(f"{nm:44s} {len(p):6d}  (too few)"); return
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        st = f"{pf(pS):5.2f}" if pS is not None else "    -"
        say(f"{nm:44s} {len(p):6d} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {st} | "
            f"{p.sum():+6.0f} {p[te >= mid].sum():+5.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {ddn:+5.0f} {dp.min():+5.0f}")

    def run(tp):
        p, xi, fi, ex = run_f(O, H, L, C, S, hm, eod, dayend, zhi, zlo, zs, ze, zd, tp, usd)
        pS, xS, _, _ = run_f(O, H, L, C, S * 1.5, hm, eod, dayend, zhi, zlo, zs, ze, zd, tp, usd)
        return p, xi, fi, ex, pS, xS

    p, xi, fi, ex, pS, xS = run(np.zeros(len(Z)))
    ok = xi >= 0
    say("\n== LIVE v2.32 rule\n" + hdr)
    stats("LIVE (TP none)", p[ok], T[xi[ok]], pS[xS >= 0])
    F = Z[ok].copy(); F["p"] = p[ok]; F["te"] = T[xi[ok]]; F["exc"] = ex[ok]
    ft = T[fi[ok]]; F["fill_min"] = ft.hour * 60 + ft.minute
    F["hrs"] = [(f - fd.normalize()).total_seconds() / 3600 - 1.5 + 24 * (len(days[(days > fd.normalize() - pd.Timedelta(days=0)) & (days < f.normalize())]) if False else 0)
                for f, fd in zip(ft, ft)]
    # hours from the 01:30 of the first trading day after the base to the fill, counting only trading time
    fday = ft.normalize()
    age = np.array([((days > z) & (days <= f)).sum() for z, f in zip(F.day, fday)])
    F["age"] = age
    F["hrs"] = (age - 1) * 22 + (F.fill_min.values - 90) / 60.0

    def split(title, col, edges, labels):
        say(f"\n-- split by {title}\n" + hdr)
        for (lo_, hi_), lab in zip(edges, labels):
            m = (F[col] >= lo_) & (F[col] < hi_)
            stats(f"   {lab}", F.p[m].values, pd.DatetimeIndex(F.te[m]))

    q = F.hatr.quantile([1 / 3, 2 / 3]).values
    split("base height / ATR(H1)", "hatr", [(0, q[0]), (q[0], q[1]), (q[1], 99)], [f"thin  < {q[0]:.2f}", f"mid   {q[0]:.2f}-{q[1]:.2f}", f"thick > {q[1]:.2f}"])
    split("excursion before the return (base heights)", "exc", [(0, 1), (1, 2), (2, 4), (4, 999)], ["< 1", "1-2", "2-4", ">= 4"])
    split("hours of trading time from 01:30 to the fill", "hrs", [(0, 1), (1, 3), (3, 7.5), (7.5, 14), (14, 999)],
          ["< 1 h", "1-3 h", "3-7.5 h (to London)", "7.5-14 h (London)", "later / next days"])
    split("session of the fill (server time)", "fill_min", [(90, 540), (540, 930), (930, 1380)], ["Asia 01:30-09:00", "London 09:00-15:30", "NY 15:30-23:00"])
    qb = F.body.quantile([1 / 3, 2 / 3]).values
    split("D1 body / ATR14(D1) of the base day", "body", [(0, qb[0]), (qb[0], qb[1]), (qb[1], 99)], [f"small < {qb[0]:.2f}", f"mid {qb[0]:.2f}-{qb[1]:.2f}", f"big > {qb[1]:.2f}"])
    F["cl_sig"] = np.where(F.want == 1, F.cloc, 1 - F.cloc)          # 1 = the base bar closed at the side the trade is placed (buy: at its high)
    split("close location of the base bar (1 = at the entry edge)", "cl_sig", [(0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1.01)], ["far third", "middle third", "near third"])
    split("next day's 01:30 open vs the zone", "open_side", [(-1, 0), (0, 1), (1, 2)], ["other side", "inside the zone", "already on the right side"])

    say("\n== TP variants (everything else live)\n" + hdr)
    tps = {"TP none (live)": np.zeros(len(Z)),
           "TP at the base day's extreme (buy: D1 high)": np.where(Z.want == 1, Z.dh, Z.dl).astype(float),
           "TP at the base day's open": Z.do.values.astype(float),
           "TP at the base day's mid": Z.dmid.values.astype(float),
           "TP 1R": np.full(len(Z), -1.0), "TP 2R": np.full(len(Z), -2.0), "TP 3R": np.full(len(Z), -3.0)}
    for nm, tp in tps.items():
        p2, x2, _, _, s2, sx2 = run(tp)
        stats(nm, p2[x2 >= 0], T[x2[x2 >= 0]], s2[sx2 >= 0])


if __name__ == "__main__":
    main()
