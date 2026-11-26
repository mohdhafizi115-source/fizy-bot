# Round 170 (M1) / 170b (env TF=300 CAP=12 for M5, TF=900 CAP=16 for M15): TRENDLINE + S/R on gold M1, real ticks (owner: "teknik trendline gabung dengan snr. kalau trendline sell
# di break oleh bull, jgn terus buy tapi check kena break juga resistant. test di m1").
# M1 bars from the ticks (tl169 engine). Online fractal swings n 3 / 5 / 10 (known n bars later).
# Falling trendline = 2 latest swing highs (lower high). A close above it = TL break. Then WAIT: buy only when a later
# close (within W bars) is above the RESISTANCE, before any close back below the line. Resistance =
#   near: the nearest unbroken swing high above the break close (last 50 swings), or
#   last: the line's own last swing high (the lower high).
# If the close is already above the resistance at the break, enter at once. Mirror for sells (rising line, support).
# Controls: TL break alone (enter at once), S/R break alone (close above the nearest unbroken swing high, no line),
# and 2 random-direction twins of every cell. Entry next M1 open at the real ask / bid, exits on M1 bid / ask,
# SL 1.5 ATR(M1) or beyond the 10-bar extreme, TP 1 / 2 / 3R, out after 60 min, one position at a time,
# no entries 23:45-01:30 server, optional cost gate ATR(M1) >= 8 x spread. 0.01 lot. Last 3 months / the 3 before.
import numpy as np, pandas as pd
exec(open("tl169.py").read().split("E = M_t[-1] + 1")[0])
E = M_t[-1] + 1
import os
TFS = int(os.environ.get("TF", "60")); B = bars(TFS); B["sp"] = M_ao[B["s"]] - M_bo[B["s"]]
CAP = int(os.environ.get("CAP", "60"))   # in bars of the timeframe

def unbroken(v, idx, j, up):
    seg = v[idx + 1:j + 1]
    return (seg.max() < v[idx]) if up else (seg.min() > v[idx])

def sig170(n, mode, W, rmode, gate):
    h, l, c, atr, tt, sp = B["h"], B["l"], B["c"], B["atr"], B["t"], B["sp"]; N = len(c)
    sh, sl, out, pend = [], [], [], []
    used_h = used_l = -1; used_r = set()
    def line(i1, i2, v, x): return v[i2] + (v[i2] - v[i1]) / (i2 - i1) * (x - i2)
    for j in range(2 * n + 1, N):
        i = j - n
        if h[i] == h[i - n:i + n + 1].max() and h[i] > h[i - n:i].max(): sh.append(i)
        if l[i] == l[i - n:i + n + 1].min() and l[i] < l[i - n:i].min(): sl.append(i)
        mins = (tt[j] // 60000) % 1440
        ok = 90 <= mins < 1425 and (not gate or atr[j] >= 8 * sp[j])
        def fire(d):
            if ok: out.append((j, d))
        if mode == "snr":
            for d, lst, v, up in ((1, sh, h, True), (-1, sl, l, False)):
                for idx in lst[-50:][::-1]:
                    if idx in used_r: continue
                    lev = v[idx]
                    if (up and c[j] > lev and c[j - 1] <= lev) or ((not up) and c[j] < lev and c[j - 1] >= lev):
                        if unbroken(v, idx, j - 1, up): used_r.add(idx); fire(d)
                        break
            continue
        # trendline breaks
        if len(sh) >= 2:
            i1, i2 = sh[-2], sh[-1]
            if h[i2] < h[i1] and used_h != i2 and j - 1 > i2:
                L0, L1 = line(i1, i2, h, j), line(i1, i2, h, j - 1)
                if c[j] > L0 and c[j - 1] <= L1:
                    used_h = i2
                    if mode == "tl": fire(1)
                    else:
                        if rmode == "last": R = h[i2]
                        else:
                            cand = [h[k] for k in sh[-50:] if h[k] > c[j] and unbroken(h, k, j, True)]
                            R = min(cand) if cand else None
                        if R is None or c[j] > R: fire(1)
                        else: pend.append([j, 1, i1, i2, R])
        if len(sl) >= 2:
            i1, i2 = sl[-2], sl[-1]
            if l[i2] > l[i1] and used_l != i2 and j - 1 > i2:
                L0, L1 = line(i1, i2, l, j), line(i1, i2, l, j - 1)
                if c[j] < L0 and c[j - 1] >= L1:
                    used_l = i2
                    if mode == "tl": fire(-1)
                    else:
                        if rmode == "last": S = l[i2]
                        else:
                            cand = [l[k] for k in sl[-50:] if l[k] < c[j] and unbroken(l, k, j, False)]
                            S = max(cand) if cand else None
                        if S is None or c[j] < S: fire(-1)
                        else: pend.append([j, -1, i1, i2, S])
        if pend:
            keep = []
            for p in pend:
                jb, d, i1, i2, lev = p
                if j <= jb: keep.append(p); continue
                if j - jb > W: continue
                v = h if d == 1 else l; L0 = line(i1, i2, v, j)
                if (d == 1 and c[j] < L0) or (d == -1 and c[j] > L0): continue      # failed TL break
                if (d == 1 and c[j] > lev) or (d == -1 and c[j] < lev): fire(d); continue
                keep.append(p)
            pend = keep
    return out

def run2(sig, slm, tpR, rnd=None, stress=1.0):
    s, h, l, atr, c = B["s"], B["h"], B["l"], B["atr"], B["c"]; NB = len(s)
    res = []; busy = -1; rng = np.random.default_rng(rnd) if rnd is not None else None
    for (j, d) in sig:
        if j + 1 >= NB: continue
        m0 = s[j + 1]
        if m0 <= busy: continue
        if rng is not None: d = 1 if rng.random() < 0.5 else -1
        if slm == "atr": dist = 1.5 * atr[j]
        else:
            dist = (c[j] - l[max(0, j - 9):j + 1].min() + 0.1 * atr[j]) if d == 1 else (h[max(0, j - 9):j + 1].max() - c[j] + 0.1 * atr[j])
            dist = max(dist, 0.5 * atr[j])
        mend = s[j + 1 + CAP] if j + 1 + CAP < NB else NM
        p, mx = trade(m0, d, dist, tpR, mend, stress); busy = mx; res.append((M_t[m0], p))
    return res

print("mode   n  W   R    gate SL   TP | LAST 3 M: trades win PF stress net DD worstDay rand | PREV 3 M: trades PF net rand", flush=True)
rows = []
cfgs = [("tl", 0, "-")] + [("tlsr", W, r) for W in (30, 120) for r in ("near", "last")] + [("snr", 0, "-")]
for n in tuple(int(x) for x in os.environ.get("NS", "3,5,10").split(",")):
    for mode, W, rm in cfgs:
        for gate in (False, True):
            sig = sig170(n, mode, W, rm, gate)
            for slm in ("atr", "swing"):
                for tpR in (1, 2, 3):
                    r = run2(sig, slm, tpR); rs = run2(sig, slm, tpR, stress=1.5)
                    rr = [run2(sig, slm, tpR, rnd=k) for k in (1, 2)]
                    x, y, xs = stats(r, A3, E), stats(r, A6, A3), stats(rs, A3, E)
                    xr = [stats(q, A3, E)["pf"] for q in rr]; yr = [stats(q, A6, A3)["pf"] for q in rr]
                    ok = x["n"] >= 30 and x["pf"] >= 1.15 and xs["pf"] >= 1.05 and x["net"] > 0
                    fl = (" PASS" if ok else "") + ("+REPEAT" if ok and y["pf"] >= 1.15 else "") + (" (random as good)" if ok and max(xr) >= x["pf"] else "")
                    print(f"{mode:5s} {n:2d} {W:3d} {rm:4s} {'G8' if gate else '- '}   {slm:5s} {tpR}R | {x['n']:5d} {x['win']:3.0f}% PF {x['pf']:4.2f} st {xs['pf']:4.2f} "
                          f"net {x['net']:+7.0f} DD {x['dd']:+6.0f} wd {x['wd']:+5.0f} rand {xr[0]:4.2f}/{xr[1]:4.2f} | {y['n']:5d} PF {y['pf']:4.2f} net {y['net']:+7.0f} "
                          f"rand {yr[0]:4.2f}/{yr[1]:4.2f}{fl}", flush=True)
                    rows.append(dict(mode=mode, n=n, W=W, R=rm, gate=gate, sl=slm, tp=tpR, n3=x["n"], pf3=x["pf"], net3=x["net"], dd3=x["dd"],
                                     r3=max(xr), n6=y["n"], pf6=y["pf"], net6=y["net"], r6=max(yr), ok=ok))
D = pd.DataFrame(rows)
print("\nSUMMARY (median PF last 3 m / previous, median of the better random twin)")
for k, q in D.groupby(["mode", "R"]):
    print(f"  {k[0]:5s} {k[1]:4s}: cells {len(q):3d}, trades/3m median {q.n3.median():6.0f}, PF {q.pf3.median():.2f} / {q.pf6.median():.2f}, random {q.r3.median():.2f} / {q.r6.median():.2f}, "
          f"pass both windows {((q.pf3>=1.15)&(q.pf6>=1.15)&(q.n3>=30)&(q.n6>=30)).sum()}")
both = D[(D.ok) & (D.pf6 >= 1.15) & (D.n6 >= 30)]
print(f"pass last 3 m {D.ok.sum()} of {len(D)}, also >= 1.15 before {len(both)}, of which beat both random twins in both windows {((both.pf3>both.r3)&(both.pf6>both.r6)).sum()}")
print(both.sort_values("pf3", ascending=False).head(15).to_string(index=False))
