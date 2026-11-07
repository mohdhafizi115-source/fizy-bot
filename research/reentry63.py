"""Round 63 (7 Nov 2026): re-enter a gold M1 trend after its pullback.

Owner: "jadi macam mana aku nak reentry selepas retrace" (round 62: most 2026 trends pull back once, by
~$2, then go on). Trend = 0.10% wick zigzag leg (live FizyLEG definition), all ONLINE on closed bars.
  BREAK  after the leg's first pullback of >= X dollars, a stop order at the leg extreme: when price takes
         out the extreme again, enter WITH the trend. SL beyond the pullback extreme. TP 1R / 2R, or out
         after 30 min.
  DIP    a limit order X dollars back from the leg extreme: enter WITH the trend on the pullback. SL where
         the leg would end (0.10% from the extreme). TP back at the extreme, or 1 X beyond it.
  first pullback only, or also the second. Gate 8 variant. Controls: random direction at the same entries;
  the same rule on the day-shuffled path.
Pass rule: >= 150 trades, PF >= 1.15 after spread, halves >= 1.05, stress 1.5x spread >= 1.05, last 12 m > 0.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    sp = B.s.values.astype(float)
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = atr / np.where(sp > 0, sp, np.nan)
    mid, end = B.index[n // 2], B.index[-1]; ndays = len(np.unique(day))
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars")
    rng = np.random.default_rng(63)
    lr = np.r_[0.0, np.diff(np.log(C))]; lr[newd] = 0
    st = np.where(newd)[0]; en = np.r_[st[1:], n]
    Cs = np.empty(n)
    for a, b in zip(st, en):
        seg = lr[a + 1:b].copy(); rng.shuffle(seg); Cs[a] = C[a]; Cs[a + 1:b] = C[a] * np.exp(np.cumsum(seg))
    hr = (H - L) / 2; Os = np.r_[Cs[0], Cs[:-1]]; Os[newd] = Cs[newd]
    Hs = np.maximum(Os, Cs) + 0.5 * hr; Ls = np.minimum(Os, Cs) - 0.5 * hr

    def run(o, h, l, c, mode, X, R, which=(1,), g=False, rand=False, lab=""):
        pct = 0.001; res = []; rg = np.random.default_rng(7)
        d_ = 0; ext = 0; lo0 = hi0 = 0
        pbn = 0; inpb = False; pbx = None             # pullback count in this leg, in-pullback flag, its extreme
        pend = None                                   # pending order: (kind, level, dir, sl, tp_r, legx)
        busy = -1
        k = 0
        while k < n:
            if newd[k]:
                d_, ext, lo0, hi0 = 0, k, k, k; pbn = 0; inpb = False; pbx = None; pend = None; k += 1; continue
            # --- pending order fill (uses bar k)
            if pend is not None and k > busy and 90 <= hm[k] < 1320:
                kind, lvl, dr, sl, tpd = pend
                fill = None
                if kind == "stop":
                    if dr == 1 and h[k] >= lvl: fill = max(o[k], lvl)
                    if dr == -1 and l[k] <= lvl: fill = min(o[k], lvl)
                else:
                    if dr == 1 and l[k] <= lvl: fill = min(o[k], lvl)
                    if dr == -1 and h[k] >= lvl: fill = max(o[k], lvl)
                if fill is not None and (not g or gate[k] >= 8):
                    if rand: dr = 1 if rg.random() < 0.5 else -1; sl = fill - dr * abs(fill - sl); tpd = tpd
                    risk = abs(fill - sl)
                    tp = fill + dr * (tpd if kind == "limit" else R * risk)
                    if risk > 0:
                        ex = None; q = k + (0 if kind == "limit" else 1)
                        q = k + 1
                        while q < n and q < k + 31:
                            if newd[q]: ex = o[q]; break
                            if dr == 1:
                                if l[q] <= sl: ex = min(o[q], sl); break
                                if h[q] >= tp: ex = max(o[q], tp) if o[q] > tp else tp; break
                            else:
                                if h[q] >= sl: ex = max(o[q], sl); break
                                if l[q] <= tp: ex = min(o[q], tp) if o[q] < tp else tp; break
                            q += 1
                        if ex is None: ex = c[min(q, n - 1)]
                        res.append((k, (ex - fill) * dr, sp[k])); busy = q
                    pend = None
            # --- leg / pullback bookkeeping on closed bar k
            if d_ == 0:
                if l[k] < l[lo0]: lo0 = k
                if h[k] > h[hi0]: hi0 = k
                if h[k] >= l[lo0] * (1 + pct): d_, ext = 1, k; pbn = 0; inpb = False
                elif l[k] <= h[hi0] * (1 - pct): d_, ext = -1, k; pbn = 0; inpb = False
                k += 1; continue
            if d_ == 1:
                if h[k] > h[ext]:
                    ext = k; inpb = False; pend = None if (pend and pend[0] == "limit") else pend
                elif l[k] <= h[ext] * (1 - pct):
                    d_, ext = -1, k; pbn = 0; inpb = False; pend = None; k += 1; continue
                elif not inpb and h[ext] - l[k] >= X:
                    inpb = True; pbn += 1; pbx = l[k]
                    if pbn in which and mode == "break":
                        pend = ("stop", h[ext] + 0.01, 1, pbx - sp[k], None)
                elif inpb: pbx = min(pbx, l[k])
                if mode == "dip" and not inpb and (pbn + 1) in which:
                    pend = ("limit", h[ext] - X, 1, h[ext] * (1 - pct), R)
            else:
                if l[k] < l[ext]:
                    ext = k; inpb = False; pend = None if (pend and pend[0] == "limit") else pend
                elif h[k] >= l[ext] * (1 + pct):
                    d_, ext = 1, k; pbn = 0; inpb = False; pend = None; k += 1; continue
                elif not inpb and h[k] - l[ext] >= X:
                    inpb = True; pbn += 1; pbx = h[k]
                    if pbn in which and mode == "break":
                        pend = ("stop", l[ext] - 0.01, -1, pbx + sp[k], None)
                elif inpb: pbx = max(pbx, h[k])
                if mode == "dip" and not inpb and (pbn + 1) in which:
                    pend = ("limit", l[ext] + X, -1, l[ext] * (1 + pct), R)
            k += 1
        if len(res) < 30: say(f"{lab:>40} too few"); return
        T = pd.DataFrame(res, columns=["k", "pnl", "sp"]); T["t"] = B.index[T.k.values]
        net = (T.pnl - T.sp) * usd; stp = (T.pnl - 1.5 * T.sp) * usd
        pf = lambda x: x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
        h1, h2 = net[T.t < mid], net[T.t >= mid]
        l12 = net[T.t >= end - pd.Timedelta(days=365)].sum()
        eq = net.cumsum().values; dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        wd = net.groupby(T.t.dt.normalize().values).sum().min()
        ok = len(T) >= 150 and pf(net) >= 1.15 and pf(h1) >= 1.05 and pf(h2) >= 1.05 and pf(stp) >= 1.05 and l12 > 0
        say(f"{lab:>40} {len(T):6d} {len(T) / ndays:5.2f} {100 * (net > 0).mean():5.1f} {pf(net):5.2f} {pf(h1):5.2f} "
            f"{pf(h2):5.2f} {pf(stp):5.2f} {l12:+7.0f} {net.sum():+7.0f} {dd:+7.0f} {wd:+7.1f}  {'PASS' if ok and not rand and 'SHUF' not in lab else ''}")

    say(f"{'variant':>40} {'trades':>6} {'/day':>5} {'win%':>5} {'PF':>5} {'h1':>5} {'h2':>5} {'strs':>5} {'last12':>7} "
        f"{'net$':>7} {'maxDD':>7} {'worstd':>7}")
    for X in (1.0, 2.0, 3.0):
        for R in (1.0, 2.0):
            run(O, H, L, C, "break", X, R, lab=f"BREAK pb${X:.0f} 1st TP {R:.0f}R")
        run(O, H, L, C, "break", X, 1.0, which=(1, 2), lab=f"BREAK pb${X:.0f} 1st+2nd TP 1R")
        run(O, H, L, C, "break", X, 1.0, g=True, lab=f"BREAK pb${X:.0f} 1st TP 1R gate8")
        run(O, H, L, C, "break", X, 1.0, rand=True, lab=f"BREAK pb${X:.0f} RANDOM dir")
        run(Os, Hs, Ls, Cs, "break", X, 1.0, lab=f"BREAK pb${X:.0f} SHUFFLED path")
        for tpd in (X, 2 * X):
            run(O, H, L, C, "dip", X, tpd, lab=f"DIP pb${X:.0f} 1st TP +${tpd:.0f}")
        run(O, H, L, C, "dip", X, 2 * X, g=True, lab=f"DIP pb${X:.0f} TP +${2 * X:.0f} gate8")
        run(Os, Hs, Ls, Cs, "dip", X, 2 * X, lab=f"DIP pb${X:.0f} SHUFFLED path")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
