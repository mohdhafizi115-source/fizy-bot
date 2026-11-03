"""Round 23 (3 Nov 2026): classic INDICATOR systems (no range breakouts) on M15, H1 and H4, 12 instruments, with swap.

The owner wants no more breakout techniques ("aku tak nak ... breakout ... kau cari teknik lain guna indikator").
Rules fixed before the run; signal at a bar close, entry at the next open; buy shown, sell mirrored:
  MACD     MACD (12, 26, 9) crosses its signal on the EMA 200 side; exit on the opposite cross; SL 2 ATR
  EMA_X    EMA 20 crosses EMA 50; exit on the opposite cross; SL 2 ATR
  STREND   Supertrend (10, 3) turns up; exit when it turns down; SL 3 ATR
  PSAR     Parabolic SAR (0.02, 0.2) flips below price on the EMA 200 side; exit on the next flip; SL 3 ATR
  ADX_DI   ADX (14) > 25 and +DI crosses above -DI; exit when -DI crosses back above; SL 2 ATR
  RSI_REV  RSI (14) crosses back above 30 on the EMA 200 side; SL 1.5 ATR, TP 2R
  RSI_MOM  RSI (14) crosses above 50 on the EMA 200 side; exit when RSI < 40; SL 2 ATR
  STOCH    Stochastic (14, 3, 3) %K crosses %D below 20 on the EMA 200 side; SL 1.5 ATR, TP 2R
  BB_MR    close back inside the lower Bollinger band (20, 2) while ADX < 20; TP the middle band, SL 1.5 ATR
  CCI      CCI (20) crosses back above -100 on the EMA 200 side; SL 1.5 ATR, TP 2R
  HA       Heikin Ashi turns bullish with no lower wick, on the EMA 50 side; exit on the next bearish HA candle; SL 2 ATR
  WPR      Williams %R (14) crosses up through -80 on the EMA 200 side; SL 1.5 ATR, TP 2R
  TK       Ichimoku Tenkan crosses above Kijun with the close above the cloud; exit on the opposite cross; SL 2 ATR
  AROON    Aroon (25) up crosses above down with up >= 70; exit on the opposite cross; SL 2 ATR
  KUMO     re-check of the LIVE gold H1 Kumo module with the broker's real swap (-71 / -84 points a night per lot):
           H1 close breaks out of the cloud with Tenkan above Kijun; SL max 0.2 ATR beyond the cloud / 0.5 ATR;
           exit on a close back inside the cloud or after the bar limit (it is a cloud breakout, shown for the check only)
  RAND     random entries (about one a day), random side, SL 1.5 ATR, TP 2R (chance baseline)
Modes: M15d / H1d = day trades (signals 01:30-21:00 server, flat 23:00, no swap); H1s / H4s = swing (signals outside
the 23:00-01:30 rollover, at most 48 H1 / 30 H4 bars, closed before the weekend, broker swap counted, triple on the
broker's 3-day swap weekday). Costs: the bar's spread (stress 1.5x). Fixed 0.01 lot, so PF and net are in dollars.
Pass rule per instrument and mode: >= 150 trades, PF >= 1.15, halves >= 1.05, stress >= 1.05, last 12 months positive,
PF 0.10 above RAND. With 14 rules x 12 instruments x 4 modes, a few passes are expected by chance: a real edge should
show up on several instruments or modes of the same rule.
"""
import os, sys, time, csv
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
from goldh1_detail import sim2

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP", "BTCUSD"]
RULES = ["MACD", "EMA_X", "STREND", "PSAR", "ADX_DI", "RSI_REV", "RSI_MOM", "STOCH", "BB_MR", "CCI", "HA", "WPR", "TK", "AROON", "KUMO", "RAND"]
MODES = {"M15d": ("15min", False, 64), "H1d": ("1h", False, 24), "H1s": ("1h", True, 48), "H4s": ("4h", True, 30)}
SWAPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swaps23.csv")
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def wilder(x, n):
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().values


def ind(B):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    C = pd.Series(c)
    I = {}
    ema = lambda x, s: pd.Series(x).ewm(span=s, adjust=False).mean().values
    I["e20"], I["e50"], I["e200"] = ema(c, 20), ema(c, 50), ema(c, 200)
    macd = ema(c, 12) - ema(c, 26)
    I["macd"], I["sig"] = macd, ema(macd, 9)
    c1 = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
    atr14 = wilder(tr, 14)
    I["atr"] = np.r_[np.nan, atr14[:-1]]
    # Supertrend (10, 3)
    a10 = wilder(tr, 10)
    hl2 = (h + l) / 2
    ub, lb = hl2 + 3 * a10, hl2 - 3 * a10
    fu, fl, st = ub.copy(), lb.copy(), np.ones(n)
    for i in range(1, n):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        st[i] = 1 if c[i] > fu[i - 1] else (-1 if c[i] < fl[i - 1] else st[i - 1])
    I["st"] = st
    # Parabolic SAR (0.02, 0.2): trend direction after bar i
    ps = np.ones(n)
    up, sar, ep, af = True, l[0], h[0], 0.02
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar:
                up, sar, ep, af = False, ep, l[i], 0.02
            elif h[i] > ep:
                ep, af = h[i], min(af + 0.02, 0.2)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar:
                up, sar, ep, af = True, ep, h[i], 0.02
            elif l[i] < ep:
                ep, af = l[i], min(af + 0.02, 0.2)
        ps[i] = 1 if up else -1
    I["psar"] = ps
    # ADX / DI (14)
    um, dm = h - np.r_[h[0], h[:-1]], np.r_[l[0], l[:-1]] - l
    pdm = np.where((um > dm) & (um > 0), um, 0.0)
    mdm = np.where((dm > um) & (dm > 0), dm, 0.0)
    pdi = 100 * wilder(pdm, 14) / np.maximum(atr14, 1e-12)
    mdi = 100 * wilder(mdm, 14) / np.maximum(atr14, 1e-12)
    dx = 100 * np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-12)
    I["pdi"], I["mdi"], I["adx"] = pdi, mdi, wilder(dx, 14)
    d_ = np.diff(c, prepend=c[0])
    I["rsi"] = 100 - 100 / (1 + wilder(np.clip(d_, 0, None), 14) / np.maximum(wilder(np.clip(-d_, 0, None), 14), 1e-12))
    hh14, ll14 = pd.Series(h).rolling(14).max().values, pd.Series(l).rolling(14).min().values
    k = 100 * (c - ll14) / np.maximum(hh14 - ll14, 1e-12)
    I["k"] = pd.Series(k).rolling(3).mean().values
    I["d"] = pd.Series(I["k"]).rolling(3).mean().values
    I["wpr"] = -100 * (hh14 - c) / np.maximum(hh14 - ll14, 1e-12)
    m20, s20 = C.rolling(20).mean().values, C.rolling(20).std(ddof=0).values
    I["bbm"], I["bbl"], I["bbu"] = m20, m20 - 2 * s20, m20 + 2 * s20
    tp = (h + l + c) / 3
    smt = pd.Series(tp).rolling(20).mean().values
    md = pd.Series(tp).rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True).values
    I["cci"] = (tp - smt) / np.maximum(0.015 * md, 1e-12)
    hc = (o + h + l + c) / 4
    ho = np.r_[o[0], pd.Series(hc).ewm(alpha=0.5, adjust=False).mean().values[:-1]]
    ho[0] = (o[0] + c[0]) / 2
    for i in range(1, min(n, 3)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    hlow, hhigh = np.minimum(l, np.minimum(ho, hc)), np.maximum(h, np.maximum(ho, hc))
    I["ha_bull"] = (hc > ho) & (np.abs(np.minimum(ho, hc) - hlow) < 1e-12)     # bullish, no lower wick
    I["ha_bear"] = (hc < ho) & (np.abs(hhigh - np.maximum(ho, hc)) < 1e-12)    # bearish, no upper wick
    I["ha_col"] = np.sign(hc - ho)
    mid = lambda m: (pd.Series(h).rolling(m).max().values + pd.Series(l).rolling(m).min().values) / 2
    ten, kij = mid(9), mid(26)
    sa, sb = np.r_[np.full(26, np.nan), ((ten + kij) / 2)[:-26]], np.r_[np.full(26, np.nan), mid(52)[:-26]]
    I["ten"], I["kij"], I["ctop"], I["cbot"] = ten, kij, np.fmax(sa, sb), np.fmin(sa, sb)
    since_h = pd.Series(h).rolling(26).apply(lambda x: 25 - np.argmax(x), raw=True).values
    since_l = pd.Series(l).rolling(26).apply(lambda x: 25 - np.argmin(x), raw=True).values
    I["aru"], I["ard"] = 100 * (25 - since_h) / 25, 100 * (25 - since_l) / 25
    return I


def cross_up(a, b):
    return (a > b) & np.r_[False, (a <= b)[:-1]]


def signals(B, I, swing, maxb, seed):
    o, h, l, c = (B[x].values for x in ("o", "h", "l", "c"))
    n = len(c)
    hm = B.hm.values
    A = I["atr"]
    if swing:
        okt = (hm >= 90) & (hm < 1380)
    else:
        okt = (hm >= 90) & (hm < 1260)
    ok = okt & np.isfinite(A) & np.isfinite(I["e200"]) & (np.arange(n) >= 220)
    ok[-2:] = False
    up200, dn200 = c > I["e200"], c < I["e200"]
    S = {r: [] for r in RULES}

    def add(rule, i, dr, sl, **kw):
        if (sl - c[i]) * dr >= 0:
            return
        g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=maxb)
        g.update(kw)
        S[rule].append(g)

    def both(rule, bu, bd, slm, **kw):
        for i in np.where(ok & bu)[0]:
            add(rule, i, 1, c[i] - slm * A[i], **kw)
        for i in np.where(ok & bd)[0]:
            add(rule, i, -1, c[i] + slm * A[i], **kw)

    mu, md_ = cross_up(I["macd"], I["sig"]), cross_up(I["sig"], I["macd"])
    both("MACD", mu & up200, md_ & dn200, 2, xl=md_, xs=mu)
    eu, ed = cross_up(I["e20"], I["e50"]), cross_up(I["e50"], I["e20"])
    both("EMA_X", eu, ed, 2, xl=ed, xs=eu)
    st = I["st"]; st1 = np.r_[st[0], st[:-1]]
    su, sd = (st == 1) & (st1 == -1), (st == -1) & (st1 == 1)
    both("STREND", su, sd, 3, xl=sd, xs=su)
    ps = I["psar"]; ps1 = np.r_[ps[0], ps[:-1]]
    pu, pd_ = (ps == 1) & (ps1 == -1), (ps == -1) & (ps1 == 1)
    both("PSAR", pu & up200, pd_ & dn200, 3, xl=pd_, xs=pu)
    du, dd = cross_up(I["pdi"], I["mdi"]), cross_up(I["mdi"], I["pdi"])
    both("ADX_DI", du & (I["adx"] > 25), dd & (I["adx"] > 25), 2, xl=dd, xs=du)
    r = I["rsi"]
    both("RSI_REV", cross_up(r, np.full(n, 30.0)) & up200, cross_up(np.full(n, 70.0), r) & dn200, 1.5, tp_r=2.0)
    both("RSI_MOM", cross_up(r, np.full(n, 50.0)) & up200, cross_up(np.full(n, 50.0), r) & dn200, 2, xl=r < 40, xs=r > 60)
    K, D = I["k"], I["d"]; K1 = np.r_[np.nan, K[:-1]]
    both("STOCH", cross_up(K, D) & (K1 < 20) & up200, cross_up(D, K) & (K1 > 80) & dn200, 1.5, tp_r=2.0)
    c1 = np.r_[c[0], c[:-1]]
    bl1, bu1 = np.r_[np.nan, I["bbl"][:-1]], np.r_[np.nan, I["bbu"][:-1]]
    rng_ = I["adx"] < 20
    for i in np.where(ok & (c1 < bl1) & (c > I["bbl"]) & rng_)[0]:
        add("BB_MR", i, 1, min(l[i], c[i]) - 1.5 * A[i], tp=I["bbm"][i])
    for i in np.where(ok & (c1 > bu1) & (c < I["bbu"]) & rng_)[0]:
        add("BB_MR", i, -1, max(h[i], c[i]) + 1.5 * A[i], tp=I["bbm"][i])
    cc = I["cci"]
    both("CCI", cross_up(cc, np.full(n, -100.0)) & up200, cross_up(np.full(n, 100.0), cc) & dn200, 1.5, tp_r=2.0)
    col = I["ha_col"]; col1 = np.r_[0, col[:-1]]
    both("HA", I["ha_bull"] & (col1 < 0) & (c > I["e50"]), I["ha_bear"] & (col1 > 0) & (c < I["e50"]), 2,
         xl=col < 0, xs=col > 0)
    w = I["wpr"]
    both("WPR", cross_up(w, np.full(n, -80.0)) & up200, cross_up(np.full(n, -20.0), w) & dn200, 1.5, tp_r=2.0)
    tu, td = cross_up(I["ten"], I["kij"]), cross_up(I["kij"], I["ten"])
    both("TK", tu & (c > I["ctop"]), td & (c < I["cbot"]), 2, xl=td, xs=tu)
    au, ad = cross_up(I["aru"], I["ard"]), cross_up(I["ard"], I["aru"])
    both("AROON", au & (I["aru"] >= 70), ad & (I["ard"] >= 70), 2, xl=ad, xs=au)
    top, bot = I["ctop"], I["cbot"]
    top1, bot1 = np.r_[np.nan, top[:-1]], np.r_[np.nan, bot[:-1]]
    kok = ok & (hm <= 1319)
    for i in np.where(kok & (c > top) & (c1 <= top1) & (I["ten"] > I["kij"]))[0]:
        add("KUMO", i, 1, min(bot[i] - 0.2 * A[i], c[i] - 0.5 * A[i]), xl=c < top, xs=c > bot)
    for i in np.where(kok & (c < bot) & (c1 >= bot1) & (I["ten"] < I["kij"]))[0]:
        add("KUMO", i, -1, max(top[i] + 0.2 * A[i], c[i] + 0.5 * A[i]), xl=c < top, xs=c > bot)
    rg = np.random.default_rng(seed)
    bars_day = max(1, int(round(86400 / max(pd.Series(B.index).diff().dt.total_seconds().median(), 1))))
    for i in np.where(ok & (rg.random(n) < 1 / bars_day))[0]:
        dr = 1 if rg.random() < 0.5 else -1
        add("RAND", i, dr, c[i] - dr * 1.5 * A[i], tp_r=2.0)
    return S


def load_swaps():
    sw = {}
    if os.path.exists(SWAPS):
        for r in csv.DictReader(open(SWAPS)):
            sw[r["base"]] = dict(mode=int(r["swap_mode"]), long=float(r["swap_long"]), short=float(r["swap_short"]), d3=int(r["swap_3day"]))
    return sw


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    SW = load_swaps()
    say(f"swap specs for {len(SW)} symbols (points per lot per night, current broker values used for all years)")
    rows = []
    info = {}
    for si, sym in enumerate(SYMS):
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")):
            say(f"{sym}: no data"); continue
        mt = meta[sym]
        usd = mt["tick_value"] / mt["tick_size"] * 0.01 if mt["tick_size"] > 0 else 0.0
        d5 = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
        sw = SW.get(sym)
        for mode, (rule_tf, swing, maxb) in MODES.items():
            B = DT.bars(d5, rule_tf)
            dates = B.date.values
            last = np.r_[dates[1:] != dates[:-1], True]
            if swing:
                gap = np.r_[(pd.Series(B.date).diff().dt.days.values[1:] > 1), True]   # last bar before a weekend / holiday gap
                flat = gap.copy()
            else:
                flat = (B.hm.values >= 1380) | np.r_[True, dates[1:] != dates[:-1]] | last
            I = ind(B)
            S = signals(B, I, swing, maxb, seed=7 + si)
            arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
            for rule in RULES:
                for (k, dr, pnl, sp, risk, why, kx) in sim2(*arr, sorted(S[rule], key=lambda g: g["k0"]), flat):
                    swap = 0.0
                    if swing and kx > k and sw and sw["mode"] == 1:
                        d0, d1 = B.date.values[k], B.date.values[min(kx, len(B) - 1)]
                        if d1 <= d0:
                            cnt = 0
                        elif 1 <= sw["d3"] <= 5:                                  # weekday triple swap (forex, gold)
                            nights = pd.bdate_range(pd.Timestamp(d0), pd.Timestamp(d1) - pd.Timedelta(days=1))
                            cnt = sum(3 if x.weekday() == sw["d3"] - 1 else 1 for x in nights)
                        else:                                                       # every calendar night (crypto)
                            cnt = int((pd.Timestamp(d1) - pd.Timestamp(d0)).days)
                        swap = (sw["long"] if dr == 1 else sw["short"]) * mt["point"] * cnt * usd
                    rows.append((sym, mode, rule, B.index[k], (pnl - sp) * usd + swap, (pnl - 1.5 * sp) * usd + swap, swap))
            info[(sym, mode)] = dict(mid=B.index[len(B) // 2], end=B.index[-1], days=B.index.normalize().nunique())
        say(f"  {sym} done, {time.time() - T0:.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "mode", "rule", "t", "net", "st", "swap"])
    pf = SA.pf
    say("\nPF$ after spread (and swap in H1s / H4s) per rule and mode, median over the 12 instruments [instruments with PF > 1]:")
    say("rule      " + "".join(f"{m:>16s}" for m in MODES))
    for rule in RULES:
        cells = []
        for mode in MODES:
            v = [pf(T[(T.sym == s) & (T["mode"] == mode) & (T.rule == rule)].net.values) for s in SYMS if (s, mode) in info]
            v = [x for x in v if np.isfinite(x)]
            cells.append(f"{np.median(v):8.2f} [{sum(x > 1 for x in v):2d}/{len(v)}]" if v else "      -")
        say(f"{rule:9s} " + "".join(f"{x:>16s}" for x in cells))
    say("\nPasses (>= 150 trades, PF >= 1.15, halves >= 1.05, stress >= 1.05, last 12 months > 0, PF 0.10 above RAND):")
    say("sym     mode rule     trades /day  win%   PF  half1 half2 stress last12$   net$  swap$  RAND  by year")
    npass = 0
    G = T.groupby(["sym", "mode", "rule"])
    for (sym, mode, rule), x in G:
        if rule in ("RAND",) or (rule == "KUMO" and not (sym == "XAUUSD" and mode == "H1s")):
            continue
        inf_ = info[(sym, mode)]
        P = pf(x.net.values)
        if len(x) < 150 or P < 1.15:
            continue
        P1, P2, PS = pf(x[x.t < inf_["mid"]].net.values), pf(x[x.t >= inf_["mid"]].net.values), pf(x.st.values)
        l12 = x[x.t >= inf_["end"] - pd.Timedelta(days=365)].net.sum()
        rnd = T[(T.sym == sym) & (T["mode"] == mode) & (T.rule == "RAND")]
        PR = pf(rnd.net.values)
        ok = P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P - PR >= 0.10
        yr = " ".join(f"{y % 100}:{SA.f2(pf(x[x.t.dt.year == y].net.values)).strip()}" for y in sorted(x.t.dt.year.unique()))
        say(f"{sym:7s} {mode:4s} {rule:8s} {len(x):6d} {len(x) / inf_['days']:4.2f} {100 * (x.net > 0).mean():5.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {x.net.sum():+6.0f} {x.swap.sum():+6.0f} {SA.f2(PR)}  {yr} {'PASS' if ok else '(fails: ' + ', '.join(n_ for n_, b in (('half1', P1 >= 1.05), ('half2', P2 >= 1.05), ('stress', PS >= 1.05), ('last12', l12 > 0), ('vsRAND', P - PR >= 0.10)) if not b) + ')'}")
        npass += ok
    for mode in ("H1s", "H1d"):
        x = T[(T.sym == "XAUUSD") & (T["mode"] == mode) & (T.rule == "KUMO")]
        if len(x):
            inf_ = info[("XAUUSD", mode)]
            say(f"LIVE KUMO re-check, XAUUSD {mode} with the broker swap: {len(x)} trades, PF {SA.f2(pf(x.net.values)).strip()}, "
                f"halves {SA.f2(pf(x[x.t < inf_['mid']].net.values)).strip()} / {SA.f2(pf(x[x.t >= inf_['mid']].net.values)).strip()}, "
                f"net ${x.net.sum():+.0f}, swap ${x.swap.sum():+.0f}, last 12 months ${x[x.t >= inf_['end'] - pd.Timedelta(days=365)].net.sum():+.0f}")
    tests = (len(RULES) - 2) * len(info)
    say(f"\n{npass} passes out of {tests} rule / instrument / mode tests")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
