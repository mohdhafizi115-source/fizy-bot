"""Round 110b (14 Nov 2026): is round 110's only pass, Connors RSI(3,2,100) on gold M15 with the EMA 200 side, a plateau?
Pass cell: CRSI crosses below 10 (above 90) with close above (below) EMA 200 -> buy (sell) at the next M1 open,
SL 1.5 x ATR(14) of the frame, out after 120 min (PF 1.24, 516 trades; the same with 60 min: 1.04).
Checks, all on the last 2 years:
  hold 30 / 60 / 90 / 120 / 180 / 240 / 360 min; SL 1 / 1.5 / 2 / 3 ATR / none (5 ATR disaster stop)
  threshold 5 / 10 / 15 / 20 (and 95 / 90 / 85 / 80); NON-OVERLAPPING bands of CRSI at the cross (the round 45 method)
  trend filter EMA 50 / 100 / 200 / 300 / none; frame M10 / M15 / M20 / M30
  Connors' own exit: close back above (below) SMA 5 or CRSI > 70 (< 30), with a 240 / 480 min cap
  buys and sells; by quarter; random-direction and always-buy twins on every row."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import scalp110 as S1

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()


def crsi_of(c):
    dd = np.diff(c, prepend=c[0]); streak = np.zeros(len(c))
    for i in range(1, len(c)):
        streak[i] = (streak[i - 1] + 1 if streak[i - 1] > 0 else 1) if dd[i] > 0 else ((streak[i - 1] - 1 if streak[i - 1] < 0 else -1) if dd[i] < 0 else 0)
    roc = pd.Series(dd / np.r_[c[0], c[:-1]])
    prank = roc.rolling(100).apply(lambda a: (a[:-1] < a[-1]).mean() * 100, raw=True).values
    return (S1.rsi(c, 3) + S1.rsi(streak, 2) + prank) / 3


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=30)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    res = []

    def go(name, sg):
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.d != 0)]
        if len(sg) < 20: return None
        r = bk.run(sg)
        x = M.line(name, r, mid, end)
        if x: res.append(x); M.show(x)
        return r

    frames = {}
    for tf in (10, 15, 20, 30):
        X = M.resample(Bw, tf); c = X.c.values.astype(float)
        frames[tf] = dict(X=X, c=c, xa=M.atr(X).values, cr=crsi_of(c),
                          at=np.searchsorted(tv, (X.index + pd.Timedelta(minutes=tf)).values.astype("datetime64[ns]")),
                          sma5=S1.sma(c, 5), ema={k: S1.ema(c, k) for k in (50, 100, 200, 300)})

    def signals(tf, lo=10, hi=90, ema=200, band=None):
        F = frames[tf]; cr, c = F["cr"], F["c"]; p = np.r_[50, cr[:-1]]
        if band is None:
            cb = (cr < lo) & (p >= lo); cs = (cr > hi) & (p <= hi)
        else:                                         # first bar under 20 / over 80, kept only when its CRSI is inside the band
            b0, b1 = band
            cb = (cr < 20) & (p >= 20) & (cr >= b0) & (cr < b1); cs = (cr > 80) & (p <= 80) & (100 - cr >= b0) & (100 - cr < b1)
        if ema:
            e = F["ema"][ema]; cb &= c > e; cs &= c < e
        k = np.where(cb | cs)[0]; k = k[(k > 300) & (F["at"][k] < n - 2)]
        return k, np.where(cb[k], 1, -1)

    def frame_rows(tf, k, dr, slk=1.5, hold=120, tp=None, cexit=None):
        F = frames[tf]; ii = F["at"][k]
        x = np.minimum(ii + hold, exb(ii))
        if cexit:                                      # Connors exit on frame closes: close beyond SMA 5 or CRSI past 70 / 30
            cr, c, s5, at = F["cr"], F["c"], F["sma5"], F["at"]
            xs = []
            for kk, dd, i0, xc in zip(k, dr, ii, x):
                j = kk + 1; out = xc
                while j < len(c) and at[j] - 1 < xc:
                    if (dd == 1 and (c[j] > s5[j] or cr[j] > 70)) or (dd == -1 and (c[j] < s5[j] or cr[j] < 30)):
                        out = min(xc, at[j]); break
                    j += 1
                xs.append(max(out, i0 + 1))
            x = np.array(xs)
        sl = (slk if slk else 5.0) * F["xa"][k]
        return pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": sl, "tp": (tp * F["xa"][k]) if tp else np.nan, "x": x})

    say(M.HDR)
    k, dr = signals(15)
    say("-- centre (M15, < 10 / > 90, EMA 200, SL 1.5 ATR, 120 min) and its hold sweep")
    r = None
    for hold in (30, 60, 90, 120, 150, 180, 240, 360):
        rr = go(f"M15 hold {hold}m", frame_rows(15, k, dr, hold=hold))
        if hold == 120: r = rr
    say("-- SL sweep at 120 min")
    for slk in (1.0, 1.5, 2.0, 3.0, None): go(f"M15 SL {slk if slk else 'none(5)'} ATR 120m", frame_rows(15, k, dr, slk=slk))
    say("-- TP sweep at 120 min (x ATR)")
    for tp in (1.0, 1.5, 2.0, 3.0): go(f"M15 TP {tp} ATR 120m", frame_rows(15, k, dr, tp=tp))
    say("-- Connors' own exit (SMA 5 / CRSI 70-30)")
    for cap in (240, 480): go(f"M15 Connors exit cap {cap}m", frame_rows(15, k, dr, hold=cap, cexit=True))
    say("-- threshold sweep (cumulative) at 120 min")
    for lo in (5, 10, 15, 20, 25):
        kk, dd = signals(15, lo, 100 - lo); go(f"M15 CRSI < {lo} / > {100 - lo} 120m", frame_rows(15, kk, dd))
    say("-- NON-OVERLAPPING bands of CRSI at the first bar under 20 (over 80), 120 min")
    for b in ((0, 5), (5, 10), (10, 15), (15, 20)):
        kk, dd = signals(15, band=b); go(f"M15 band {b[0]}-{b[1]} 120m", frame_rows(15, kk, dd))
    say("-- trend filter")
    for e in (50, 100, 200, 300, 0):
        kk, dd = signals(15, ema=e)
        for hold in (60, 120): go(f"M15 EMA {e if e else 'none'} {hold}m", frame_rows(15, kk, dd, hold=hold))
    say("-- frame")
    for tf in (10, 15, 20, 30):
        kk, dd = signals(tf)
        for hold in (60, 120, 180): go(f"M{tf} {hold}m", frame_rows(tf, kk, dd, hold=hold))

    # centre: by side, by quarter, by hour
    if r is not None:
        p = np.asarray(r["pnl"]); ti = pd.DatetimeIndex(r["t"])
        q = pd.Series(p, index=ti)
        say("\ncentre by quarter: " + "  ".join(f"{k_}: {v:+.0f}" for k_, v in q.groupby(q.index.to_period('Q')).sum().items()))
        mo = q.groupby(q.index.to_period('M')).sum(); say(f"months positive {int((mo > 0).sum())} of {len(mo)}")
        hr = q.groupby(((q.index.hour + 6) % 24)).agg(["count", "sum"])
        say("by MYT hour (n, $): " + "  ".join(f"{h}:{int(a)}/{b:+.0f}" for h, (a, b) in hr.iterrows()))
    say(f"\n{len(res)} rows; PASS {sum(1 for x in res if x['ok'])}; done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
