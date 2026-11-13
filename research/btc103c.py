"""Round 103c (13 Nov 2026): the two BTC legs to be run 24/7 together (owner: "aku nak 24/7 tanpa henti untuk btc"), last 2 years.
SMC  M20 / H4, swing 3, BOS, limit at OTE 0.705, filled in the killzone 09-12 / 14-17 server EVERY day (weekends too), TP 3R,
     SL protected extreme + 0.1 ATR + spread, out after 48 bars (16 h), one position.
FOL  M5 big candle |body| >= 2.5 ATR(M5), ATR >= 8 x spread, enter its way at the next open, SL 0.3 ATR beyond the bar's far
     end, out after 12 bars (1 h), any hour, any day, one position.
Report each leg (and the follow leg by weekday / weekend), then both together at 0.01 lot each: trades, PF, years, $, max DD,
worst day, months positive, longest losing run, and the same with 0.02 / 0.03 lots scaled."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA, ind23 as R23
say = M.say; pf = M.pf


def main():
    meta = SA.load_meta(os.path.join(M.DATA, "meta.txt")); SW = R23.load_swaps()
    mt = meta["BTCUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01; sw = SW.get("BTCUSD")
    swl = sw["long"] * mt["point"]; sws = sw["short"] * mt["point"]
    d = SA.load(os.path.join(M.DATA, "BTCUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    B = d[d.index >= start - pd.Timedelta(days=60)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(B, usd, swl, sws, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    a5 = M.atr(B).values; body = C - O
    big = (np.abs(body) >= 2.5 * a5) & (a5 >= 8 * S)
    ii = np.where(big)[0] + 1; ii = ii[ii < len(B) - 1]
    dr = np.sign(body[ii - 1]).astype(int)
    ext = np.where(dr == 1, L[ii - 1], H[ii - 1]); mk = np.where(dr == 1, O[ii] + S[ii], O[ii])
    sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": np.abs(mk - (ext - dr * 0.3 * a5[ii - 1])), "tp": np.nan, "x": ii + 12})
    rf = bk.run(sg[sg.d != 0])
    say(M.HDR)
    M.show(M.line("FOL M5 big candle follow, 24/7", rf, mid, end))
    wk = pd.DatetimeIndex(rf["t"]).day_of_week >= 5
    for lab, msk in (("FOL weekdays", ~wk), ("FOL weekend", wk)):
        r2 = {k: (v[msk] if isinstance(v, np.ndarray) and len(v) == len(msk) else v) for k, v in rf.items()}
        r2["t"] = rf["t"][msk]; r2["n"] = int(msk.sum()); M.show(M.line(lab, r2, mid, end))

    import smc102 as SM
    SM.PAIRS = ((20, 240),); SM.BUY_CTRL = True
    A, END = SM.run("BTCUSD", mt, sw)
    for c_ in ("entry", "tp", "typ"): A[c_] = A[c_].astype(str)
    A = A.sort_values("t", kind="stable")
    kz = ((A.hr >= 9) & (A.hr < 12)) | ((A.hr >= 14) & (A.hr < 17))
    g = SM.busy(A[(A.n == 3) & (A.entry == "OTE 0.705") & (A.tp == "3R") & (A.typ == "BOS") & kz])
    rs = dict(n=len(g), t=pd.DatetimeIndex(g.t), pnl=(g.r * g.risk).values.astype(float), d=g.d.values, risk=g.risk.values.astype(float),
              swap=np.zeros(len(g)), sp=(g.sp * g.risk).values.astype(float), rand=(g.rr * g.risk).values.astype(float)[~np.isnan(g.rr.values)],
              buy=(g.rb * g.risk).values.astype(float)[~np.isnan(g.rb.values)])
    M.show(M.line("SMC M20 n3 OTE TP 3R killzone, every day", rs, mid, end))
    wk2 = rs["t"].day_of_week >= 5
    say(f"   SMC weekend trades {int(wk2.sum())}, PF {pf(rs['pnl'][wk2]):.2f}; weekdays {int((~wk2).sum())}, PF {pf(rs['pnl'][~wk2]):.2f}")

    # both together (by entry day; each leg keeps its own one-position rule)
    t = np.r_[np.asarray(rf["t"]), np.asarray(rs["t"])]; p = np.r_[rf["pnl"], rs["pnl"]]
    o = np.argsort(t, kind="stable"); t, p = t[o], p[o]
    T = pd.DatetimeIndex(t); y1 = T < mid
    say(f"\nBOTH LEGS 24/7 at 0.01 lot each: {len(p)} trades ({len(p) / 104:.1f} a week), PF {pf(p):.2f}, years {pf(p[y1]):.2f} / {pf(p[~y1]):.2f}")
    for lot in (1, 2, 3):
        q = p * lot; eq = np.cumsum(q); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        dy = pd.Series(q, index=T).groupby(T.normalize()).sum(); mo = pd.Series(q, index=T).groupby(T.to_period("M")).sum()
        a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
        say(f"  lot 0.0{lot}: net ${q.sum():+.0f}, last 12 months ${q[~y1].sum():+.0f}, last 3 months ${q[T >= a3].sum():+.0f}, "
            f"previous 3 ${q[(T >= a6) & (T < a3)].sum():+.0f}, max DD ${dd:.0f}, worst day ${dy.min():.0f}, worst trade ${q.min():.0f}, "
            f"months positive {(mo > 0).sum()}/{len(mo)}, worst month ${mo.min():.0f}")
    run = max(len(x) for x in "".join("L" if v <= 0 else "W" for v in p).split("W"))
    say(f"  longest losing run {run} trades; trades by weekday " + " ".join(f"{n}:{(T.day_of_week == k).sum()}" for k, n in enumerate("MTWTFSS")))


if __name__ == "__main__":
    main()
