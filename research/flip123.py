"""Round 123 (16 Nov 2026): the GOLD_ORB idea inside FLIP.  Owner: "modul orb tu power la, boleh ke apply teknik orb masuk dalam flip?".
Engine = round 122 (v2.35 real-time trail $5, freeze at +$1, reverse on a stop, $25 target, out 23:30, permission per bar).
ORB range = high / low of the M1 bars 01:00-03:59 server (as FizyORB).  Variants:
  LIVE       OCO at the 01:30 open +- $3, no filter
  D1REV      v2.43 filter (longs only after a red day, shorts only after a green one)
  ORB START  flat until 04:00, the first OCO of the day at the range high / low, then normal flips
  ORB DIR    ORB START, and after the first M1 close beyond the range only that side is allowed for the rest of the day
  + D1REV    the same with the D1 filter on top (ORB DIR + D1REV: a side must be allowed by both)
Controls: start at 04:00 with an OCO at the 04:00 open +- $3 (only the later start), a FAKE range 10:00-12:59, the range shifted by
+-0.5 of its height, and a random side per day after 04:00.  Last 3 months and the 3 before, OHLC and coin path order, 0.01 lot."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flip122 as P
F = P.F
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
P.DATA = DATA; F.DATA = DATA; F.M.DATA = DATA; F.W.DATA = DATA; F.G.DATA = DATA
say = F.say; pf = F.pf; jit = F.jit


@jit
def sim(O, H, L, C, S, live, dayid, usd, D, lk, K, tgt, order_rand, seed, allow, bsA, ssA):
    n = len(O); xi = np.zeros(4 * n + 10, np.int64); pn = np.zeros(4 * n + 10); m = 0
    np.random.seed(seed)
    pos = 0; ent = 0.0; stop = 0.0; locked = False; dpnl = 0.0; done = False; oco = False; bs = 0.0; ss = 0.0; armed = False
    pts = np.zeros(4)
    for j in range(n):
        if j > 0 and dayid[j] != dayid[j - 1]:
            dpnl = 0.0; done = False; oco = False; armed = False
        s = S[j]; al = allow[j]
        okL = al == 1 or al == 2; okS = al == -1 or al == 2
        if pos != 0 and (not live[j] or done):
            px = O[j] if pos == 1 else O[j] + s
            p = (px - ent) * pos * usd; xi[m] = j; pn[m] = p; m += 1; pos = 0
            continue
        if not live[j]:
            oco = False
            continue
        if pos == 0 and not done and not oco and (okL or okS):
            oco = True
            if not armed and not np.isnan(bsA[j]):
                bs = bsA[j]; ss = ssA[j]
            else:
                bs = O[j] + K; ss = O[j] - K
            armed = True
        up = C[j] >= O[j]
        if order_rand: up = np.random.random() < 0.5
        pts[0] = O[j]; pts[3] = C[j]
        if up:
            pts[1] = L[j]; pts[2] = H[j]
        else:
            pts[1] = H[j]; pts[2] = L[j]
        for q in range(3):
            a = pts[q]; b = pts[q + 1]
            if done: break
            if b >= a:
                if pos == 0 and oco and okL and b + s >= bs:
                    pos = 1; ent = max(bs, a + s); stop = ent - s - D; locked = False; oco = False
                if pos == -1 and b + s >= stop:
                    px = max(stop, a + s); p = (ent - px) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okL:
                        pos = 1; ent = px; stop = px - s - D; locked = False
                    else:
                        pos = 0; oco = True; bs = px - s + K; ss = px - s - K
                if pos == 1 and not locked:
                    if b - ent >= lk:
                        stop = max(stop, ent + lk - D); locked = True
                    else:
                        stop = max(stop, b - D)
            else:
                if pos == 0 and oco and okS and b <= ss:
                    pos = -1; ent = min(ss, a); stop = ent + s + D; locked = False; oco = False
                if pos == 1 and b <= stop:
                    px = min(stop, a); p = (px - ent) * usd; xi[m] = j; pn[m] = p; m += 1; dpnl += p
                    if dpnl >= tgt:
                        done = True; pos = 0; break
                    if okS:
                        pos = -1; ent = px; stop = px + s + D; locked = False
                    else:
                        pos = 0; oco = True; bs = px + K; ss = px - K
                if pos == -1 and not locked:
                    if ent - (b + s) >= lk:
                        stop = min(stop, ent - lk + D); locked = True
                    else:
                        stop = min(stop, b + s + D)
    return xi[:m], pn[:m]


def main():
    mt, sw = F.W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = F.SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    full = d
    d = d[d.index >= a6 - pd.Timedelta(days=3)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    nd = len(np.unique(dayid[live & (T >= a3)]))
    d1 = P.rs(full, "1D")
    d1rev = -P.sgn(P.to_m1(d1.c - d1.o, "1D", T)); d1rev[d1rev == -2] = 2
    n = len(T); NAN = np.full(n, np.nan); ALL = np.full(n, 2, np.int64)
    dser = pd.Series(dayid)

    def rng(h0, h1, shift=0.0):
        m = (hm >= h0) & (hm < h1)
        hi = pd.Series(np.where(m, H + S, np.nan)).groupby(dser).transform("max").values   # ask high for the buy side
        lo = pd.Series(np.where(m, L, np.nan)).groupby(dser).transform("min").values
        ht = hi - lo
        return hi + shift * ht, lo + shift * ht

    def start_arrays(h1, hi, lo):
        al = np.where(hm >= h1, 2, 0).astype(np.int64)
        bsA = np.where(hm >= h1, hi, np.nan); ssA = np.where(hm >= h1, lo, np.nan)
        return al, bsA, ssA

    def dir_after(h1, hi, lo):
        # side of the first M1 CLOSE beyond the range after h1, allowed from the next bar for the rest of the day
        side = np.zeros(n, np.int64); cur = 0
        for j in range(n):
            if j > 0 and dayid[j] != dayid[j - 1]: cur = 0
            if hm[j] < h1: side[j] = 0; continue
            side[j] = cur if cur != 0 else 2
            if cur == 0 and not np.isnan(hi[j]):
                if C[j] > hi[j] - S[j]: cur = 1
                elif C[j] < lo[j]: cur = -1
        return side

    def inter(a, b):
        out = np.where(a == 2, b, np.where(b == 2, a, np.where(a == b, a, 0)))
        out[(a == 0) | (b == 0)] = 0
        return out.astype(np.int64)

    def row(lab, allow, bsA=NAN, ssA=NAN):
        out = []
        for orr in (False, True):
            out.append(sim(O, H, L, C, S, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, orr, 1, allow, bsA, ssA))
        xS, pS = sim(O, H, L, C, S * 1.5, live, dayid, usd, 5.0, 1.0, 3.0, 25.0, False, 1, allow, bsA, ssA)
        xi, p = out[0]; te = T[xi]; m = te >= a3; m2 = te < a3; v = p[m]
        dp = pd.Series(v, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum()
        dp2 = pd.Series(p[m2], index=te[m2].normalize()).groupby(level=0).sum(); eq2 = dp2.cumsum()
        xc, pc = out[1]; tc = T[xc]
        say(f"{lab:34s} | {len(v):5d} {len(v) / nd:4.0f} {pf(v):5.2f} {pf(pS[T[xS] >= a3]):5.2f} {v.sum():+6.0f} {(eq - eq.cummax()).min():+5.0f} {dp.min():+5.0f} "
            f"{(dp < -30).sum():4d} | {pf(p[m2]):7.2f} {p[m2].sum():+6.0f} {(eq2 - eq2.cummax()).min():+5.0f} {dp2.min():+5.0f} | {pf(pc[tc >= a3]):7.2f} {pf(pc[tc < a3]):5.2f}")

    say(f"FLIP + ORB (range 01:00-04:00 server), LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), v2.35 engine, gap $5, 0.01 lot")
    say(f"{'variant':34s} | {'trd':>5} {'/day':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'<-30':>4} | {'prev PF':>7} {'net$':>6} {'DD':>5} {'wDay':>5} | {'coin PF':>7} {'prev':>5}")
    row("LIVE (01:30 OCO +-$3)", ALL)
    row("D1REV (v2.43)", d1rev)
    hi, lo = rng(60, 240)
    al, bsA, ssA = start_arrays(240, hi, lo)
    row("ORB START", al, bsA, ssA)
    row("ORB START + D1REV", inter(al, d1rev), bsA, ssA)
    od = dir_after(240, hi, lo)
    row("ORB DIR", od, bsA, ssA)
    row("ORB DIR + D1REV", inter(od, d1rev), bsA, ssA)
    rv = -od; rv[od == 2] = 2; rv[od == 0] = 0
    row("ORB DIR reversed", rv, bsA, ssA)
    say("-- ORB range length --")
    for h1 in (180, 300):
        h, l = rng(60, h1); a_, b_, s_ = start_arrays(h1, h, l)
        row(f"ORB START 01:00-{h1 // 60:02d}:00", a_, b_, s_)
        row(f"ORB START 01:00-{h1 // 60:02d}:00 + D1REV", inter(a_, d1rev), b_, s_)
    say("-- controls --")
    row("start 04:00, OCO 04:00 open +-$3", np.where(hm >= 240, 2, 0).astype(np.int64))
    row("start 04:00 + D1REV", inter(np.where(hm >= 240, 2, 0).astype(np.int64), d1rev))
    for sh in (-0.5, 0.5):
        h, l = rng(60, 240, sh); a_, b_, s_ = start_arrays(240, h, l)
        row(f"ORB START range shifted {sh:+.1f}", a_, b_, s_)
    h, l = rng(600, 780); a_, b_, s_ = start_arrays(780, h, l)
    row("FAKE range 10:00-13:00 START", a_, b_, s_)
    row("FAKE range 10:00-13:00 DIR", dir_after(780, h, l), b_, s_)
    for sd in (1, 2, 3):
        r = np.random.default_rng(sd); sg = np.where(r.random(dayid.max() - dayid.min() + 1) < 0.5, 1, -1)[dayid - dayid.min()]
        row(f"random side per day after 04:00 s{sd}", np.where(hm >= 240, sg, 0).astype(np.int64), bsA, ssA)


if __name__ == "__main__":
    main()
