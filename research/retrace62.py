"""Round 62 (7 Nov 2026): how many times does price pull back inside one gold M1 trend?

Owner: "dalam 1 trend ada berapa kali dia retrace".
Trend = a 0.10% wick zigzag leg (as live FizyLEG; a leg ends when price reverses 0.10%, ~$4).
Retracement = a smaller counter-move inside that leg, counted with a second wick zigzag of $1 / $2 / $3
(absolute dollars) run over the bars of the leg only. Reported per leg: number of pullbacks, by leg length,
whole history and 2026. Control: the same on the day-shuffled path.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)


def legs(H, L, newd, pct):
    out = []; d_ = ext = piv = lo0 = hi0 = 0
    for k in range(len(H)):
        if newd[k]: d_, ext, piv, lo0, hi0 = 0, k, k, k, k; continue
        if d_ == 0:
            if L[k] < L[lo0]: lo0 = k
            if H[k] > H[hi0]: hi0 = k
            if H[k] >= L[lo0] * (1 + pct): d_, piv, ext = 1, lo0, k
            elif L[k] <= H[hi0] * (1 - pct): d_, piv, ext = -1, hi0, k
            continue
        if d_ == 1:
            if H[k] > H[ext]: ext = k
            elif L[k] <= H[ext] * (1 - pct): out.append((piv, ext, 1)); piv, d_, ext = ext, -1, k
        else:
            if L[k] < L[ext]: ext = k
            elif H[k] >= L[ext] * (1 + pct): out.append((piv, ext, -1)); piv, d_, ext = ext, 1, k
    return out


def pullbacks(H, L, a, b, dr, step):
    """count counter-moves of >= step dollars inside bars a..b of a leg going dr"""
    cnt = 0; depth = []
    ext = L[a] if dr == 1 else H[a]          # running extreme in the trend direction
    if dr == 1: ext = H[a]
    else: ext = L[a]
    inpb = False; pbext = None
    for k in range(a, b + 1):
        if dr == 1:
            if H[k] > ext:
                if inpb: cnt += 1; depth.append(ext - pbext)
                ext = H[k]; inpb = False; pbext = None
            elif ext - L[k] >= step:
                pbext = L[k] if pbext is None else min(pbext, L[k]); inpb = True
        else:
            if L[k] < ext:
                if inpb: cnt += 1; depth.append(pbext - ext)
                ext = L[k]; inpb = False; pbext = None
            elif H[k] - ext >= step:
                pbext = H[k] if pbext is None else max(pbext, H[k]); inpb = True
    return cnt, depth


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); day = B.date.values; newd = np.r_[True, day[1:] != day[:-1]]
    yr = B.index.year.values
    rng = np.random.default_rng(62)
    lr = np.r_[0.0, np.diff(np.log(C))]; lr[newd] = 0
    st = np.where(newd)[0]; en = np.r_[st[1:], n]
    Cs = np.empty(n)
    for a, b in zip(st, en):
        seg = lr[a + 1:b].copy(); rng.shuffle(seg); Cs[a] = C[a]; Cs[a + 1:b] = C[a] * np.exp(np.cumsum(seg))
    hr = (H - L) / 2; Os = np.r_[Cs[0], Cs[:-1]]; Os[newd] = Cs[newd]
    Hs = np.maximum(Os, Cs) + 0.5 * hr; Ls = np.minimum(Os, Cs) - 0.5 * hr
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}; trend = 0.10% wick zigzag leg")
    for HH, LL, tag in ((H, L, "REAL"), (Hs, Ls, "SHUFFLED control")):
        lg = legs(HH, LL, newd, 0.001)
        say(f"\n=== {tag}: {len(lg):,} trends ===")
        for step in (1.0, 2.0, 3.0):
            rows = []
            for a, b, dr in lg:
                c, dp = pullbacks(HH, LL, a, b, dr, step)
                rows.append((b - a, c, yr[a], np.mean(dp) if dp else 0))
            R = pd.DataFrame(rows, columns=["len", "pb", "yr", "depth"])
            say(f"pullbacks of >= ${step:.0f} inside a trend: mean {R.pb.mean():.2f}, "
                f"0: {100 * (R.pb == 0).mean():.0f}%  1: {100 * (R.pb == 1).mean():.0f}%  2: {100 * (R.pb == 2).mean():.0f}%  "
                f"3: {100 * (R.pb == 3).mean():.0f}%  4+: {100 * (R.pb >= 4).mean():.0f}%; mean depth ${R.depth[R.pb > 0].mean():.2f}")
            if tag == "REAL":
                bins = [(1, 9), (10, 19), (20, 29), (30, 59), (60, 10 ** 6)]
                say("   by trend length: " + "  ".join(
                    f"{lo}-{hi if hi < 10 ** 6 else '+'} candles: {R.pb[(R.len >= lo) & (R.len <= hi)].mean():.1f}" for lo, hi in bins))
                r26 = R[R.yr == 2026]
                say(f"   2026 only: mean {r26.pb.mean():.2f}, 0: {100 * (r26.pb == 0).mean():.0f}%, "
                    f"1: {100 * (r26.pb == 1).mean():.0f}%, 2+: {100 * (r26.pb >= 2).mean():.0f}%; trends of 20+ candles: {r26.pb[r26.len >= 20].mean():.1f}")


if __name__ == "__main__":
    main()
