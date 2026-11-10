"""Round 79d (causal exclusion check before the build); from round 79c (10 Nov 2026): the Keltner re-entry module with a breakeven stop (owner: "kalau keltner buat ada
breakeven at least 30 pip?"; 30 pips = $3).  Engine of round 79b:

  LIVE   1-bar down spike >= 2 ATR, gate 8, SL 0.2 ATR under the bar, no TP, 45 min (v2.12, live)
  BE     the same + stop to breakeven after +0.5 / 1 / 2 / 3 ATR
  KELT   close back above EMA20 - 3 ATR after a close below it, gate 8, BUY, SL 0.2 ATR under the bar, no TP, 45 min
  DROP2  close fell >= 2.5 ATR over 2 bars, gate 8, BUY, same exit
Each module trades one position of its own.  KELT and DROP2 are also measured on the signals LIVE does not take
(no LIVE signal within 5 bars), because an added rule must stand on its own (the round 45 method).
$ per 0.01 lot, spread charged once; stress = 1.5 x spread.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    X = DT.bars(d, "1min"); del d
    end = X.index[-1]
    O, H, L, C = (X[c].values.astype(float) for c in ("o", "h", "l", "c"))
    S = X.s.values.astype(float); T = X.index; n = len(C)
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values
    day = T.normalize().values
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    a1 = np.r_[np.nan, atr[:-1]]
    gate = a1 / np.where(S > 0, S, np.nan)
    rng = H - L; body = C - O
    ok = (hm >= 90) & (hm < 1320) & (wd < 5)
    e20 = pd.Series(C).ewm(span=20, adjust=False).mean().values
    say(f"XAUUSD M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars")

    def sim(sig, slm=0.2, hold=45, be=0.0, cost=1.0, beusd=0.0, lock=0.0):
        res = []; busy = -1
        for k in np.where((sig != 0) & ok)[0]:
            if k <= busy or k + 1 >= n: continue
            e = O[k + 1]; a = atr[k]
            if not np.isfinite(a) or a <= 0: continue
            sl = L[k] - slm * a
            if e - sl <= 0: continue
            x = None; q = k + 1; moved = False
            while q < n:
                if q - (k + 1) >= hold or hm[q] >= 1425 or day[q] != day[k + 1]:
                    x = O[q] if q > k + 1 else C[q]; break
                if L[q] <= sl: x = min(O[q], sl) if q > k + 1 else sl; break
                if (be or beusd) and not moved and H[q] >= e + (beusd if beusd else be * a): sl = e + lock; moved = True
                q += 1
            if x is None: continue
            res.append((T[k + 1], ((x - e) - cost * S[k + 1]) * usd)); busy = q
        return pd.DataFrame(res, columns=["t", "net"])

    pf = lambda x: x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9) if len(x) else 0
    mid = T[n // 2]
    def show(name, R, Rs=None):
        if len(R) == 0: say(f"{name}: no trades"); return
        dd = R.set_index("t").net.cumsum(); mdd = (dd - dd.cummax()).min()
        dly = R.groupby(R.t.dt.normalize()).net.sum()
        mon = R.groupby(R.t.dt.to_period("M")).net.sum()
        w = lambda a, b=None: R[(R.t >= a) & (R.t < (b if b is not None else end + pd.Timedelta(minutes=1)))].net.sum()
        run = 0; worst = 0
        for v in R.net.values:
            run = run + 1 if v <= 0 else 0; worst = max(worst, run)
        say(f"\n--- {name} ---")
        say(f"{len(R):,} trades ({len(R) / dly.index.nunique() if False else len(R) / pd.Series(day).nunique():.2f} a day), win {100 * (R.net > 0).mean():.0f}%, PF {pf(R.net):.2f}, halves {pf(R.net[R.t < mid]):.2f} / {pf(R.net[R.t >= mid]):.2f}"
            + (f", stress {pf(Rs.net):.2f}" if Rs is not None else "") + f", net ${R.net.sum():+,.0f}")
        say(f"last 3 months ${w(end - pd.Timedelta(days=90)):+.0f}, 3 before ${w(end - pd.Timedelta(days=180), end - pd.Timedelta(days=90)):+.0f}, "
            f"last 12 months ${w(end - pd.Timedelta(days=365)):+.0f}; max DD ${mdd:+.0f}, worst day ${dly.min():+.0f}, "
            f"months positive {int((mon > 0).sum())} of {len(mon)}, longest losing run {worst}")
        say("by year PF: " + " ".join(f"{y}:{pf(g.net):.2f}({g.net.sum():+.0f})" for y, g in R.groupby(R.t.dt.year)))

    down = body < 0; g8 = gate >= 8
    live = np.where((rng >= 2.0 * a1) & down & g8, 1, 0)
    lo_ = e20 - 3.0 * atr
    kelt = np.where(np.r_[False, (C < lo_)[:-1]] & (C >= lo_) & g8, 1, 0)
    mv2 = C - np.r_[np.nan, np.nan, C[:-2]]
    drop2 = np.where((mv2 <= -2.5 * a1) & g8, 1, 0)
    near = pd.Series(live).rolling(11, center=True, min_periods=1).max().values > 0     # a LIVE signal within 5 bars
    kx = np.where(near, 0, kelt)
    past = pd.Series(live).rolling(6, min_periods=1).max().values > 0                    # causal: a LIVE signal on this bar or the 5 before
    kc = np.where(past, 0, kelt)
    show("KELT centred exclusion (79c, uses 5 future bars) + BE $3", sim(kx, beusd=3.0), sim(kx, beusd=3.0, cost=1.5))
    show("KELT CAUSAL exclusion (LIVE signal now or in the 5 bars before) + BE $3", sim(kc, beusd=3.0), sim(kc, beusd=3.0, cost=1.5))
    show("KELT no exclusion + BE $3", sim(kelt, beusd=3.0), sim(kelt, beusd=3.0, cost=1.5))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
