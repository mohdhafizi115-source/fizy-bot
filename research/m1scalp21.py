"""Round 21 (3 Nov 2026): gold M1 scalping on the broker's own M1 history (JustMarkets, 2020 onwards).

The owner asked for a gold M1 scalping EA ("buatkan aku ea scalping gold m1"). M1 was only tested before on 3 months
of a manual export (every rule lost, PF 0.73-0.95). This is the long test, rules fixed before the run (server time,
signal at an M1 close, entry at the next M1 open unless stated; ATR = Wilder ATR(14) on M1 up to the previous bar):
  EMA_X     EMA 9 crosses EMA 21 on the side of the EMA 200; SL 1.5 ATR, TP 1.5R
  BB_RSI    close outside Bollinger (20, 2) with RSI(7) < 20 / > 80: fade; TP at the middle band, SL 1.5 ATR
  STOCH     Stochastic (5, 3, 3) %K crosses %D below 20 / above 80, on the side of the EMA 50; SL 1.5 ATR, TP 1R
  RSI2      close above EMA 200 and RSI(2) < 10: buy (sell mirrored); exit on a close back over the SMA 5 or after 24 bars,
            SL 2 ATR (the old M5 scalp, on M1)
  DON_BO    close beyond the 20-bar high / low on the side of the EMA 200; SL 1.5 ATR, TP 1.5R
  PULL50    trend (close and EMA 50 above EMA 200): a bullish candle whose low touches the EMA 50 and closes above it
            (sell mirrored); SL 0.2 ATR beyond the candle, TP 1.5R
  OPEN_BO   London 08:00 and New York 09:30 (local time, converted per day): OCO stops 0.05 ATR beyond the range of the
            15 M1 bars before the open, SL at the other side, TP 1.5R, orders live 30 min, exit after 60 min
  SPK_FADE  an M1 bar with range >= 3 ATR: fade it; SL 0.2 ATR beyond its extreme, TP half the bar back
  SPK_FOLW  the same bar: follow it; SL at its middle, TP 1R
  RAND      random entries (about one per 30 minutes), random side, SL 1.5 ATR, TP 1.5R (chance baseline)
Signals 09:00-21:00 server (London and New York; no rollover), everything flat at 22:30 or the day's last bar, at most
60 bars per trade unless stated, one trade at a time per rule. Costs: the bar's spread from the export (stress 1.5x).
Fixed 0.01 lot, so PF and net are in dollars.
Pass rule: >= 150 trades, PF >= 1.15, halves >= 1.05, stress >= 1.05, last 12 months positive, PF 0.10 above RAND.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYM = "XAUUSD"
T0 = time.time()
RULES = ["EMA_X", "BB_RSI", "STOCH", "RSI2", "DON_BO", "PULL50", "OPEN_BO", "SPK_FADE", "SPK_FOLW", "RAND"]
SRV, LON, NYC = ZoneInfo("Europe/Athens"), ZoneInfo("Europe/London"), ZoneInfo("America/New_York")


def say(s=""):
    print(s, flush=True)


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    dn = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + up / np.maximum(dn, 1e-12))


def features(d):
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    C = pd.Series(c)
    F = {}
    for n in (9, 21, 50, 200):
        F[f"e{n}"] = C.ewm(span=n, adjust=False).mean().values
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    F["atr"] = np.r_[np.nan, pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values[:-1]]
    F["rsi7"], F["rsi2"] = rsi(c, 7), rsi(c, 2)
    m20, s20 = C.rolling(20).mean().values, C.rolling(20).std(ddof=0).values
    F["bbm"], F["bbu"], F["bbl"] = m20, m20 + 2 * s20, m20 - 2 * s20
    hh, ll = pd.Series(h).rolling(5).max().values, pd.Series(l).rolling(5).min().values
    k = 100 * (c - ll) / np.maximum(hh - ll, 1e-12)
    F["k"] = pd.Series(k).rolling(3).mean().values
    F["dd"] = pd.Series(F["k"]).rolling(3).mean().values
    F["hi20"] = np.r_[np.nan, pd.Series(h).rolling(20).max().values[:-1]]
    F["lo20"] = np.r_[np.nan, pd.Series(l).rolling(20).min().values[:-1]]
    F["sma5"] = C.rolling(5).mean().values
    return F


def opens(d):
    """bar index of each London 08:00 / New York 09:30 open, in server time"""
    days = pd.DatetimeIndex(d.index.normalize().unique())
    idx = d.index
    out = []
    for day in days:
        for tz, hh, mm in ((LON, 8, 0), (NYC, 9, 30)):
            t = pd.Timestamp(day.year, day.month, day.day, hh, mm, tzinfo=tz).tz_convert(SRV).tz_localize(None)
            k = idx.searchsorted(t)
            if k < len(idx) and idx[k] == t and k >= 15:
                out.append(k)
    return out


def signals(d, F, seed=21):
    o, h, l, c = (d[x].values for x in ("o", "h", "l", "c"))
    A = F["atr"]
    n = len(c)
    hm = d.index.hour.values * 60 + d.index.minute.values
    ok = (hm >= 540) & (hm < 1260) & np.isfinite(A) & np.isfinite(F["e200"]) & (np.arange(n) >= 300)
    ok[-2:] = False
    S = {r: [] for r in RULES}
    e9, e21, e50, e200 = F["e9"], F["e21"], F["e50"], F["e200"]

    def mk(rule, i, dr, sl, **kw):
        if (sl - c[i]) * dr >= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=kw.pop("maxb", 60))
        g.update(kw)
        S[rule].append(g)

    up_x = (e9 > e21) & (np.r_[False, e9[:-1] <= e21[:-1]])
    dn_x = (e9 < e21) & (np.r_[False, e9[:-1] >= e21[:-1]])
    for i in np.where(ok & up_x & (c > e200))[0]:
        mk("EMA_X", i, 1, c[i] - 1.5 * A[i], tp_r=1.5)
    for i in np.where(ok & dn_x & (c < e200))[0]:
        mk("EMA_X", i, -1, c[i] + 1.5 * A[i], tp_r=1.5)
    for i in np.where(ok & (c < F["bbl"]) & (F["rsi7"] < 20))[0]:
        mk("BB_RSI", i, 1, c[i] - 1.5 * A[i], tp=F["bbm"][i], maxb=30)
    for i in np.where(ok & (c > F["bbu"]) & (F["rsi7"] > 80))[0]:
        mk("BB_RSI", i, -1, c[i] + 1.5 * A[i], tp=F["bbm"][i], maxb=30)
    K, D = F["k"], F["dd"]
    kx_up = (K > D) & np.r_[False, K[:-1] <= D[:-1]]
    kx_dn = (K < D) & np.r_[False, K[:-1] >= D[:-1]]
    for i in np.where(ok & kx_up & (np.r_[np.nan, K[:-1]] < 20) & (c > e50))[0]:
        mk("STOCH", i, 1, c[i] - 1.5 * A[i], tp_r=1.0, maxb=30)
    for i in np.where(ok & kx_dn & (np.r_[np.nan, K[:-1]] > 80) & (c < e50))[0]:
        mk("STOCH", i, -1, c[i] + 1.5 * A[i], tp_r=1.0, maxb=30)
    xl, xs = c > F["sma5"], c < F["sma5"]
    for i in np.where(ok & (c > e200) & (F["rsi2"] < 10))[0]:
        mk("RSI2", i, 1, c[i] - 2 * A[i], xl=xl, xs=xs, maxb=24)
    for i in np.where(ok & (c < e200) & (F["rsi2"] > 90))[0]:
        mk("RSI2", i, -1, c[i] + 2 * A[i], xl=xl, xs=xs, maxb=24)
    for i in np.where(ok & (c > F["hi20"]) & (c > e200))[0]:
        mk("DON_BO", i, 1, c[i] - 1.5 * A[i], tp_r=1.5)
    for i in np.where(ok & (c < F["lo20"]) & (c < e200))[0]:
        mk("DON_BO", i, -1, c[i] + 1.5 * A[i], tp_r=1.5)
    for i in np.where(ok & (c > e200) & (e50 > e200) & (l <= e50) & (c > e50) & (c > o))[0]:
        mk("PULL50", i, 1, l[i] - 0.2 * A[i], tp_r=1.5)
    for i in np.where(ok & (c < e200) & (e50 < e200) & (h >= e50) & (c < e50) & (c < o))[0]:
        mk("PULL50", i, -1, h[i] + 0.2 * A[i], tp_r=1.5)
    for k in opens(d):
        if not np.isfinite(A[k]):
            continue
        H_, L_ = h[k - 15:k].max(), l[k - 15:k].min()
        if not (L_ < o[k] < H_):
            continue
        bf = 0.05 * A[k]
        S["OPEN_BO"].append(dict(k0=k, kind="oco", dir=0, P=H_ + bf, sl=L_, P2=L_ - bf, sl2=H_, tp_r=1.5, exp=k + 29, maxb=60))
    rg = h - l
    spk = ok & (rg >= 3 * A)
    for i in np.where(spk)[0]:
        dr = 1 if c[i] > o[i] else -1
        if c[i] == o[i]:
            continue
        mk("SPK_FADE", i, -dr, (h[i] + 0.2 * A[i]) if dr == 1 else (l[i] - 0.2 * A[i]), tp=c[i] - dr * 0.5 * rg[i], maxb=15)
        mk("SPK_FOLW", i, dr, (h[i] + l[i]) / 2, tp_r=1.0, maxb=15)
    r = np.random.default_rng(seed)
    for i in np.where(ok & (r.random(n) < 1 / 30))[0]:
        dr = 1 if r.random() < 0.5 else -1
        mk("RAND", i, dr, c[i] - dr * 1.5 * A[i], tp_r=1.5)
    return S


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    say(open(os.path.join(DATA, "meta.txt"), encoding="latin-1").readline().strip())
    m = meta[SYM]
    usd = m["tick_value"] / m["tick_size"] * 0.01 if m["tick_size"] > 0 else 1.0
    d = SA.load(os.path.join(DATA, SYM + ".csv"), m["point"])
    step = pd.Series(d.index).diff().dt.total_seconds().median()
    dates = d.index.normalize().values
    hm = d.index.hour.values * 60 + d.index.minute.values
    flat = (hm >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    days = pd.Index(dates).nunique()
    say(f"{SYM}: {len(d):,} bars of {step / 60:.0f} min, {d.index[0]:%Y-%m-%d} .. {d.index[-1]:%Y-%m-%d %H:%M} server, {days} days; "
        f"median spread ${np.median(d.s.values) * usd:.2f} at 0.01 lot (09:00-21:00: ${np.median(d.s.values[(hm >= 540) & (hm < 1260)]) * usd:.2f})")
    if step > 90:
        say("WARNING: this is not M1 data")
    F = features(d)
    S = signals(d, F)
    say(f"signals built in {time.time() - T0:.0f} s")
    arr = [d[x].values for x in ("o", "h", "l", "c", "s")]
    end, mid = d.index[-1], d.index[len(d) // 2]
    rows = []
    for rule in RULES:
        for (k, dr, pnl, sp, risk, why) in SA.sim(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat):
            rows.append((rule, k, dr, pnl, sp, risk, why))
        say(f"  {rule}: {len(S[rule])} signals, {time.time() - T0:.0f} s")
    T = pd.DataFrame(rows, columns=["rule", "k", "dir", "pnl", "sp", "risk", "why"])
    T["t"] = d.index[T.k.values]
    T["net"] = (T.pnl - T.sp) * usd
    T["st"] = (T.pnl - 1.5 * T.sp) * usd
    T["year"] = T.t.dt.year
    pf = SA.pf
    rand_pf = pf(T[T.rule == "RAND"].net.values)
    say("\nrule      trades /day  win%   PF$  half1 half2 stress  last12$   net$  $/trade  avg risk$  by year (PF$)")
    passes = []
    for rule in RULES:
        x = T[T.rule == rule]
        if x.empty:
            say(f"{rule:9s} no trades"); continue
        P, P1, P2, PS = pf(x.net.values), pf(x[x.t < mid].net.values), pf(x[x.t >= mid].net.values), pf(x.st.values)
        l12 = x[x.t >= end - pd.Timedelta(days=365)].net.sum()
        yr = " ".join(f"{y % 100}:{SA.f2(pf(x[x.year == y].net.values)).strip()}" for y in sorted(x.year.unique()))
        okp = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and (rule == "RAND" or P - rand_pf >= 0.10)
        say(f"{rule:9s} {len(x):6d} {len(x) / days:5.2f} {100 * (x.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
            f"{l12:+8.0f} {x.net.sum():+7.0f} {x.net.mean():+7.3f} {x.risk.mean() * usd:9.2f}  {yr} {'PASS' if okp and rule != 'RAND' else ''}")
        if okp and rule != "RAND":
            passes.append(rule)
    say("\nWithout costs (PF$ before spread), to see whether there is any raw edge:")
    say("  " + "  ".join(f"{r} {SA.f2(pf((T[T.rule == r].pnl * usd).values)).strip()}" for r in RULES))
    say(f"\nPASSED: {', '.join(passes) if passes else 'none'}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
