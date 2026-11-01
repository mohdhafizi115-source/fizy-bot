"""Round 7: event-time scalps on the broker's M5 history, 30 instruments (1 Nov 2026).

The Gotobi result showed where short-term edges live: at fixed clock times when big, price-insensitive flows hit
the market (fixings, opens, closes, option cuts). This scans every such time for every instrument:
  events  Tokyo fix 09:55 JST, Tokyo open 09:00 JST, CNY fix 09:15 Shanghai, Frankfurt open 08:00 CET, London
          open 08:00, ECB fix 14:15 CET, LBMA gold 10:30 and 15:00 London, WM/R fix 16:00 London, US data 08:30
          New York, US stock open 09:30 NY, NY option cut 10:00 NY, COMEX gold close 13:30 NY, US close 16:00 NY
  windows before the event (-30/-15/-5 min -> event), after it (event -> +5/+15/+30/+60 min), after it with a
          5-minute delay (+5 -> +30), and conditional: fade or follow the 30 minutes before the event, for
          +5/+15/+30/+60 after it
  days    all days, Gotobi days, month-end (last business day)
Honest selection: direction and window chosen on the first half only (t >= 3); a result is KEPT only if the
second half also has t >= 2 and PF > 1.1 after spread. The same scan on fake event times (each event shifted by
+2h15m) shows how many KEPT results luck alone produces. Trades that enter or exit between 23:45 and 01:30 server
time are dropped: around the daily rollover the bid is distorted by very wide spreads (a data artefact, not an edge).
Also: SHOCK = fade / follow a big M5 bar (|close-open| >= 3 ATR(14)), exit after 1, 3 or 6 bars.
Entry and exit at M5 bar opens; cost = the entry bar's spread (MT5 export), once per trade.
"""
import os, sys, glob, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
EVENTS = [("TKY_FIX", "Asia/Tokyo", 595), ("TKY_OPEN", "Asia/Tokyo", 540), ("CNY_FIX", "Asia/Shanghai", 555),
          ("FRA_OPEN", "Europe/Berlin", 480), ("LDN_OPEN", "Europe/London", 480), ("ECB_FIX", "Europe/Berlin", 855),
          ("LBMA_AM", "Europe/London", 630), ("LBMA_PM", "Europe/London", 900), ("WMR_FIX", "Europe/London", 960),
          ("US_DATA", "America/New_York", 510), ("US_OPEN", "America/New_York", 570), ("NY_CUT", "America/New_York", 600),
          ("COMEX_CL", "America/New_York", 810), ("US_CLOSE", "America/New_York", 960)]
FAKE_SHIFT = 135                 # a multiple of 5 minutes, so the fake times fall on M5 bar opens
WINDOWS = [("pre", -30, 0), ("pre", -15, 0), ("pre", -5, 0), ("post", 0, 5), ("post", 0, 15), ("post", 0, 30), ("post", 0, 60),
           ("post", 5, 30)]
COND = [5, 15, 30, 60]


def say(s=""):
    print(s, flush=True)


def gotobi_set(dates):
    out = set()
    for d in pd.date_range(min(dates), max(dates), freq="D"):
        if d.day in (5, 10, 15, 20, 25, 30) or (d.day == d.days_in_month and d.day < 30):
            x = d
            while x.day_of_week >= 5:
                x -= pd.Timedelta(days=1)
            out.add(x.date())
    return out


def monthend_set(dates):
    s = pd.Series(sorted(set(dates)))
    s = s[pd.to_datetime(s).dt.day_of_week < 5]
    return set(s.groupby(pd.to_datetime(s).dt.to_period("M")).max().values)


def scan(D, shift=0):
    """Returns a list of results (one per symbol / event / window / day type / side) with first and second half
    stats; shift moves every event time (fake-event control)."""
    res = []
    for s, d in D.items():
        pip = 0.01 if "JPY" in s else (1.0 if s in ("XAUUSD", "BTCUSD") else 0.0001)
        for ev, tz, m0 in EVENTS:
            m0 = (m0 + shift) % 1440
            loc = d.index.tz_convert(tz)
            hm = (loc.hour * 60 + loc.minute).values
            dates = np.array(loc.date)
            srv = d.index.tz_convert("Europe/Athens"); shm = (srv.hour * 60 + srv.minute).values
            roll = (shm >= 1425) | (shm < 90)
            need = sorted({(m0 + a) % 1440 for _, a, b in WINDOWS} | {(m0 + b) % 1440 for _, a, b in WINDOWS} | {(m0 + c) % 1440 for c in COND} | {(m0 - 30) % 1440})
            px, sp = {}, {}
            for m in need:
                k = hm == m
                k = k & ~roll
                ser = pd.Series(d.o.values[k], index=dates[k]); ser = ser[~ser.index.duplicated()]
                sps = pd.Series(d.s.values[k], index=dates[k]); sps = sps[~sps.index.duplicated()]
                px[m], sp[m] = ser, sps
            alld = sorted(set(dates))
            gd, me = gotobi_set(alld), monthend_set(alld)
            mid = alld[len(alld) // 2]
            def stats(a, b, sign=None, cond=False, cmin=None):
                ma, mb = (m0 + a) % 1440, (m0 + b) % 1440
                if mb <= ma and b > a:          # window crosses midnight: skip
                    return None
                X = pd.concat({"pa": px[ma], "pb": px[mb], "sp": sp[ma]}, axis=1, join="inner").dropna()
                if cond:
                    pre = pd.concat({"p0": px[(m0 - 30) % 1440], "p1": px[m0 % 1440]}, axis=1, join="inner").dropna()
                    X = X.join((pre.p1 - pre.p0).rename("pre"), how="inner")
                    X = X[X.pre != 0]
                    X["g"] = np.sign(X.pre) * (X.pb - X.pa)       # follow the pre-event move
                else:
                    X["g"] = X.pb - X.pa
                return X
            for kind, a, b in WINDOWS + [("cond", 0, c) for c in COND]:
                X = stats(a, b, cond=(kind == "cond"))
                if X is None or len(X) < 100:
                    continue
                for dt, sel in (("all", None), ("gotobi", gd), ("monthend", me)):
                    Y = X if sel is None else X[X.index.isin(sel)]
                    if len(Y) < 40:
                        continue
                    first = np.array([x < mid for x in Y.index])
                    for side in (1, -1):
                        g1 = side * Y.g.values[first]; g2 = side * Y.g.values[~first]
                        t1 = FL.tstat(g1)
                        if not (t1 >= 3):
                            continue
                        n2 = g2 - Y.sp.values[~first]
                        t2 = FL.tstat(g2); p2 = FL.pf(n2)
                        nall = side * Y.g.values - Y.sp.values
                        yr = pd.Series(nall, index=pd.to_datetime(list(Y.index)).year).groupby(level=0).sum()
                        res.append(dict(sym=s, ev=ev, kind=kind, a=a, b=b, days=dt, side=side, n=len(Y), t1=t1, t2=t2,
                                        net2=n2.mean() / pip, pf2=p2, pf=FL.pf(nall), netall=nall.mean() / pip,
                                        yrs=f"{int((yr > 0).sum())}/{len(yr)}", kept=(t2 >= 2 and p2 > 1.1)))
    return res


def shock(D):
    say("\n== SHOCK: after a big M5 bar (|close - open| >= 3 ATR), fade or follow; first half picks the side ==")
    say("sym       side   hold  n     first-half t  second-half t  net2/trade  PF2   KEPT")
    kept = 0; tot = 0
    for s, d in D.items():
        pip = 0.01 if "JPY" in s else (1.0 if s in ("XAUUSD", "BTCUSD") else 0.0001)
        c1 = d.c.shift()
        tr = np.maximum(d.h - d.l, np.maximum((d.h - c1).abs(), (d.l - c1).abs()))
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
        z = (d.c - d.o) / atr
        srv = d.index.tz_convert("Europe/Athens"); hm = srv.hour * 60 + srv.minute
        ok = (hm >= 120) & (hm < 1320)
        idx = np.where((np.abs(z.values) >= 3) & ok)[0]
        idx = idx[idx < len(d) - 8]
        if len(idx) < 60:
            continue
        mid = d.index[len(d) // 2]
        for hold in (1, 3, 6):
            e = d.o.values[idx + 1]; x = d.o.values[idx + 1 + hold]
            g = np.sign(z.values[idx]) * (x - e)               # follow
            spv = d.s.values[idx + 1]
            first = d.index[idx] < mid
            for side in (1, -1):
                tot += 1
                t1 = FL.tstat(side * g[first])
                if t1 < 3:
                    continue
                n2 = side * g[~first] - spv[~first]
                t2 = FL.tstat(side * g[~first]); p2 = FL.pf(n2)
                k = t2 >= 2 and p2 > 1.1
                kept += k
                say(f"{s:8s} {'follow' if side == 1 else 'fade  '} {hold:4d} {len(idx):5d}  {t1:+6.2f}        {t2:+6.2f}        "
                    f"{n2.mean() / pip:+7.2f}   {FL.f2(p2)}  {'KEPT' if k else ''}")
    say(f"SHOCK: {kept} kept of {tot} tests")


def main():
    meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
    D = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        b = os.path.basename(f)[:-4]
        if b in meta:
            d = FL.load(f, meta[b]["point"])
            if len(d) >= 20000:
                D[b] = d
    say(f"Round 7 event-time scan: {len(D)} instruments, {len(EVENTS)} events, {time.time() - T0:.0f} s")
    real = scan(D)
    say(f"real events done, {time.time() - T0:.0f} s")
    fake = scan(D, FAKE_SHIFT)
    say(f"fake events done, {time.time() - T0:.0f} s")
    nk_r = sum(r["kept"] for r in real); nk_f = sum(r["kept"] for r in fake)
    say(f"\nfirst-half hits (t >= 3): real {len(real)}, fake {len(fake)}; KEPT on the second half: real {nk_r}, fake {nk_f}")
    say("\n== KEPT results (real events), best first ==")
    say("sym      event     window                 days     side  n     t1     t2    net2/trade  PF2   PF all  net all  years+")
    for r in sorted([r for r in real if r["kept"]], key=lambda r: -r["pf2"]):
        w = (f"cond follow 0->+{r['b']}" if r["side"] == 1 else f"cond fade 0->+{r['b']}") if r["kind"] == "cond" else f"{r['kind']} {r['a']:+d}->{r['b']:+d}"
        side = "" if r["kind"] == "cond" else ("BUY " if r["side"] == 1 else "SELL")
        say(f"{r['sym']:8s} {r['ev']:9s} {w:22s} {r['days']:8s} {side:4s} {r['n']:5d} {r['t1']:+5.2f} {r['t2']:+5.2f} {r['net2']:+8.2f}   "
            f"{FL.f2(r['pf2'])} {FL.f2(r['pf'])} {r['netall']:+8.2f}  {r['yrs']}")
    say("\n== KEPT results on FAKE event times (what luck gives) ==")
    for r in sorted([r for r in fake if r["kept"]], key=lambda r: -r["pf2"])[:40]:
        say(f"  {r['sym']:8s} {r['ev']}+{FAKE_SHIFT}m {r['kind']} {r['a']:+d}->{r['b']:+d} {r['days']} side {r['side']:+d} n {r['n']} "
            f"t1 {r['t1']:+.2f} t2 {r['t2']:+.2f} PF2 {FL.f2(r['pf2'])}")
    shock(D)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
