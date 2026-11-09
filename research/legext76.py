"""Round 76 (10 Nov 2026): LEG EMA-distance filter measured from the leg's last peak / trough instead of the
firing candle's close (owner: "mesti ukur guna puncak atau lembah terakhir").

Round 69b (9 Nov 2026): robustness of round 69's EMA-distance entry filter on the full 6.6 years.

Round 69 (9 Nov 2026): other LEG exits (owner: "kalau semua floating, harga sentuh ema ... close dalam rugi. atau kau ada idea lain"):
moving TP (wait for a profit) PLUS a basket $ stop or a time stop, and an entry filter that only fades when price is
already at least $D beyond the EMA 50, so the EMA touch is far enough to pay.

Round 68 (9 Nov 2026): live LEG v2.06 with a moving basket TP so a basket only closes in profit
(owner: "tp nya kau adjust berubah2 untuk sentiasa profit"): close the whole basket at the EMA 50 touch only
when the basket is at least +mintp $; otherwise wait for the price where it is. TP = min(EMA, BE - mintp) for sells.

Based on round 56 (6 Nov 2026): the owner's own leg-fade rule, exactly as ordered, on a $100 account.

Owner: "ea akan baca pergerakan bilangan candle di m1, buat range. jika dah sampai tahap max, entry. jika
naik lagi entry lagi. TP di max perjalanan seterusnya. tiada sl" -- answered: SELL against an up leg (BUY
against a down leg), at most 5 entries of 0.01 lot each (no doubling).

  leg      online zigzag 0.10% on M1 closes (round 54/55), reset each server day
  entry 1  when the current leg is 60 candles old (round 54: p90 of leg length is 59-63), fade it
  adds     each time price runs another 0.10% beyond the last entry, add one more in the same direction,
           up to 5 open
  TP       each position: 0.35% of price back the other way (round 54: p90 of a leg's size, ~$14)
  SL       none. No time exit. Positions hold overnight and pay the broker swap (-$0.80 a night per 0.01
           lot, round 23's measured rate, both ways).
  account  $100, 1:500, broker stop-out at 50% margin level. A stop-out closes everything; it is counted
           and the account is refilled to $100 so the test can go on.
Entries 01:30-22:00 server on weekdays, one basket at a time.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)
SWAP = 0.80


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01          # $ per 1.0 price move at 0.01 lot
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C)
    hm = B.hm.values
    day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    sp = B.s.values.astype(float)
    wd = B.index.dayofweek.values
    yr = B.index.year.values
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {B.index[-1]:%Y-%m-%d}, {n:,} bars, $ per 1.0 move at 0.01 lot = {usd:.2f}")

    def run(pct=0.0010, N=60, tpp=0.0035, maxn=5, label="", wick=False, emaP=None, side=True, lots=(1, 1, 1, 1, 1), stop_steps=None, be2=False, follow=False, mintp=None, bstop=None, tstop=None, mind=None, fromext=False):
        XH, XL = (H, L) if wick else (C, C)
        EV = pd.Series(C).ewm(span=emaP, adjust=False).mean().values if emaP else None
        EP = np.r_[np.nan, EV[:-1]] if emaP else None     # EMA of the last CLOSED bar, known at bar k
        lo0 = hi0 = 0
        bal, blow, blow_t = 100.0, 0, []
        pos = []                       # [entry, dir, k]
        closed = []                    # (k_exit, pnl$, k_entry)
        d_ = 0; ext = 0; piv = 0; fired = False
        worst_float = 0.0
        stuck = []
        for k in range(n):
            # ---- swap on open positions at each new server day
            if newd[k] and pos:
                bal -= SWAP * sum(lots[i] for i in range(len(pos)))
            # ---- owner's question (6-7 Nov): what to do once 2 entries float
            if pos and (stop_steps or (be2 and len(pos) >= 2)):
                dr = pos[0][1]
                xs = None
                if stop_steps and len(pos) >= maxn:
                    sl = pos[-1][0] * (1 - dr * pct * stop_steps)
                    if (dr == -1 and H[k] + sp[k] >= sl) or (dr == 1 and L[k] <= sl):
                        xs = max(O[k] + sp[k], sl) if dr == -1 else min(O[k], sl)
                if xs is None and be2 and len(pos) >= 2:
                    w = sum(lots[qi] for qi in range(len(pos)))
                    avg = sum(e * lots[qi] for qi, (e, _, _) in enumerate(pos)) / w
                    be = avg - dr * 0.05                                    # 5 cents over break-even
                    if (dr == -1 and L[k] + sp[k] <= be) or (dr == 1 and H[k] >= be):
                        xs = min(O[k] + sp[k], be) if dr == -1 else max(O[k], be)
                if xs is not None:
                    for qi, (e, dd, k0) in enumerate(pos):
                        pnl = (xs - e) * dd * usd * lots[qi]
                        bal += pnl; closed.append((k, pnl, k0))
                    pos = []
            # ---- manage the open basket on this bar
            if pos and (bstop or tstop):
                dr = pos[0][1]
                w = sum(lots[qi] for qi in range(len(pos)))
                avg = sum(e * lots[qi] for qi, (e, _, _) in enumerate(pos)) / w
                xs = None
                if tstop and k - pos[0][2] >= tstop:
                    xs = O[k] + sp[k] if dr == -1 else O[k]
                elif bstop:
                    lv = avg - dr * bstop / (usd * w)
                    if dr == -1 and H[k] + sp[k] >= lv: xs = max(O[k] + sp[k], lv)
                    elif dr == 1 and L[k] <= lv: xs = min(O[k], lv)
                if xs is not None:
                    for qi, (e, dd, k0) in enumerate(pos):
                        pnl = (xs - e) * dd * usd * lots[qi]
                        bal += pnl; closed.append((k, pnl, k0))
                    pos = []
            if pos and emaP and mintp is not None:
                dr = pos[0][1]
                w = sum(lots[qi] for qi in range(len(pos)))
                avg = sum(e * lots[qi] for qi, (e, _, _) in enumerate(pos)) / w
                be = avg - dr * mintp / (usd * w)
                tp = min(EP[k], be) if dr == -1 else max(EP[k], be)
                if (dr == -1 and L[k] + sp[k] <= tp) or (dr == 1 and H[k] >= tp):
                    x = min(O[k] + sp[k], tp) if dr == -1 else max(O[k], tp)
                    for qi, (e, dd, k0) in enumerate(pos):
                        pnl = (x - e) * dd * usd * lots[qi]
                        bal += pnl; closed.append((k, pnl, k0))
                    pos = []
            if pos and not (emaP and mintp is not None):
                keep = []
                for qi, (e, dd, k0) in enumerate(pos):
                    m = lots[qi] if qi < len(lots) else 1
                    tp = e * (1 + dd * tpp) if not emaP else EP[k]
                    # sell closes at ask: bar low + spread <= tp ; buy closes at bid: high >= tp
                    hit = (L[k] + sp[k] <= tp) if dd == -1 else (H[k] >= tp)
                    if hit:
                        x = min(O[k] + sp[k], tp) if dd == -1 else max(O[k], tp)
                        pnl = (x - e) * dd * usd * m
                        bal += pnl; closed.append((k, pnl, k0))
                    else:
                        keep.append([e, dd, k0])
                if emaP and len(keep) < len(pos): keep = []      # EMA mode closes the whole basket
                pos = keep
            if pos:
                dr = pos[0][1]
                # add when price has run another pct beyond the last entry (against the basket)
                last = pos[-1][0]
                lvl = last * (1 - dr * pct)
                while len(pos) < maxn and not (hm[k] >= 1425 or hm[k] < 90) and \
                        ((dr == -1 and H[k] >= lvl) or (dr == 1 and L[k] + sp[k] <= lvl)):
                    e = max(O[k], lvl) if dr == -1 else min(O[k] + sp[k], lvl)
                    pos.append([e, dr, k]); last = e
                    lvl = last * (1 - dr * pct)
                # floating at the bar's worst point -> stop-out check (50% margin level)
                adverse = (H[k] + sp[k]) if dr == -1 else L[k]
                fl = sum((adverse - e) * dd * usd * lots[qi] for qi, (e, dd, _) in enumerate(pos))
                worst_float = min(worst_float, fl)
                margin = sum(lots[qi] for qi in range(len(pos))) * C[k] * 100 * 0.01 / 500
                if bal + fl <= 0.5 * margin:
                    for qi, (e, dd, k0) in enumerate(pos):
                        pnl = (adverse - e) * dd * usd * lots[qi]
                        closed.append((k, pnl, k0))
                    bal += fl
                    blow += 1; blow_t.append(k)
                    pos = []
                    bal = 100.0
            # ---- online zigzag (closed bar k) and the entry signal
            if newd[k]:
                d_, ext, piv, fired = 0, k, k, False
                lo0 = hi0 = k
                continue
            if d_ == 0:
                if XL[k] < XL[lo0]: lo0 = k
                if XH[k] > XH[hi0]: hi0 = k
                if XH[k] >= XL[lo0] * (1 + pct): d_, piv, ext, fired = 1, lo0, k, False
                elif XL[k] <= XH[hi0] * (1 - pct): d_, piv, ext, fired = -1, hi0, k, False
                continue
            if d_ == 1:
                if XH[k] > XH[ext]: ext = k
                elif XL[k] <= XH[ext] * (1 - pct):
                    piv, d_, ext, fired = ext, -1, k, False; continue
            else:
                if XL[k] < XL[ext]: ext = k
                elif XH[k] >= XL[ext] * (1 + pct):
                    piv, d_, ext, fired = ext, 1, k, False; continue
            if not fired and k - piv >= N:
                fired = True
                if not pos and k + 1 < n and not newd[k + 1] and 90 <= hm[k] < 1320 and wd[k] < 5:
                    dr = d_ if follow else -d_
                    ref = (XH[ext] if d_ == 1 else XL[ext]) if fromext else C[k]
                    if emaP and mind is not None and ((dr == -1 and ref - EV[k] < mind) or (dr == 1 and EV[k] - ref < mind)):
                        continue                                        # round 69: fade only when price is $mind beyond the EMA
                    if emaP and side and ((dr == -1 and C[k] <= EV[k]) or (dr == 1 and C[k] >= EV[k])):
                        continue                                        # TP at the EMA needs price on the far side
                    e = O[k + 1] if dr == -1 else O[k + 1] + sp[k + 1]    # sell at bid, buy at ask
                    pos.append([e, dr, k + 1])
        T = pd.DataFrame(closed, columns=["k", "net", "k0"])
        T["t"] = B.index[T.k.values]
        T["y"] = yr[T.k.values]
        g = T.net[T.net > 0].sum(); ls = -T.net[T.net < 0].sum()
        daily = T.groupby(T.t.dt.normalize()).net.sum()
        held = (T.k - T.k0) / 60.0
        by = pd.Series(blow_t, dtype=int).map(lambda q: yr[q]).value_counts().sort_index() if blow_t else pd.Series(dtype=int)
        say(f"\n--- {label}: zigzag {pct * 100:.2f}%, leg age {N}, TP {('EMA' + str(emaP)) if emaP else f'{tpp * 100:.2f}%'}, max {maxn} entries ---")
        say(f"closed trades {len(T):,} ({len(T) / len(np.unique(day)):.2f} a day), win {100 * (T.net > 0).mean():.1f}%, "
            f"PF {g / ls if ls else 0:.2f}, net ${T.net.sum():+,.0f} (swap included), avg win ${T.net[T.net > 0].mean():.2f}, "
            f"avg loss ${T.net[T.net < 0].mean():.2f}")
        say(f"ACCOUNT $100 BLOWN (stop-out) {blow} times in {len(np.unique(yr))} years; worst day ${daily.min():+.2f}; "
            f"worst floating loss ${worst_float:+.2f}; hold median {held.median():.0f} h, p90 {held.quantile(.9):.0f} h, max {held.max():.0f} h")
        say("by year: " + "  ".join(f"{y}: net ${T[T.y == y].net.sum():+.0f}, blown {int(by.get(y, 0))}x" for y in sorted(T.y.unique())))
        e_ = B.index[-1]
        for nm, a, b in (("last month", e_ - pd.Timedelta(days=30), e_ + pd.Timedelta(minutes=1)),
                         ("month before", e_ - pd.Timedelta(days=60), e_ - pd.Timedelta(days=30))):
            x = T[(T.t >= a) & (T.t < b)]
            bl = sum(1 for q in blow_t if a <= B.index[q] < b)
            wdy = x.groupby(x.t.dt.normalize()).net.sum().min() if len(x) else 0
            say(f"{nm}: {len(x)} closes, win {100 * (x.net > 0).mean() if len(x) else 0:.0f}%, net ${x.net.sum():+.0f}, "
                f"stop-outs {bl}, worst day ${wdy:+.0f}")
        l12 = T[T.t >= B.index[-1] - pd.Timedelta(days=365)]
        say(f"last 12 months: {len(l12)} trades, net ${l12.net.sum():+.0f}, blown {sum(1 for q in blow_t if B.index[q] >= B.index[-1] - pd.Timedelta(days=365))}x")
        if blow_t:
            first = B.index[blow_t[0]]
            say(f"first stop-out on {first:%Y-%m-%d}, {(first - B.index[0]).days} days after the start; "
                f"median days between stop-outs {np.median(np.diff([B.index[q] for q in blow_t]).astype('timedelta64[D]').astype(int)) if len(blow_t) > 1 else 0}")

    for lab, kw in [('LIVE before v2.13 (no filter)', {}), ('v2.13: closed M1 bar >= $5 from EMA 50', {'mind': 5.0}), ('PEAK/TROUGH of the leg >= $5 from EMA 50', {'mind': 5.0, 'fromext': True}), ('PEAK/TROUGH >= $3', {'mind': 3.0, 'fromext': True}), ('PEAK/TROUGH >= $8', {'mind': 8.0, 'fromext': True}), ('PEAK/TROUGH >= $10', {'mind': 10.0, 'fromext': True})]:
        kw = dict(kw)
        run(N=20, wick=True, emaP=50, side=False, maxn=5, lots=(1, 1, 2, 2, 3), label=lab, **kw)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
