"""Candidate systematic strategies on XAUUSD (rules fixed in advance, then tested Jan-May vs Jun-Oct)."""
import numpy as np, pandas as pd
from bt import load, resample, atr, swap_cost, report, Pos


def run_bars(m, signals, manage):
    """Generic M15 execution. signals: dict time -> list of order dicts
    {type: 'stop'|'market', dir, price, sl, tp, expire, oco, be_at, close_at, tag}
    manage(pos, bar_time) may return 'close' (exit at bar open)."""
    trades, pend, pos = [], [], None
    t_index = m.index; o, h, l, c, sp = (m[x].values for x in ("open", "high", "low", "close", "spread"))
    for n, t in enumerate(t_index):
        if pos is not None:
            act = manage(pos, t, n)
            if act == "close":
                px = o[n]; pnl = (px - pos.entry) * pos.dr - swap_cost(pos.t, t, pos.dr)
                trades.append(dict(open=pos.t, close=t, dir=pos.dr, pnl=pnl, R=pnl / pos.risk, tag=pos.tag, res="time"))
                pos = None
        if t in signals and pos is None:
            pend = [dict(x) for x in signals[t]]
        path = [o[n], l[n], h[n], c[n]] if c[n] >= o[n] else [o[n], h[n], l[n], c[n]]
        for a, b in zip(path[:-1], path[1:]):
            lo, hi = min(a, b), max(a, b)
            if pos is None and pend:
                pend = [p for p in pend if p.get("expire") is None or t < p["expire"]]
                for p in pend:
                    hit = False
                    if p["type"] == "market":
                        hit = True; px = o[n] + (sp[n] if p["dir"] == 1 else 0)
                    elif p["dir"] == 1 and hi + sp[n] >= p["price"]:
                        hit = True; px = max(p["price"], a + sp[n]) if a + sp[n] > p["price"] else p["price"]
                    elif p["dir"] == -1 and lo <= p["price"]:
                        hit = True; px = min(p["price"], a) if a < p["price"] else p["price"]
                    if hit:
                        risk = abs(px - p["sl"])
                        pos = Pos(t, p["dir"], px, p["sl"], p["tp"], risk, p.get("tag", ""))
                        pos.be_at = p.get("be_at"); pos.close_at = p.get("close_at"); pos.trail = p.get("trail")
                        pos.be_off = p.get("be_off", 0.10)   # breakeven offset in price (0.10 = $0.10 gold)
                        pend = []
                        break
            if pos is not None:
                dr = pos.dr
                bid_lo, bid_hi = lo, hi
                ask_lo, ask_hi = lo + sp[n], hi + sp[n]
                if dr == 1:
                    ex = pos.sl if bid_lo <= pos.sl else (pos.tp if pos.tp and bid_hi >= pos.tp else None)
                else:
                    ex = pos.sl if ask_hi >= pos.sl else (pos.tp if pos.tp and ask_lo <= pos.tp else None)
                if ex is not None:
                    res = "SL" if ex == pos.sl else "TP"
                    pnl = (ex - pos.entry) * dr - swap_cost(pos.t, t, dr)
                    trades.append(dict(open=pos.t, close=t, dir=dr, pnl=pnl, R=pnl / pos.risk, tag=pos.tag,
                                       res="BE" if (res == "SL" and pos.be_done) else res))
                    pos = None
                    break
                if pos.be_at and not pos.be_done:
                    reach = (bid_hi >= pos.entry + pos.be_at * pos.risk) if dr == 1 else (ask_lo <= pos.entry - pos.be_at * pos.risk)
                    if reach:
                        pos.sl = pos.entry + dr * pos.be_off; pos.be_done = True
    return pd.DataFrame(trades)


def first_bar(m, t):
    i = m.index.searchsorted(t)
    return m.index[i] if i < len(m.index) else None


def new_bar_checker(m, d, tf):
    """returns f(t) -> index (in d) of the last closed tf bar when t is the first M15 bar of a new tf bar"""
    starts = set()
    prev_bin = None
    for t in m.index:
        b = t.floor(tf) if tf != "1D" else t.normalize()
        if b != prev_bin:
            starts.add(t)
        prev_bin = b
    pos = {t: i for i, t in enumerate(d.index)}

    def f(t):
        if t not in starts:
            return None
        b = t.floor(tf) if tf != "1D" else t.normalize()
        i = pos.get(b)
        return None if i is None or i == 0 else i - 1
    return f


# ---------------------------------------------------------------- A. London breakout (Asian range)
def london_breakout(m, r0=3, r1=8, tp_r=2.5, be_r=1.5, close_h=21, fmin=0.30, fmax=1.60, cap=0.6, buf=0.10):
    sig = {}
    for day, g in m.groupby(m.index.normalize()):
        rg = g[(g.index.hour >= r0) & (g.index.hour < r1)]
        if len(rg) < (r1 - r0) * 4 - 2:
            continue
        hi, lo = rg.high.max(), rg.low.min()
        mid = (hi + lo) / 2; width = (hi - lo) / mid * 100
        if width < fmin or width > fmax:
            continue
        t = day + pd.Timedelta(hours=r1)
        if t not in m.index:
            continue
        exp = day + pd.Timedelta(hours=close_h)
        capd = mid * cap / 100
        sl_b = max(lo, hi + buf - capd); sl_s = min(hi, lo - buf + capd)
        rb = hi + buf - sl_b; rs = sl_s - (lo - buf)
        sig[t] = [dict(type="stop", dir=1, price=hi + buf, sl=sl_b, tp=hi + buf + tp_r * rb, expire=exp, be_at=be_r, close_at=exp, tag="LB"),
                  dict(type="stop", dir=-1, price=lo - buf, sl=sl_s, tp=lo - buf - tp_r * rs, expire=exp, be_at=be_r, close_at=exp, tag="LB")]

    def manage(pos, t, n):
        return "close" if pos.close_at is not None and t >= pos.close_at else None
    return run_bars(m, sig, manage)


# ---------------------------------------------------------------- B. H4 Donchian trend following (Turtle style)
def donchian(m, tf="4h", n_in=20, n_out=10, atr_mult=2.0):
    d = resample(m, tf)
    up = d.high.rolling(n_in).max().shift(); dn = d.low.rolling(n_in).min().shift()
    ex_up = d.high.rolling(n_out).max().shift(); ex_dn = d.low.rolling(n_out).min().shift()
    a = atr(d).shift()
    sig = {}
    period = pd.Timedelta(tf)
    # signal on close beyond channel, enter at next bar open (market)
    for i in range(len(d) - 1):
        t = d.index[i]
        if np.isnan(up.iloc[i]) or np.isnan(a.iloc[i]):
            continue
        if d.close.iloc[i] > up.iloc[i]:
            nt = first_bar(m, d.index[i + 1])
            if nt is not None:
                sig[nt] = [dict(type="market", dir=1, price=None, sl=d.close.iloc[i] - atr_mult * a.iloc[i], tp=None, tag="DC")]
        elif d.close.iloc[i] < dn.iloc[i]:
            nt = first_bar(m, d.index[i + 1])
            if nt is not None:
                sig[nt] = [dict(type="market", dir=-1, price=None, sl=d.close.iloc[i] + atr_mult * a.iloc[i], tp=None, tag="DC")]
    nb = new_bar_checker(m, d, tf)

    def manage(pos, t, n):
        # exit at the open of a new tf bar when the last closed tf bar closed beyond the exit channel
        i = nb(t)
        if i is None:
            return None
        cl = d.close.iloc[i]
        if pos.dr == 1 and cl < ex_dn.iloc[i]:
            return "close"
        if pos.dr == -1 and cl > ex_up.iloc[i]:
            return "close"
        return None
    return run_bars(m, sig, manage)


# ---------------------------------------------------------------- C. RSI(2) pullback in the trend (Connors style)
def rsi2(m, tf="1h", ma=200, lo_th=10, hi_th=90, atr_sl=2.0):
    d = resample(m, tf)
    delta = d.close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)
    sma = d.close.rolling(ma).mean(); sma5 = d.close.rolling(5).mean(); a = atr(d)
    sig = {}; period = pd.Timedelta(tf)
    for i in range(len(d) - 1):
        if np.isnan(sma.iloc[i]) or np.isnan(a.iloc[i]):
            continue
        nt = first_bar(m, d.index[i + 1])
        if nt is None:
            continue
        if d.close.iloc[i] > sma.iloc[i] and rsi.iloc[i] < lo_th:
            sig[nt] = [dict(type="market", dir=1, price=None, sl=d.close.iloc[i] - atr_sl * a.iloc[i], tp=None, tag="RSI2")]
        elif d.close.iloc[i] < sma.iloc[i] and rsi.iloc[i] > hi_th:
            sig[nt] = [dict(type="market", dir=-1, price=None, sl=d.close.iloc[i] + atr_sl * a.iloc[i], tp=None, tag="RSI2")]
    nb = new_bar_checker(m, d, tf)

    def manage(pos, t, n):   # exit when close crosses the 5-period SMA
        i = nb(t)
        if i is None:
            return None
        if pos.dr == 1 and d.close.iloc[i] > sma5.iloc[i]:
            return "close"
        if pos.dr == -1 and d.close.iloc[i] < sma5.iloc[i]:
            return "close"
        return None
    return run_bars(m, sig, manage)


if __name__ == "__main__":
    m = load()
    res = {}
    res["A London breakout (blog rules)"] = london_breakout(m)
    res["B H4 Donchian 20/10, 2ATR stop"] = donchian(m)
    res["B2 D1 Donchian 20/10, 2ATR stop"] = donchian(m, tf="1D")
    res["C H1 RSI(2) pullback, 200 SMA"] = rsi2(m)
    for k, v in res.items():
        report(k, v)
        v.to_csv(f"/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/strat/{k.split()[0]}.csv", index=False)
