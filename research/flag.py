"""Gold bull / bear flag pattern (rules fixed in advance, 30 Oct 2026). Buy shown, sell mirrored.
  Pole: the pole top candle p has the highest high of the last 8 candles; pole height = high[p] - lowest low of
        the 8 candles up to p, at least 3 ATR.
  Flag: 3-12 candles after p, all highs at or below high[p], lowest low retraces at most 50% of the pole.
  Breakout: a bullish candle closes above the flag high -> buy at the next open (one trade per pole).
  SL: flag low - 0.1 ATR. TP: measured move (pole height from the entry) or 2R. Max 36 candles.
  Option "+ema": only in the EMA 50 direction.
Entries 08:00-20:00 chart time, all trades closed by 21:00. One spread per trade."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import scalp2 as X
import scalp3 as Y


def flag_signals(d, tp_mode="mm", ema=False, min_pole=3.0):
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    A = d.atr.values; chh = d.ch_h.values; e50 = d.e50.values; n = len(d)
    sig, used = {}, set()
    for i in range(30, n - 1):
        if not (8 <= chh[i] < 20) or np.isnan(A[i]):
            continue
        for F in range(3, 13):
            p = i - F - 1
            if p < 10:
                break
            for dr in (1, -1):
                if (dr, p) in used or (ema and (c[i] - e50[i]) * dr <= 0):
                    continue
                fh, fl = h[i - F:i].max(), l[i - F:i].min()
                if dr == 1:
                    top = h[p]
                    if top < h[p - 7:p + 1].max() or fh > top:
                        continue
                    H = top - l[p - 7:p + 1].min()
                    if H < min_pole * A[p] or top - fl > 0.5 * H:
                        continue
                    if not (c[i] > fh and c[i] > o[i]):
                        continue
                    sl = fl - 0.1 * A[i]
                else:
                    bot = l[p]
                    if bot > l[p - 7:p + 1].min() or fl < bot:
                        continue
                    H = h[p - 7:p + 1].max() - bot
                    if H < min_pole * A[p] or fh - bot > 0.5 * H:
                        continue
                    if not (c[i] < fl and c[i] < o[i]):
                        continue
                    sl = fh + 0.1 * A[i]
                risk = (c[i] - sl) * dr
                if risk <= 0:
                    continue
                used.add((dr, p))
                if tp_mode == "mm":
                    sig[i] = dict(type="market", dir=dr, price=None, sl=sl, tp=c[i] + dr * H, exp=i + 1, maxb=36)
                else:
                    sig[i] = dict(type="market", dir=dr, price=None, sl=sl, tp=None, tp_r=2.0, exp=i + 1, maxb=36)
                break
            if i in sig:
                break
    return sig


VARIANTS = [("measured move", dict(tp_mode="mm")), ("TP 2R", dict(tp_mode="r")),
            ("measured move + EMA 50", dict(tp_mode="mm", ema=True)), ("TP 2R + EMA 50", dict(tp_mode="r", ema=True)),
            ("pole >= 2 ATR, measured move", dict(tp_mode="mm", min_pole=2.0))]


def report(d, sp, label):
    days = d.ch_day.nunique(); mid_t = d.index[len(d) // 2]
    X.say(f"\n{label}: {len(d)} candles {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d} ({days} days), spread ${sp}")
    for name, kw in VARIANTS:
        tr = Y.run3(d, flag_signals(d, **kw), sp)
        if not len(tr):
            X.say(f"  {name}: no trades"); continue
        x = tr.pnl.values; h1 = tr[tr.t < mid_t].pnl.values; h2 = tr[tr.t >= mid_t].pnl.values
        cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
        X.say(f"  {name:30s} {len(tr):4d} trades ({len(tr) / days:.1f}/day) win {np.mean(x > 0) * 100:.0f}% PF {X.pf(x):.2f} "
              f"net ${x.sum():+.0f} halves {X.pf(h1):.2f}/{X.pf(h2):.2f} | before spread PF {X.pf(x + sp):.2f} | max DD ${dd:.0f} "
              f"| exits {tr.res.value_counts().to_dict()}")


if __name__ == "__main__":
    for label, loader, sp in (("Deriv XAUUSD 5m", lambda: Y.deriv(300, 45), 0.25), ("Yahoo GC=F 5m", X.yahoo5, 0.30)):
        try:
            report(Y.prep(loader()), sp, label)
        except Exception as e:
            X.say(f"{label}: data error {e}")
    os.makedirs("status", exist_ok=True)
    open("status/research.txt", "w").write("Gold flag pattern\n" + "\n".join(X.out) + "\n")
