"""Round 115c (15 Nov 2026): the last-H1-candle base with the direction from the DAY'S COLOUR.  Owner: "kalau h1 base tu di bawah iaitu
d1 bearish, dia akan jadi buy la kan untuk trigger akan datang?"  i.e. D1 bearish (close < open) -> the base sits low -> BUY when price
comes back to it; D1 bullish -> SELL.
  D1-BOUNCE : D1 bearish -> wait until price is above the zone, BUY LIMIT at the zone high (SL below the zone low); bullish mirrored.
  D1-ANY    : D1 bearish -> BUY at the zone high on the first touch from either side (limit from above / stop from below).
  OPPOSITE  : control, D1 bearish -> SELL bounce at the zone low (the other colour rule).
  RAND      : control, a coin flip instead of the D1 colour (3 seeds), D1-BOUNCE rules.
Also D1-BOUNCE only when the base closed in the bottom (top) 30% of the day's range.  Base = 21 / 22 / 23 / 23:00-23:44 server H1 bar;
valid 1 / 3 / 5 / 10 trading days; TP 2R / none, out 23:30 server; SL buffer spread + 0.1 x height.  Gold M1, last 2 years, 0.01 lot."""
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
def run_dir(O, H, L, C, S, hm, eod, zhi, zlo, zs, ze, zdir, anyside, R, usd):
    nz = len(zhi); pn = np.zeros(nz); xi = np.full(nz, -1, np.int64); dr = np.zeros(nz, np.int64)
    for z in range(nz):
        hi = zhi[z]; lo = zlo[z]; ht = hi - lo; want = zdir[z]; j = zs[z]
        if ht <= 0 or want == 0: continue
        side = 0
        if anyside == 0:
            while j < ze[z]:                      # wait until price is on the side that lets the wanted bounce happen
                if hm[j] >= 90 and hm[j] < 1380:
                    if want == 1 and C[j] > hi: side = 1; j += 1; break
                    if want == -1 and C[j] < lo: side = -1; j += 1; break
                j += 1
            if side == 0: continue
        else:
            while j < ze[z] and (hm[j] < 90 or hm[j] >= 1380): j += 1
            if j >= ze[z]: continue
            side = 1 if O[j] > hi else (-1 if O[j] < lo else 0)
            j += 1
        d = 0; ent = 0.0; sl = 0.0
        while j < ze[z]:
            if hm[j] < 90 or hm[j] >= 1380: j += 1; continue
            buf = S[j] + 0.1 * ht
            if want == 1:
                if (side == 1 or anyside == 0) and L[j] + S[j] <= hi:
                    d = 1; ent = min(O[j] + S[j], hi); sl = lo - buf
                elif anyside == 1 and side != 1 and H[j] + S[j] >= hi:
                    d = 1; ent = max(O[j] + S[j], hi); sl = lo - buf
            else:
                if (side == -1 or anyside == 0) and H[j] >= lo:
                    d = -1; ent = max(O[j], lo); sl = hi + buf
                elif anyside == 1 and side != -1 and L[j] <= lo:
                    d = -1; ent = min(O[j], lo); sl = hi + buf
            if d != 0: break
            j += 1
        if d == 0: continue
        risk = abs(ent - sl); tp = ent + d * R * risk if R > 0 else 0.0
        e = eod[j]; px = 0.0; done = False
        if d == 1 and L[j] <= sl: px = sl; done = True
        if d == -1 and H[j] + S[j] >= sl: px = sl; done = True
        k = j + 1
        while not done and k <= e:
            if d == 1:
                if L[k] <= sl: px = min(O[k], sl); done = True
                elif R > 0 and H[k] >= tp: px = max(O[k], tp); done = True
            else:
                if H[k] + S[k] >= sl: px = max(O[k] + S[k], sl); done = True
                elif R > 0 and L[k] + S[k] <= tp: px = min(O[k] + S[k], tp); done = True
            if not done: k += 1
        if not done:
            k = e; px = O[e] if d == 1 else O[e] + S[e]
        pn[z] = (px - ent) * d * usd; xi[z] = k; dr[z] = d
    return pn, xi, dr


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
    days = pd.DatetimeIndex(np.unique(day[T.day_of_week < 5]))
    first_of_day = pos.groupby(day).min()
    b = B.copy(); b["hr"] = T.hour; b["mn"] = T.minute; b["d"] = day
    # the trading day 01:30-23:55 as the D1 candle (the broker's D1)
    dd1 = b[(b.hr * 60 + b.mn) >= 0].groupby("d").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    say(f"BASE + D1 COLOUR: gold M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, $ at 0.01 lot")
    hdr = (f"{'variant':44s} {'trades':>6} {'/wk':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} {'buy':>5} {'sell':>5} | "
           f"{'net$':>6} {'12m$':>5} {'3m$':>5} {'pr3m':>5} | {'DD':>5} {'wDay':>5}")

    def base_tbl(hb, maxmin=60):
        x = b[(b.hr == hb) & (b.mn < maxmin)]
        return x.groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))

    def build(tb, valid, rule, seed=0, posf=False):
        zh, zl, zs, ze, zd = [], [], [], [], []
        rng = np.random.default_rng(seed)
        for dd, r in tb.iterrows():
            if dd < start or dd.dayofweek >= 5 or dd not in dd1.index: continue
            nx = days[days > dd]
            if len(nx) < 1: continue
            D = dd1.loc[dd]; col = -1 if D.c < D.o else (1 if D.c > D.o else 0)
            if col == 0: continue
            want = -col                                    # bearish day -> buy, bullish -> sell
            if rule == "opp": want = col
            if rule == "rand": want = int(rng.choice([-1, 1]))
            if posf:
                rg = D.h - D.l
                if rg <= 0: continue
                pos_ = (r.c - D.l) / rg
                if want == 1 and pos_ > 0.3: continue
                if want == -1 and pos_ < 0.7: continue
            zh.append(r.h); zl.append(r.l); zs.append(first_of_day[nx[0]])
            ze.append(eod[first_of_day[nx[min(valid, len(nx)) - 1]]] + 1); zd.append(want)
        return np.array(zh), np.array(zl), np.array(zs, np.int64), np.array(ze, np.int64), np.array(zd, np.int64)

    def run(nm, tb, valid, R, rule="col", anyside=0, posf=False):
        if rule == "rand":
            ps_ = []
            for sd in range(3):
                zh, zl, zs, ze, zd = build(tb, valid, "rand", sd, posf)
                p, xi, dr = run_dir(O, H, L, C, S, hm, eod, zh, zl, zs, ze, zd, anyside, R, usd)
                ps_.append(p[xi >= 0])
            p = np.concatenate(ps_)
            say(f"{nm:44s} {len(p) // 3:6d}      {100 * (p > 0).mean():4.0f} {pf(p):5.2f}   (3 seeds pooled)")
            return
        zh, zl, zs, ze, zd = build(tb, valid, rule, 0, posf)
        p, xi, dr = run_dir(O, H, L, C, S, hm, eod, zh, zl, zs, ze, zd, anyside, R, usd)
        pS, xS, _ = run_dir(O, H, L, C, S * 1.5, hm, eod, zh, zl, zs, ze, zd, anyside, R, usd)
        ok = xi >= 0; p = p[ok]; te = T[xi[ok]]; dr = dr[ok]
        if len(p) < 20: say(f"{nm:44s} {len(p):6d}"); return
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum(); eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:44s} {len(p):6d} {len(p) / 104:4.1f} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} "
            f"{pf(pS[xS >= 0]):5.2f} {pf(p[dr == 1]):5.2f} {pf(p[dr == -1]):5.2f} | {p.sum():+6.0f} {p[te >= mid].sum():+5.0f} "
            f"{p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | {dd:+5.0f} {dp.min():+5.0f}")

    bases = [("21:00", base_tbl(21)), ("22:00", base_tbl(22)), ("23:00", base_tbl(23)), ("23:00-23:44", base_tbl(23, 45))]
    for R in (2.0, 0.0):
        for bn, tb in bases:
            say(f"\n== base H1 {bn}, TP {('%gR' % R) if R else 'none (out 23:30)'}\n" + hdr)
            for valid in (1, 3, 5, 10):
                run(f"D1-BOUNCE valid {valid}d", tb, valid, R)
            for valid in (1, 5):
                run(f"D1-ANY side valid {valid}d", tb, valid, R, anyside=1)
                run(f"D1-BOUNCE base in day's 30% end, {valid}d", tb, valid, R, posf=True)
                run(f"OPPOSITE colour (control) {valid}d", tb, valid, R, rule="opp")
                run(f"RANDOM colour (control) {valid}d", tb, valid, R, rule="rand")


if __name__ == "__main__":
    main()
