"""Round 6b: order-flow and time-of-day edges on the broker's M5 history, 30 instruments (1 Nov 2026).

These are documented flow effects, not indicators:
  GOTOBI  USDJPY on Gotobi days (5th, 10th, 15th, 20th, 25th, 30th; a weekend date moves to the Friday before):
          Japanese importers buy USD into the Tokyo fix at 09:55 JST (Ito & Yamada 2017, Bessho et al.).
          Long from 08:00 / 08:30 / 09:00 JST to 09:55 JST, then short from 09:55 to 10:30 / 11:00 JST.
          Control: the same windows on the other days.
  TKFIX   The same Tokyo-fix windows on every day, for USDJPY and the JPY crosses.
  LDNFIX  London 4 pm WM/Reuters fix (16:00 London): move 15:00->16:00, then 16:00->17:00. Rule: when the
          pre-fix hour moved > 0.5 ATR(H1), fade it to 17:00 (all days; month-end days separately).
  GOLDFIX Gold LBMA fixes 10:30 and 15:00 London: the same pre/post test.
  HOURS   Hour-of-day drift per instrument with an honest holdout: on the first half of the data, find every
          (start hour, 1-4 h hold, buy/sell) window with t >= 3; then check those windows on the second half.
  COST    Spread vs typical M5 / H1 movement per instrument and hour: where scalping can even pay.
Entry and exit at M5 bar opens; cost = the entry bar's spread (MT5 export) once per trade.
"""
import os, sys, glob, time
import numpy as np, pandas as pd

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def say(s=""):
    print(s, flush=True)


def load_meta(path):
    meta = {}
    for ln in open(path, encoding="latin-1"):
        p = ln.strip().split(",")
        if len(p) >= 12 and p[0] != "base":
            try:
                meta[p[0]] = dict(sym=p[1], point=float(p[3]), tick_size=float(p[4]), tick_value=float(p[5]))
            except ValueError:
                pass
    return meta


def load(path, point):
    df = pd.read_csv(path).drop_duplicates("t").sort_values("t")
    d = pd.DataFrame({"o": df.o.values, "h": df.h.values, "l": df.l.values, "c": df.c.values,
                      "s": df.s.values.astype(float) * point}, index=pd.to_datetime(df.t.values, unit="s"))
    med = np.median(d.s.values[d.s.values > 0]) if (d.s.values > 0).any() else point
    d.loc[d.s <= 0, "s"] = med
    u = d.index.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT")
    d = d[~u.isna()]
    d.index = u[~u.isna()].tz_convert("UTC")
    return d[~d.index.duplicated()]


def pf(x):
    g = x[x > 0].sum(); b = -x[x < 0].sum()
    return g / b if b > 0 else (np.inf if g > 0 else np.nan)


def f2(x):
    return "  inf" if x == np.inf else ("  nan" if x != x else f"{x:5.2f}")


def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else np.nan


def window_trades(d, tz, t_in, t_out, days=None, side=1):
    """Enter at the open of the bar starting at local time t_in, exit at the open of the bar at t_out, same local
    date. Returns a frame of trades (pnl after spread in price units)."""
    loc = d.index.tz_convert(tz)
    hm = loc.hour * 60 + loc.minute
    date = pd.Index(loc.date)
    a = pd.Series(np.arange(len(d)), index=date)
    ins = d.o.values[hm == t_in]; ins_d = date[hm == t_in]; ins_s = d.s.values[hm == t_in]
    outs = pd.Series(d.o.values[hm == t_out], index=date[hm == t_out])
    outs = outs[~outs.index.duplicated()]
    I = pd.DataFrame({"pin": ins, "sp": ins_s}, index=ins_d)
    I = I[~I.index.duplicated()]
    I = I.join(outs.rename("pout"), how="inner")
    if days is not None:
        I = I[I.index.isin(days)]
    I["gross"] = side * (I.pout - I.pin)
    I["net"] = I.gross - I.sp
    I.index = pd.to_datetime(I.index)
    return I


def report(name, I, unit):
    if len(I) < 20:
        say(f"  {name:38s} {len(I):5d} trades (too few)"); return
    h = I.index >= I.index[len(I) // 2]
    yrs = " ".join(f"{y}:{I.net[I.index.year == y].sum() / unit:+.0f}" for y in sorted(set(I.index.year)))
    say(f"  {name:38s} {len(I):5d} gross {I.gross.mean() / unit:+6.2f} t {tstat(I.gross):+5.2f} | net {I.net.mean() / unit:+6.2f} "
        f"PF {f2(pf(I.net.values))} halves {f2(pf(I.net.values[~h]))} {f2(pf(I.net.values[h]))} | {yrs}")


def gotobi_days(index_dates):
    days = pd.DatetimeIndex(sorted(set(pd.to_datetime(index_dates))))
    out = set()
    bd = days[days.dayofweek < 5]
    for d in pd.date_range(days.min(), days.max(), freq="D"):
        if d.day in (5, 10, 15, 20, 25, 30):
            x = d
            while x.dayofweek >= 5:
                x -= pd.Timedelta(days=1)
            out.add(x.normalize())
    return pd.DatetimeIndex(sorted(out)).date


def main():
    meta = load_meta(os.path.join(DATA, "meta.txt"))
    D = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        b = os.path.basename(f)[:-4]
        if b in meta:
            d = load(f, meta[b]["point"])
            if len(d) >= 20000:
                D[b] = d
    say(f"Round 6b flows: {len(D)} instruments, {time.time() - T0:.0f} s")
    pip = {s: (0.01 if "JPY" in s else (1.0 if s in ("XAUUSD",) else (1.0 if s == "BTCUSD" else 0.0001))) for s in D}
    unit_name = "pips (gold/BTC: $)"

    # ---- COST
    say("\n== COST: median spread vs movement (lower is better for scalping) ==")
    say("sym      spread   ATR(M5)  spread/ATR5  ATR(H1) spread/ATRH1  cheapest hours (server, spread/ATR5)")
    rows = []
    for s, d in D.items():
        c1 = d.c.shift()
        tr = np.maximum(d.h - d.l, np.maximum((d.h - c1).abs(), (d.l - c1).abs()))
        a5 = tr.rolling(14).mean()
        H = d.resample("1h").agg({"h": "max", "l": "min", "c": "last"}).dropna()
        Hc1 = H.c.shift()
        trh = np.maximum(H.h - H.l, np.maximum((H.h - Hc1).abs(), (H.l - Hc1).abs()))
        sv = d.s.median(); a5m = a5.median(); ah = trh.rolling(14).mean().median()
        srv = d.index.tz_convert("Europe/Athens").hour
        byh = (d.s / a5).groupby(srv).median()
        cheap = ", ".join(f"{h:02d}:{v:.2f}" for h, v in byh.sort_values().head(4).items())
        rows.append((sv / a5m, s))
        say(f"{s:7s} {sv / pip[s]:7.2f} {a5m / pip[s]:8.2f} {sv / a5m:11.3f} {ah / pip[s]:8.1f} {sv / ah:11.3f}   {cheap}")
    say("ranking (cheapest first): " + ", ".join(s for _, s in sorted(rows)))

    # ---- GOTOBI and Tokyo fix
    say(f"\n== GOTOBI / Tokyo fix 09:55 JST (per trade in {unit_name}, after spread) ==")
    for s in ("USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY"):
        if s not in D:
            continue
        d = D[s]
        gd = gotobi_days(d.index.tz_convert("Asia/Tokyo").date)
        alld = pd.Index(d.index.tz_convert("Asia/Tokyo").date).unique()
        other = [x for x in alld if x not in set(gd)]
        say(f" {s}: {len(gd)} gotobi days")
        for t_in in (480, 510, 540):
            I = window_trades(d, "Asia/Tokyo", t_in, 595, days=gd, side=1)
            report(f"gotobi long {t_in // 60:02d}:{t_in % 60:02d}->09:55", I, pip[s])
            if s == "USDJPY":
                report(f"other days long {t_in // 60:02d}:{t_in % 60:02d}->09:55", window_trades(d, "Asia/Tokyo", t_in, 595, days=other, side=1), pip[s])
        for t_out in (630, 660):
            report(f"gotobi short 09:55->{t_out // 60:02d}:{t_out % 60:02d}", window_trades(d, "Asia/Tokyo", 595, t_out, days=gd, side=-1), pip[s])
            if s == "USDJPY":
                report(f"other days short 09:55->{t_out // 60:02d}:{t_out % 60:02d}", window_trades(d, "Asia/Tokyo", 595, t_out, days=other, side=-1), pip[s])

    # ---- London 4 pm fix and gold fixes: fade the pre-fix hour when it moved > 0.5 ATR(H1)
    say("\n== London fixes: fade the hour before the fix when it moved > 0.5 ATR(H1), hold 1 hour ==")
    for s, d in D.items():
        loc = d.index.tz_convert("Europe/London")
        hm = loc.hour * 60 + loc.minute
        date = pd.Index(loc.date)
        H = d.resample("1h").agg({"h": "max", "l": "min", "c": "last"}).dropna()
        Hc1 = H.c.shift()
        atrh = np.maximum(H.h - H.l, np.maximum((H.h - Hc1).abs(), (H.l - Hc1).abs())).rolling(24 * 5).mean()
        fixes = [(960, "16:00 WMR")] if s not in ("XAUUSD", "BTCUSD") else ([(630, "10:30 LBMA AM"), (900, "15:00 LBMA PM"), (960, "16:00 WMR")] if s == "XAUUSD" else [(960, "16:00")])
        for tf, nm in fixes:
            pre = pd.Series(d.o.values[hm == tf - 60], index=date[hm == tf - 60]); pre = pre[~pre.index.duplicated()]
            at = pd.DataFrame({"p": d.o.values[hm == tf], "sp": d.s.values[hm == tf], "t": d.index[hm == tf]}, index=date[hm == tf])
            at = at[~at.index.duplicated()]
            post = pd.Series(d.o.values[hm == tf + 60], index=date[hm == tf + 60]); post = post[~post.index.duplicated()]
            X = at.join(pre.rename("pre"), how="inner").join(post.rename("post"), how="inner")
            X["atr"] = atrh.reindex(X.t, method="ffill").values
            X["m1"] = X.p - X.pre; X["m2"] = X.post - X.p
            X = X.dropna()
            X.index = pd.to_datetime(X.index)
            corr = np.corrcoef(X.m1, X.m2)[0, 1] if len(X) > 30 else np.nan
            sel = X[X.m1.abs() > 0.5 * X.atr]
            I = pd.DataFrame({"gross": -np.sign(sel.m1) * sel.m2}, index=sel.index); I["net"] = I.gross - sel.sp
            me = X.index.to_series().groupby(X.index.to_period("M")).transform("max") == X.index.to_series()
            selm = X[me.values & (X.m1.abs() > 0.25 * X.atr)]
            Im = pd.DataFrame({"gross": -np.sign(selm.m1) * selm.m2}, index=selm.index); Im["net"] = Im.gross - selm.sp
            say(f" {s:7s} {nm:14s} corr(pre, post) {corr:+.3f}")
            report("   fade pre-fix move, all days", I, pip[s])
            report("   fade pre-fix move, month-end days", Im, pip[s])

    # ---- HOURS: hour-of-day drift with a holdout
    say("\n== HOURS: hour-of-day windows found on the first half (t >= 3), checked on the second half ==")
    found = kept = 0
    lines = []
    for s, d in D.items():
        srv = d.index.tz_convert("Europe/Athens")
        hm = srv.hour * 60 + srv.minute
        date = pd.Index(srv.date)
        opens = {}
        for hh in range(1, 24):
            x = pd.DataFrame({"o": d.o.values[hm == hh * 60], "s": d.s.values[hm == hh * 60]}, index=date[hm == hh * 60])
            opens[hh] = x[~x.index.duplicated()]
        alld = sorted(set(date))
        mid = alld[len(alld) // 2]
        for h0 in range(1, 23):
            for L in (1, 2, 3, 4):
                h1 = h0 + L
                if h1 > 23:
                    continue
                X = opens[h0].join(opens[h1].o.rename("o2"), how="inner")
                if len(X) < 200:
                    continue
                g = X.o2 - X.o
                first = X.index < mid
                for side in (1, -1):
                    t1 = tstat(side * g[first])
                    if t1 >= 3:
                        found += 1
                        net2 = side * g[~first] - X.s[~first]
                        t2 = tstat(side * g[~first])
                        ok = t2 >= 2 and pf(net2.values) > 1.1
                        kept += ok
                        lines.append(f"  {s:7s} {'BUY ' if side == 1 else 'SELL'} {h0:02d}:00->{h1:02d}:00  first half t {t1:+.2f}  "
                                     f"second half t {t2:+.2f}, net/trade {net2.mean() / pip[s]:+.2f}, PF {f2(pf(net2.values))}  {'KEPT' if ok else ''}"
                                     f"{' (starts at the daily reopen: real spread much wider)' if h0 == 1 else ''}")
    for ln in lines:
        say(ln)
    tests = len(D) * sum(1 for h0 in range(1, 23) for L in (1, 2, 3, 4) if h0 + L <= 23) * 2
    say(f"{found} windows with t >= 3 on the first half out of about {tests} tested (chance alone: about {tests * 0.00135:.0f}); "
        f"{kept} held on the second half (t >= 2 and PF > 1.1 after spread)")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
