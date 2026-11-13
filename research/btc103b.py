"""Round 103b (13 Nov 2026): robustness of round 103's two BTC survivors, last 2 years.
A  M5 big-candle FOLLOW: |M5 bar| >= k ATR(M5), ATR >= gate x spread, enter its way at the next open, SL 0.3 ATR beyond the
   bar's far end, out after N bars.  Checked: k as NON-OVERLAPPING bands (a lower k is a superset of a higher one), gate, hold,
   SL, buys / sells, weekday / weekend, by quarter.
B  SMC BOS + limit at the OTE 0.705 in the killzone (round 102 rules) on M10 / M15 / M20: killzone vs all day vs FAKE hours,
   weekdays only (the live EA skips weekends), order life, by quarter."""
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
    a5 = M.atr(B).values; body = C - O; wd = B.index.day_of_week.values
    say("A. M5 BIG-CANDLE FOLLOW on BTC"); say(M.HDR)

    def follow(name, kmin, kmax, gate, hold, slk=0.3, wfilter=None, side=0):
        big = (np.abs(body) >= kmin * a5) & (np.abs(body) < kmax * a5) & (a5 >= gate * S)
        ii = np.where(big)[0] + 1; ii = ii[ii < len(B) - 1]
        dr = np.sign(body[ii - 1]).astype(int)
        if side: ii, dr = ii[dr == side], dr[dr == side]
        if wfilter is not None: m = wfilter(wd[ii]); ii, dr = ii[m], dr[m]
        ext = np.where(dr == 1, L[ii - 1], H[ii - 1])
        mk = np.where(dr == 1, O[ii] + S[ii], O[ii])
        dist = np.abs(mk - (ext - dr * slk * a5[ii - 1]))
        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": dist, "tp": np.nan, "x": ii + hold})
        r = bk.run(sg[sg.d != 0]); x = M.line(name, r, mid, end); M.show(x); return r

    say("-- k bands on their own (gate 4, hold 12)")
    for a, b in ((1.5, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 5.0), (2.5, 99), (3.0, 99)):
        follow(f"band k {a}-{b if b < 99 else 'up'}", a, b, 4, 12)
    say("-- gate (k >= 2.5, hold 12)")
    for g in (0, 2, 4, 6, 8, 12): follow(f"gate {g}", 2.5, 99, g, 12)
    say("-- hold in M5 bars (k >= 2.5, gate 4)")
    for h in (3, 6, 12, 24, 48): follow(f"hold {h}", 2.5, 99, 4, h)
    say("-- SL beyond the bar (k >= 2.5, gate 4, hold 12)")
    for s in (0.0, 0.3, 0.6, 1.0): follow(f"SL {s} ATR beyond", 2.5, 99, 4, 12, s)
    say("-- sides and days (k >= 2.5, gate 4, hold 12)")
    follow("buys only", 2.5, 99, 4, 12, side=1); follow("sells only", 2.5, 99, 4, 12, side=-1)
    follow("weekdays only", 2.5, 99, 4, 12, wfilter=lambda w: w < 5); follow("weekend only", 2.5, 99, 4, 12, wfilter=lambda w: w >= 5)
    r = follow("CENTRE k>=2.5 gate 4 hold 12 weekdays", 2.5, 99, 4, 12, wfilter=lambda w: w < 5)
    if r:
        q = pd.Series(r["pnl"], index=r["t"]).groupby(pd.Series(r["t"]).dt.to_period("Q").values).sum()
        say("   by quarter $: " + "  ".join(f"{k}: {v:+.0f}" for k, v in q.items()))
        mo = pd.Series(r["pnl"], index=r["t"]).groupby(pd.Series(r["t"]).dt.to_period("M").values).sum()
        say(f"   months positive {(mo > 0).sum()}/{len(mo)}, worst month ${mo.min():.0f}")

    say("\nB. SMC BOS + OTE 0.705 LIMIT on BTC (round 102 rules)"); say(M.HDR)
    import smc102 as SM
    SM.PAIRS = ((10, 240), (15, 240), (20, 240)); SM.BUY_CTRL = True
    A, END = SM.run("BTCUSD", mt, sw)
    for c_ in ("entry", "tp", "typ"): A[c_] = A[c_].astype(str)
    A = A.sort_values("t", kind="stable")
    wdA = pd.DatetimeIndex(A.t).day_of_week.values
    HRS = {"killzone 09-12 + 14-17": lambda h: ((h >= 9) & (h < 12)) | ((h >= 14) & (h < 17)), "London 09-12": lambda h: (h >= 9) & (h < 12),
           "NY 14-17": lambda h: (h >= 14) & (h < 17), "all day": lambda h: h >= 0, "FAKE 02-05 + 19-22": lambda h: ((h >= 2) & (h < 5)) | ((h >= 19) & (h < 22)),
           "Asia 01-08": lambda h: (h >= 1) & (h < 8)}

    def smc(name, msk):
        g = SM.busy(A[msk])
        if len(g) < 20: return None
        r = dict(n=len(g), t=pd.DatetimeIndex(g.t), pnl=(g.r * g.risk).values.astype(float), d=g.d.values, risk=g.risk.values.astype(float),
                 swap=np.zeros(len(g)), sp=(g.sp * g.risk).values.astype(float), rand=(g.rr * g.risk).values.astype(float),
                 buy=(g.rb * g.risk).values.astype(float))
        r["rand"] = r["rand"][~np.isnan(r["rand"])]; r["buy"] = r["buy"][~np.isnan(r["buy"])]
        x = M.line(name, r, mid, END); M.show(x); return r

    base = (A.entry == "OTE 0.705") & (A.typ == "BOS")
    for hn, hf in HRS.items():
        for tf in (10, 15, 20):
            smc(f"{hn} M{tf} n3 TP 3R", base & hf(A.hr.values) & (A.tf == tf) & (A.n == 3) & (A.tp == "3R"))
    say("-- weekdays only (the live EA trades the killzone on weekdays)")
    kz = HRS["killzone 09-12 + 14-17"](A.hr.values)
    for tf in (10, 15, 20):
        for n_ in (3, 5):
            for tp in ("2R", "3R", "liquidity"):
                r = smc(f"weekdays M{tf} n{n_} TP {tp}", base & kz & (wdA < 5) & (A.tf == tf) & (A.n == n_) & (A.tp == tp))
    say("-- the same with BOS + CHoCH, and the OB 50% / FVG entries (weekdays, killzone, M20 n3 TP 3R)")
    for en in ("OB top", "OB 50%", "FVG top", "FVG 50%", "OTE 0.705"):
        smc(f"entry {en}", (A.entry == en) & (A.typ == "BOS") & kz & (wdA < 5) & (A.tf == 20) & (A.n == 3) & (A.tp == "3R"))
    smc("OTE BOS + CHoCH", (A.entry == "OTE 0.705") & kz & (wdA < 5) & (A.tf == 20) & (A.n == 3) & (A.tp == "3R"))
    r = smc("CENTRE weekdays killzone M20 n3 OTE TP 3R", base & kz & (wdA < 5) & (A.tf == 20) & (A.n == 3) & (A.tp == "3R"))
    if r:
        q = pd.Series(r["pnl"], index=r["t"]).groupby(r["t"].to_period("Q")).sum()
        say("   by quarter $: " + "  ".join(f"{k}: {v:+.0f}" for k, v in q.items()))
        mo = pd.Series(r["pnl"], index=r["t"]).groupby(r["t"].to_period("M")).sum()
        say(f"   months positive {(mo > 0).sum()}/{len(mo)}, worst month ${mo.min():.0f}, longest losing run "
            f"{max(len(x) for x in ''.join('L' if v <= 0 else 'W' for v in r['pnl']).split('W'))}")


if __name__ == "__main__":
    main()
