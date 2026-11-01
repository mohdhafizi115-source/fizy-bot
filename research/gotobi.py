"""Gotobi post-fix reversal: robustness check on the broker's M5 history (Mar 2020 - Oct 2026).

Round 6b found: on Gotobi days (5, 10, 15, 20, 25, 30 / month-end; weekend -> Friday before), selling the JPY pairs
at the Tokyo fix (09:55 JST) and buying back 35-65 minutes later made money after spread, with t ~ 5-6, while the
same trade on other days did not. Here, before anything goes live:
  - exits 10:15 / 10:30 / 10:45 / 11:00 JST, and a later entry at 10:00 / 10:05 (does it depend on one bar?)
  - Gotobi defined with the month-end instead of the 30th
  - a protective stop at 1x / 1.5x ATR(H1) from the entry
  - per year and per pair, a 4-pair basket, and worst streaks
Cost: the entry bar's spread (MT5 export) once per trade.
"""
import os, sys, glob
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as FL

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
PAIRS = ("USDJPY", "EURJPY", "GBPJPY", "CHFJPY", "CADJPY", "AUDJPY", "NZDJPY")


def gotobi(dates, monthend=False):
    days = pd.DatetimeIndex(sorted(set(pd.to_datetime(list(dates)))))
    out = set()
    for d in pd.date_range(days.min(), days.max(), freq="D"):
        last = d.day == d.days_in_month
        hit = d.day in (5, 10, 15, 20, 25) or (d.day == 30 if not monthend else last) or (not monthend and last and d.day < 30)
        if hit:
            x = d
            while x.day_of_week >= 5:
                x -= pd.Timedelta(days=1)
            out.add(x.date())
    return out


def trades(d, t_in, t_out, days, stop_atr=None):
    loc = d.index.tz_convert("Asia/Tokyo")
    hm = loc.hour * 60 + loc.minute
    date = np.array(loc.date)
    o, h, l = d.o.values, d.h.values, d.l.values
    H = d.resample("1h").agg({"h": "max", "l": "min", "c": "last"}).dropna()
    c1 = H.c.shift()
    atr = np.maximum(H.h - H.l, np.maximum((H.h - c1).abs(), (H.l - c1).abs())).rolling(24 * 5).mean()
    atr_at = atr.reindex(d.index, method="ffill").values
    rows = []
    for i in np.where(hm == t_in)[0]:
        if date[i] not in days:
            continue
        e = o[i]
        sl = e + stop_atr * atr_at[i] if stop_atr else None
        j = i
        ex = None
        while j + 1 < len(d) and date[j + 1] == date[i] and hm[j + 1] <= t_out:
            if sl is not None and h[j] >= sl:
                ex = max(sl, o[j]) if j > i else sl
                break
            j += 1
            if hm[j] == t_out:
                ex = o[j]
                break
        if ex is None:
            continue
        rows.append((pd.Timestamp(date[i]), e - ex, d.s.values[i]))
    T = pd.DataFrame(rows, columns=["day", "gross", "sp"]).set_index("day")
    T["net"] = T.gross - T.sp
    return T


def line(name, T, pip):
    if len(T) < 30:
        print(f"  {name:44s} {len(T)} trades"); return
    h = T.index >= T.index[len(T) // 2]
    yrs = " ".join(f"{y % 100}:{T.net[T.index.year == y].sum() / pip:+.0f}" for y in sorted(set(T.index.year)))
    pos_y = sum(T.net[T.index.year == y].sum() > 0 for y in set(T.index.year))
    print(f"  {name:44s} {len(T):4d} gross {T.gross.mean() / pip:+5.2f}p t {FL.tstat(T.gross):+5.2f} net {T.net.mean() / pip:+5.2f}p "
          f"PF {FL.f2(FL.pf(T.net.values))} halves {FL.f2(FL.pf(T.net.values[~h]))} {FL.f2(FL.pf(T.net.values[h]))} "
          f"yrs+ {pos_y}/{len(set(T.index.year))} | {yrs}")


meta = FL.load_meta(os.path.join(DATA, "meta.txt"))
D = {s: FL.load(os.path.join(DATA, s + ".csv"), meta[s]["point"]) for s in PAIRS if os.path.exists(os.path.join(DATA, s + ".csv"))}
pip = 0.01
print("Gotobi post-fix reversal (short the JPY pair at the Tokyo fix), per trade in pips after spread")
for s, d in D.items():
    alld = set(d.index.tz_convert("Asia/Tokyo").date)
    g = gotobi(alld) & alld; gm = gotobi(alld, monthend=True) & alld; other = alld - g
    sp = d.s[(d.index.tz_convert("Asia/Tokyo").hour * 60 + d.index.tz_convert("Asia/Tokyo").minute) == 595].median() / pip
    print(f"\n{s}: {len(g)} Gotobi days, median spread at 09:55 JST {sp:.1f} pips")
    for t_in, t_out in ((595, 615), (595, 630), (595, 645), (595, 660), (600, 630), (605, 630), (605, 660)):
        T = trades(d, t_in, t_out, g); T["gross"] *= 1; T["net"] = T.gross - T.sp
        line(f"short {t_in // 60}:{t_in % 60:02d} -> {t_out // 60}:{t_out % 60:02d}", T, pip)
    line("short 9:55 -> 10:30, month-end version", trades(d, 595, 630, gm), pip)
    line("short 9:55 -> 10:30, stop 1.0 ATR(H1)", trades(d, 595, 630, g, 1.0), pip)
    line("short 9:55 -> 10:30, stop 1.5 ATR(H1)", trades(d, 595, 630, g, 1.5), pip)
    line("short 9:55 -> 10:30, NOT Gotobi days", trades(d, 595, 630, other), pip)

# basket of the four cheapest JPY pairs, 9:55 -> 10:30, equal weight in pips
print("\nBasket USDJPY + EURJPY + GBPJPY + CHFJPY, short 9:55 -> 10:30 on Gotobi days (sum of pips per day)")
parts = []
for s in ("USDJPY", "EURJPY", "GBPJPY", "CHFJPY"):
    if s in D:
        alld = set(D[s].index.tz_convert("Asia/Tokyo").date)
        parts.append(trades(D[s], 595, 630, gotobi(alld) & alld).net.rename(s))
B = pd.concat(parts, axis=1).sum(axis=1) / pip
eq = B.cumsum(); dd = (eq - eq.cummax()).min()
mon = B.groupby(B.index.to_period("M")).sum()
streak = 0; worst = 0
for x in B.values:
    streak = streak + 1 if x < 0 else 0; worst = max(worst, streak)
print(f"  {len(B)} days, mean {B.mean():+.2f} pips/day, PF {FL.f2(FL.pf(B.values))}, total {B.sum():+.0f} pips, max drawdown {dd:.0f} pips, "
      f"winning months {(mon > 0).sum()}/{len(mon)}, worst losing streak {worst} days")
print("  by year: " + ", ".join(f"{y}: {B[B.index.year == y].sum():+.0f}p" for y in sorted(set(B.index.year))))
