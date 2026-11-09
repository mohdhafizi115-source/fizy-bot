"""Round 73 (9 Nov 2026): round 72's M1 Gold Hedge with the live $25 daily target (owner: "target dah achived 25$
tiada masalah guna ea ni"): after +$25 closed in a server day no NEW basket starts until the next day.

Round 72 (9 Nov 2026): hedging techniques from the web, on gold M1, $100 account (owner: "cari la source teknik
hedging"). Sources: MQL5 Market "Zone recovery MT5" (product 123572), "M1 Gold Hedge" (product 165459), Axiory /
CMC hedging guides.

ZONE RECOVERY (classic): open a trade; if price runs Z against it, open the opposite side at the zone edge with a
  lot sized so that, if price then reaches that side's TP (T beyond the zone edge), the whole basket nets +target $.
  Alternate at the two zone edges until one TP is hit. Up to maxlv positions.
M1 GOLD HEDGE (MQL5 product 165459, as described on its page): BuyStop above the last 3 M1 bars' high when the H1
  EMA 21 > EMA 50 (SellStop below the low when below), 08:00-21:00 GMT; if price runs 2 x ATR(14) against, open the
  opposite side with the next lot of 0.01 / 0.02 / 0.03 / 0.05 / 0.08 / 0.12 (alternating at the zone edges); close
  the basket at +$10 combined; no new hedges while the basket is below -$30 (freeze); emergency close at margin
  level 10%.
Controls: the same machinery with random entries.
Account $100, 1:500, broker stop-out at 50% margin level (then refilled to $100 and counted); margin of a hedged
basket = the larger side. Prices on the bid, buys at ask; swap $0.80 a night per 0.01 lot.
"""
import os, sys, math, time
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
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    B = B[B.index >= B.index[-1] - pd.Timedelta(days=400)]           # last 13 months
    del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    sp = B.s.values.astype(float)
    n = len(C)
    hm = B.hm.values
    day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    wd = B.index.dayofweek.values
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    h1 = pd.Series(C, index=B.index).resample("1h").last().dropna()
    e21 = h1.ewm(span=21, adjust=False).mean().shift(1).reindex(B.index, method="ffill").values   # last CLOSED H1
    e50 = h1.ewm(span=50, adjust=False).mean().shift(1).reindex(B.index, method="ffill").values
    hi3 = pd.Series(H).rolling(3).max().shift(1).values
    lo3 = pd.Series(L).rolling(3).min().shift(1).values
    end = B.index[-1]
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars")

    def run(label, entry="rand", zmode="usd", Z=3.0, T=3.0, target=1.0, maxlv=6, seq=None, btp=None, freeze=None,
            win=(90, 1320), dtarget=None):
        rg = np.random.default_rng(72)
        bal, blow, blow_t = 100.0, 0, []
        bk = []                     # [side, entry, units]
        U = D = None; zt = T
        res = []                    # (k_close, pnl, k_open, n_positions)
        k_open = 0; maxu = 0
        dpnl = 0.0; first_blow = None
        def net(bid, ksp):
            return sum(u * ((bid - e) if s == 1 else (e - bid - ksp)) for s, e, u in bk) * usd
        for k in range(1, n):
            if newd[k]: dpnl = 0.0
            if bk and newd[k]:
                bal -= SWAP * sum(u for _, _, u in bk)
            if bk:
                s_last = bk[-1][0]
                # ---- hedge trigger first (the adverse event)
                if len(bk) < maxlv and not (freeze and net(C[k - 1], sp[k - 1]) <= -freeze):
                    if s_last == 1 and L[k] <= D:                     # open a SELL at D (bid)
                        e = min(O[k], D)
                        if seq: u = seq[len(bk)]
                        else:
                            bidtp = D - zt - sp[k]
                            u = max(1, math.ceil((target - net(bidtp, sp[k])) / (zt * usd)))
                        bk.append([-1, e, u]); maxu = max(maxu, u)
                    elif s_last == -1 and H[k] + sp[k] >= U:          # open a BUY at U (ask)
                        e = max(O[k] + sp[k], U)
                        if seq: u = seq[len(bk)]
                        else:
                            bidtp = U + zt
                            u = max(1, math.ceil((target - net(bidtp, sp[k])) / (zt * usd)))
                        bk.append([1, e, u]); maxu = max(maxu, u)
                # ---- exits
                x = None
                if btp is not None:
                    if net(C[k], sp[k]) >= btp: x = C[k]
                else:
                    if bk[-1][0] == 1 and H[k] >= U + zt: x = max(O[k], U + zt)
                    elif bk[-1][0] == -1 and L[k] + sp[k] <= D - zt: x = min(O[k], D - zt - sp[k])
                if x is not None:
                    p = net(x, sp[k]); bal += p; dpnl += p; res.append((k, p, k_open, len(bk))); bk = []
                    continue
                # ---- stop-out (worst point of the bar) and the emergency close
                wn = min(net(H[k], sp[k]), net(L[k], sp[k]))
                bu = sum(u for s, _, u in bk if s == 1); su = sum(u for s, _, u in bk if s == -1)
                margin = max(bu, su) * C[k] * 100 * 0.01 / 500
                if bal + wn <= 0.5 * margin or (seq and bal + wn <= 0.10 * margin):
                    bal += wn; res.append((k, wn, k_open, len(bk))); bk = []
                    dpnl += wn; blow += 1; blow_t.append(k); bal = 100.0
                    if first_blow is None: first_blow = k
                continue
            # ---- flat: new entry
            if dtarget is not None and dpnl >= dtarget:
                continue
            if wd[k] >= 5 or not (win[0] <= hm[k] < win[1]) or not np.isfinite(atr[k]):
                continue
            dr = 0
            if entry == "rand":
                if rg.random() < 1 / 30: dr = 1 if rg.random() < 0.5 else -1
            elif entry == "bo" and np.isfinite(e50[k]) and np.isfinite(hi3[k]):
                if e21[k] > e50[k] and H[k] > hi3[k]: dr = 1
                elif e21[k] < e50[k] and L[k] < lo3[k]: dr = -1
            if dr == 0:
                continue
            z = Z * atr[k] if zmode == "atr" else Z
            zt = T * atr[k] if zmode == "atr" else T
            u = seq[0] if seq else 1
            if dr == 1:
                e = (max(O[k], hi3[k]) if entry == "bo" else O[k]) + sp[k]
                U = e; D = U - z
            else:
                e = min(O[k], lo3[k]) if entry == "bo" else O[k]
                D = e; U = D + z
            bk = [[dr, e, u]]; k_open = k; maxu = max(maxu, u)
        openfl = 0.0
        if bk:                                                       # a basket still open at the end: mark it to market
            openfl = net(C[-1], sp[-1]); res.append((n - 1, openfl, k_open, len(bk)))
        R = pd.DataFrame(res, columns=["k", "net", "k0", "npos"])
        R["t"] = B.index[R.k.values]
        g = R.net[R.net > 0].sum(); l_ = -R.net[R.net < 0].sum()
        say(f"\n--- {label} ---")
        say(f"baskets {len(R):,} ({len(R) / len(np.unique(day)):.1f} a day), win {100 * (R.net > 0).mean():.1f}%, PF {g / l_ if l_ else 0:.2f}, "
            f"13 months net ${R.net.sum():+,.0f}, avg win ${R.net[R.net > 0].mean():.2f} vs avg loss ${R.net[R.net < 0].mean():.2f}, "
            f"biggest lot {maxu / 100:.2f}, baskets reaching the last level {100 * (R.npos >= (len(seq) if seq else maxlv)).mean():.1f}%")
        if bk: say(f"!! a basket opened {B.index[k_open]:%Y-%m-%d %H:%M} is STILL OPEN at the end ({len(bk)} positions), floating ${openfl:+.0f} (counted as closed now)")
        if first_blow is not None: say(f"a real $100 account would have ended on {B.index[first_blow]:%Y-%m-%d}, {(B.index[first_blow] - B.index[0]).days} days after the start")
        days_t = R.groupby(R.t.dt.normalize()).net.sum(); say(f"days >= +$25: {(days_t >= 25).sum()} of {len(days_t)}; days <= -$25: {(days_t <= -25).sum()}; days <= -$100: {(days_t <= -100).sum()}")
        say(f"ACCOUNT $100 BLOWN {blow} times in 13 months; worst day ${R.groupby(R.t.dt.normalize()).net.sum().min():+.0f}")
        for nm, a, b in (("last month", end - pd.Timedelta(days=30), end + pd.Timedelta(minutes=1)),
                         ("month before", end - pd.Timedelta(days=60), end - pd.Timedelta(days=30)),
                         ("last 12 months", end - pd.Timedelta(days=365), end + pd.Timedelta(minutes=1))):
            x = R[(R.t >= a) & (R.t < b)]
            bl = sum(1 for q in blow_t if a <= B.index[q] < b)
            say(f"{nm}: {len(x)} baskets, win {100 * (x.net > 0).mean() if len(x) else 0:.0f}%, net ${x.net.sum():+.0f}, blown {bl}x")

    seq = [1, 2, 3, 5, 8, 12]
    for tgt in (None, 25.0):
        tl = "" if tgt is None else " + DAILY TARGET $25"
        run("M1 GOLD HEDGE as sold (TP +$10)" + tl, entry="bo", zmode="atr", Z=2.0, T=2.0, seq=seq, btp=10.0, freeze=30.0, win=(600, 1380), dtarget=tgt)
        run("M1 GOLD HEDGE with TP +$3" + tl, entry="bo", zmode="atr", Z=2.0, T=2.0, seq=seq, btp=3.0, freeze=30.0, win=(600, 1380), dtarget=tgt)
    run("M1 GOLD HEDGE as sold + DAILY TARGET $25, RANDOM entries (control)", entry="rand", zmode="atr", Z=2.0, T=2.0, seq=seq, btp=10.0, freeze=30.0, win=(600, 1380), dtarget=25.0)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
