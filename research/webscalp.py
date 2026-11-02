"""Round 17 (2 Nov 2026): scalping systems that are taught on the web, coded as written, on the broker's M5 history.

The owner asked: "cari lagi di google banyak teknik scalping yang orang ajar … test di sini". Systems not tested
before (sources: FXOpen "three working 5-minute strategies", MQL5 blog "Best Indicators for Scalping", Babypips
"3 Ducks", StockSharp "Williams %R Zone Scalper", a CCI scalping guide, a 5-8-13 SMA ribbon freqtrade strategy, a
TradingView "EMA Ribbon + ADX momentum" script). Where a source leaves a value open, the choice is written here and
fixed before the run. M5 bars, entries 09:00-21:00 server (London + New York), flat 23:00. Pip = 0.0001 (JPY 0.01,
gold $0.10, BTC $10).
  MOMO       FXOpen "Momo": close crosses the EMA 20 with the MACD(12,26,9) histogram above zero for the last 5 bars or
             just crossing it; stop order 10 pips beyond the EMA (valid 6 bars); SL 10 pips on the other side of the
             EMA; half the position TP 1R, the other half exits when the histogram turns the other way
  EMA_RSI    FXOpen: EMA 9 crosses EMA 55 with EMA 55 on the right side of EMA 200 and RSI(14) > 52 (< 48); SL at the
             10-bar swing; exit when RSI(14) crosses back over 50
  EMA_BB     FXOpen: EMA 5 crosses EMA 20, MACD histogram on the same side, close in the lower (upper) half of the
             Bollinger band (20, 2) or just past the middle; SL 7 pips beyond the 10-bar swing; exit when the histogram
             stops growing
  DUCKS      Babypips 3 Ducks: H4 and H1 closes on the same side of their SMA 60, M5 close crosses its SMA 60; stop order
             at the 10-bar high (low), valid 6 bars; SL at the 10-bar low (high); TP 2R
  WPR        Williams %R(14) leaves -80 upwards -> buy, leaves -20 downwards -> sell; exit on the opposite signal; SL 3 ATR
             (safety; the source has none)
  WPR_TREND  the same, only on the EMA 200 side
  CCI        CCI(20) crosses above -100 with the close above SMA 50 (shorts mirrored); SL at the 10-bar swing; TP 1R;
             exit if CCI crosses zero against the trade
  STOCH533   Stochastic (5,3,3): %K crosses %D below 20 -> buy, above 80 -> sell; SL at the 10-bar swing; TP 1R
  RIBBON     SMA 5 > 8 > 13 with SMA5-SMA13 > 0.1% of price, tick volume > 1.2x its 20-bar mean, a higher close, RSI(14) < 75
             (shorts mirrored); exit on SMA 5 crossing SMA 8, RSI > 70 (< 30) or after 30 minutes; SL 0.3%, TP 0.5%
  EMA9_21    MQL5 framework: EMA 9 above EMA 21 and RSI(14) > 50, a bar dips to the EMA 9 and closes back above it;
             SL 0.1 ATR below the 3-bar low; TP 2R (shorts mirrored)
  ADX_RIB    EMA 10 > 21 > 34 > 55 with ADX(14) > 25 and DI+ > DI- turning on -> buy at the next open (shorts mirrored);
             exit when EMA 10 crosses EMA 21; SL 2 ATR
  RAND       3 random entries a day in the same hours, SL 1 ATR, TP 1R (chance baseline)
Pass rule per instrument (CLAUDE.md): >= 150 trades, PF >= 1.15 after spread, both halves >= 1.05, stress 1.5x >= 1.05,
last 12 months positive.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP", "BTCUSD"]
RULES = ["MOMO", "EMA_RSI", "EMA_BB", "DUCKS", "WPR", "WPR_TREND", "CCI", "STOCH533", "RIBBON", "EMA9_21", "ADX_RIB", "RAND"]
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def side_of_sma(c, rule, n=60):
    """+1 / -1: last completed higher-timeframe close above / below its SMA n, known at the M5 bar's open"""
    hc = c.resample(rule, label="right", closed="left").last().dropna()
    s = np.sign(hc - hc.rolling(n).mean())
    return s.reindex(c.index, method="ffill").fillna(0).values


def build(d, sym):
    o, h, l, c, v = d.o, d.h, d.l, d.c, d.v
    n = len(d)
    pip = 0.01 if "JPY" in sym else (0.1 if sym == "XAUUSD" else (10.0 if sym == "BTCUSD" else 0.0001))
    c1 = c.shift()
    atr = np.maximum(h - l, np.maximum((h - c1).abs(), (l - c1).abs())).ewm(alpha=1 / 14, adjust=False).mean()
    hm = d.index.hour * 60 + d.index.minute
    sess = np.asarray((hm >= 540) & (hm < 1260))
    e5, e9, e10, e20, e21, e34, e55, e200 = (ema(c, k) for k in (5, 9, 10, 20, 21, 34, 55, 200))
    macd = ema(c, 12) - ema(c, 26)
    hist = (macd - ema(macd, 9)).values
    r14 = rsi(c).values
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    up_bb, lo_bb = (mid + 2 * sd).values, (mid - 2 * sd).values
    hh10, ll10 = h.rolling(10).max().values, l.rolling(10).min().values
    ll3, hh3 = l.rolling(3).min().values, h.rolling(3).max().values
    hh14, ll14 = h.rolling(14).max(), l.rolling(14).min()
    wpr = (-100 * (hh14 - c) / (hh14 - ll14).replace(0, np.nan)).values
    tp_ = (h + l + c) / 3
    md = tp_.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = ((tp_ - tp_.rolling(20).mean()) / (0.015 * md.replace(0, np.nan))).values
    ll5, hh5 = l.rolling(5).min(), h.rolling(5).max()
    k_ = (100 * (c - ll5) / (hh5 - ll5).replace(0, np.nan)).rolling(3).mean()
    dK, dD = k_.values, k_.rolling(3).mean().values
    s5, s8, s13, s50, s60 = (c.rolling(k).mean().values for k in (5, 8, 13, 50, 60))
    vma = v.rolling(20).mean().shift(1).values
    # ADX / DI
    upm, dnm = h.diff(), -l.diff()
    pdm = np.where((upm > dnm) & (upm > 0), upm, 0.0); ndm = np.where((dnm > upm) & (dnm > 0), dnm, 0.0)
    trs = pd.Series(np.maximum(h - l, np.maximum((h - c1).abs(), (l - c1).abs())).values)
    atr_w = trs.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / 14, adjust=False).mean() / atr_w
    ndi = 100 * pd.Series(ndm).ewm(alpha=1 / 14, adjust=False).mean() / atr_w
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / 14, adjust=False).mean().values
    pdi, ndi = pdi.values, ndi.values
    h4, h1s = side_of_sma(c, "4h"), side_of_sma(c, "1h")
    O, H, L, C, A = o.values, h.values, l.values, c.values, atr.values
    E = {k: x.values for k, x in (("e5", e5), ("e9", e9), ("e10", e10), ("e20", e20), ("e21", e21), ("e34", e34), ("e55", e55), ("e200", e200))}
    S = {r: [] for r in RULES}
    X = {}                                           # exit flags per rule: (exit long, exit short)
    X["MOMO"] = (hist < 0, hist > 0)
    X["EMA_RSI"] = (r14 < 50, r14 > 50)
    hd = np.r_[np.nan, np.diff(hist)]
    X["EMA_BB"] = (hd < 0, hd > 0)
    wl, ws = (np.r_[False, (wpr[:-1] >= -20) & (wpr[1:] < -20)]), (np.r_[False, (wpr[:-1] <= -80) & (wpr[1:] > -80)])
    X["WPR"] = X["WPR_TREND"] = (wl, ws)
    X["CCI"] = (cci < 0, cci > 0)
    s5x8d = np.r_[False, (s5[:-1] >= s8[:-1]) & (s5[1:] < s8[1:])]; s5x8u = np.r_[False, (s5[:-1] <= s8[:-1]) & (s5[1:] > s8[1:])]
    X["RIBBON"] = (s5x8d | (r14 > 70), s5x8u | (r14 < 30))
    X["ADX_RIB"] = (E["e10"] < E["e21"], E["e10"] > E["e21"])
    bull = (E["e10"] > E["e21"]) & (E["e21"] > E["e34"]) & (E["e34"] > E["e55"]) & (adx > 25) & (pdi > ndi)
    bear = (E["e10"] < E["e21"]) & (E["e21"] < E["e34"]) & (E["e34"] < E["e55"]) & (adx > 25) & (ndi > pdi)
    rng = np.random.default_rng(17)
    dates = d.index.normalize().values
    for i in range(250, n - 2):
        if not sess[i] or not np.isfinite(A[i]) or A[i] <= 0:
            continue
        a = A[i]
        def mk(rule, dr, sl, **kw):
            g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=kw.pop("maxb", 10 ** 6))
            g.update(kw)
            S[rule].append(g)
        # MOMO
        for dr in (1, -1):
            crossed = (C[i] - E["e20"][i]) * dr > 0 and (C[i - 1] - E["e20"][i - 1]) * dr <= 0
            mom = all(hist[i - 5:i + 1] * dr > 0) or (hist[i] * dr > 0 and hist[i - 1] * dr <= 0)
            if crossed and mom:
                P = E["e20"][i] + dr * 10 * pip
                sl = E["e20"][i] - dr * 10 * pip
                base = dict(k0=i + 1, kind="stop", dir=dr, P=P, sl=sl, exp=i + 6, maxb=10 ** 6)
                S["MOMO"].append(dict(base, tp_r=1.0))
                S["MOMO"].append(dict(base, tp=None, xl=X["MOMO"][0], xs=X["MOMO"][1], half=2))
        # EMA_RSI
        if E["e9"][i] > E["e55"][i] and E["e9"][i - 1] <= E["e55"][i - 1] and E["e55"][i] > E["e200"][i] and r14[i] > 52:
            mk("EMA_RSI", 1, min(ll10[i], C[i] - 0.2 * a), tp=None, xl=X["EMA_RSI"][0], xs=X["EMA_RSI"][1], maxb=48)
        if E["e9"][i] < E["e55"][i] and E["e9"][i - 1] >= E["e55"][i - 1] and E["e55"][i] < E["e200"][i] and r14[i] < 48:
            mk("EMA_RSI", -1, max(hh10[i], C[i] + 0.2 * a), tp=None, xl=X["EMA_RSI"][0], xs=X["EMA_RSI"][1], maxb=48)
        # EMA_BB
        m_ = (up_bb[i] + lo_bb[i]) / 2
        if E["e5"][i] > E["e20"][i] and E["e5"][i - 1] <= E["e20"][i - 1] and hist[i] > 0 and C[i] <= m_ + 0.25 * (up_bb[i] - m_):
            mk("EMA_BB", 1, min(ll10[i] - 7 * pip, C[i] - 0.2 * a), tp=None, xl=X["EMA_BB"][0], xs=X["EMA_BB"][1], maxb=48)
        if E["e5"][i] < E["e20"][i] and E["e5"][i - 1] >= E["e20"][i - 1] and hist[i] < 0 and C[i] >= m_ - 0.25 * (m_ - lo_bb[i]):
            mk("EMA_BB", -1, max(hh10[i] + 7 * pip, C[i] + 0.2 * a), tp=None, xl=X["EMA_BB"][0], xs=X["EMA_BB"][1], maxb=48)
        # DUCKS
        for dr in (1, -1):
            if h4[i] == dr and h1s[i] == dr and (C[i] - s60[i]) * dr > 0 and (C[i - 1] - s60[i - 1]) * dr <= 0:
                P = max(hh10[i], C[i] + pip) if dr == 1 else min(ll10[i], C[i] - pip)
                sl = ll10[i] if dr == 1 else hh10[i]
                S["DUCKS"].append(dict(k0=i + 1, kind="stop", dir=dr, P=P, sl=sl, tp_r=2.0, exp=i + 6, maxb=10 ** 6))
        # WPR
        if ws[i]:
            mk("WPR", 1, C[i] - 3 * a, tp=None, xl=wl, xs=ws)
            if C[i] > E["e200"][i]:
                mk("WPR_TREND", 1, C[i] - 3 * a, tp=None, xl=wl, xs=ws)
        if wl[i]:
            mk("WPR", -1, C[i] + 3 * a, tp=None, xl=wl, xs=ws)
            if C[i] < E["e200"][i]:
                mk("WPR_TREND", -1, C[i] + 3 * a, tp=None, xl=wl, xs=ws)
        # CCI
        if cci[i] > -100 >= cci[i - 1] and C[i] > s50[i]:
            mk("CCI", 1, min(ll10[i], C[i] - 0.2 * a), tp_r=1.0, xl=X["CCI"][0], xs=X["CCI"][1])
        if cci[i] < 100 <= cci[i - 1] and C[i] < s50[i]:
            mk("CCI", -1, max(hh10[i], C[i] + 0.2 * a), tp_r=1.0, xl=X["CCI"][0], xs=X["CCI"][1])
        # STOCH 5,3,3
        if dK[i] > dD[i] and dK[i - 1] <= dD[i - 1] and dK[i - 1] < 20 and dD[i - 1] < 20:
            mk("STOCH533", 1, min(ll10[i], C[i] - 0.2 * a), tp_r=1.0)
        if dK[i] < dD[i] and dK[i - 1] >= dD[i - 1] and dK[i - 1] > 80 and dD[i - 1] > 80:
            mk("STOCH533", -1, max(hh10[i], C[i] + 0.2 * a), tp_r=1.0)
        # RIBBON
        if np.isfinite(vma[i]) and vma[i] > 0 and d.v.values[i] > 1.2 * vma[i]:
            if s5[i] > s8[i] > s13[i] and s5[i] - s13[i] > 0.001 * s13[i] and C[i] > C[i - 1] and r14[i] < 75:
                mk("RIBBON", 1, C[i] * 0.997, tp=C[i] * 1.005, xl=X["RIBBON"][0], xs=X["RIBBON"][1], maxb=6)
            if s5[i] < s8[i] < s13[i] and s13[i] - s5[i] > 0.001 * s13[i] and C[i] < C[i - 1] and r14[i] > 25:
                mk("RIBBON", -1, C[i] * 1.003, tp=C[i] * 0.995, xl=X["RIBBON"][0], xs=X["RIBBON"][1], maxb=6)
        # EMA 9 / 21 pullback
        if E["e9"][i] > E["e21"][i] and r14[i] > 50 and L[i] <= E["e9"][i] < C[i]:
            mk("EMA9_21", 1, ll3[i] - 0.1 * a, tp_r=2.0)
        if E["e9"][i] < E["e21"][i] and r14[i] < 50 and H[i] >= E["e9"][i] > C[i]:
            mk("EMA9_21", -1, hh3[i] + 0.1 * a, tp_r=2.0)
        # ADX ribbon
        if bull[i] and not bull[i - 1]:
            mk("ADX_RIB", 1, C[i] - 2 * a, tp=None, xl=X["ADX_RIB"][0], xs=X["ADX_RIB"][1])
        if bear[i] and not bear[i - 1]:
            mk("ADX_RIB", -1, C[i] + 2 * a, tp=None, xl=X["ADX_RIB"][0], xs=X["ADX_RIB"][1])
    # RAND: 3 a day in the same hours
    for dt in np.unique(dates):
        idx = np.where((dates == dt) & sess)[0]
        idx = idx[(idx > 250) & (idx < n - 2)]
        if len(idx) < 10:
            continue
        for i in rng.choice(idx, 3, replace=False):
            dr = 1 if rng.random() < 0.5 else -1
            if np.isfinite(A[i]):
                S["RAND"].append(dict(k0=i + 1, kind="mkt", dir=dr, sl=C[i] - dr * A[i], tp_r=1.0, exp=i + 1, maxb=10 ** 6))
    return S


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    rows, info = [], {}
    for sym in SYMS:
        f = os.path.join(DATA, sym + ".csv")
        if sym not in meta or not os.path.exists(f):
            continue
        d = SA.load(f, meta[sym]["point"])
        dates = d.index.normalize().values
        flat = ((d.index.hour * 60 + d.index.minute) >= 1380) | np.r_[True, dates[1:] != dates[:-1]]
        info[sym] = dict(days=len(np.unique(dates)), mid=d.index[len(d) // 2], end=d.index[-1],
                         usd=meta[sym]["tick_value"] / meta[sym]["tick_size"] * 0.01 if meta[sym]["tick_size"] > 0 else 0.0)
        S = build(d, sym)
        arr = [d[x].values for x in ("o", "h", "l", "c", "s")]
        for rule, sig in S.items():
            sig = sorted(sig, key=lambda g: g["k0"])
            if rule == "MOMO":                        # the two halves run as two independent position streams
                parts = [[g for g in sig if not g.get("half")], [g for g in sig if g.get("half")]]
            else:
                parts = [sig]
            for p in parts:
                for (k, dr, pnl, s_, risk, why) in SA.sim(*arr, p, flat):
                    rows.append((sym, rule, d.index[k], pnl, s_, risk))
        say(f"  {sym:7s} done, {time.time() - T0:5.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "rule", "t", "pnl", "sp", "risk"])
    T["R"] = (T.pnl - T.sp) / T.risk
    T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = (T.pnl - T.sp) * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [t >= info[s]["mid"] for s, t in zip(T.sym, T.t)]
    T["l12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    pf, f2 = SA.pf, SA.f2
    say("\n== All 12 instruments together (R units after spread) ==")
    say("rule        trades /sym/day  win%    PF  half1 half2 stress  syms PF>1  pass")
    passes = []
    for rule in RULES:
        g = T[T.rule == rule]
        if g.empty:
            say(f"{rule:10s} no trades"); continue
        npass = 0
        for s, x in g.groupby("sym"):
            P, P1, P2, PS = pf(x.R.values), pf(x[~x.half].R.values), pf(x[x.half].R.values), pf(x.Rs.values)
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and x[x.l12].R.sum() > 0
            if ok:
                npass += 1
                passes.append(f"{rule:9s} {s:7s} {len(x):6d} trades ({len(x) / info[s]['days']:.2f}/day) PF {f2(P)} halves {f2(P1)} {f2(P2)} "
                              f"stress {f2(PS)} net ${x.usd.sum():+.0f} per 0.01 lot")
        days = np.mean([info[s]["days"] for s in g.sym.unique()])
        npos = sum(1 for s, x in g.groupby("sym") if pf(x.R.values) > 1)
        say(f"{rule:10s} {len(g):7d} {len(g) / days / g.sym.nunique():7.2f} {100 * (g.R > 0).mean():5.1f} {f2(pf(g.R.values))} "
            f"{f2(pf(g[~g.half].R.values))} {f2(pf(g[g.half].R.values))} {f2(pf(g.Rs.values))} {npos:3d}/{g.sym.nunique():2d}  {npass:3d}")
    say("\n== Per instrument PF (R after spread) ==")
    say("sym     " + " ".join(f"{r[:8]:>8s}" for r in RULES))
    for s in SYMS:
        if s in info:
            say(f"{s:7s} " + " ".join(f"{f2(pf(T[(T.sym == s) & (T.rule == r)].R.values)):>8s}" for r in RULES))
    say("\n== Gold (XAUUSD) per rule: trades a day, net $ per 0.01 lot ==")
    for r in RULES:
        x = T[(T.sym == "XAUUSD") & (T.rule == r)]
        if len(x):
            say(f"  {r:10s} {len(x) / info['XAUUSD']['days']:5.2f}/day  PF {f2(pf(x.R.values))}  net ${x.usd.sum():+8.0f}")
    say("\n== Passed (instrument x rule) ==")
    for p in passes:
        say("  " + p)
    nr = sum(1 for p in passes if p.startswith("RAND"))
    say(f"  {len(passes) - nr} rule passes of {(len(RULES) - 1) * len(info)}; RAND passed on {nr} of {len(info)} instruments")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
