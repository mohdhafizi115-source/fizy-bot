"""Round 8: forex-only edges from documented flows, on the broker's M5 history (28 pairs, Mar 2020 - Oct 2026).

Indicator rules lost on forex (rounds 1-5), so this looks only at effects with an economic reason:
  A  Session drift (Breedon & Ranaldo 2013): a currency tends to weaken during its own home trading hours and
     strengthen during the other side's hours. Fixed rule, no fitting: for pair BASE/QUOTE, SELL during the base
     currency's home morning, BUY during the quote's home morning. Home mornings: Europe (EUR, GBP, CHF)
     08:00-12:00 London, North America (USD, CAD) 08:00-12:00 New York, Asia-Pacific (JPY, AUD, NZD)
     09:00-13:00 Tokyo. Plus every 4-8 hour window, chosen on the first half and checked on the second.
  B  Turn of the month: USD strength on the last business day (08:00 -> 16:00 London, into and after the
     16:00 WM/R fix) and on the first business day.
  C  Month-end equity-hedge rebalancing at the London 4 pm fix (Melvin & Prins 2015): when US stocks beat the
     pair's foreign index month-to-date, foreign investors sell USD into the fix (and the reverse). Rule fixed in
     advance: trade the USD in that direction 12:00 -> 16:00 and 15:00 -> 16:00 London on the last business day.
     Index data: Yahoo daily (^GSPC vs ^STOXX50E, ^FTSE, ^N225, ^AXJO, ^GSPTSE, ^SSMI, ^NZ50).
  D  Month-end Tokyo-fix moves on crosses found in round 7 (CADCHF, NZDCHF, GBPNZD, USDCAD), by year.
  E  Intraday momentum (Elaut et al. 2018): the sign of an early-session return predicts the rest of the session.
  F  Weekday effects, 02:00 -> 23:00 server (no overnight swap), chosen on the first half, checked on the second.
Entry and exit at M5 bar opens; cost = the entry bar's spread (MT5 export) once per trade. Pips per trade.
A result counts only with t >= 2 and PF > 1.1 after spread on the second half (and, for fitted ones, t >= 3 on the
first half).
"""
import os, sys, glob, time
import numpy as np, pandas as pd, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
CCY = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF")
HOME = {"EUR": ("Europe/London", 480, 720), "GBP": ("Europe/London", 480, 720), "CHF": ("Europe/London", 480, 720),
        "USD": ("America/New_York", 480, 720), "CAD": ("America/New_York", 480, 720),
        "JPY": ("Asia/Tokyo", 540, 780), "AUD": ("Asia/Tokyo", 540, 780), "NZD": ("Asia/Tokyo", 540, 780)}
REGION = {"EUR": "EU", "GBP": "EU", "CHF": "EU", "USD": "NA", "CAD": "NA", "JPY": "AP", "AUD": "AP", "NZD": "AP"}
FOREIGN = {"EUR": "^STOXX50E", "GBP": "^FTSE", "JPY": "^N225", "AUD": "^AXJO", "CAD": "^GSPTSE", "CHF": "^SSMI", "NZD": "^NZ50"}


def say(s=""):
    print(s, flush=True)


def pipof(s):
    return 0.01 if "JPY" in s else 0.0001


def line(name, I, pip, extra=""):
    if len(I) < 30:
        say(f"  {name:44s} {len(I):5d} trades (too few)"); return None
    h = I.index >= I.index[len(I) // 2]
    p1, p2 = FL.pf(I.net.values[~h]), FL.pf(I.net.values[h])
    t2 = FL.tstat(I.gross.values[h])
    yr = I.net.groupby(I.index.year).sum()
    ok = p2 > 1.1 and t2 >= 2 and p1 > 1.0
    say(f"  {name:44s} {len(I):5d} gross {I.gross.mean() / pip:+6.2f}p t {FL.tstat(I.gross):+5.2f} | net {I.net.mean() / pip:+6.2f}p "
        f"PF {FL.f2(FL.pf(I.net.values))} halves {FL.f2(p1)} {FL.f2(p2)} yrs+ {int((yr > 0).sum())}/{len(yr)} {'PASS' if ok else ''}{extra}")
    return ok


def last_bd(dates):
    s = pd.Series(sorted(set(dates)))
    s = s[pd.to_datetime(s).dt.day_of_week < 5]
    g = s.groupby(pd.to_datetime(s).dt.to_period("M"))
    return set(g.max().values), set(g.min().values)


def usd_side(s):
    return 1 if s.startswith("USD") else (-1 if s.endswith("USD") else 0)      # +1: buying the pair = buying USD


def yahoo_daily(sym):
    UA = {"User-Agent": "Mozilla/5.0"}
    p = {"interval": "1d", "period1": 1546300800, "period2": int(time.time())}
    for k in range(3):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params=p, headers=UA, timeout=60)
            res = r.json()["chart"]["result"][0]
            c = pd.Series(res["indicators"]["quote"][0]["close"], index=pd.to_datetime(res["timestamp"], unit="s").normalize()).dropna()
            return c[~c.index.duplicated(keep="last")]
        except Exception:
            time.sleep(3)
    return None


def main():
    meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
    D = {}
    for f in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
        b = os.path.basename(f)[:-4]
        if b in meta and b[:3] in CCY and b[3:6] in CCY:
            D[b] = FL.load(f, meta[b]["point"])
    say(f"Round 8 forex flows: {len(D)} pairs, {time.time() - T0:.0f} s")
    passed = []

    # ---- A. session drift, fixed theory rule
    say("\n== A. Session drift (Breedon & Ranaldo): SELL the base in its home morning, BUY it in the quote's home morning ==")
    for s, d in D.items():
        b, q = s[:3], s[3:6]
        if REGION[b] == REGION[q]:
            continue
        for who, side in ((b, -1), (q, 1)):
            tz, t0, t1 = HOME[who]
            I = FL.window_trades(d, tz, t0, t1, side=side)
            if line(f"{s} {'SELL' if side < 0 else 'BUY '} in {who} morning ({tz.split('/')[1]} {t0 // 60:02d}-{t1 // 60:02d})", I, pipof(s)):
                passed.append(f"A {s} {'SELL' if side < 0 else 'BUY'} {who} morning")
    # A2: fitted windows (UTC), 4-8 hours, inside 00:00-20:00 UTC (clear of the rollover)
    say("\n   A2. any 4-8 hour UTC window, side and window chosen on the first half (t >= 3), checked on the second half")
    found = kept = tests = 0
    for s, d in D.items():
        for h0 in range(0, 17):
            for L in (4, 6, 8):
                if h0 + L > 20:
                    continue
                I = FL.window_trades(d, "UTC", h0 * 60, (h0 + L) * 60, side=1)
                if len(I) < 300:
                    continue
                first = I.index < I.index[len(I) // 2]
                for side in (1, -1):
                    tests += 1
                    if FL.tstat(side * I.gross.values[first]) < 3:
                        continue
                    found += 1
                    g2 = side * I.gross.values[~first]; n2 = g2 - I.sp.values[~first]
                    ok = FL.tstat(g2) >= 2 and FL.pf(n2) > 1.1
                    kept += ok
                    say(f"   {s} {'BUY ' if side > 0 else 'SELL'} {h0:02d}-{h0 + L:02d} UTC: t1 {FL.tstat(side * I.gross.values[first]):+.2f} "
                        f"t2 {FL.tstat(g2):+.2f} net2 {n2.mean() / pipof(s):+.2f}p PF2 {FL.f2(FL.pf(n2))} {'KEPT' if ok else ''}")
                    if ok:
                        passed.append(f"A2 {s} {'BUY' if side > 0 else 'SELL'} {h0:02d}-{h0 + L:02d} UTC")
    say(f"   {found} first-half hits of {tests} tests (chance about {tests * 0.00135:.1f}), {kept} kept")

    # ---- B. turn of the month, USD strength
    say("\n== B. Turn of the month: trade the USD side (buy USD) ==")
    for s, d in D.items():
        u = usd_side(s)
        if not u:
            continue
        ld = pd.Index(d.index.tz_convert("Europe/London").date)
        me, fm = last_bd(ld)
        for nm, days, t0, t1 in (("last bday 08:00-16:00", me, 480, 960), ("last bday 15:00-16:00", me, 900, 960),
                                 ("last bday 16:00-17:00", me, 960, 1020), ("first bday 08:00-16:00", fm, 480, 960)):
            I = FL.window_trades(d, "Europe/London", t0, t1, days=days, side=u)
            if line(f"{s} buy USD {nm}", I, pipof(s)):
                passed.append(f"B {s} buy USD {nm}")

    # ---- C. month-end equity hedge (Melvin & Prins)
    say("\n== C. Month-end hedge rebalancing: US stocks beat the foreign index month-to-date -> SELL USD into the fix ==")
    spx = yahoo_daily("^GSPC")
    if spx is None:
        say("  Yahoo ^GSPC not reachable, section skipped")
    else:
        for s, d in D.items():
            u = usd_side(s)
            if not u:
                continue
            fx = s[3:6] if s.startswith("USD") else s[:3]
            fi = yahoo_daily(FOREIGN[fx])
            if fi is None:
                say(f"  {s}: {FOREIGN[fx]} not reachable"); continue
            ld = pd.Index(d.index.tz_convert("Europe/London").date)
            me, _ = last_bd(ld)
            sig = {}
            for day in me:
                t = pd.Timestamp(day)
                prev_m_end = t.replace(day=1) - pd.Timedelta(days=1)
                def mtd(x):
                    a = x[x.index <= prev_m_end]; b = x[x.index < t]
                    return b.iloc[-1] / a.iloc[-1] - 1 if len(a) and len(b) else np.nan
                diff = mtd(spx) - mtd(fi)
                if diff == diff:
                    sig[day] = -1 if diff > 0 else 1          # US outperformed -> sell USD
            for nm, t0, t1 in (("12:00-16:00", 720, 960), ("15:00-16:00", 900, 960)):
                I = FL.window_trades(d, "Europe/London", t0, t1, days=set(sig), side=1)
                if len(I) == 0:
                    continue
                dirn = np.array([sig[x.date()] * u for x in I.index])     # +1 buy the pair
                I = I.assign(gross=dirn * (I.pout - I.pin)); I["net"] = I.gross - I.sp
                if line(f"{s} hedge-flow USD {nm} (vs {FOREIGN[fx]})", I, pipof(s)):
                    passed.append(f"C {s} hedge-flow {nm}")

    # ---- D. month-end Tokyo-fix moves on crosses (round 7)
    say("\n== D. Month-end Tokyo fix, round-7 finds, checked by year ==")
    for s, side, t0, t1 in (("CADCHF", -1, 590, 595), ("CADCHF", -1, 580, 595), ("NZDCHF", -1, 580, 595), ("NZDCHF", -1, 565, 595),
                            ("USDCAD", 1, 565, 595), ("USDCAD", 1, 580, 595), ("GBPNZD", 1, 580, 595), ("GBPNZD", 1, 565, 595)):
        if s not in D:
            continue
        d = D[s]
        me, _ = last_bd(pd.Index(d.index.tz_convert("Asia/Tokyo").date))
        I = FL.window_trades(d, "Asia/Tokyo", t0, t1, days=me, side=side)
        yrs = " ".join(f"{y % 100}:{I.net[I.index.year == y].sum() / pipof(s):+.0f}" for y in sorted(set(I.index.year)))
        if line(f"{s} {'SELL' if side < 0 else 'BUY'} {t0 // 60}:{t0 % 60:02d}->{t1 // 60}:{t1 % 60:02d} JST month-end", I, pipof(s), " | " + yrs):
            passed.append(f"D {s} {'SELL' if side < 0 else 'BUY'} {t0 // 60}:{t0 % 60:02d}-{t1 // 60}:{t1 % 60:02d} JST month-end")

    # ---- E. intraday momentum
    say("\n== E. Intraday momentum: follow the sign of an early return (first half picks follow / fade) ==")
    VAR = [("London 1st hour -> 09-12", "Europe/London", 480, 540, 540, 720), ("London 08-15 -> last hour 15-16", "Europe/London", 480, 900, 900, 960),
           ("Tokyo 1st hour -> 10-13", "Asia/Tokyo", 540, 600, 600, 780), ("NY 1st hour -> 09-12 NY", "America/New_York", 480, 540, 540, 720)]
    ek = et = 0
    for s, d in D.items():
        for nm, tz, a0, a1, b0, b1 in VAR:
            A_ = FL.window_trades(d, tz, a0, a1, side=1); B_ = FL.window_trades(d, tz, b0, b1, side=1)
            X = A_[["gross"]].rename(columns={"gross": "pre"}).join(B_, how="inner")
            X = X[X.pre != 0]
            if len(X) < 300:
                continue
            g = np.sign(X.pre.values) * X.gross.values
            first = X.index < X.index[len(X) // 2]
            for side in (1, -1):
                et += 1
                t1 = FL.tstat(side * g[first])
                if t1 < 3:
                    continue
                n2 = side * g[~first] - X.sp.values[~first]; t2 = FL.tstat(side * g[~first])
                ok = t2 >= 2 and FL.pf(n2) > 1.1
                ek += ok
                say(f"  {s} {nm} {'follow' if side > 0 else 'fade'}: t1 {t1:+.2f} t2 {t2:+.2f} net2 {n2.mean() / pipof(s):+.2f}p PF2 {FL.f2(FL.pf(n2))} {'KEPT' if ok else ''}")
                if ok:
                    passed.append(f"E {s} {nm} {'follow' if side > 0 else 'fade'}")
    say(f"  {ek} kept of {et} tests")

    # ---- F. weekday effects
    say("\n== F. Weekday drift 02:00 -> 23:00 server (first half picks the side) ==")
    fk = ft = 0
    for s, d in D.items():
        I = FL.window_trades(d, "Europe/Athens", 120, 1380, side=1)
        for wd in range(5):
            X = I[I.index.day_of_week == wd]
            if len(X) < 150:
                continue
            first = X.index < X.index[len(X) // 2]
            for side in (1, -1):
                ft += 1
                t1 = FL.tstat(side * X.gross.values[first])
                if t1 < 3:
                    continue
                n2 = side * X.gross.values[~first] - X.sp.values[~first]; t2 = FL.tstat(side * X.gross.values[~first])
                ok = t2 >= 2 and FL.pf(n2) > 1.1
                fk += ok
                say(f"  {s} {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][wd]} {'BUY' if side > 0 else 'SELL'}: t1 {t1:+.2f} t2 {t2:+.2f} PF2 {FL.f2(FL.pf(n2))} {'KEPT' if ok else ''}")
                if ok:
                    passed.append(f"F {s} {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][wd]} {'BUY' if side > 0 else 'SELL'}")
    say(f"  {fk} kept of {ft} tests (chance about {ft * 0.00135 * 0.05:.2f})")

    say("\n== Everything that passed ==")
    for p in passed:
        say("  " + p)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
