"""Round 64 (7 Nov 2026): read the leg's candle count at the pullback -- continue if young, fade if old.

Owner: "kalau tak tahu trend masih sambung atau patah balik baca la bilangan candle dah ke berapa, kalau dah
hujung2 memang la patah balik ... cukup 1 bulan dah". Judged on the LAST MONTH (owner's choice), with the
month before shown next to it as a repeat check.
Trend = 0.10% wick zigzag leg (live FizyLEG). At the leg's first pullback of >= X dollars, its age A (candles
since the leg's start, a closed-bar count):
  A <  N  -> CONTINUE: buy-stop / sell-stop at the leg extreme, SL beyond the pullback, TP 1R
  A >= N  -> FADE: enter against the leg at the next open, SL beyond the leg extreme, TP 1R
Out after 30 min. One position at a time. $ per 0.01 lot after spread. Random-direction control.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    B = B[B.index >= B.index[-1] - pd.Timedelta(days=62)]              # two months is all this needs
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]; sp = B.s.values.astype(float)
    end = B.index[-1]; m1 = end - pd.Timedelta(days=30); m0 = end - pd.Timedelta(days=60)
    say(f"XAUUSD M1, last month {m1:%d %b} .. {end:%d %b %Y}, month before {m0:%d %b} .. {m1:%d %b}")

    def run(X, N, use, rand=False):
        pct = 0.001; res = []; rg = np.random.default_rng(64)
        d_ = ext = piv = lo0 = hi0 = 0; pbn = 0; inpb = False; pbx = None; pend = None; busy = -1
        for k in range(n):
            if newd[k]:
                d_, ext, piv, lo0, hi0 = 0, k, k, k, k; pbn = 0; inpb = False; pend = None; continue
            # pending entry
            if pend is not None and k > busy and 90 <= hm[k] < 1320:
                kind, lvl, dr, sl = pend; fill = None
                if kind == "now": fill = O[k] + (sp[k] if dr == 1 else 0)
                elif dr == 1 and H[k] >= lvl: fill = max(O[k], lvl)
                elif dr == -1 and L[k] <= lvl: fill = min(O[k], lvl)
                if fill is not None:
                    if rand:
                        dist = abs(fill - sl); dr = 1 if rg.random() < 0.5 else -1; sl = fill - dr * dist
                    risk = abs(fill - sl); tp = fill + dr * risk
                    if risk > 0:
                        ex = None; q = k + 1
                        while q < n and q < k + 31:
                            if newd[q]: ex = O[q]; break
                            if dr == 1:
                                if L[q] <= sl: ex = min(O[q], sl); break
                                if H[q] >= tp: ex = tp; break
                            else:
                                if H[q] + sp[q] >= sl: ex = max(O[q] + sp[q], sl); break
                                if L[q] + sp[q] <= tp: ex = tp; break
                            q += 1
                        if ex is None: ex = C[min(q, n - 1)]
                        cost = sp[k] if dr == -1 else 0.0                  # buys paid the ask at entry already
                        res.append((k, ((ex - fill) * dr - (sp[k] if dr == -1 else 0) - (0 if dr == -1 else 0)) * usd))
                        busy = q
                    pend = None
            # leg bookkeeping
            if d_ == 0:
                if L[k] < L[lo0]: lo0 = k
                if H[k] > H[hi0]: hi0 = k
                if H[k] >= L[lo0] * (1 + pct): d_, piv, ext = 1, lo0, k; pbn = 0; inpb = False
                elif L[k] <= H[hi0] * (1 - pct): d_, piv, ext = -1, hi0, k; pbn = 0; inpb = False
                continue
            if d_ == 1:
                if H[k] > H[ext]: ext = k; inpb = False
                elif L[k] <= H[ext] * (1 - pct): piv, d_, ext = ext, -1, k; pbn = 0; inpb = False; pend = None; continue
                elif not inpb and H[ext] - L[k] >= X:
                    inpb = True; pbn += 1; age = k - piv
                    if pbn == 1:
                        if age < N and use in ("cont", "both"): pend = ("stop", H[ext] + 0.01, 1, L[k] - sp[k])
                        if age >= N and use in ("fade", "both"): pend = ("now", None, -1, H[ext] + sp[k])
            else:
                if L[k] < L[ext]: ext = k; inpb = False
                elif H[k] >= L[ext] * (1 + pct): piv, d_, ext = ext, 1, k; pbn = 0; inpb = False; pend = None; continue
                elif not inpb and H[k] - L[ext] >= X:
                    inpb = True; pbn += 1; age = k - piv
                    if pbn == 1:
                        if age < N and use in ("cont", "both"): pend = ("stop", L[ext] - 0.01, -1, H[k] + sp[k])
                        if age >= N and use in ("fade", "both"): pend = ("now", None, 1, L[ext] - sp[k])
        T = pd.DataFrame(res, columns=["k", "net"]); T["t"] = B.index[T.k.values]
        return T

    def show(lab, T):
        def part(a, b):
            x = T.net[(T.t >= a) & (T.t < b)]
            if len(x) == 0: return "   0 trades"
            g, l = x[x > 0].sum(), -x[x < 0].sum()
            wd = x.groupby(T.t[(T.t >= a) & (T.t < b)].dt.normalize().values).sum().min()
            return f"{len(x):4d} tr {100 * (x > 0).mean():3.0f}% win PF {g / l if l else 0:4.2f} net ${x.sum():+6.0f} worst day ${wd:+5.0f}"
        say(f"{lab:>34} | LAST MONTH {part(m1, end + pd.Timedelta(minutes=1))} | MONTH BEFORE {part(m0, m1)}")

    for X in (1.0, 2.0):
        say(f"\n--- first pullback of ${X:.0f} ---")
        for N in (5, 10, 15, 20):
            show(f"age<{N} continue", run(X, N, "cont"))
            show(f"age>={N} fade", run(X, N, "fade"))
            show(f"both (N={N})", run(X, N, "both"))
            show(f"both (N={N}) RANDOM direction", run(X, N, "both", rand=True))


if __name__ == "__main__":
    main()
