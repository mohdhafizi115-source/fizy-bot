"""Supply & Demand (SnD) zones, turned into fixed rules (buy / demand shown, sell / supply mirrored):
  1. Zone TF (H1 or H4): 1..max_base "base" candles (small body: body <= base_body x range, and
     range <= base_atr x ATR14) right before ONE explosive leg-out candle
     (body >= 0.6 x range, range >= legout_atr x ATR14, close beyond the whole base).
     Leg-out up = demand (DBR / RBR), leg-out down = supply (RBD / DBD).
  2. Zone: proximal = highest body edge of the base, distal = lowest low of base + leg-out candle.
     Zone height <= max_h x ATR14. Active from the leg-out close, for max_age zone-TF candles.
  3. Fresh only: the first time price comes back to the proximal line, a limit order fills there
     (if no other trade is open). The zone is used up on that first touch either way.
     Broken (removed) if an execution candle closes beyond the distal line before the touch.
  4. Odds enhancer "departure": before the touch, price must have moved away from the proximal line
     by >= dep x zone height.
  5. Trend filter (optional): H4 close vs H4 EMA 200 (demand only above, supply only below).
  6. SL = distal -/+ sl_buf x ATR(zone TF); TP = rr x risk.
Execution on the smallest bars given (M15 for gold, H1 for forex); intrabar path O-L-H-C for a bull
bar, O-H-L-C for a bear bar; spread paid on buys at entry and on sells at exit."""
import numpy as np, pandas as pd
from bt import resample, atr, swap_cost, metrics, SPLIT


def zones(d, max_base=3, base_body=0.5, base_atr=1.0, legout_atr=1.5, max_h=1.5):
    a = atr(d).values
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    rng = h - l; body = np.abs(c - o)
    out = []
    for i in range(20, len(d)):
        A = a[i - 1]
        if np.isnan(A) or rng[i] <= 0:
            continue
        if body[i] < 0.6 * rng[i] or rng[i] < legout_atr * A:
            continue
        dr = 1 if c[i] > o[i] else -1
        k = 0
        while k < max_base and i - k - 1 >= 0:
            j = i - k - 1
            if rng[j] > 0 and body[j] <= base_body * rng[j] and rng[j] <= base_atr * A:
                k += 1
            else:
                break
        if k == 0:
            continue
        b = range(i - k, i)
        if dr == 1:
            if c[i] <= max(h[j] for j in b):
                continue
            prox = max(max(o[j], c[j]) for j in b); dist = min(min(l[j] for j in b), l[i])
        else:
            if c[i] >= min(l[j] for j in b):
                continue
            prox = min(min(o[j], c[j]) for j in b); dist = max(max(h[j] for j in b), h[i])
        hgt = abs(prox - dist)
        if hgt <= 0 or hgt > max_h * A:
            continue
        out.append(dict(i=i, dir=dr, prox=prox, dist=dist, h=hgt, atr=A))
    return out


def snd(e, ztf="1h", trend=True, rr=2.0, dep=2.0, max_age=120, sl_buf=0.1, swap=True, **zkw):
    """e: execution candles (open/high/low/close/spread), broker time. Returns trades (pnl in price units, R)."""
    d = resample(e, ztf)
    zs = zones(d, **zkw)
    per = pd.Timedelta(ztf)
    act_t = {}
    for z in zs:
        z["start"] = d.index[z["i"]] + per                    # usable after the leg-out candle closes
        z["end"] = d.index[min(z["i"] + max_age, len(d) - 1)] + per
        z["sl"] = z["dist"] - z["dir"] * sl_buf * z["atr"]
        act_t.setdefault(z["start"], []).append(z)
    if trend:
        h4 = resample(e, "4h"); ema = h4.close.ewm(span=200, adjust=False).mean()
        up = (h4.close > ema).astype(int) - (h4.close < ema).astype(int)
        up.index = up.index + pd.Timedelta("4h")              # known after the H4 candle closes
        up = up.iloc[200:]
        tr_at = up.reindex(e.index, method="ffill").fillna(0).values
    else:
        tr_at = np.zeros(len(e))
    o, h, l, c, sp = (e[x].values for x in ("open", "high", "low", "close", "spread"))
    live, trades, pos = [], [], None
    starts = sorted(act_t)
    si = 0
    for n, t in enumerate(e.index):
        while si < len(starts) and starts[si] <= t:
            for z in act_t[starts[si]]:
                z["far"] = z["prox"]                          # furthest price since activation
                live.append(z)
            si += 1
        live = [z for z in live if t < z["end"]]
        path = [o[n], l[n], h[n], c[n]] if c[n] >= o[n] else [o[n], h[n], l[n], c[n]]
        for a_, b_ in zip(path[:-1], path[1:]):
            lo, hi = min(a_, b_), max(a_, b_)
            # touches (fresh zones are used up on the first touch)
            keep = []
            for z in live:
                touched = (lo + sp[n] <= z["prox"]) if z["dir"] == 1 else (hi >= z["prox"])
                if not touched:
                    z["far"] = max(z["far"], hi) if z["dir"] == 1 else min(z["far"], lo)
                    keep.append(z); continue
                ok = pos is None and abs(z["far"] - z["prox"]) >= dep * z["h"] and \
                    (not trend or tr_at[n] == z["dir"])
                if ok:
                    px = z["prox"]
                    if z["dir"] == 1 and a_ + sp[n] < px:
                        px = a_ + sp[n]                       # gapped through: filled at the better price
                    if z["dir"] == -1 and a_ > px:
                        px = a_
                    risk = abs(px - z["sl"])
                    if risk > 0:
                        pos = dict(t=t, dr=z["dir"], entry=px, sl=z["sl"], tp=px + z["dir"] * rr * risk, risk=risk)
            live = keep
            if pos is not None:
                dr = pos["dr"]
                if pos["t"] == t and pos.get("seg") is None:
                    # filled inside this segment: only the move AFTER the fill (fill price -> segment end)
                    # can hit SL / TP, not the part of the segment before it
                    pos["seg"] = 1
                    fill_px = pos["entry"] - (sp[n] if dr == 1 else 0)   # bid-side price at the fill
                    lo, hi = min(fill_px, b_), max(fill_px, b_)
                if dr == 1:
                    ex = pos["sl"] if lo <= pos["sl"] else (pos["tp"] if hi >= pos["tp"] else None)
                else:
                    ex = pos["sl"] if hi + sp[n] >= pos["sl"] else (pos["tp"] if lo + sp[n] <= pos["tp"] else None)
                if ex is not None:
                    pnl = (ex - pos["entry"]) * dr - (swap_cost(pos["t"], t, dr) if swap else 0)
                    trades.append(dict(open=pos["t"], close=t, dir=dr, pnl=pnl, R=pnl / pos["risk"],
                                       res="SL" if ex == pos["sl"] else "TP"))
                    pos = None
        # zones broken by a close beyond the distal line
        live = [z for z in live if not ((z["dir"] == 1 and c[n] < z["dist"]) or (z["dir"] == -1 and c[n] > z["dist"]))]
    return pd.DataFrame(trades)


def summary(tr):
    if len(tr) == 0:
        return dict(n=0, win=0, pf=0, R=0, pfA=0, pfB=0, net=0)
    def pf(r):
        gp, gl = r[r > 0].sum(), -r[r < 0].sum()
        return round(gp / gl, 2) if gl else 99.0
    A = tr[tr.open < SPLIT]; B = tr[tr.open >= SPLIT]
    return dict(n=len(tr), win=round((tr.R > 0).mean() * 100, 1), pf=pf(tr.R.values), R=round(tr.R.sum(), 1),
                net=round(tr.pnl.sum(), 1), pfA=pf(A.R.values) if len(A) else 0, pfB=pf(B.R.values) if len(B) else 0)
