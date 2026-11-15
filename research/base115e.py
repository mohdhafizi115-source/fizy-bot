"""Round 115e (15 Nov 2026): how to VALIDATE an older base before entering.  Owner picked the base version (115c) and asked:
"macam mana nak validkan dulu pada area base semalam atau kelmarin atau 2 3 hari punya sebelum entry tu?"
Base = H1 23:00 (and 23:00-23:44) bar of a red day -> BUY at its high on the return from above; green day -> SELL at its low.
TP none, out 23:30 server of the fill day.  Validation options (alone and combined):
  AGE      : the 115c fills split by the base's age at the fill (1 = the next trading day, 2, 3, 4-5), each band on its own.
  INV-CLOSE: the base is cancelled if any later D1 close (before the touch) is beyond its far side (buy base: close < low).
  INV-COL  : the base is cancelled if a later day closes the OTHER colour (buy base: a green day before the touch).
  CONF M5 / M15 : on the touch no limit fill; wait for an M5 / M15 close back outside the base (buy: close > high), enter at the next
                  open, SL as before; cancelled if price reaches the SL level first.
Random-H1-bar zones with the same rules as a control.  Gold M1, last 2 years, 0.01 lot."""
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
def run_v(O, H, L, C, S, hm, eod, dayend, daycol, zhi, zlo, zs, ze, zdir, conf, invc, invk, usd):
    nz = len(zhi); pn = np.zeros(nz); xi = np.full(nz, -1, np.int64); fi = np.full(nz, -1, np.int64)
    for z in range(nz):
        hi = zhi[z]; lo = zlo[z]; ht = hi - lo; want = zdir[z]; j = zs[z]
        if ht <= 0 or want == 0: continue
        side = False; armed = False; d = 0; ent = 0.0; sl = 0.0; dead = False
        while j < ze[z]:
            if dayend[j] and not armed:
                if invc == 1 and ((want == 1 and C[j] < lo) or (want == -1 and C[j] > hi)): dead = True; break
                if invk == 1 and daycol[j] == want: dead = True; break
            if hm[j] < 90 or hm[j] >= 1380: j += 1; continue
            buf = S[j] + 0.1 * ht
            if not side:
                if (want == 1 and C[j] > hi) or (want == -1 and C[j] < lo): side = True
                j += 1; continue
            if not armed:
                touch = (L[j] + S[j] <= hi) if want == 1 else (H[j] >= lo)
                if touch:
                    if conf == 0:
                        d = want
                        if want == 1: ent = min(O[j] + S[j], hi); sl = lo - buf
                        else: ent = max(O[j], lo); sl = hi + buf
                        break
                    armed = True; sl = (lo - buf) if want == 1 else (hi + buf)
            if armed:
                if want == 1 and L[j] <= sl: dead = True; break
                if want == -1 and H[j] + S[j] >= sl: dead = True; break
                if (hm[j] + 1) % conf == 0:
                    if (want == 1 and C[j] > hi) or (want == -1 and C[j] < lo):
                        if j + 1 < len(O) and eod[j + 1] == eod[j] and j + 1 < eod[j]:
                            j += 1; d = want; ent = O[j] + S[j] if want == 1 else O[j]
                            break
            j += 1
        if dead or d == 0: continue
        e = eod[j]; px = 0.0; done = False
        if d == 1 and L[j] <= sl: px = sl; done = True
        if d == -1 and H[j] + S[j] >= sl: px = sl; done = True
        k = j + 1
        while not done and k <= e:
            if d == 1 and L[k] <= sl: px = min(O[k], sl); done = True
            elif d == -1 and H[k] + S[k] >= sl: px = max(O[k] + S[k], sl); done = True
            if not done: k += 1
        if not done:
            k = e; px = O[e] if d == 1 else O[e] + S[e]
        pn[z] = (px - ent) * d * usd; xi[z] = k; fi[z] = j
    return pn, xi, fi


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start - pd.Timedelta(days=5)][["o", "h", "l", "c", "s"]]
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
    dpos = {dd: i for i, dd in enumerate(days)}
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["mn"] = T.minute; b["d"] = day
    dd1 = b.groupby("d").agg(o=("o", "first"), c=("c", "last"))
    colmap = np.sign(dd1.c - dd1.o)
    daycol = colmap.reindex(day).values.astype(np.int64)
    h1 = b.groupby(["d", "hr"]).agg(h=("h", "max"), l=("l", "min"))
    say(f"BASE VALIDATION: gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot, red day -> BUY at the base, green -> SELL, TP none")
    hdr = (f"{'variant':44s} {'trades':>6} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'buy':>5} {'sell':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5}")

    def build(tb, valid, randseed=None):
        rng = np.random.default_rng(randseed if randseed is not None else 0)
        zh, zl, zs, ze, zd, zday = [], [], [], [], [], []
        for dd, r in tb.iterrows():
            if dd < start or dd.dayofweek >= 5 or dd not in dd1.index: continue
            nx = days[days > dd]
            if len(nx) < 1: continue
            col = int(colmap.loc[dd])
            if col == 0: continue
            hi, lo = r.h, r.l
            if randseed is not None:
                hr = int(rng.integers(2, 21))
                if (dd, hr) not in h1.index: continue
                hi, lo = h1.loc[(dd, hr)].h, h1.loc[(dd, hr)].l
            if hi <= lo: continue
            zh.append(hi); zl.append(lo); zs.append(first_of_day[nx[0]])
            ze.append(eod[first_of_day[nx[min(valid, len(nx)) - 1]]] + 1); zd.append(-col); zday.append(dd)
        return (np.array(zh), np.array(zl), np.array(zs, np.int64), np.array(ze, np.int64), np.array(zd, np.int64)), zday

    def run(nm, tb, valid, conf=0, invc=0, invk=0, randseed=None, ages=False):
        a, zday = build(tb, valid, randseed)
        p, xi, fi = run_v(O, H, L, C, S, hm, eod, dayend, daycol, *a, conf, invc, invk, usd)
        pS, xS, _ = run_v(O, H, L, C, S * 1.5, hm, eod, dayend, daycol, *a, conf, invc, invk, usd)
        ok = xi >= 0; dr = a[4][ok]
        pp = p[ok]; te = T[xi[ok]]
        if len(pp) < 20: say(f"{nm:44s} {len(pp):6d}"); return
        dp = pd.Series(pp, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        say(f"{nm:44s} {len(pp):6d} {100 * (pp > 0).mean():4.0f} {pf(pp):5.2f} {pf(pp[te < mid]):5.2f} {pf(pp[te >= mid]):5.2f} "
            f"{pf(pS[xS >= 0]):5.2f} {pf(pp[dr == 1]):5.2f} {pf(pp[dr == -1]):5.2f} | {pp.sum():+6.0f} {pp[te >= mid].sum():+5.0f} "
            f"{pp[te >= a3].sum():+5.0f} {pp[(te >= a6) & (te < a3)].sum():+5.0f} | {ddn:+5.0f} {dp.min():+5.0f}")
        if ages:
            zd_ok = np.array(zday, dtype="datetime64[ns]")[ok]
            fday = T[fi[ok]].normalize()
            age = np.array([dpos.get(f, 0) - dpos.get(pd.Timestamp(z), 0) for f, z in zip(fday, zd_ok)])
            for lo_, hi_, lab in ((1, 1, "1 (the next day)"), (2, 2, "2"), (3, 3, "3"), (4, 5, "4-5")):
                m = (age >= lo_) & (age <= hi_)
                if m.sum() < 5: continue
                x = pp[m]; tx = te[m]
                say(f"   age {lab:16s}: {m.sum():4d} trades, win {100 * (x > 0).mean():3.0f}%, PF {pf(x):5.2f} "
                    f"(yr1 {pf(x[tx < mid]):5.2f} / yr2 {pf(x[tx >= mid]):5.2f}), net {x.sum():+6.0f} $, 12m {x[tx >= mid].sum():+5.0f} $")

    def base_tbl(hb, maxmin=60):
        x = b[(b.hr == hb) & (b.mn < maxmin)]
        return x.groupby("d").agg(h=("h", "max"), l=("l", "min"))

    for bn, tb in (("23:00", base_tbl(23)), ("23:00-23:44", base_tbl(23, 45))):
        for valid in (5, 3):
            say(f"\n== base H1 {bn}, valid {valid} d\n" + hdr)
            run("LIMIT (115c rule)", tb, valid, ages=True)
            run("LIMIT + INV-CLOSE", tb, valid, invc=1)
            run("LIMIT + INV-COL", tb, valid, invk=1)
            run("LIMIT + INV-CLOSE + INV-COL", tb, valid, invc=1, invk=1)
            for cf in (5, 15):
                run(f"CONF M{cf}", tb, valid, conf=cf, ages=True)
                run(f"CONF M{cf} + INV-CLOSE", tb, valid, conf=cf, invc=1)
                run(f"CONF M{cf} + INV-COL", tb, valid, conf=cf, invk=1)
                run(f"CONF M{cf} + INV-CLOSE + INV-COL", tb, valid, conf=cf, invc=1, invk=1)
            for sd in (1, 2, 3):
                run(f"control RANDOM H1 bar, LIMIT (seed {sd})", tb, valid, randseed=sd)
                run(f"control RANDOM H1 bar, CONF M5 (seed {sd})", tb, valid, conf=5, randseed=sd)


if __name__ == "__main__":
    main()
