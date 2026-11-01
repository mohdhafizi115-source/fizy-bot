"""Round 10: follow the news surprise (scheduled releases), on the broker's M5 history (Mar 2020 - Oct 2026).

Calendar: the MQL5 economic calendar exported by mt5/ExportCal.mq5 (data/calendar.csv): high-importance events
with actual, forecast and MetaQuotes' impact flag (actual better or worse than forecast for the currency).
The export gives every past time at today's server offset (+2 h); it is converted to the real server clock
(Europe/Athens, +2/+3), the same clock as the M5 bars (checked: NFP lands at 15:30 server).
Instruments per currency (+1 = buy it when the currency is strong):
  USD -> EURUSD -1, GBPUSD -1, USDJPY +1, XAUUSD -1;  EUR -> EURUSD;  GBP -> GBPUSD;  JPY -> USDJPY -1;
  AUD -> AUDUSD;  NZD -> NZDUSD;  CAD -> USDCAD -1;  CHF -> USDCHF -1
An EA only knows the number after the release, so the earliest entry here is the open of the first M5 bar after
the release bar (+5 minutes), then +10 and +15. Holds of 15, 30, 60 and 120 minutes.
Tests:
  1  How often the release bar already jumps in the surprise direction (the part nobody retail can catch).
  2  SURPRISE: trade in the surprise direction; all surprises, |z| >= 1 and |z| >= 2 (surprise divided by the
     spread of earlier surprises of the same event).
  3  SHOCK: no numbers needed: follow or fade a release bar that moved >= 1.5 ATR(M5).
  4  Per event (NFP, CPI, rate decisions ...): surprise >= 1 z, +5 min entry, 30 min hold.
Cost: the entry bar's spread (MT5 export); stress test 2x spread (spreads are wide right after news).
PASS: >= 100 trades, PF > 1.1 in both halves after spread, PF > 1.0 at 2x spread.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "calendar.csv")
INST = {"USD": [("EURUSD", -1), ("GBPUSD", -1), ("USDJPY", 1), ("XAUUSD", -1)], "EUR": [("EURUSD", 1)], "GBP": [("GBPUSD", 1)],
        "JPY": [("USDJPY", -1)], "AUD": [("AUDUSD", 1)], "NZD": [("NZDUSD", 1)], "CAD": [("USDCAD", -1)], "CHF": [("USDCHF", -1)]}
EVENTS = [("NFP", "nonfarm-payrolls"), ("CPI", "cpi"), ("Fed rate", "fed-interest-rate"), ("Retail sales", "retail-sales"),
          ("ISM", "ism-"), ("GDP", "gdp"), ("Jobless claims", "jobless-claims"), ("PPI", "ppi"), ("ECB rate", "ecb-"),
          ("Unemployment", "unemployment-rate"), ("PMI", "pmi"), ("BoE/BoJ/RBA/BoC/SNB/RBNZ rate", "rate-decision")]


def say(s=""):
    print(s, flush=True)


def load_px(sym, point):
    df = pd.read_csv(os.path.join(DATA, sym + ".csv")).drop_duplicates("t").sort_values("t")
    s = df.s.values.astype(float) * point
    s[s <= 0] = np.median(s[s > 0])
    o, h, l, c = (df[x].values.astype(float) for x in ("o", "h", "l", "c"))
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - c1), abs(l - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    return dict(t=df.t.values.astype(np.int64), o=o, c=c, s=s, atr=atr)


def stats(x, sp, idx):
    """x: gross per trade (fraction of price), sp: spread cost (fraction). Returns a summary string and pass flag."""
    if len(x) < 20:
        return f"{len(x):5d} trades", False
    n1, n2 = x - sp, x - 2 * sp
    order = np.argsort(idx); n1o = n1[order]
    h = np.arange(len(n1o)) >= len(n1o) // 2
    p1, p2 = FL.pf(n1o[~h]), FL.pf(n1o[h])
    yrs = pd.Series(n1, index=pd.to_datetime(idx, unit="s")).groupby(lambda d: d.year).sum()
    ok = len(x) >= 100 and p1 > 1.1 and p2 > 1.1 and FL.pf(n2) > 1.0
    return (f"{len(x):5d} trades, gross {1e4 * x.mean():+6.2f} bp (t {FL.tstat(x):+5.2f}), PF {FL.f2(FL.pf(n1))}, 2x spread {FL.f2(FL.pf(n2))}, "
            f"halves {FL.f2(p1)} {FL.f2(p2)}, yrs+ {int((yrs > 0).sum())}/{len(yrs)}{'  PASS' if ok else ''}"), ok


def main():
    if not os.path.exists(CAL):
        say("data/calendar.csv missing: run the MT5 calendar export first"); return
    cal = pd.read_csv(CAL, low_memory=False)
    cal = cal[(cal.importance == 3) & cal.currency.isin(list(INST))].copy()
    # The calendar converts every past time with today's server offset (+2 h), so summer times are an hour early:
    # take it as UTC+2, then convert to the real server clock (Europe/Athens, +2/+3) used by the M5 bars.
    utc = pd.to_datetime(cal.time.astype(np.int64) - 7200, unit="s", utc=True)
    srv = utc.dt.tz_convert("Europe/Athens").dt.tz_localize(None)
    cal["t"] = (srv - pd.Timestamp("1970-01-01")).dt.total_seconds().astype(np.int64)
    cal = cal[cal.t >= 1585526400]                                      # from 30 Mar 2020 (start of the M5 data)
    cal = cal.sort_values("t")
    cal["has"] = cal.actual.notna() & cal.forecast.notna()
    cal["s"] = cal.actual - cal.forecast
    cal["dirc"] = np.where(cal.impact == 1, 1, np.where(cal.impact == 2, -1, 0))   # currency direction after the number
    # z: surprise over the spread of earlier surprises of the same event (no look-ahead)
    cal["z"] = np.nan
    for code, g in cal[cal.has].groupby("event_code"):
        sd = g.s.abs().expanding().mean().shift(1)
        cal.loc[g.index, "z"] = (g.s.abs() / sd.replace(0, np.nan)).where(g.index.isin(g.index[5:]))
    say(f"Round 10 news test: {len(cal)} high-importance releases ({int(cal.has.sum())} with actual and forecast, "
        f"{int((cal.dirc != 0).sum())} with an impact flag), {time.time() - T0:.0f} s")
    nfp = cal[cal.event_code.astype(str).str.contains("nonfarm-payrolls")]
    if len(nfp):
        hm = pd.to_datetime(nfp.t, unit="s").dt.strftime("%H:%M").value_counts().head(3)
        say("time check, NFP in server time (expected 15:30): " + ", ".join(f"{k} x{v}" for k, v in hm.items()))
    meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
    PX = {s: load_px(s, meta[s]["point"]) for s in {x for v in INST.values() for x, _ in v} if os.path.exists(os.path.join(DATA, s + ".csv"))}

    rows = []                                                           # one row per release x instrument
    for r in cal.itertuples(index=False):
        for sym, sg in INST[r.currency]:
            P = PX.get(sym)
            if P is None:
                continue
            tb = r.t - r.t % 300
            k0 = np.searchsorted(P["t"], tb)
            if k0 >= len(P["t"]) - 30 or P["t"][k0] != tb or not np.isfinite(P["atr"][k0]):
                continue
            rows.append(dict(sym=sym, cur=r.currency, code=str(r.event_code), t=r.t, k0=k0, sg=sg, dirc=r.dirc, z=r.z,
                             r0=(P["c"][k0] - P["o"][k0]), atr=P["atr"][k0]))
    E = pd.DataFrame(rows)
    say(f"{len(E)} release x instrument cases with M5 bars")

    def trade(sub, dirs, delay, H):
        x, sp, idx = [], [], []
        for (row, dr) in zip(sub.itertuples(index=False), dirs):
            if dr == 0:
                continue
            P = PX[row.sym]; ke = row.k0 + 1 + delay; kx = ke + H
            if kx >= len(P["t"]) or P["t"][kx] - P["t"][row.k0] > (1 + delay + H) * 300 + 600:
                continue
            x.append(dr * (P["o"][kx] - P["o"][ke]) / P["o"][ke]); sp.append(P["s"][ke] / P["o"][ke]); idx.append(row.t)
        return np.array(x), np.array(sp), np.array(idx)

    # 1. the release bar
    S = E[(E.dirc != 0) & (E.z >= 1)]
    agree = np.mean(np.sign(S.r0) == S.dirc * S.sg) if len(S) else np.nan
    say(f"\n== 1. release bar: with a surprise of >= 1 z, the 5-minute release bar already moved in the surprise direction "
        f"{100 * agree:.0f}% of the time ({len(S)} cases); average jump {np.mean(np.abs(S.r0) / S.atr):.1f} ATR(M5)")

    # 2. follow the surprise
    say("\n== 2. SURPRISE: trade in the surprise direction (all instruments together) ==")
    passed = []
    for zmin in (0, 1, 2):
        S = E[(E.dirc != 0) & ((E.z >= zmin) if zmin else True)]
        for delay in (0, 1, 2):
            for H in (3, 6, 12, 24):
                x, sp, idx = trade(S, (S.dirc * S.sg).values, delay, H)
                txt, ok = stats(x, sp, idx)
                say(f"  z >= {zmin}, entry +{5 * (delay + 1):2d} min, hold {5 * H:3d} min: {txt}")
                if ok:
                    passed.append(f"SURPRISE z>={zmin} entry +{5 * (delay + 1)} hold {5 * H}")
    say("\n   per instrument, z >= 1, entry +5 min, hold 30 min:")
    S = E[(E.dirc != 0) & (E.z >= 1)]
    for (sym, cur), g in S.groupby(["sym", "cur"]):
        x, sp, idx = trade(g, (g.dirc * g.sg).values, 0, 6)
        txt, ok = stats(x, sp, idx)
        say(f"   {cur} news on {sym:7s}: {txt}")
        if ok:
            passed.append(f"SURPRISE {cur} on {sym}")

    # 3. shock follow / fade
    say("\n== 3. SHOCK: the release bar moved >= 1.5 ATR(M5); follow or fade it (all high-importance releases) ==")
    S = E[np.abs(E.r0) >= 1.5 * E.atr]
    for side, nm in ((1, "follow"), (-1, "fade")):
        for H in (3, 6, 12):
            x, sp, idx = trade(S, side * np.sign(S.r0).values, 0, H)
            txt, ok = stats(x, sp, idx)
            say(f"  {nm:6s} entry +5 min, hold {5 * H:3d} min: {txt}")
            if ok:
                passed.append(f"SHOCK {nm} hold {5 * H}")

    # 4. per event
    say("\n== 4. per event: surprise >= 1 z, entry +5 min, hold 30 min (USD events on EURUSD, USDJPY, XAUUSD, GBPUSD) ==")
    S = E[(E.dirc != 0) & (E.z >= 1)]
    for nm, key in EVENTS:
        g = S[S.code.str.contains(key, regex=False)]
        if len(g) < 20:
            continue
        x, sp, idx = trade(g, (g.dirc * g.sg).values, 0, 6)
        txt, ok = stats(x, sp, idx)
        say(f"  {nm:30s} {txt}")
        if ok:
            passed.append(f"EVENT {nm}")

    say("\n== passed ==")
    for p in passed:
        say("  " + p)
    say(f"  {len(passed)} passed; about 60 tests were run, so 1-3 passes could be luck")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
