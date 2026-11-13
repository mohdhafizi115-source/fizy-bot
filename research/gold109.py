"""Round 109 (13 Nov 2026): more NEW gold scalps.  Owner: "cari lagi scalping gold bro selain semua yang dah di cuba".
Data: M1 export run 43450356142 (XAUUSD, XAGUSD, EURUSD, USDJPY from 2024-09), last 2 years.
  E  gold-market event minutes, the COMEX-open idea applied elsewhere: LBMA AM 10:30 / PM 15:00 London, COMEX settlement
     13:30 NY, Shanghai Gold Exchange 09:00 / 13:30 / 20:00 Shanghai, MCX India 09:00 IST: follow / fade the first 1-minute
     bar, hold 5 / 15 min, SL 1 ATR(M1).  Control: the same rule at fake minutes -10 / -5 / -2 / +2 / +5 / +10 around each.
  R  relative value: gold's 30-bar move against what its partner (silver, EURUSD, USDJPY inverted) implies, beta from the
     previous day; when the residual is >= K sd (gold rich / cheap) -> fade it, hold 10 / 30 min.  Control: the same with
     gold's own 30-bar z-score (no partner), to see whether the partner adds anything.
Every trade has a random-direction and an always-buy twin, real spread, rollover dropped.  $ per 0.01 lot."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()


def to_server(dates, hh, mm, tz):
    t = pd.DatetimeIndex(dates) + pd.Timedelta(hours=hh, minutes=mm)
    return t.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").tz_convert("Europe/Athens").tz_localize(None)


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=20)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    a1 = M.atr(Bw).values
    exb = lambda i: M.exit_bar(Bw, np.asarray(i, dtype=np.int64))
    dates = pd.DatetimeIndex(T.normalize().unique()); dates = dates[dates.day_of_week < 5]
    res = []

    def go(name, sg, show=True):
        if sg is None or len(sg) == 0: return None
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1) & (sg.d != 0)]
        if len(sg) == 0: return None
        x = M.line(name, bk.run(sg), mid, end)
        if x:
            res.append(x)
            if show: M.show(x)
        return x

    def ev(ts, m=1, thr=0.0, hold=5, mode="follow", slk=1.0):
        ts = ts.dropna()
        a = np.searchsorted(tv, ts.values.astype("datetime64[ns]"))
        ok = (a < n - 40) & (np.abs(tv[np.minimum(a, n - 1)] - ts.values.astype("datetime64[ns]")) < np.timedelta64(60, "s"))
        a = a[ok]
        mv = C[a + m - 1] - O[a]
        sel = np.abs(mv) >= thr * a1[a]
        ii = a[sel] + m; dr = np.sign(mv[sel]).astype(int) * (1 if mode == "follow" else -1)
        return pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slk * a1[ii - 1], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))})

    # ---------------------------------------------------------------- E: gold-market event minutes
    say("-- E gold-market event minutes: follow / fade the first 1-minute bar, SL 1 ATR(M1); then the fake-time control"); say(M.HDR)
    events = (("LBMA AM 10:30 London", 10, 30, "Europe/London"), ("LBMA PM 15:00 London", 15, 0, "Europe/London"),
              ("COMEX settle 13:30 NY", 13, 30, "America/New_York"), ("COMEX pre-settle 13:28 NY", 13, 28, "America/New_York"),
              ("SGE 09:00 Shanghai", 9, 0, "Asia/Shanghai"), ("SGE 13:30 Shanghai", 13, 30, "Asia/Shanghai"),
              ("SGE night 20:00 Shanghai", 20, 0, "Asia/Shanghai"), ("MCX 09:00 India", 9, 0, "Asia/Kolkata"),
              ("COMEX open 08:20 NY (live, reference)", 8, 20, "America/New_York"))
    for nm, hh, mm, tz in events:
        ts = to_server(dates, hh, mm, tz)
        for mode in ("follow", "fade"):
            for hold in (5, 15):
                for thr in (0.0, 0.5):
                    go(f"E {nm} {mode} >= {thr} ATR {hold}m", ev(ts, thr=thr, hold=hold, mode=mode))
        # fake-time control for the follow 5 m / fade 5 m cells
        line = []
        for mode in ("follow", "fade"):
            pfs = []
            for off in (-10, -5, -2, 2, 5, 10):
                t2 = to_server(dates, hh, mm, tz) + pd.Timedelta(minutes=off)
                r = bk.run(ev(t2, hold=5, mode=mode)); pfs.append(pf(r["pnl"]) if r else 0)
            line.append(f"{mode} 5m fakes " + " ".join(f"{p:.2f}" for p in pfs) + f" (median {np.median(pfs):.2f})")
        say(f"   {nm}: " + " | ".join(line))

    # ---------------------------------------------------------------- R: relative value vs a partner
    say("\n-- R gold's 30-bar move vs its partner's (beta from the previous ~1 day): fade a >= K sd residual, SL 1.5 ATR, gate 8"); say(M.HDR)
    lg = np.log(C)
    g30 = lg - np.r_[np.full(30, np.nan), lg[:-30]]
    for psym, inv in (("XAGUSD", 1), ("EURUSD", 1), ("USDJPY", -1), ("OWN", 0)):
        if psym != "OWN":
            p = os.path.join(DATA, psym + ".csv")
            if not os.path.exists(p): continue
            mx, _ = W.read_meta(psym)
            X = SA.load(p, mx["point"]); X = X[~X.index.duplicated()].reindex(T).ffill()
            lp = inv * np.log(X.c.values)
            p30 = lp - np.r_[np.full(30, np.nan), lp[:-30]]
            # rolling beta of gold 30-bar moves on the partner's, from the previous 1,440 bars (no look-ahead)
            gs, ps = pd.Series(g30), pd.Series(p30)
            cov = (gs * ps).rolling(1440, min_periods=500).mean() - gs.rolling(1440, min_periods=500).mean() * ps.rolling(1440, min_periods=500).mean()
            var = ps.rolling(1440, min_periods=500).var(ddof=0)
            beta = (cov / var).shift(1).values
            resid = g30 - beta * p30
            say(f"   {psym}: median beta {np.nanmedian(beta):+.2f}")
        else:
            resid = g30.copy()
        rs = pd.Series(resid)
        z = ((rs - rs.rolling(1440, min_periods=500).mean().shift(1)) / rs.rolling(1440, min_periods=500).std().shift(1)).values
        for K in (2.0, 2.5, 3.0):
            beyond = (np.abs(z) > K) & np.isfinite(z) & (a1 >= 8 * S)
            cr = beyond & ~np.r_[False, beyond[:-1]]
            j = np.where(cr)[0]; ii = j + 1; ii = ii[ii < n - 1]; j = ii - 1
            dr = -np.sign(z[j]).astype(int)                                # gold rich -> sell, cheap -> buy
            for hold in (10, 30):
                go(f"R {psym} resid >= {K} sd fade {hold}m", pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": 1.5 * a1[j], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))}))
                go(f"R {psym} resid >= {K} sd FOLLOW {hold}m", pd.DataFrame({"i": ii, "d": -dr, "ep": np.nan, "sl": 1.5 * a1[j], "tp": np.nan, "x": np.minimum(ii + hold, exb(ii))}))

    say("\n" + "=" * 30 + " SUMMARY " + "=" * 30)
    R = pd.DataFrame(res)
    if len(R):
        R["fam"] = R.name.str.split().str[0]
        say(f"{len(R)} variants; PASS {int(R.ok.sum())}; median PF {R.PF.median():.2f}, random {R.rand.median():.2f}")
        say("by family: " + "  ".join(f"{f}: {g.PF.median():.2f} (rand {g.rand.median():.2f}, n {len(g)})" for f, g in R.groupby("fam")))
        say("\nTOP 20 with >= 150 trades"); say(M.HDR)
        for _, x in R[R.n >= 150].sort_values("PF", ascending=False).head(20).iterrows(): M.show(x.to_dict())
        if R.ok.any():
            say("\nPASSES"); say(M.HDR)
            for _, x in R[R.ok].iterrows(): M.show(x.to_dict())
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
