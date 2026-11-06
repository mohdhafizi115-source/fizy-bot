"""Round 59 (6 Nov 2026): the owner's 'trend stairs' on gold M1, traded WITH the trend.

Owner (chart of 6 Nov 10:58-13:14 server: four falling legs of 19-20 candles each, lower highs, price
under a falling moving average): "aku nak kau buat ea ikut trend ... arrow adalah bilangan candle setiap
range 19-20 candle".

Rule, all online on closed M1 bars:
  swings   0.10% zigzag on wicks (highs / lows), as in FizyLEG v2.03, reset each server day
  trend    close below EMA(P) and EMA(P) below its value 10 bars ago -> down trend (mirror for up)
  entry    when a new DOWN leg is confirmed (price falls 0.10% from a swing high) and that swing high is
           LOWER than the previous swing high (lower high) and the trend is down: SELL at the next open.
           Mirror: new UP leg from a higher low in an up trend: BUY.
  SL       beyond the swing high (low) + the spread
  exit     at bar pivot + X candles (the owner's 19-20 candle leg) or a TP of R x the risk, whichever first
Variants: EMA 20 / 50 / 100, exit X = 15 / 20 / 25 / 30 / none (TP only), TP 1R / 2R / none, cost gate 8.
Controls: random direction at the same entries; the same rule on the day-shuffled path.
Pass rule: >= 150 trades, PF >= 1.15 after spread, both halves >= 1.05, stress 1.5x spread >= 1.05,
last 12 months positive. Worst day and max drawdown per 0.01 lot, against the $100 account.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def signals(O, H, L, C, newd, pct, ema, slope_ok):
    """returns entries (k = confirmation bar, dir, pivot bar, pivot price)"""
    n = len(C); out = []
    d_ = 0; ext = piv = lo0 = hi0 = 0
    lastH = lastL = None                          # previous swing high / low prices
    for k in range(n):
        if newd[k]:
            d_, ext, piv, lo0, hi0 = 0, k, k, k, k; lastH = lastL = None; continue
        if d_ == 0:
            if L[k] < L[lo0]: lo0 = k
            if H[k] > H[hi0]: hi0 = k
            if H[k] >= L[lo0] * (1 + pct): d_, piv, ext = 1, lo0, k; lastL = L[lo0]
            elif L[k] <= H[hi0] * (1 - pct): d_, piv, ext = -1, hi0, k; lastH = H[hi0]
            continue
        if d_ == 1:
            if H[k] > H[ext]: ext = k
            elif L[k] <= H[ext] * (1 - pct):
                hp = H[ext]
                if lastH is not None and hp < lastH and C[k] < ema[k] and slope_ok[k] == -1:
                    out.append((k, -1, ext, hp))
                lastH = hp; piv, d_, ext = ext, -1, k
        else:
            if L[k] < L[ext]: ext = k
            elif H[k] >= L[ext] * (1 + pct):
                lp = L[ext]
                if lastL is not None and lp > lastL and C[k] > ema[k] and slope_ok[k] == 1:
                    out.append((k, 1, ext, lp))
                lastL = lp; piv, d_, ext = ext, 1, k
    return out


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    sp = B.s.values.astype(float)
    ndays = len(np.unique(day)); mid = B.index[n // 2]; end = B.index[-1]
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = atr / np.where(sp > 0, sp, np.nan)
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars, {ndays} days")

    rng = np.random.default_rng(59)
    lr = np.r_[0.0, np.diff(np.log(C))]; lr[newd] = 0
    st = np.where(newd)[0]; en = np.r_[st[1:], n]
    Cs = np.empty(n)
    for a, b in zip(st, en):
        seg = lr[a + 1:b].copy(); rng.shuffle(seg); Cs[a] = C[a]; Cs[a + 1:b] = C[a] * np.exp(np.cumsum(seg))
    hr = (H - L) / 2
    Os = np.r_[Cs[0], Cs[:-1]]; Os[newd] = Cs[newd]
    Hs = np.maximum(Os, Cs) + 0.5 * hr; Ls = np.minimum(Os, Cs) - 0.5 * hr

    def ema_of(c, P):
        e = pd.Series(c).ewm(span=P, adjust=False).mean().values
        s = np.sign(e - np.r_[np.full(10, np.nan), e[:-10]])
        return e, s

    HDR = (f"{'variant':>34} {'trades':>6} {'/day':>5} {'win%':>5} {'PF':>5} {'half1':>6} {'half2':>6} {'stress':>6} "
           f"{'last12$':>7} {'net$':>6} {'maxDD$':>7} {'worstday':>8}  pass")

    def run(sig, o, h, l, c, X, R, g, rand=False, lab=""):
        res, busy = [], -1
        rg = np.random.default_rng(7)
        for k, dr, pk, pp in sig:
            if k <= busy or k + 1 >= n or newd[k + 1] or not (90 <= hm[k] < 1320): continue
            if g and not gate[k] >= 8: continue
            if rand: dr = 1 if rg.random() < 0.5 else -1
            e = o[k + 1]
            sl = pp + sp[k] if dr == -1 else pp - sp[k]
            if rand: sl = e + (e - (pp if dr == 1 else pp)) * 0 + (abs(e - pp) + sp[k]) * (-dr)
            risk = abs(e - sl)
            if risk <= 0: continue
            tp = e + dr * R * risk if R else None
            last = (pk + X) if X else k + 240
            ex = None; q = k + 1
            while q < n:
                if newd[q] or q > last: ex = o[q]; break
                if dr == 1:
                    if l[q] <= sl: ex = min(sl, o[q]); break
                    if tp is not None and h[q] >= tp: ex = max(tp, o[q]) if o[q] > tp else tp; break
                else:
                    if h[q] >= sl: ex = max(sl, o[q]); break
                    if tp is not None and l[q] <= tp: ex = min(tp, o[q]) if o[q] < tp else tp; break
                q += 1
            if ex is None: continue
            res.append((k + 1, (ex - e) * dr, sp[k + 1])); busy = q
        if len(res) < 30: say(f"{lab:>34} too few ({len(res)})"); return
        T = pd.DataFrame(res, columns=["k", "pnl", "sp"]); T["t"] = B.index[T.k.values]
        net = (T.pnl - T.sp) * usd; stp = (T.pnl - 1.5 * T.sp) * usd
        pf = lambda x: x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9)
        h1, h2 = net[T.t < mid], net[T.t >= mid]
        l12 = net[T.t >= end - pd.Timedelta(days=365)].sum()
        eq = net.cumsum().values; dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        wd = net.groupby(T.t.dt.normalize().values).sum().min()
        ok = len(T) >= 150 and pf(net) >= 1.15 and pf(h1) >= 1.05 and pf(h2) >= 1.05 and pf(stp) >= 1.05 and l12 > 0
        say(f"{lab:>34} {len(T):6d} {len(T) / ndays:5.2f} {100 * (net > 0).mean():5.1f} {pf(net):5.2f} {pf(h1):6.2f} "
            f"{pf(h2):6.2f} {pf(stp):6.2f} {l12:+7.0f} {net.sum():+6.0f} {dd:+7.0f} {wd:+8.1f}  {'PASS' if ok and not rand and 'SHUF' not in lab else ''}")

    for P in (20, 50, 100):
        e, s = ema_of(C, P); es, ss = ema_of(Cs, P)
        sig = signals(O, H, L, C, newd, 0.001, e, s)
        sigs = signals(Os, Hs, Ls, Cs, newd, 0.001, es, ss)
        say(f"\n=== EMA {P}: {len(sig)} signals ({len(sig) / ndays:.2f}/day), shuffled path {len(sigs)} ===")
        say(HDR)
        for X, R in ((15, None), (20, None), (25, None), (30, None), (20, 1.0), (20, 2.0), (None, 1.0), (None, 2.0)):
            tag = f"exit {X if X else '-'} candles TP {R if R else '-'}R"
            run(sig, O, H, L, C, X, R, False, lab=tag)
            run(sig, O, H, L, C, X, R, True, lab=tag + " gate8")
        run(sig, O, H, L, C, 20, None, False, rand=True, lab="exit 20 RANDOM direction")
        run(sigs, Os, Hs, Ls, Cs, 20, None, False, lab="exit 20 SHUFFLED path")
        run(sigs, Os, Hs, Ls, Cs, None, 2.0, False, lab="TP 2R SHUFFLED path")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
