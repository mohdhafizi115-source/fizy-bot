"""Round 58 (6 Nov 2026): the owner's 18-24 candle cycle on gold M1.

Owner: "FOKUS PADA 18-24 CANDLE UNTUK 1 PERJALANAN. price akan break dan berbalik arah semula dari arah
sebelumnya ... V ... W ... M ... perjalanan ini berlaku disemua TF dengan jumlah candle yg sama."
(He sent three points -- legs of 18-24 candles, a yellow/aqua signal-line cross after 130-145 candles,
CCI peaking every 18-24 / 130-145 candles -- and asked to focus on point 1 only.)

Tested three ways, each with a control (the same M1 returns shuffled inside each day):
  A. Leg length: zigzag legs at 0.05 / 0.10 / 0.20% -- is 18-24 candles a peak in the length distribution,
     and once a leg is 18 candles old does it end by candle 24 more often than chance?
  B. Without any zigzag: if a cycle of ~2 x 21 candles exists, the move of the last L candles predicts
     the OPPOSITE move over the next L candles. corr(last L, next L) for L = 6..60, real vs shuffled.
     A real 18-24 cycle shows as a negative dip around L = 18-24 that the shuffled path does not have.
  C. Trading it: fade the move of the last L candles (L = 18 / 21 / 24), entry at the next open, SL and
     TP at 1 x the size of that move, out after L candles; also a version gated by ATR >= 8 x spread.
Pass rule: >= 150 trades, PF >= 1.15 after spread, both halves >= 1.05, stress 1.5x spread >= 1.05.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def zz_lengths(c, newd, pct):
    out = []; d_ = 0; ext = piv = 0
    for k in range(len(c)):
        if newd[k]: d_, ext, piv = 0, k, k; continue
        if d_ == 0:
            if c[k] >= c[piv] * (1 + pct): d_, ext = 1, k
            elif c[k] <= c[piv] * (1 - pct): d_, ext = -1, k
            continue
        if d_ == 1:
            if c[k] > c[ext]: ext = k
            elif c[k] <= c[ext] * (1 - pct): out.append(ext - piv); piv, d_, ext = ext, -1, k
        else:
            if c[k] < c[ext]: ext = k
            elif c[k] >= c[ext] * (1 + pct): out.append(ext - piv); piv, d_, ext = ext, 1, k
    return np.array(out)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    sp = B.s.values.astype(float)
    mid = n // 2
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars")
    rng = np.random.default_rng(58)
    lr = np.r_[0.0, np.diff(np.log(C))]; lr[newd] = 0
    st = np.where(newd)[0]; en = np.r_[st[1:], n]
    lrs = lr.copy()
    for a, b in zip(st, en):
        seg = lrs[a + 1:b].copy(); rng.shuffle(seg); lrs[a + 1:b] = seg
    Cs = np.empty(n)
    for a, b in zip(st, en):
        Cs[a:b] = C[a] * np.exp(np.cumsum(lrs[a:b]))

    say("\n=== A. Zigzag leg length: share of legs that last 18-24 candles, real vs shuffled ===")
    say(f"{'zigzag':>7} {'legs':>7} {'median':>7} {'18-24 real':>11} {'18-24 shuf':>11} {'10-17 real':>11} {'10-17 shuf':>11} "
        f"{'25-35 real':>11} {'25-35 shuf':>11} | reached 18: ended by 24, real / shuf")
    for pct in (0.0005, 0.0010, 0.0020):
        a, b = zz_lengths(C, newd, pct), zz_lengths(Cs, newd, pct)
        sh = lambda x, lo, hi: 100 * ((x >= lo) & (x <= hi)).mean()
        e = lambda x: 100 * ((x >= 18) & (x <= 24)).sum() / max((x >= 18).sum(), 1)
        say(f"{pct * 100:6.2f}% {len(a):7d} {np.median(a):7.0f} {sh(a,18,24):10.1f}% {sh(b,18,24):10.1f}% {sh(a,10,17):10.1f}% "
            f"{sh(b,10,17):10.1f}% {sh(a,25,35):10.1f}% {sh(b,25,35):10.1f}% | {e(a):5.1f}% / {e(b):5.1f}%")
    say("histogram at 0.10% (share of legs of each length, real vs shuffled; a cycle would show a bump at 18-24):")
    a, b = zz_lengths(C, newd, 0.001), zz_lengths(Cs, newd, 0.001)
    row = []
    for lo in range(1, 61, 3):
        m1 = 100 * ((a >= lo) & (a < lo + 3)).mean(); m2 = 100 * ((b >= lo) & (b < lo + 3)).mean()
        row.append(f"{lo:2d}-{lo + 2:2d}: {m1:4.1f}/{m2:4.1f}")
    for i in range(0, len(row), 5): say("   " + "   ".join(row[i:i + 5]))

    say("\n=== B. No zigzag: does the move of the last L candles predict the opposite move over the next L? ===")
    say("corr < 0 = reversal. 'shuf' is the control. t = corr x sqrt(number of independent windows)")
    say(f"{'L':>4} {'corr real':>10} {'t':>6} {'half1':>7} {'half2':>7} {'corr shuf':>10} | mean next-L move after a last-L UP move > 1 ATR ($)")
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).rolling(60).mean().shift(1).values
    cl = np.log(C); cls = np.log(Cs)
    for Lw in (6, 12, 15, 18, 21, 24, 27, 30, 40, 60):
        res = []
        for x in (cl, cls):
            past = x[Lw:-Lw] - x[:-2 * Lw]; fut = x[2 * Lw:] - x[Lw:-Lw]
            ok = (day[:-2 * Lw] == day[2 * Lw:]) & (hm[Lw:-Lw] >= 90) & (hm[Lw:-Lw] < 1320)
            idx = np.where(ok)[0][::Lw]                                        # non-overlapping windows
            res.append((np.corrcoef(past[idx], fut[idx])[0, 1], len(idx), idx, past, fut))
        r, m, idx, past, fut = res[0]
        h1 = idx[idx < mid]; h2 = idx[idx >= mid]
        big = idx[(past[idx] * C[idx + Lw] > atr[idx + Lw])]
        say(f"{Lw:4d} {r:10.4f} {r * np.sqrt(m):6.1f} {np.corrcoef(past[h1], fut[h1])[0, 1]:7.4f} "
            f"{np.corrcoef(past[h2], fut[h2])[0, 1]:7.4f} {res[1][0]:10.4f} | {np.mean(fut[big] * C[big + Lw]) * usd:+.3f} (n={len(big)})")

    say("\n=== C. Trade it: fade the last L candles' move (> 1 ATR), SL / TP = that move, out after L candles ===")
    say(f"{'variant':>26} {'trades':>7} {'/day':>5} {'win%':>5} {'PF':>5} {'half1':>6} {'half2':>6} {'stress':>6} {'net$':>7} {'worst day':>9}  pass")
    gate = atr / np.where(sp > 0, sp, np.nan)
    ndays = len(np.unique(day))
    def trade(Lw, g, x_atr, path_c, path_h, path_l, path_o, lab):
        res, busy = [], -1
        for k in range(Lw, n - Lw - 1):
            if k <= busy or newd[k + 1] or day[k - Lw] != day[k] or not (90 <= hm[k] < 1320): continue
            mv = path_c[k] - path_c[k - Lw]
            if not np.isfinite(atr[k]) or abs(mv) < x_atr * atr[k] or (g and not gate[k] >= 8): continue
            dr = -1 if mv > 0 else 1
            e = path_o[k + 1]; dist = abs(mv); sl = e - dr * dist; tp = e + dr * dist; ex = None
            for q in range(k + 1, min(n, k + 1 + Lw)):
                if newd[q]: ex = path_o[q]; break
                if dr == 1:
                    if path_l[q] <= sl: ex = sl; break
                    if path_h[q] >= tp: ex = tp; break
                else:
                    if path_h[q] >= sl: ex = sl; break
                    if path_l[q] <= tp: ex = tp; break
            if ex is None: ex = path_c[q]
            res.append((k, (ex - e) * dr, sp[k + 1])); busy = q
        if len(res) < 30: say(f"{lab:>26} too few"); return
        T = pd.DataFrame(res, columns=["k", "pnl", "sp"])
        net = (T.pnl - T.sp) * usd; strs = (T.pnl - 1.5 * T.sp) * usd
        pf = lambda x: x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
        h1, h2 = net[T.k < mid], net[T.k >= mid]
        wd = net.groupby(day[T.k.values]).sum().min()
        ok = len(T) >= 150 and pf(net) >= 1.15 and pf(h1) >= 1.05 and pf(h2) >= 1.05 and pf(strs) >= 1.05
        say(f"{lab:>26} {len(T):7d} {len(T) / ndays:5.2f} {100 * (net > 0).mean():5.1f} {pf(net):5.2f} {pf(h1):6.2f} {pf(h2):6.2f} "
            f"{pf(strs):6.2f} {net.sum():+7.0f} {wd:+9.1f}  {'PASS' if ok else ''}")
    hr = (H - L) / 2
    Os = np.r_[Cs[0], Cs[:-1]]; Os[newd] = Cs[newd]
    Hs = np.maximum(Os, Cs) + 0.5 * hr; Ls = np.minimum(Os, Cs) - 0.5 * hr
    for Lw in (18, 21, 24):
        for xa in (1.0, 2.0, 3.0):
            trade(Lw, False, xa, C, H, L, O, f"L{Lw} move>{xa:.0f}ATR")
            trade(Lw, True, xa, C, H, L, O, f"L{Lw} move>{xa:.0f}ATR gate8")
        trade(Lw, False, 2.0, Cs, Hs, Ls, Os, f"L{Lw} >2ATR SHUFFLED")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
