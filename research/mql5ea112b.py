"""Round 112b (14 Nov 2026): are round 112's two passes real, and can their risk fit a $100 account at 0.01 lot?
  ORB    GOLD_ORB: range of the M1 bars 01:00 .. 01:00 + R h server (R 1 / 2 / 3 / 4), buy stop at the high and sell stop
         at the low (one each a day), SL f x ATR14(D1) (f 0.15 / 0.25 / 0.35 / 0.5), TP 3 x SL / 2 x SL / none, out 23:30.
         Also: SL at the other side of the range, and the overlap with the live ATR open-band breakout (FizyATB:
         01:30 open +- 0.25 ATR, SL half the band) as a daily-P&L correlation.
  LUMEN  close beyond the N-bar high / low (N 20 / 30 / 40 / 50) with the EMA E trend (E 100 / 200 / 300), H1 / M30,
         SL k x ATR (k 1 / 1.5 / 2 / 2.5), TP 2 x SL or none, out 23:30; by quarter."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G
import scalp110 as S1
import mql5ea112 as E

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()
ema = S1.ema


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=60)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    say(M.HDR)

    def go(name, sg, one=False):
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1)]
        if len(sg) < 20: return None
        r = bk.run(sg, one); M.show(M.line(name, r, mid, end)); return r

    def daily(r):
        return pd.Series(r["pnl"], index=pd.DatetimeIndex(r["t"]).normalize()).groupby(level=0).sum()

    def quarters(r):
        q = pd.Series(r["pnl"], index=pd.DatetimeIndex(r["t"]))
        return "  ".join(f"{k}: {v:+.0f}" for k, v in q.groupby(q.index.to_period("Q")).sum().items())

    day = T.normalize(); D = Bw.groupby(day).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    pc = D.c.shift(); tr = np.maximum(D.h - D.l, np.maximum((D.h - pc).abs(), (D.l - pc).abs()))
    datr = tr.rolling(14).mean().shift(1)
    days = [dd for dd in D.index[D.index >= start] if dd.dayofweek < 5]
    ts = lambda dd, mins: np.searchsorted(tv, (dd + pd.Timedelta(minutes=mins)).to_datetime64())

    # ---------------- the live ATB, for the overlap check
    rows = []
    for dd in days:
        A = datr.get(dd, np.nan); a = ts(dd, 90); e = ts(dd, 1410)
        if not np.isfinite(A) or e <= a + 5: continue
        op = O[a]; up, dn = op + 0.25 * A, op - 0.25 * A
        j, dr, fp = G.scan_oco(O, H, L, S, a, e, up, dn)
        if j >= 0: rows.append((j, dr, fp, 0.125 * A, np.nan))
    atb = pd.DataFrame(rows, columns=["i", "d", "ep", "sl", "tp"]); atb["x"] = exb(atb.i.values)
    say("-- reference: the live ATB rule (01:30 open +- 0.25 ATR, SL half the band)")
    ratb = go("ATB live reference", atb, one=True); datb = daily(ratb)

    say("\n-- ORB: range hours x SL fraction x TP")
    best = None
    for R in (1, 2, 3, 4):
        sig = []
        for dd in days:
            A = datr.get(dd, np.nan); a = ts(dd, 60); b = ts(dd, 60 + 60 * R); e = ts(dd, 1410)
            if not np.isfinite(A) or b - a < 20 * R or e <= b: continue
            hi, lo = H[a:b].max(), L[a:b].min()
            for dr, lvl in ((1, hi), (-1, lo)):
                j, fp = E.scan_stop(O, H, L, S, b, e, lvl, dr)
                if j >= 0: sig.append((j, dr, fp, A, hi - lo))
        sig = pd.DataFrame(sig, columns=["i", "d", "ep", "A", "rg"])
        for fr in (0.15, 0.25, 0.35, 0.5):
            for tpm in (3.0, 2.0, None):
                sg = pd.DataFrame({"i": sig.i, "d": sig.d, "ep": sig.ep, "sl": fr * sig.A, "tp": (tpm * fr * sig.A) if tpm else np.nan})
                sg["x"] = exb(sg.i.values)
                r = go(f"ORB {R}h SL{fr}ATR TP{tpm if tpm else 'none'}{'xSL' if tpm else ''}", sg)
                if R == 3 and fr == 0.5 and tpm == 3.0: best = r
        sg = pd.DataFrame({"i": sig.i, "d": sig.d, "ep": sig.ep, "sl": sig.rg, "tp": 3.0 * sig.rg}); sg["x"] = exb(sg.i.values)
        go(f"ORB {R}h SL other side of range TP3R", sg)
    if best is not None:
        dorb = daily(best); j = pd.concat([dorb, datb], axis=1).fillna(0)
        say(f"\nORB 3h centre by quarter: {quarters(best)}")
        say(f"daily P&L correlation ORB 3h centre vs live ATB: {j.corr().iloc[0, 1]:+.2f} over {len(j)} days; "
            f"days both trade {int(((j.iloc[:, 0] != 0) & (j.iloc[:, 1] != 0)).sum())}")

    say("\n-- LUMEN: N-bar close breakout with the EMA trend, both sides")
    for tf in (30, 60):
        X = M.resample(Bw, tf); c, h, l = (X[k].values.astype(float) for k in ("c", "h", "l")); xa = M.atr(X).values
        at = np.searchsorted(tv, (X.index + pd.Timedelta(minutes=tf)).values.astype("datetime64[ns]"))
        for N in (20, 30, 40, 50):
            hh = pd.Series(h).rolling(N).max().shift(1).values; ll = pd.Series(l).rolling(N).min().shift(1).values
            for Ep in (100, 200, 300):
                if (tf, N, Ep) != (60, 30, 200) and not (N == 30 or Ep == 200): continue   # one-at-a-time around the centre
                e2 = ema(c, Ep)
                bu = (c > hh) & (c > e2); se = (c < ll) & (c < e2)
                bu &= ~np.r_[False, bu[:-1]]; se &= ~np.r_[False, se[:-1]]
                k = np.where(bu | se)[0]; k = k[at[k] < n - 2]; dr = np.where(bu[k], 1, -1); ii = at[k]
                for slk in (1.0, 1.5, 2.0, 2.5):
                    for tpm in (2.0, None):
                        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slk * xa[k], "tp": (tpm * slk * xa[k]) if tpm else np.nan, "x": exb(ii)})
                        r = go(f"LUMEN M{tf} N{N} EMA{Ep} SL{slk}ATR TP{tpm if tpm else 'none'}", sg, one=True)
                        if (tf, N, Ep, slk, tpm) == (60, 30, 200, 2.5, None) and r is not None:
                            say(f"   centre by quarter: {quarters(r)}")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
