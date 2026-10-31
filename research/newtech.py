"""New techniques (never tested before here), rules fixed in advance, on long Yahoo data (runs in GitHub):
28 forex pairs (=X), gold (GC=F) and BTC (BTC-USD). Daily data from 2004 (BTC from 2014), H1 data 2 years.
Costs: one spread per trade = 1 pip forex, $0.30 gold, 0.05% BTC. Swap NOT included (matters for multi-day holds).
Results in R (1R = the initial stop distance) so instruments can be added up.
  A  NR7 breakout (Toby Crabel), D1: today's range is the narrowest of the last 7 days -> next day OCO stop
     orders at today's high / low; SL at the other side; exit at the next day's close (A1) or after 3 days (A3).
  B  Double 7s (Larry Connors), D1: close above SMA 200 and the lowest close of 7 days -> buy next open; exit
     when the close is the highest of 7 days. Sell mirrored. Safety SL 3 x ATR14 (= 1R).
  C  RSI(2) daily (Connors' original timeframe): close > SMA 200 and RSI(2) < 10 -> buy next open; exit on a
     close above SMA 5; sell mirrored; SL 3 x ATR14.
  D  Ichimoku D1: Tenkan crosses Kijun, close on the same side of the cloud, Chikou above / below the close 26
     days ago -> next open; exit on the opposite Tenkan / Kijun cross; SL 2 x ATR14.
  E  Monday gap fade, H1: the first H1 open of the week is more than 0.15 x ATR14(D1) away from Friday's last
     close -> fade it at that open; TP = Friday's close; SL = one more gap beyond the open; exit 12:00 UTC.
  F  Cross-sectional currency momentum, weekly: each Friday rank the 8 currencies by their 12-week strength
     (average return against the other 7); buy the strongest / sell the weakest through their pair for one
     week (1 pip cost). Reported as % return per week on the pair, yearly."""
import os, sys, time, traceback
import numpy as np, pandas as pd, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
CCY = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]
FX = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD", "EURGBP", "EURJPY", "EURCHF", "EURAUD",
      "EURCAD", "EURNZD", "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD", "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
      "NZDJPY", "NZDCHF", "NZDCAD", "CADJPY", "CADCHF", "CHFJPY"]
ALL = FX + ["XAUUSD", "BTCUSD"]
out = []


def say(s=""):
    print(s, flush=True); out.append(s)


def ysym(n):
    return "GC=F" if n == "XAUUSD" else ("BTC-USD" if n == "BTCUSD" else n + "=X")


def yahoo(n, interval):
    if interval == "1d":
        p = {"interval": "1d", "period1": 1072915200, "period2": int(time.time())}
    else:
        p = {"interval": "60m", "range": "730d"}
    for k in range(3):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym(n)}", params=p, headers=UA, timeout=60)
            res = r.json()["chart"]["result"][0]
            break
        except Exception:
            time.sleep(3)
    else:
        raise RuntimeError("download failed")
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")}, index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
    df = df[(df.high >= df.low) & (df.close > 0)]
    if interval != "1d":
        df.index = df.index.floor("1h")
        df = df.groupby(level=0).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    return df


def cost(n, price):
    return 0.30 if n == "XAUUSD" else (price * 0.0005 if n == "BTCUSD" else (0.01 if "JPY" in n else 0.0001))


def atr(d, k=14):
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - d.close.shift()), abs(d.low - d.close.shift())))
    return tr.rolling(k).mean()


def run(d, sig, n, exl=None, exs=None):
    """sig: {i: dict(type market|stop, dir, price, sl, tp, exp, maxb)} placed at the close of bar i.
    Fills from bar i+1; exits at SL / TP inside a bar (path O-L-H-C / O-H-L-C, gaps fill at the open),
    at the open after exl / exs (exit flags at a close), or after maxb bars. Returns a list of (time, R)."""
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    res, pend, pos = [], None, None
    for k in range(1, len(d)):
        if pos is not None:
            dr = pos["dir"]
            if (pos["maxb"] and k - pos["k"] >= pos["maxb"]) or (dr == 1 and exl is not None and exl[k - 1]) or (dr == -1 and exs is not None and exs[k - 1]):
                res.append((d.index[k], ((o[k] - pos["e"]) * dr - pos["cost"]) / pos["risk"])); pos = None
        if pos is None and pend is None and (k - 1) in sig:
            pend = sig[k - 1]
        if pend is not None and k > pend["exp"]:
            pend = None
        path = [o[k], l[k], h[k], c[k]] if c[k] >= o[k] else [o[k], h[k], l[k], c[k]]
        for a, b in zip(path[:-1], path[1:]):
            lo, hi = min(a, b), max(a, b)
            if pos is None and pend is not None:
                dr, P = pend["dir"], pend["price"]
                fill = a if pend["type"] == "market" else (max(P, a) if dr == 1 and hi >= P else (min(P, a) if dr == -1 and lo <= P else None))
                if fill is None:
                    continue
                risk = abs(fill - pend["sl"])
                if risk <= 0:
                    pend = None; continue
                pos = dict(k=k, dir=dr, e=fill, sl=pend["sl"], tp=pend.get("tp"), maxb=pend.get("maxb"), risk=risk, cost=cost(n, fill))
                pend = None
                lo, hi = min(fill, b), max(fill, b)
            if pos is not None:
                dr, sl, tp = pos["dir"], pos["sl"], pos["tp"]
                ex = None
                if (dr == 1 and lo <= sl) or (dr == -1 and hi >= sl):
                    ex = sl if (a - sl) * dr > 0 else a                # gapped through the stop: out at that price
                elif tp is not None and ((dr == 1 and hi >= tp) or (dr == -1 and lo <= tp)):
                    ex = tp
                if ex is not None:
                    res.append((d.index[k], ((ex - pos["e"]) * dr - pos["cost"]) / pos["risk"])); pos = None
                    break
    return res


def rsi2(c):
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def strat_daily(d, n, kind):
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    A = atr(d).values; cs = d.close
    s200, s5 = cs.rolling(200).mean().values, cs.rolling(5).mean().values
    sig, exl, exs = {}, None, None
    N = len(d)
    if kind in ("A1", "A3"):
        rng = d.high - d.low
        nr7 = (rng == rng.rolling(7).min()).values
        for i in range(20, N - 1):
            if nr7[i] and h[i] > l[i]:
                hold = 1 if kind == "A1" else 3
                # OCO: two orders; the first that fills wins (one order dict per side, pick by fill below)
                sig[i] = dict(type="stop", dir=1, price=h[i], sl=l[i], exp=i + 1, maxb=hold, oco=dict(type="stop", dir=-1, price=l[i], sl=h[i], exp=i + 1, maxb=hold))
        return sig, None, None
    if kind == "B":
        lo7, hi7 = cs.rolling(7).min().values, cs.rolling(7).max().values
        exl, exs = c >= hi7, c <= lo7
        for i in range(210, N - 1):
            if np.isnan(s200[i]) or np.isnan(A[i]):
                continue
            if c[i] > s200[i] and c[i] <= lo7[i]:
                sig[i] = dict(type="market", dir=1, price=None, sl=c[i] - 3 * A[i], exp=i + 1, maxb=None)
            elif c[i] < s200[i] and c[i] >= hi7[i]:
                sig[i] = dict(type="market", dir=-1, price=None, sl=c[i] + 3 * A[i], exp=i + 1, maxb=None)
    elif kind == "C":
        r = rsi2(cs).values
        exl, exs = c > s5, c < s5
        for i in range(210, N - 1):
            if np.isnan(s200[i]) or np.isnan(A[i]):
                continue
            if c[i] > s200[i] and r[i] < 10:
                sig[i] = dict(type="market", dir=1, price=None, sl=c[i] - 3 * A[i], exp=i + 1, maxb=None)
            elif c[i] < s200[i] and r[i] > 90:
                sig[i] = dict(type="market", dir=-1, price=None, sl=c[i] + 3 * A[i], exp=i + 1, maxb=None)
    elif kind == "D":
        ten = ((d.high.rolling(9).max() + d.low.rolling(9).min()) / 2).values
        kij = ((d.high.rolling(26).max() + d.low.rolling(26).min()) / 2).values
        sa = ((pd.Series(ten) + pd.Series(kij)) / 2).shift(26).values
        sb = ((d.high.rolling(52).max() + d.low.rolling(52).min()) / 2).shift(26).values
        up_x = np.r_[False, (ten[1:] > kij[1:]) & (ten[:-1] <= kij[:-1])]
        dn_x = np.r_[False, (ten[1:] < kij[1:]) & (ten[:-1] >= kij[:-1])]
        exl, exs = dn_x, up_x
        for i in range(80, N - 1):
            if np.isnan(sa[i]) or np.isnan(sb[i]) or np.isnan(A[i]):
                continue
            top, bot = max(sa[i], sb[i]), min(sa[i], sb[i])
            if up_x[i] and c[i] > top and c[i] > c[i - 26]:
                sig[i] = dict(type="market", dir=1, price=None, sl=c[i] - 2 * A[i], exp=i + 1, maxb=None)
            elif dn_x[i] and c[i] < bot and c[i] < c[i - 26]:
                sig[i] = dict(type="market", dir=-1, price=None, sl=c[i] + 2 * A[i], exp=i + 1, maxb=None)
    return sig, exl, exs


def run_oco(d, sig, n):
    """NR7: split into the two sides; take whichever fills first on the next day (if both could, the side
    the bar path reaches first)."""
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    res = []
    for i, s in sig.items():
        b, sl_side = s, s["oco"]
        k = i + 1
        if k >= len(d):
            continue
        path = [o[k], l[k], h[k], c[k]] if c[k] >= o[k] else [o[k], h[k], l[k], c[k]]
        first = None
        for a_, b_ in zip(path[:-1], path[1:]):
            lo, hi = min(a_, b_), max(a_, b_)
            if hi >= b["price"]:
                first = b; break
            if lo <= sl_side["price"]:
                first = sl_side; break
        if first is None:
            continue
        sub = d.iloc[i:i + first["maxb"] + 3]                 # the signal bar + a few days is enough
        r = run(sub, {0: dict(first, exp=1)}, n)
        res += r[:1]
    return res


def summary(name, rows):
    if not rows:
        say(f"  {name}: no trades"); return
    df = pd.DataFrame(rows, columns=["inst", "t", "R"])
    x = df.R.values
    pf = x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else 99
    df["half"] = np.where(df.t < pd.Timestamp("2015-07-01", tz="UTC"), 1, 2)
    ph = {}
    for hh, g in df.groupby("half"):
        y = g.R.values; ph[hh] = (y[y > 0].sum() / -y[y < 0].sum() if (y < 0).any() else 99, y.sum())
    per = df.groupby("inst").R.sum()
    cls = {"FX": df[df.inst.isin(FX)], "gold": df[df.inst == "XAUUSD"], "BTC": df[df.inst == "BTCUSD"]}
    cl = ", ".join(f"{k} {len(g)}t {g.R.sum():+.0f}R" for k, g in cls.items() if len(g))
    last3 = df[df.t >= pd.Timestamp("2023-11-01", tz="UTC")].R
    say(f"  {name}: {len(df)} trades, win {np.mean(x > 0) * 100:.0f}%, PF {pf:.2f}, total {x.sum():+.0f}R (avg {x.mean():+.3f}R) | "
        f"2004-2015 PF {ph.get(1, (0, 0))[0]:.2f} {ph.get(1, (0, 0))[1]:+.0f}R | 2015-2026 PF {ph.get(2, (0, 0))[0]:.2f} {ph.get(2, (0, 0))[1]:+.0f}R | "
        f"last 3 years {last3.sum():+.0f}R | instruments positive {np.mean(per > 0) * 100:.0f}% | {cl}")


try:
    daily = {}
    for n in ALL:
        try:
            daily[n] = yahoo(n, "1d")
        except Exception as e:
            say(f"{n}: daily data error {e}")
    say(f"Daily data: {len(daily)} instruments, e.g. EURUSD {daily['EURUSD'].index[0]:%Y-%m-%d}..{daily['EURUSD'].index[-1]:%Y-%m-%d}, "
        f"BTC from {daily['BTCUSD'].index[0]:%Y-%m-%d}" if "BTCUSD" in daily and "EURUSD" in daily else "")
    for kind, name in (("A1", "A1 NR7 breakout, exit next close"), ("A3", "A3 NR7 breakout, exit after 3 days"),
                       ("B", "B Connors Double 7s (SL 3 ATR)"), ("C", "C RSI(2) daily + SMA 200 (SL 3 ATR)"),
                       ("D", "D Ichimoku D1 Tenkan/Kijun cross with cloud + Chikou (SL 2 ATR)")):
        rows = []
        for n, d in daily.items():
            try:
                sig, exl, exs = strat_daily(d, n, kind)
                r = run_oco(d, sig, n) if kind.startswith("A") else run(d, sig, n, exl, exs)
                rows += [(n, t, R) for t, R in r]
            except Exception:
                say(f"  {name} {n}: error {traceback.format_exc()[-200:]}")
        summary(name, rows)
    # E. Monday gap fade on H1 (2 years)
    rows = []
    for n in ALL:
        if n == "BTCUSD":
            continue                                   # BTC trades at weekends: no Monday gap
        try:
            h1 = yahoo(n, "1h")
        except Exception as e:
            say(f"  E {n}: H1 data error {e}"); continue
        dd = daily.get(n)
        A = atr(dd).shift() if dd is not None else None
        idx = h1.index
        gaps = np.where((idx[1:] - idx[:-1]) > pd.Timedelta(hours=24))[0] + 1    # first bar after the weekend
        for g in gaps:
            fri_close, mon = h1.close.iloc[g - 1], h1.iloc[g]
            gap = mon.open - fri_close
            a = A.asof(idx[g].normalize()) if A is not None else np.nan
            if np.isnan(a) or abs(gap) < 0.15 * a:
                continue
            dr = -1 if gap > 0 else 1
            sl = mon.open - dr * abs(gap)
            tp = fri_close
            end = idx[g].normalize() + pd.Timedelta(hours=12) + (pd.Timedelta(days=1) if idx[g].hour >= 12 else pd.Timedelta(0))
            seg = h1[(h1.index >= idx[g]) & (h1.index < end)]
            if len(seg) < 2:
                continue
            # run() fills from bar 1: put Friday's last bar in front as bar 0
            pre = h1.iloc[[g - 1]]
            sub2 = pd.concat([pre, seg])
            sub2.iloc[0, sub2.columns.get_loc("close")] = mon.open
            r = run(sub2, {0: dict(type="market", dir=dr, price=None, sl=sl, tp=tp, exp=1, maxb=len(seg) - 1)}, n)
            if not r:
                last = seg.close.iloc[-1]
                r = [(seg.index[-1], ((last - mon.open) * dr - cost(n, mon.open)) / abs(gap))]
            rows += [(n, t, R) for t, R in r[:1]]
    say("")
    say("E Monday gap fade (H1, 2 years; halves split at 2015 do not apply, see 'last 3 years'):")
    summary("E Monday gap fade, TP Friday close", rows)
    # F. cross-sectional currency momentum (weekly)
    closes = pd.DataFrame({n: daily[n].close for n in FX if n in daily}).resample("W-FRI").last().dropna(how="all")
    rets = np.log(closes).diff()
    strength = pd.DataFrame(0.0, index=closes.index, columns=CCY)
    cnt = pd.DataFrame(0, index=closes.index, columns=CCY)
    lb = np.log(closes).diff(12)
    for p in closes.columns:
        b, q = p[:3], p[3:]
        strength[b] = strength[b].add(lb[p].fillna(0)); strength[q] = strength[q].sub(lb[p].fillna(0))
        cnt[b] += lb[p].notna(); cnt[q] += lb[p].notna()
    strength = strength / cnt.replace(0, np.nan)
    wk = []
    for i in range(13, len(closes) - 1):
        s = strength.iloc[i].dropna()
        if len(s) < 8:
            continue
        top, bot = s.idxmax(), s.idxmin()
        pair, dr = (top + bot, 1) if top + bot in closes.columns else ((bot + top, -1) if bot + top in closes.columns else (None, 0))
        if pair is None:
            continue
        nxt = rets[pair].iloc[i + 1]
        if np.isnan(nxt):
            continue
        c0 = closes[pair].iloc[i]
        wk.append((closes.index[i + 1], dr * nxt - cost(pair, c0) / c0))
    w = pd.Series([x for _, x in wk], index=[t for t, _ in wk])
    say("")
    say(f"F Currency momentum (12-week strength, strongest vs weakest, weekly): {len(w)} weeks, mean {w.mean() * 100:+.3f}% a week, "
        f"win {np.mean(w > 0) * 100:.0f}%, Sharpe {w.mean() / w.std() * np.sqrt(52):.2f}")
    say("   by year: " + ", ".join(f"{y} {g.sum() * 100:+.1f}%" for y, g in w.groupby(w.index.year)))
except Exception:
    say(traceback.format_exc())
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("New techniques round 4 (long data)\n" + "\n".join(out) + "\n")
