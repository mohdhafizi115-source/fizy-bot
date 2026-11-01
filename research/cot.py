"""Round 9: does big-money positioning (CFTC Commitments of Traders) predict next week's move?

Data: CFTC weekly COT reports (positions as of Tuesday, published Friday 15:30 New York), downloaded from
cftc.gov: the Legacy futures-only report (large speculators = non-commercials, hedgers = commercials) and the
Traders in Financial Futures report (leveraged funds, asset managers) for the currency futures.
Prices: the broker's own M5 history (Mar 2020 - Oct 2026). Each report is traded the week after it is published:
enter Monday 02:00 server time, exit Friday 22:00 server time (no weekend hold, no look-ahead).
Futures -> broker symbol: gold GC -> XAUUSD, Euro FX -> EURUSD, pound -> GBPUSD, Aussie -> AUDUSD, kiwi ->
NZDUSD, yen -> USDJPY (inverted), Canadian dollar -> USDCAD (inverted), Swiss franc -> USDCHF (inverted),
Bitcoin -> BTCUSD.
Signals (fixed in advance; +1 = buy the foreign currency / gold / BTC future):
  SPEC_CHG   follow the weekly change of the large speculators' net position
  SPEC_TREND follow the sign of the large speculators' net position
  SPEC_FADE  COT index of the speculators' net (position in its 52-week range) > 90 -> sell, < 10 -> buy
  COMM_EXT   COT index of the commercials' net > 90 -> buy, < 10 -> sell (follow the hedgers at extremes)
  LEV_CHG    follow the weekly change of the leveraged funds' net (currencies only, TFF)
  AM_CHG     follow the weekly change of the asset managers' net (currencies only, TFF)
Costs: the entry bar's spread, plus an estimated swap for the 6 rollover charges Monday-Friday (Wednesday triple):
0.3 pip a night for forex, $0.80 a night per ounce for gold, 0.06% a night for BTC (estimates, not broker data).
Results in % of price per trade. A signal counts only with PF > 1.1 after costs in both halves.
"""
import os, sys, io, zipfile, time
import numpy as np, pandas as pd, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
UA = {"User-Agent": "Mozilla/5.0 (research script)"}
MAP = {  # CFTC contract code, name keyword, broker symbol, sign (+1: long future = long symbol)
    "GOLD": ("088691", "GOLD - COMMODITY EXCHANGE", "XAUUSD", 1),
    "EUR": ("099741", "EURO FX - CHICAGO", "EURUSD", 1),
    "GBP": ("096742", "BRITISH POUND", "GBPUSD", 1),
    "AUD": ("232741", "AUSTRALIAN DOLLAR", "AUDUSD", 1),
    "NZD": ("112741", "NZ DOLLAR", "NZDUSD", 1),
    "JPY": ("097741", "JAPANESE YEN", "USDJPY", -1),
    "CAD": ("090741", "CANADIAN DOLLAR", "USDCAD", -1),
    "CHF": ("092741", "SWISS FRANC", "USDCHF", -1),
    "BTC": ("133741", "BITCOIN - CHICAGO MERCANTILE", "BTCUSD", 1),
}
SWAP = {"XAUUSD": ("abs", 0.80), "BTCUSD": ("pct", 0.0006)}


def say(s=""):
    print(s, flush=True)


def get_zip(url):
    for k in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=120)
            if r.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(r.content))
                return pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
            say(f"  {url}: HTTP {r.status_code}")
        except Exception as e:
            say(f"  {url}: {e}")
        time.sleep(3)
    return None


def col(df, *keys):
    for c in df.columns:
        lc = c.lower()
        if all(k.lower() in lc for k in keys):
            return c
    raise KeyError(keys)


def load_cot():
    legacy, tff = [], []
    for y in range(2018, 2027):
        a = get_zip(f"https://www.cftc.gov/files/dea/history/deacot{y}.zip")
        if a is not None:
            legacy.append(a)
        b = get_zip(f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{y}.zip")
        if b is not None:
            tff.append(b)
    L = pd.concat(legacy, ignore_index=True)
    out = {}
    lc_code, lc_name = col(L, "contract market code"), col(L, "market and exchange")
    lc_date = col(L, "yyyy-mm-dd")
    for k, (code, name, sym, sg) in MAP.items():
        x = L[(L[lc_code].astype(str).str.strip().str.zfill(6) == code) | L[lc_name].str.upper().str.contains(name, regex=False)]
        if x.empty:
            say(f"  {k}: not in the legacy report"); continue
        f = pd.DataFrame({"date": pd.to_datetime(x[lc_date]),
                          "oi": x[col(L, "open interest (all)")].astype(float),
                          "spec": x[col(L, "noncommercial positions-long (all)")].astype(float) - x[col(L, "noncommercial positions-short (all)")].astype(float),
                          "comm": x[col(L, "commercial positions-long (all)")].astype(float) - x[col(L, "commercial positions-short (all)")].astype(float)})
        out[k] = f.groupby("date").last().sort_index()
    if tff:
        T = pd.concat(tff, ignore_index=True)
        tc_code, tc_name, tc_date = col(T, "contract_market_code"), col(T, "market_and_exchange"), col(T, "yyyy-mm-dd")
        for k, (code, name, sym, sg) in MAP.items():
            if k in ("GOLD",) or k not in out:
                continue
            x = T[(T[tc_code].astype(str).str.strip().str.zfill(6) == code) | T[tc_name].str.upper().str.contains(name, regex=False)]
            if x.empty:
                continue
            f = pd.DataFrame({"date": pd.to_datetime(x[tc_date]),
                              "lev": x[col(T, "lev_money_positions_long")].astype(float) - x[col(T, "lev_money_positions_short")].astype(float),
                              "am": x[col(T, "asset_mgr_positions_long")].astype(float) - x[col(T, "asset_mgr_positions_short")].astype(float)})
            out[k] = out[k].join(f.groupby("date").last(), how="left")
    return out


def cot_index(s, n=52):
    lo, hi = s.rolling(n, min_periods=26).min(), s.rolling(n, min_periods=26).max()
    return 100 * (s - lo) / (hi - lo).replace(0, np.nan)


def weekly_trades(d, report_dates):
    """Entry Monday 02:00 server after the Friday release, exit Friday 22:00 server. Returns frame by report date."""
    srv = d.index.tz_convert("Europe/Athens").tz_localize(None)
    t = srv.values
    rows = []
    for rd in report_dates:
        mon = (rd + pd.Timedelta(days=6)).normalize()                     # Tuesday + 6 = Monday
        a = np.searchsorted(t, np.datetime64(mon + pd.Timedelta(hours=2)))
        b = np.searchsorted(t, np.datetime64(mon + pd.Timedelta(days=4, hours=22)))
        if a >= len(t) or b >= len(t) or b <= a or (srv[a] - (mon + pd.Timedelta(hours=2))) > pd.Timedelta(hours=6):
            continue
        rows.append((rd, d.o.values[a], d.o.values[b], d.s.values[a]))
    return pd.DataFrame(rows, columns=["rd", "pin", "pout", "sp"]).set_index("rd").dropna()


def main():
    meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
    cot = load_cot()
    say(f"Round 9 COT test: {len(cot)} markets from the CFTC files: " + ", ".join(f"{k} {len(v)} weeks" for k, v in cot.items()))
    allres = {}
    for k, C in cot.items():
        code, name, sym, sg = MAP[k]
        f = os.path.join(DATA, sym + ".csv")
        if not os.path.exists(f):
            continue
        d = FL.load(f, meta[sym]["point"])
        W = weekly_trades(d, C.index)
        if W.empty:
            continue
        C = C.copy()
        C["spec_chg"] = np.sign(C.spec.diff()); C["spec_tr"] = np.sign(C.spec)
        ci = cot_index(C.spec); C["spec_fade"] = np.where(ci > 90, -1, np.where(ci < 10, 1, 0))
        cc = cot_index(C.comm); C["comm_ext"] = np.where(cc > 90, 1, np.where(cc < 10, -1, 0))
        if "lev" in C:
            C["lev_chg"] = np.sign(C.lev.diff()); C["am_chg"] = np.sign(C.am.diff())
        X = W.join(C, how="inner")
        X = X[X.index >= pd.Timestamp("2020-03-24")]
        ret = (X.pout - X.pin) / X.pin                                   # long the broker symbol, fraction of price
        kind, val = SWAP.get(sym, ("pip", 0.3))
        pip = 0.01 if "JPY" in sym else 0.0001
        swap = (6 * val / X.pin) if kind == "abs" else (6 * val if kind == "pct" else 6 * val * pip / X.pin)
        cost = X.sp / X.pin
        for sig in ("spec_chg", "spec_tr", "spec_fade", "comm_ext", "lev_chg", "am_chg"):
            if sig not in X:
                continue
            pos = sg * X[sig].fillna(0).values                              # +1 long the broker symbol
            m = pos != 0
            g = pos[m] * ret.values[m]
            n1 = g - cost.values[m]; n2 = n1 - swap.values[m]
            allres.setdefault(sig, []).append((k, sym, X.index[m], g, n1, n2))
    say("\nper market: trades, gross % a week (t), PF after spread, PF after spread + est. swap, halves (after both)")
    summary = []
    for sig, rows in allres.items():
        say(f"\n== {sig} ==")
        G, N2, D = [], [], []
        for k, sym, idx, g, n1, n2 in rows:
            h = idx >= idx[len(idx) // 2] if len(idx) else []
            yr = pd.Series(n2, index=idx).groupby(idx.year).sum()
            say(f"  {sym:7s} {len(g):4d} gross {100 * g.mean():+6.3f}% (t {FL.tstat(g):+5.2f}) PF {FL.f2(FL.pf(n1))} / {FL.f2(FL.pf(n2))} "
                f"halves {FL.f2(FL.pf(n2[~h]))} {FL.f2(FL.pf(n2[h]))} yrs+ {int((yr > 0).sum())}/{len(yr)}")
            G.extend(g); N2.extend(n2); D.extend(idx)
            if FL.pf(n2[~h]) > 1.1 and FL.pf(n2[h]) > 1.1 and len(g) >= 80:
                summary.append(f"{sig} {sym}: PF {FL.pf(n2):.2f}, halves {FL.pf(n2[~h]):.2f} / {FL.pf(n2[h]):.2f}, {len(g)} weeks")
        G, N2 = np.array(G), np.array(N2)
        say(f"  ALL     {len(G):4d} gross {100 * G.mean():+6.3f}% (t {FL.tstat(G):+5.2f}) PF after spread + swap {FL.f2(FL.pf(N2))}")
    say("\n== markets where a signal held in both halves (PF > 1.1 after spread + swap, >= 80 weeks) ==")
    tests = sum(len(r) for r in allres.values())
    for s in summary:
        say("  " + s)
    # chance control: random weekly long/short signs on the same weeks, same costs, 50 draws per market
    rng = np.random.default_rng(7); passes = trials = 0
    for k, sym, idx, g, n1, n2 in allres.get("spec_tr", []):
        base = np.abs(g)                                  # |weekly move|; a random sign re-creates gross
        cst = g - n2                                      # this market's per-trade cost
        for _ in range(50):
            sg = rng.choice([-1, 1], size=len(g))
            r = sg * np.sign(g) * base - cst
            h = np.arange(len(r)) >= len(r) // 2
            trials += 1
            passes += FL.pf(r[~h]) > 1.1 and FL.pf(r[h]) > 1.1
    say(f"  {len(summary)} of {tests} market x signal tests passed; random signs pass {100 * passes / max(trials, 1):.1f}% of the time, "
        f"so luck alone would give about {passes / max(trials, 1) * tests:.1f}")


if __name__ == "__main__":
    main()
