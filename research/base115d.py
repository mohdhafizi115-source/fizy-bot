"""Round 115d (15 Nov 2026): is it the BASE or just the D1 colour?  Owner: "cuba dulu" (after round 115c).
Same direction rule as 115c (day closed red -> BUY next day, green -> SELL), D1-BOUNCE entry, TP none, out 23:30 server, valid 5 days,
but the LEVEL is replaced:
  REAL      : the base (H1 23:00 / 21:00 / 23:00-23:44 bar, wick to wick), as 115c.
  SHIFT s   : the same-height zone moved s x height (s = -2, -1, -0.5, +0.5, +1, +2).
  RANDH1    : the zone of a random H1 bar 02-20 of the same day (3 seeds).
  MKT 01:30 : no level, market order at the next day's 01:30 open, SL = base height + buffer from the entry.
  MKT RAND  : no level, market order at a random minute 01:30-20:00 of the next day, same SL (3 seeds).
Gold M1, last 2 years, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import base115c as C

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA; C.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit


@jit
def run_mkt(O, H, L, S, eod, eb, zdir, rsk, usd):
    nz = len(eb); pn = np.zeros(nz); xi = np.full(nz, -1, np.int64)
    for z in range(nz):
        j = eb[z]; d = zdir[z]
        if j < 0 or d == 0: continue
        e = eod[j]
        if e <= j: continue
        ent = O[j] + S[j] if d == 1 else O[j]
        sl = ent - d * rsk[z]; px = 0.0; done = False; k = j
        while k <= e:
            if d == 1 and L[k] <= sl: px = min(O[k], sl) if k > j else sl; done = True; break
            if d == -1 and H[k] + S[k] >= sl: px = max(O[k] + S[k], sl) if k > j else sl; done = True; break
            k += 1
        if not done:
            k = e; px = O[e] if d == 1 else O[e] + S[e]
        pn[z] = (px - ent) * d * usd; xi[z] = k
    return pn, xi


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    B = d[d.index >= start - pd.Timedelta(days=5)][["o", "h", "l", "c", "s"]]
    O, H, L, C_, S = (B[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = B.index; N = len(O)
    hm = (T.hour.values * 60 + T.minute.values).astype(np.int64)
    day = T.normalize()
    pos = pd.Series(np.arange(N), index=T)
    lastbar = pos.groupby(day).transform("max").values
    cut = pd.Series(np.where(hm >= 1410, np.arange(N), N + 1), index=T).groupby(day).transform("min").values
    eod = np.minimum(cut, lastbar).astype(np.int64)
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["mn"] = T.minute; b["d"] = day
    dd1 = b.groupby("d").agg(o=("o", "first"), c=("c", "last"))
    h1 = b.groupby(["d", "hr"]).agg(h=("h", "max"), l=("l", "min"))
    # first bar at or after 01:30 of each day, and the bars 01:30-20:00 for random entries
    win = pd.Series(np.where((hm >= 90) & (hm < 1200), np.arange(N), -1), index=T)
    say(f"BASE OR COLOUR? gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot, direction = opposite of the D1 colour, TP none")
    hdr = (f"{'variant':40s} {'trades':>6} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5}")

    def base_tbl(hb, maxmin=60):
        x = b[(b.hr == hb) & (b.mn < maxmin)]
        return x.groupby("d").agg(h=("h", "max"), l=("l", "min"))

    def rows(tb):
        out = []
        for dd, r in tb.iterrows():
            if dd < start or dd.dayofweek >= 5 or dd not in dd1.index: continue
            nx = days[days > dd]
            if len(nx) < 1: continue
            D = dd1.loc[dd]; col = -1 if D.c < D.o else (1 if D.c > D.o else 0)
            if col == 0 or r.h <= r.l: continue
            out.append((dd, r.h, r.l, -col, nx))
        return out

    def report(nm, p, te, pS=None):
        if len(p) < 20: say(f"{nm:40s} {len(p):6d}"); return
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        st = f"{pf(pS):5.2f}" if pS is not None else "    -"
        say(f"{nm:40s} {len(p):6d} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {st} | "
            f"{p.sum():+6.0f} {p[te >= mid].sum():+5.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {ddn:+5.0f} {dp.min():+5.0f}")

    def zone_run(nm, R_, shift=0.0, randh=None, valid=5):
        zh, zl, zs, ze, zd = [], [], [], [], []
        rng = np.random.default_rng(randh if randh is not None else 0)
        for dd, hi, lo, want, nx in R_:
            if randh is not None:
                hr = int(rng.integers(2, 21))
                if (dd, hr) not in h1.index: continue
                hi, lo = h1.loc[(dd, hr)].h, h1.loc[(dd, hr)].l
                if hi <= lo: continue
            ht = hi - lo
            zh.append(hi + shift * ht); zl.append(lo + shift * ht)
            zs.append(first_of_day[nx[0]]); ze.append(eod[first_of_day[nx[min(valid, len(nx)) - 1]]] + 1); zd.append(want)
        a = (np.array(zh), np.array(zl), np.array(zs, np.int64), np.array(ze, np.int64), np.array(zd, np.int64))
        p, xi, _ = C.run_dir(O, H, L, C_, S, hm, eod, *a, 0, 0.0, usd)
        pS, xS, _ = C.run_dir(O, H, L, C_, S * 1.5, hm, eod, *a, 0, 0.0, usd)
        ok = xi >= 0
        return p[ok], T[xi[ok]], pS[xS >= 0]

    def mkt_run(R_, seed=None):
        eb, zd, rk = [], [], []
        rng = np.random.default_rng(seed if seed is not None else 0)
        for dd, hi, lo, want, nx in R_:
            nd = nx[0]
            cand = win[(win.index >= nd) & (win.index < nd + pd.Timedelta(days=1))]
            cand = cand[cand >= 0]
            if len(cand) == 0: continue
            j = int(cand.iloc[0]) if seed is None else int(cand.iloc[rng.integers(0, len(cand))])
            ht = hi - lo
            eb.append(j); zd.append(want); rk.append(ht * 1.1 + S[j])
        eb = np.array(eb, np.int64); zd = np.array(zd, np.int64); rk = np.array(rk)
        p, xi = run_mkt(O, H, L, S, eod, eb, zd, rk, usd)
        pS, xS = run_mkt(O, H, L, S * 1.5, eod, eb, zd, rk, usd)
        ok = xi >= 0
        return p[ok], T[xi[ok]], pS[xS >= 0]

    for bn, tb in (("23:00", base_tbl(23)), ("23:00-23:44", base_tbl(23, 45)), ("21:00", base_tbl(21))):
        R_ = rows(tb)
        say(f"\n== base H1 {bn}, valid 5 d\n" + hdr)
        p, te, pS = zone_run("REAL base", R_); report("REAL base", p, te, pS)
        for s in (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0):
            p, te, pS = zone_run("", R_, shift=s); report(f"SHIFT {s:+g} x height", p, te, pS)
        for sd in (1, 2, 3):
            p, te, pS = zone_run("", R_, randh=sd); report(f"RANDOM H1 bar 02-20 (seed {sd})", p, te, pS)
        p, te, pS = mkt_run(R_); report("MKT at 01:30 open (no level)", p, te, pS)
        for sd in (1, 2, 3):
            p, te, pS = mkt_run(R_, sd); report(f"MKT random minute (seed {sd})", p, te, pS)


if __name__ == "__main__":
    main()
