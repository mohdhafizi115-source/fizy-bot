"""Round 12: WTI crude oil (and any other energy symbol in the export) on the broker's M5 history.

Run on an m5data export made with symbols=XTIUSD,WTI,USOIL,... (mt5_data.yml input). Besides the generic rounds
(scalp_all.py, daytrade.py, run separately on the same data) this tests oil-specific timing:
  A  Event times: EIA weekly crude stocks (Wednesday 10:30 New York), NYMEX open 09:00 NY, US stock open 09:30 NY,
     NYMEX settlement 14:30 NY, Baker Hughes rig count (Friday 13:00 NY), London open 08:00, Tokyo open 09:00.
     Windows -30/-15/-5 min -> event, event -> +5/+15/+30/+60, +5 -> +30, buy or sell, chosen on the first half
     (t >= 3), KEPT if the second half has t >= 2 and PF > 1.1 after spread. Control: the same scan with every
     event shifted by +2h15m (fake times).
  B  EIA surprise (MQL5 calendar, data/calendar.csv): a bigger-than-forecast stock build is bearish -> sell, a draw
     is bullish -> buy; entry 5 / 10 minutes after the release, hold 15 / 30 / 60 minutes. Also follow / fade
     the 5-minute release bar.
  C  Hour-of-day drift (1-4 hour windows) with the same first-half / second-half check.
  D  NR7 D1 breakout (as live on gold / USDJPY / AUDJPY).
Cost: the entry bar's spread from the MT5 export; trades touching the 23:45-01:30 server rollover are dropped.
"""
import os, sys, glob, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL
import scalp_all as SA

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "calendar.csv")
NY, LDN, TKY = "America/New_York", "Europe/London", "Asia/Tokyo"
EV = [("EIA stocks", NY, 630, 2), ("NYMEX open", NY, 540, None), ("US open", NY, 570, None), ("Settlement", NY, 870, None),
      ("Rig count", NY, 780, 4), ("London open", LDN, 480, None), ("Tokyo open", TKY, 540, None)]
WIN = [(-30, 0), (-15, 0), (-5, 0), (0, 5), (0, 15), (0, 30), (0, 60), (5, 30)]


def say(s=""):
    print(s, flush=True)


def no_roll(d, I, tz, a, b):
    """drop trades whose entry or exit falls in the server rollover 23:45-01:30"""
    keep = []
    for day in I.index:
        ok = True
        for m in (a, b):
            t = pd.Timestamp(day.year, day.month, day.day, m // 60, m % 60, tz=tz).tz_convert("Europe/Athens")
            hm = t.hour * 60 + t.minute
            ok &= not (hm >= 1425 or hm < 90)
        keep.append(ok)
    return I[np.array(keep, bool)] if len(I) else I


def scan(d, unit, shift=0, show=True):
    found = kept = 0
    for nm, tz, m0, wd in EV:
        m0 = (m0 + shift) % 1440
        for a, b in WIN:
            ta, tb = m0 + a, m0 + b
            if ta < 0 or tb >= 1440:
                continue
            I = FL.window_trades(d, tz, ta, tb, side=1)
            if wd is not None and len(I):
                I = I[I.index.day_of_week == wd]
            I = no_roll(d, I, tz, ta, tb)
            if len(I) < 60:
                continue
            first = I.index < I.index[len(I) // 2]
            for side in (1, -1):
                t1 = FL.tstat(side * I.gross.values[first])
                if t1 < 3:
                    continue
                found += 1
                g2 = side * I.gross.values[~first]; n2 = g2 - I.sp.values[~first]
                nall = side * I.gross.values - I.sp.values
                ok = FL.tstat(g2) >= 2 and FL.pf(n2) > 1.1
                kept += ok
                if show:
                    yr = pd.Series(nall, index=I.index.year).groupby(level=0).sum()
                    say(f"  {nm:12s} {'BUY ' if side > 0 else 'SELL'} {ta // 60:02d}:{ta % 60:02d}->{tb // 60:02d}:{tb % 60:02d} {tz.split('/')[1]:8s} "
                        f"n {len(I):4d} t1 {t1:+5.2f} t2 {FL.tstat(g2):+5.2f} net2 {n2.mean() / unit:+6.2f} PF2 {FL.f2(FL.pf(n2))} "
                        f"PF all {FL.f2(FL.pf(nall))} yrs+ {int((yr > 0).sum())}/{len(yr)} {'KEPT' if ok else ''}")
    return found, kept


def main():
    meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
    for ln in open(os.path.join(DATA, "meta.txt"), encoding="latin-1"):
        if ln.startswith("energy") or ln.startswith("connected"):
            say(ln.strip())
    syms = [os.path.basename(f)[:-4] for f in sorted(glob.glob(os.path.join(DATA, "*.csv")))]
    for s in syms:
        if s not in meta:
            continue
        d = FL.load(os.path.join(DATA, s + ".csv"), meta[s]["point"])
        if len(d) < 20000:
            say(f"{s}: only {len(d)} bars"); continue
        unit = 0.01 if d.c.median() > 5 else 0.001                     # report in cents for oil
        usd = meta[s]["tick_value"] / meta[s]["tick_size"] * 0.01 if meta[s]["tick_size"] > 0 else 0
        say(f"\n######## {s} ({meta[s]['sym']}): {len(d)} M5 bars {d.index[0].date()} .. {d.index[-1].date()}, median spread "
            f"{d.s.median() / unit:.1f} cents, $ per 1.00 move at 0.01 lot: {usd:.2f}")
        # A
        say("\n== A. oil event times (first half picks the side; KEPT = holds on the second half) ==")
        f_r, k_r = scan(d, unit)
        f_f, k_f = scan(d, unit, shift=135, show=False)
        say(f"  real times: {f_r} first-half hits, {k_r} kept | fake times (+2h15m): {f_f} hits, {k_f} kept")
        # B
        say("\n== B. EIA crude stocks surprise (build -> sell, draw -> buy) ==")
        if os.path.exists(CAL):
            cal = pd.read_csv(CAL, low_memory=False)
            m = (cal.event_code.astype(str) == "eia-crude-oil-stocks-change") & (cal.currency == "USD")
            E = cal[m & cal.actual.notna() & cal.forecast.notna()].copy()
            say(f"  {len(E)} EIA releases with actual and forecast (event codes: {', '.join(sorted(E.event_code.astype(str).unique())[:3])})")
            utc = pd.to_datetime(E.time.astype(np.int64) - 7200, unit="s", utc=True)
            E["t"] = utc.dt.tz_convert("Europe/Athens").dt.tz_localize(None)
            E["dir"] = -np.sign(E.actual - E.forecast)
            srv = d.index.tz_convert("Europe/Athens").tz_localize(None)
            tt = srv.values
            for delay in (1, 2):
                for H in (3, 6, 12):
                    x, sp = [], []
                    for r in E.itertuples(index=False):
                        if r.dir == 0:
                            continue
                        k0 = np.searchsorted(tt, np.datetime64(r.t.floor("5min")))
                        if k0 >= len(tt) - 20 or tt[k0] != np.datetime64(r.t.floor("5min")):
                            continue
                        ke, kx = k0 + delay, k0 + delay + H
                        x.append(r.dir * (d.o.values[kx] - d.o.values[ke])); sp.append(d.s.values[ke])
                    x, sp = np.array(x), np.array(sp)
                    if len(x) < 30:
                        say(f"  entry +{5 * delay} min hold {5 * H} min: {len(x)} trades"); continue
                    h = np.arange(len(x)) >= len(x) // 2
                    n = x - sp
                    say(f"  entry +{5 * delay:2d} min, hold {5 * H:2d} min: {len(x)} trades, gross {x.mean() / unit:+6.2f} c (t {FL.tstat(x):+5.2f}), "
                        f"PF {FL.f2(FL.pf(n))}, halves {FL.f2(FL.pf(n[~h]))} {FL.f2(FL.pf(n[h]))}")
            # the release bar
            agree, jumps = [], []
            for r in E.itertuples(index=False):
                k0 = np.searchsorted(tt, np.datetime64(r.t.floor("5min")))
                if k0 < len(tt) and tt[k0] == np.datetime64(r.t.floor("5min")) and r.dir != 0:
                    mv = d.c.values[k0] - d.o.values[k0]
                    agree.append(np.sign(mv) == r.dir); jumps.append(abs(mv) / unit)
            if agree:
                say(f"  the 5-minute release bar already moved with the surprise {100 * np.mean(agree):.0f}% of the time, "
                    f"average move {np.mean(jumps):.0f} cents")
        else:
            say("  data/calendar.csv missing")
        # C
        say("\n== C. hour-of-day windows (server time, 1-4 h; first half t >= 3, second half t >= 2 and PF > 1.1) ==")
        srvz = d.index.tz_convert("Europe/Athens")
        found = kept = 0
        for h0 in range(2, 23):
            for L in (1, 2, 3, 4):
                if h0 + L > 23:
                    continue
                I = FL.window_trades(d, "Europe/Athens", h0 * 60, (h0 + L) * 60, side=1)
                if len(I) < 300:
                    continue
                first = I.index < I.index[len(I) // 2]
                for side in (1, -1):
                    t1 = FL.tstat(side * I.gross.values[first])
                    if t1 < 3:
                        continue
                    found += 1
                    g2 = side * I.gross.values[~first]; n2 = g2 - I.sp.values[~first]
                    ok = FL.tstat(g2) >= 2 and FL.pf(n2) > 1.1
                    kept += ok
                    say(f"  {'BUY ' if side > 0 else 'SELL'} {h0:02d}:00->{h0 + L:02d}:00 server: t1 {t1:+.2f} t2 {FL.tstat(g2):+.2f} "
                        f"net2 {n2.mean() / unit:+.2f} c PF2 {FL.f2(FL.pf(n2))} {'KEPT' if ok else ''}")
        say(f"  {found} first-half hits, {kept} kept (about {21 * 4 * 2 * 0.00135:.1f} hits expected by chance)")
        # D
        say("\n== D. NR7 D1 ==")
        dd = SA.prep(SA.load(os.path.join(DATA, s + ".csv"), meta[s]["point"]))
        D = SA.daily(dd)
        sig, flat = SA.live_nr7(D)
        res = SA.sim(*(D[x].values for x in ("o", "h", "l", "c", "s")), sig, flat)
        if res:
            R = np.array([(p - sp_) / rk for (_, _, p, sp_, rk, _) in res])
            h = np.arange(len(R)) >= len(R) // 2
            say(f"  {len(R)} trades, PF {FL.f2(FL.pf(R))}, halves {FL.f2(FL.pf(R[~h]))} {FL.f2(FL.pf(R[h]))}, avg {R.mean():+.3f} R")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
