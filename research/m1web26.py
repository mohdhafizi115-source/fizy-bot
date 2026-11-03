"""Round 26 (4 Nov 2026): gold M1 scalping systems as taught on the web, on the broker's M1 history.

The owner: "kau cari dekat luar sana ramai yang scalping gold m1 ... cari sampai jumpa". Rules taken from public
pages (parameters the page leaves open are fixed here before the run and named as assumptions):
  FXO_VWAP_MACD  FXOpen "VWAP + MACD": close crosses the session VWAP and MACD (12, 26, 9) crosses its signal the same
                 way within 5 bars; SL beyond the 10-bar swing; exit on the opposite MACD cross
  FXO_KC_RSI     FXOpen "Keltner + RSI": 2 closes in a row outside Keltner (EMA 20 +- 2 ATR 10) with same-colour
                 candles and RSI (14) on the same side of 50; SL at the opposite band; exit on a close back over the
                 midline or RSI beyond 70 / 30
  FXO_ALMA_STO   FXOpen "ALMA + Stochastic": close crosses ALMA (21, 0.85, 6) while Stochastic (21, 1, 3) crosses up
                 through 20 (down through 80) within 3 bars; SL beyond the 10-bar swing; exit when Stochastic reaches
                 the other zone
  FXO_RSI4_BB    FXOpen "RSI + Bollinger": RSI (4) crosses back above 20 (below 80) after a touch of the Bollinger
                 (20, 2) band in the last 3 bars; SL below the 5-bar swing; TP the opposite band, or exit at RSI 80/20
  TV_ENGULF      TradingView "Gold Scalping Strategy with Precise Entries": EMA 50 above EMA 200, RSI (14) 45-55,
                 bullish engulfing, close above EMA 50 (sell mirrored); TP $2 (20 pips); SL 1.5 ATR (assumption:
                 the page gives no multiplier)
  PSAR_MACD      TradingView "PSAR MACD 200 EMA" (DaviddTech): close on the EMA 200 side, PSAR flips that way, MACD and
                 signal both below 0 (above 0 for sells) and MACD crosses the signal within 3 bars; SL beyond the
                 10-bar swing; TP 1.5R (assumption)
  ORB_FVG_NY     "1 Minute Scalping Strategy That Actually Works" (Casper SMC): range of the first 5 minutes after
                 09:30 New York; on M1 a fair value gap leaving the range (one candle closes beyond it); wait for a
                 pullback into the gap, then an engulfing candle; enter at the next open, SL beyond the deepest candle
                 in the gap, TP 3R; one trade a day, setups until 12:00 New York
  ORB_FVG_LDN    the same from 08:00 London
  RAND           random entries, SL 1.5 ATR, TP 1.5R (chance)
Signals 09:00-21:00 server unless the rule sets its own window, flat 22:30, at most 60 bars per trade (ORB: 120).
Costs: bar spread (median $0.19), stress 1.5x, 0.01 lot. Usual pass rule, PF 0.10 above RAND; last month shown.
"""
import os, sys, time
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import ind23 as R

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
SRV, LON, NYC = ZoneInfo("Europe/Athens"), ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
RULES = ["FXO_VWAP_MACD", "FXO_KC_RSI", "FXO_ALMA_STO", "FXO_RSI4_BB", "TV_ENGULF", "PSAR_MACD", "ORB_FVG_NY", "ORB_FVG_LDN", "RAND"]


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().values


def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    return 100 - 100 / (1 + R.wilder(np.clip(d, 0, None), n) / np.maximum(R.wilder(np.clip(-d, 0, None), n), 1e-12))


def recent(mask, n):
    """mask true at any of the last n bars (incl. this one)"""
    return pd.Series(mask.astype(float)).rolling(n, min_periods=1).max().values > 0


def orb_fvg(B, A, tz, hh, mm, end_h):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    idx = B.index
    out = []
    for day in pd.DatetimeIndex(idx.normalize().unique()):
        t = pd.Timestamp(day.year, day.month, day.day, hh, mm, tzinfo=tz)
        k = idx.searchsorted(t.tz_convert(SRV).tz_localize(None))
        stop = idx.searchsorted((pd.Timestamp(day.year, day.month, day.day, end_h, 0, tzinfo=tz)).tz_convert(SRV).tz_localize(None))
        if k + 8 >= len(idx) or idx[k] != t.tz_convert(SRV).tz_localize(None) or (idx[k + 4] - idx[k]).seconds != 240:
            continue
        H_, L_ = h[k:k + 5].max(), l[k:k + 5].min()
        dr, top, bot, j0 = 0, 0, 0, 0
        for j in range(k + 7, min(stop, len(idx) - 2)):
            if l[j] > h[j - 2] and max(c[j - 2], c[j - 1], c[j]) > H_:
                dr, bot, top, j0 = 1, h[j - 2], l[j], j; break
            if h[j] < l[j - 2] and min(c[j - 2], c[j - 1], c[j]) < L_:
                dr, top, bot, j0 = -1, l[j - 2], h[j], j; break
        if dr == 0:
            continue
        touched, ext = False, None
        for m in range(j0 + 1, min(stop, len(idx) - 2)):
            if (dr == 1 and c[m] < bot) or (dr == -1 and c[m] > top):
                break                                              # gap failed
            if not touched:
                if (dr == 1 and l[m] <= top) or (dr == -1 and h[m] >= bot):
                    touched, ext = True, (l[m] if dr == 1 else h[m])
                continue
            ext = min(ext, l[m]) if dr == 1 else max(ext, h[m])
            pb, pt = min(o[m - 1], c[m - 1]), max(o[m - 1], c[m - 1])
            eng = (c[m] > o[m] and c[m] >= pt and o[m] <= pb) if dr == 1 else (c[m] < o[m] and c[m] <= pb and o[m] >= pt)
            if eng:
                out.append(dict(k0=m + 1, kind="mkt", dir=dr, sl=ext - dr * 0.01, tp_r=3.0, exp=m + 1, maxb=120))
                break
    return out


def build(B):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    I = R.ind(B)
    A = I["atr"]
    hm = B.hm.values
    ok = (hm >= 540) & (hm < 1260) & np.isfinite(A) & np.isfinite(I["e200"]) & (np.arange(n) >= 300)
    ok[-2:] = False
    S = {r: [] for r in RULES}

    def add(rule, i, dr, sl, **kw):
        if (sl - c[i]) * dr >= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=60)
        g.update(kw)
        S[rule].append(g)

    cu = R.cross_up
    lo10 = np.r_[np.nan, pd.Series(l).rolling(10).min().values[:-1]]
    hi10 = np.r_[np.nan, pd.Series(h).rolling(10).max().values[:-1]]
    lo5 = pd.Series(l).rolling(5).min().values
    hi5 = pd.Series(h).rolling(5).max().values
    # VWAP per server day, tick volume
    vol = B["v"].values if "v" in B else np.ones(n)
    day = B.date.values
    tp = (h + l + c) / 3
    g = pd.DataFrame({"d": day, "pv": tp * vol, "v": vol})
    vwap = (g.groupby("d").pv.cumsum() / g.groupby("d").v.cumsum().replace(0, np.nan)).values
    mu, md = cu(I["macd"], I["sig"]), cu(I["sig"], I["macd"])
    vu, vd = cu(c, vwap), cu(vwap, c)
    for i in np.where(ok & ((vu & recent(mu, 5)) | (mu & recent(vu, 5))))[0]:
        add("FXO_VWAP_MACD", i, 1, lo10[i], xl=md, xs=mu)
    for i in np.where(ok & ((vd & recent(md, 5)) | (md & recent(vd, 5))))[0]:
        add("FXO_VWAP_MACD", i, -1, hi10[i], xl=md, xs=mu)
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    a10 = R.wilder(tr, 10)
    km = ema(c, 20)
    ku, kd = km + 2 * a10, km - 2 * a10
    r14 = I["rsi"]
    out_u = (c > ku) & (c > o); out_d = (c < kd) & (c < o)
    two_u = out_u & np.r_[False, out_u[:-1]] & ~np.r_[False, False, out_u[:-2]]
    two_d = out_d & np.r_[False, out_d[:-1]] & ~np.r_[False, False, out_d[:-2]]
    kxl, kxs = (c < km) | (r14 > 70), (c > km) | (r14 < 30)
    for i in np.where(ok & two_u & (r14 > 50))[0]:
        add("FXO_KC_RSI", i, 1, kd[i], xl=kxl, xs=kxs)
    for i in np.where(ok & two_d & (r14 < 50))[0]:
        add("FXO_KC_RSI", i, -1, ku[i], xl=kxl, xs=kxs)
    w = np.exp(-((np.arange(21) - 0.85 * 20) ** 2) / (2 * (21 / 6) ** 2)); w /= w.sum()
    alma = np.r_[np.full(20, np.nan), np.convolve(c, w[::-1], mode="valid")]
    hh21, ll21 = pd.Series(h).rolling(21).max().values, pd.Series(l).rolling(21).min().values
    st = pd.Series(100 * (c - ll21) / np.maximum(hh21 - ll21, 1e-12)).rolling(3).mean().values
    au, ad = cu(c, alma), cu(alma, c)
    su, sd = cu(st, np.full(n, 20.0)), cu(np.full(n, 80.0), st)
    sxl, sxs = st > 80, st < 20
    for i in np.where(ok & ((au & recent(su, 3)) | (su & recent(au, 3))))[0]:
        add("FXO_ALMA_STO", i, 1, lo10[i], xl=sxl, xs=sxs)
    for i in np.where(ok & ((ad & recent(sd, 3)) | (sd & recent(ad, 3))))[0]:
        add("FXO_ALMA_STO", i, -1, hi10[i], xl=sxl, xs=sxs)
    r4 = rsi(c, 4)
    tl, tu = recent(l <= I["bbl"], 3), recent(h >= I["bbu"], 3)
    bxl, bxs = r4 > 80, r4 < 20
    for i in np.where(ok & cu(r4, np.full(n, 20.0)) & tl)[0]:
        add("FXO_RSI4_BB", i, 1, lo5[i] - 0.1 * A[i], tp=I["bbu"][i], xl=bxl, xs=bxs)
    for i in np.where(ok & cu(np.full(n, 80.0), r4) & tu)[0]:
        add("FXO_RSI4_BB", i, -1, hi5[i] + 0.1 * A[i], tp=I["bbl"][i], xl=bxl, xs=bxs)
    o1 = np.r_[o[0], o[:-1]]
    beng = (c > o) & (c1 < o1) & (c >= o1) & (o <= c1)
    seng = (c < o) & (c1 > o1) & (c <= o1) & (o >= c1)
    mid_r = (r14 >= 45) & (r14 <= 55)
    for i in np.where(ok & (I["e50"] > I["e200"]) & mid_r & beng & (c > I["e50"]))[0]:
        add("TV_ENGULF", i, 1, c[i] - 1.5 * A[i], tp=c[i] + 2.0)
    for i in np.where(ok & (I["e50"] < I["e200"]) & mid_r & seng & (c < I["e50"]))[0]:
        add("TV_ENGULF", i, -1, c[i] + 1.5 * A[i], tp=c[i] - 2.0)
    ps = I["psar"]; ps1 = np.r_[ps[0], ps[:-1]]
    pu, pdn = (ps == 1) & (ps1 == -1), (ps == -1) & (ps1 == 1)
    neg = (I["macd"] < 0) & (I["sig"] < 0); pos = (I["macd"] > 0) & (I["sig"] > 0)
    for i in np.where(ok & (c > I["e200"]) & ((pu & recent(mu & neg, 3)) | (mu & neg & recent(pu, 3))))[0]:
        add("PSAR_MACD", i, 1, lo10[i], tp_r=1.5)
    for i in np.where(ok & (c < I["e200"]) & ((pdn & recent(md & pos, 3)) | (md & pos & recent(pdn, 3))))[0]:
        add("PSAR_MACD", i, -1, hi10[i], tp_r=1.5)
    S["ORB_FVG_NY"] = orb_fvg(B, A, NYC, 9, 30, 12)
    S["ORB_FVG_LDN"] = orb_fvg(B, A, LON, 8, 0, 11)
    rg = np.random.default_rng(26)
    for i in np.where(ok & (rg.random(n) < 1 / 30))[0]:
        dr = 1 if rg.random() < 0.5 else -1
        add("RAND", i, dr, c[i] - dr * 1.5 * A[i], tp_r=1.5)
    return S


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    B["v"] = d.v.reindex(B.index).fillna(1.0).values
    dates = B.date.values
    flat = (B.hm.values >= 1350) | np.r_[True, dates[1:] != dates[:-1]] | np.r_[dates[1:] != dates[:-1], True]
    print(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {len(B):,} bars", flush=True)
    S = build(B)
    print(f"signals in {time.time() - T0:.0f} s: " + ", ".join(f"{k} {len(v)}" for k, v in S.items()), flush=True)
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    mid, end, days = B.index[len(B) // 2], B.index[-1], B.index.normalize().nunique()
    t1 = end - pd.Timedelta(days=31)
    pf = SA.pf
    res = {}
    for rule in RULES:
        T = pd.DataFrame(SA.sim(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat), columns=["k", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.k.values]; T["net"] = (T.pnl - T.sp) * usd; T["st"] = (T.pnl - 1.5 * T.sp) * usd; T["raw"] = T.pnl * usd
        res[rule] = T
    PR = pf(res["RAND"].net.values)
    print("\nrule           trades /day  win%   PF  half1 half2 stress last12$    net$ rawPF | last month: trades   PF   net$  | by year")
    for rule, T in res.items():
        if T.empty:
            print(f"{rule:14s} no trades"); continue
        P, P1, P2, PS = pf(T.net.values), pf(T[T.t < mid].net.values), pf(T[T.t >= mid].net.values), pf(T.st.values)
        l12 = T[T.t >= end - pd.Timedelta(days=365)].net.sum()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P - PR >= 0.10
        M = T[T.t >= t1]
        yr = " ".join(f"{y % 100}:{SA.f2(pf(T[T.t.dt.year == y].net.values)).strip()}" for y in sorted(T.t.dt.year.unique()))
        print(f"{rule:14s} {len(T):6d} {len(T) / days:5.1f} {100 * (T.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} {SA.f2(P2)} {SA.f2(PS)} "
              f"{l12:+7.0f} {T.net.sum():+8.0f} {SA.f2(pf(T.raw.values))} | {len(M):6d} {SA.f2(pf(M.net.values))} {M.net.sum():+7.0f}  | {yr} "
              f"{'PASS' if ok and rule != 'RAND' else ''}")
    print(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
