"""Round 57 (6 Nov 2026): count Heikin Ashi candles on gold M1 instead of zigzag legs.

Owner: "kalau guna heikin ashi?" (after asking to count candles of a trend instead of zigzag legs).
  A. How many HA candles of the same colour in a row? real vs day-shuffled path (control).
  B. The owner's leg-fade structure on HA runs: when an HA run of one colour reaches N candles, fade it
     at the next open; add one more every 0.10% further against, up to 5 x 0.01 lot; TP 0.35% per
     position; NO SL; swap -$0.80 a night per position; $100 account, 1:500, stop-out at 50% margin level.
  C. The same signal with a normal trade: fade or follow, SL 1 ATR(60 bars of M1 range), TP 1 ATR, 60 min,
     one position, so a plain edge (if any) shows without the basket.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def ha(o, h, l, c, newd):
    hc = (o + h + l + c) / 4
    ho = np.empty_like(c)
    ho[0] = (o[0] + c[0]) / 2
    for k in range(1, len(c)):
        ho[k] = (o[k] + c[k]) / 2 if newd[k] else (ho[k - 1] + hc[k - 1]) / 2
    return np.sign(hc - ho)


def runs(col, newd):
    """run length so far at each bar (same colour in a row, reset each day)"""
    n = len(col); r = np.zeros(n, int)
    for k in range(n):
        r[k] = 1 if (newd[k] or col[k] != col[k - 1] or col[k] == 0) else r[k - 1] + 1
    return r


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    sp = B.s.values.astype(float); wd = B.index.dayofweek.values; yr = B.index.year.values
    ndays = len(np.unique(day))
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, {ndays} days")

    # control path
    rng = np.random.default_rng(57)
    lr = np.r_[0.0, np.diff(np.log(C))]; lr[newd] = 0
    st = np.where(newd)[0]; en = np.r_[st[1:], n]
    Cs = np.empty(n)
    for a, b in zip(st, en):
        seg = lr[a + 1:b].copy(); rng.shuffle(seg); Cs[a] = C[a]; Cs[a + 1:b] = C[a] * np.exp(np.cumsum(seg))
    hr = (H - L) / 2
    Os = np.r_[Cs[0], Cs[:-1]]; Os[newd] = Cs[newd]
    Hs = np.maximum(Os, Cs) + 0.5 * hr; Ls = np.minimum(Os, Cs) - 0.5 * hr

    col = ha(O, H, L, C, newd); R = runs(col, newd)
    cols = ha(Os, Hs, Ls, Cs, newd); Rs = runs(cols, newd)
    # completed run lengths
    def done(R, col):
        end = np.r_[R[1:] == 1, True]
        return R[end], col[end]
    L1, c1 = done(R, col); L2, c2 = done(Rs, cols)
    say("\n=== A. Heikin Ashi M1: how many candles of the same colour in a row ===")
    say(f"{'':>8} {'runs':>8} {'median':>7} {'mean':>6} {'p75':>5} {'p90':>5} {'p95':>5} {'p99':>5} {'max':>5} | shuffled median p90 p99")
    for s, lab in ((1, "GREEN"), (-1, "RED")):
        a, b = L1[c1 == s], L2[c2 == s]
        q = lambda x, p: np.percentile(x, p)
        say(f"{lab:>8} {len(a):8d} {q(a,50):7.0f} {a.mean():6.1f} {q(a,75):5.0f} {q(a,90):5.0f} {q(a,95):5.0f} {q(a,99):5.0f} {a.max():5d}"
            f" | {q(b,50):6.0f} {q(b,90):4.0f} {q(b,99):4.0f}")
    say(f"runs per day: {len(L1) / ndays:.0f}")
    say("share of runs that reach N, and of those how many go 5 more (real / shuffled):")
    for N in (5, 10, 15, 20, 30):
        a = L1; b = L2
        say(f"  N={N:3d}: reach {100 * (a >= N).mean():5.2f}% / {100 * (b >= N).mean():5.2f}%   "
            f"go 5 more {100 * (a >= N + 5).sum() / max((a >= N).sum(), 1):5.1f}% / {100 * (b >= N + 5).sum() / max((b >= N).sum(), 1):5.1f}%")

    pct, tpp = 0.0010, 0.0035
    def basket(N, maxn=5, mode="fade"):
        bal, blow, closed, pos, bt = 100.0, 0, [], [], []
        for k in range(n):
            if newd[k] and pos: bal -= 0.8 * len(pos)
            if pos:
                keep = []
                for e, dd, k0 in pos:
                    tp = e * (1 + dd * tpp)
                    hit = (L[k] + sp[k] <= tp) if dd == -1 else (H[k] >= tp)
                    if hit:
                        x = min(O[k] + sp[k], tp) if dd == -1 else max(O[k], tp)
                        p = (x - e) * dd * usd; bal += p; closed.append((k, p))
                    else: keep.append([e, dd, k0])
                pos = keep
            if pos:
                dr = pos[0][1]; last = pos[-1][0]; lvl = last * (1 - dr * pct)
                while len(pos) < maxn and 90 <= hm[k] < 1425 and ((dr == -1 and H[k] >= lvl) or (dr == 1 and L[k] + sp[k] <= lvl)):
                    e = max(O[k], lvl) if dr == -1 else min(O[k] + sp[k], lvl)
                    pos.append([e, dr, k]); lvl = e * (1 - dr * pct)
                adv = (H[k] + sp[k]) if dr == -1 else L[k]
                fl = sum((adv - e) * dd * usd for e, dd, _ in pos)
                if bal + fl <= 0.5 * len(pos) * C[k] / 500:
                    for e, dd, _ in pos: closed.append((k, (adv - e) * dd * usd))
                    blow += 1; bt.append(k); pos = []; bal = 100.0
            if R[k] == N and col[k] != 0 and not pos and k + 1 < n and not newd[k + 1] and 90 <= hm[k] < 1320 and wd[k] < 5:
                dr = -int(col[k])
                pos.append([O[k + 1] if dr == -1 else O[k + 1] + sp[k + 1], dr, k + 1])
        T = pd.DataFrame(closed, columns=["k", "net"]); T["t"] = B.index[T.k.values]
        g, ls = T.net[T.net > 0].sum(), -T.net[T.net < 0].sum()
        l12 = T.t >= B.index[-1] - pd.Timedelta(days=365)
        say(f"HA run {N:3d}: {len(T):6d} closed ({len(T) / ndays:.2f}/day) win {100 * (T.net > 0).mean():4.1f}% PF {g / ls if ls else 0:.2f} "
            f"net ${T.net.sum():+7.0f}  last12 ${T[l12].net.sum():+6.0f}  STOP-OUTS {blow:3d} (last 12 m "
            f"{sum(1 for q in bt if B.index[q] >= B.index[-1] - pd.Timedelta(days=365))})")

    c1_ = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1_), np.abs(L - c1_)))
    atr = pd.Series(tr).rolling(60).mean().shift(1).values
    def plain(N, mode):
        res, busy = [], -1
        for k in np.where((R == N) & (col != 0))[0]:
            if k <= busy or k + 2 >= n or newd[k + 1] or not (90 <= hm[k] < 1320) or not np.isfinite(atr[k]): continue
            dr = -int(col[k]) if mode == "fade" else int(col[k])
            e = O[k + 1]; a = atr[k]; sl = e - dr * a; tp = e + dr * a; ex = None
            for q in range(k + 1, min(n, k + 61)):
                if newd[q]: ex = O[q]; break
                if dr == 1:
                    if L[q] <= sl: ex = sl; break
                    if H[q] >= tp: ex = tp; break
                else:
                    if H[q] >= sl: ex = sl; break
                    if L[q] <= tp: ex = tp; break
            if ex is None: ex = C[q]
            res.append(((ex - e) * dr - sp[k + 1]) * usd); busy = q
        a = np.array(res); g, ls = a[a > 0].sum(), -a[a < 0].sum()
        h = len(a) // 2; pf = lambda x: x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
        say(f"HA run {N:3d} {mode:6s}: {len(a):6d} trades ({len(a) / ndays:.2f}/day) win {100 * (a > 0).mean():4.1f}% PF {g / ls:.2f} "
            f"halves {pf(a[:h]):.2f}/{pf(a[h:]):.2f} net ${a.sum():+7.0f}")

    p90 = int(np.percentile(L1, 90)); p95 = int(np.percentile(L1, 95)); p99 = int(np.percentile(L1, 99))
    say(f"\n=== B. The owner's structure (fade, adds every 0.10%, max 5, TP 0.35%, NO SL), $100 account ===")
    for N in sorted({p90, p95, p99, 20}):
        basket(N)
    say(f"\n=== C. Plain trade on the same signal (SL 1 ATR, TP 1 ATR, 60 min, one position) ===")
    for N in sorted({p90, p95, p99, 20}):
        plain(N, "fade"); plain(N, "follow")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
