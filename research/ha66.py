"""Round 66 (9 Nov 2026): the owner's Heikin Ashi + EMA 10/30 + Stochastic 14,3,3 rule on gold, last 2 months.

Owner's rule (buy; sell is the mirror):
  1 EMA 10 and EMA 30 aligned: EMA10 > EMA30 (variant: both also rising)
  2 an INDECISION Heikin Ashi candle: shadow above AND below, small body (body <= B x HA range, B 0.3 / 0.5)
  3 the next HA candle is BULLISH with NO lower shadow at all (HA open == HA low)
  4 Stochastic 14,3,3 %K not overbought (< 80) on that candle (sell: > 20)
  entry at the next bar's open; SL at the nearest swing low (lowest low of the last 10 bars) minus the spread;
  TP = M x ATR(14) (M 1 / 1.5 / 2); out after 100 bars at most. One trade at a time.
Timeframes M1 / M5 / M15 (built from the broker's M1). Each month reported on its own. $ per 0.01 lot after spread.
Control: the same entries with a random direction.
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
    B1 = DT.bars(d, "1min"); del d
    B1 = B1[B1.index >= B1.index[-1] - pd.Timedelta(days=75)]
    end = B1.index[-1]; m1 = end - pd.Timedelta(days=30); m0 = end - pd.Timedelta(days=60)
    say(f"XAUUSD, month 1 {m0:%d %b}..{m1:%d %b}, month 2 {m1:%d %b}..{end:%d %b %Y}")

    def tfbars(tf):
        if tf == 1: return B1[["o", "h", "l", "c", "s"]].copy()
        g = B1.resample(f"{tf}min", label="left", closed="left")
        X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "s": g.s.median()}).dropna()
        return X

    for tf in (1, 5, 15):
        X = tfbars(tf)
        O, H, L, C, S = (X[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
        n = len(C); T = X.index
        hm = T.hour.values * 60 + T.minute.values
        e10 = pd.Series(C).ewm(span=10, adjust=False).mean().values
        e30 = pd.Series(C).ewm(span=30, adjust=False).mean().values
        hc = (O + H + L + C) / 4; ho = np.empty(n); ho[0] = (O[0] + C[0]) / 2
        for k in range(1, n): ho[k] = (ho[k - 1] + hc[k - 1]) / 2
        hh = np.maximum(H, np.maximum(ho, hc)); hl = np.minimum(L, np.minimum(ho, hc))
        top = np.maximum(ho, hc); bot = np.minimum(ho, hc); rng = hh - hl
        eps = 1e-6
        ll14 = pd.Series(L).rolling(14).min().values; hh14 = pd.Series(H).rolling(14).max().values
        kraw = 100 * (C - ll14) / np.where(hh14 - ll14 > 0, hh14 - ll14, np.nan)
        K = pd.Series(kraw).rolling(3).mean().values                      # %K with slowing 3
        c1 = np.r_[C[0], C[:-1]]
        tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
        atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
        lo10 = pd.Series(L).rolling(10).min().values; hi10 = pd.Series(H).rolling(10).max().values
        say(f"\n=== M{tf}: {n:,} bars ===")
        say(f"{'variant':>32} | {'month 1: tr win% PF net worst-day':>36} | {'month 2: tr win% PF net worst-day':>36} | 2 months net | random dir PF")

        def run(Bmax, M, slope, rand=False):
            res = []; busy = -1; rg = np.random.default_rng(66)
            for j in range(31, n - 1):
                if j <= busy: continue
                if not (90 <= hm[j] < 1320): continue
                ind = (top[j - 1] < hh[j - 1] - eps) and (bot[j - 1] > hl[j - 1] + eps) and rng[j - 1] > 0 and \
                      (top[j - 1] - bot[j - 1]) <= Bmax * rng[j - 1]
                if not ind: continue
                dr = 0
                if hc[j] > ho[j] and bot[j] - hl[j] <= eps and e10[j] > e30[j] and (not slope or (e10[j] > e10[j - 1] and e30[j] > e30[j - 1])) \
                        and K[j] < 80:
                    dr = 1
                elif hc[j] < ho[j] and hh[j] - top[j] <= eps and e10[j] < e30[j] and (not slope or (e10[j] < e10[j - 1] and e30[j] < e30[j - 1])) \
                        and K[j] > 20:
                    dr = -1
                if dr == 0: continue
                e = O[j + 1]
                sl = lo10[j] - S[j] if dr == 1 else hi10[j] + S[j]
                if rand:
                    dist = abs(e - sl); dr = 1 if rg.random() < 0.5 else -1; sl = e - dr * dist
                if (e - sl) * dr <= 0: continue
                tp = e + dr * M * atr[j]; ex = None; q = j + 1
                while q < n and q <= j + 100:
                    if T[q].date() != T[j].date() and hm[q] < 90: ex = O[q]; break
                    if dr == 1:
                        if L[q] <= sl: ex = min(O[q], sl); break
                        if H[q] >= tp: ex = tp; break
                    else:
                        if H[q] >= sl: ex = max(O[q], sl); break
                        if L[q] <= tp: ex = tp; break
                    q += 1
                if ex is None: ex = C[min(q, n - 1)]
                res.append((T[j + 1], ((ex - e) * dr - S[j + 1]) * usd)); busy = q
            return pd.DataFrame(res, columns=["t", "net"])

        def part(R, a, b):
            x = R[(R.t >= a) & (R.t < b)]
            if len(x) == 0: return f"{'0 trades':>36}", 0.0
            g, l = x.net[x.net > 0].sum(), -x.net[x.net < 0].sum()
            wd = x.groupby(x.t.dt.normalize()).net.sum().min()
            return f"{len(x):4d} {100 * (x.net > 0).mean():3.0f}% {g / l if l else 9.99:4.2f} {x.net.sum():+6.0f} {wd:+6.0f}", x.net.sum()

        for Bmax in (0.3, 0.5):
            for M in (1.0, 1.5, 2.0):
                for slope in (False, True):
                    R = run(Bmax, M, slope)
                    a, na = part(R, m0, m1); b, nb = part(R, m1, end + pd.Timedelta(minutes=1))
                    Rr = run(Bmax, M, slope, rand=True); xr = Rr[Rr.t >= m0]
                    pr = xr.net[xr.net > 0].sum() / max(-xr.net[xr.net < 0].sum(), 1e-9) if len(xr) else 0
                    say(f"{'body<=' + str(Bmax) + ' TP ' + str(M) + 'ATR' + (' +slope' if slope else ''):>32} | {a:>36} | {b:>36} | {na + nb:+7.0f} | {pr:4.2f}")


if __name__ == "__main__":
    main()
