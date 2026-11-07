"""Round 60 (7 Nov 2026): the owner's recovery lot on the M1 leg fade.

Owner: "kau buat kiraan masa sedang floating berapa lot boleh entry, cukup untuk close max 1 dollar je".
Same entries as live FizyLEG (0.10% wick zigzag, leg 20 candles old, fade, adds every 0.10% against).
Entry 1: 0.01 lot, TP when price touches EMA 50 (as live).
Each add: the lot is SIZED so that if price retraces R dollars from the add price, the whole basket
nets +$1; once 2+ positions are open the basket closes as soon as it nets +$1 (instead of the EMA).
Max 5 positions. $100 account, 1:500, stop-out at 50% margin level, swap -$0.80 a night per 0.01 lot.
Also reported: the biggest lot the rule asked for and how often the 5th entry is reached.
"""
import os, sys, time, math
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    sp = B.s.values.astype(float); wd = B.index.dayofweek.values
    EV = pd.Series(C).ewm(span=50, adjust=False).mean().values
    EP = np.r_[np.nan, EV[:-1]]
    end = B.index[-1]; ndays = len(np.unique(day))
    say(f"XAUUSD M1 {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars")

    def run(R, maxn=5, label=""):
        pct = 0.001; N = 20
        bal, blow, bt = 100.0, 0, []
        pos = []                                   # [entry, dir, k, units of 0.01 lot]
        baskets = []                               # (k_close, pnl$, n_positions, max_units)
        d_ = ext = piv = lo0 = hi0 = 0; fired = False
        maxu = 0; worst_fl = 0.0

        def close_all(k, x, tag):
            nonlocal bal, pos
            pnl = sum((x - e) * dd * usd * u for e, dd, _, u in pos)
            bal += pnl
            baskets.append((k, pnl, len(pos), max(u for *_, u in pos)))
            pos = []
        for k in range(n):
            if newd[k] and pos:
                bal -= 0.8 * sum(u for *_, u in pos)
            if pos:
                dr = pos[0][1]
                U = sum(u for *_, u in pos); S = sum(e * u for e, _, _, u in pos)
                if len(pos) >= 2:                  # basket TP at +$1
                    x = S / U + dr * 1.0 / (U * usd)
                    if (dr == -1 and L[k] + sp[k] <= x) or (dr == 1 and H[k] >= x):
                        close_all(k, min(O[k] + sp[k], x) if dr == -1 else max(O[k], x), "TP1"); 
                else:                              # single position: EMA 50 touch (as live)
                    ev = EP[k]
                    if (dr == -1 and L[k] + sp[k] <= ev) or (dr == 1 and H[k] >= ev):
                        close_all(k, min(O[k] + sp[k], ev) if dr == -1 else max(O[k], ev), "EMA")
            if pos:
                dr = pos[0][1]
                lvl = pos[-1][0] * (1 - dr * pct)
                if len(pos) < maxn and 90 <= hm[k] < 1425 and ((dr == -1 and H[k] >= lvl) or (dr == 1 and L[k] + sp[k] <= lvl)):
                    e = max(O[k], lvl) if dr == -1 else min(O[k] + sp[k], lvl)
                    T = e + dr * R                                     # retrace target
                    have = sum((T - ee) * dd * usd * u for ee, dd, _, u in pos)
                    units = max(1, math.ceil((1.0 - have) / (R * usd)))
                    pos.append([e, dr, k, units]); maxu = max(maxu, units)
                adv = (H[k] + sp[k]) if dr == -1 else L[k]
                fl = sum((adv - e) * dd * usd * u for e, dd, _, u in pos)
                worst_fl = min(worst_fl, fl)
                margin = sum(u for *_, u in pos) * C[k] * 100 * 0.01 / 500
                if bal + fl <= 0.5 * margin:
                    close_all(k, adv, "STOPOUT"); blow += 1; bt.append(k); bal = 100.0
            # zigzag on wicks + entry
            if newd[k]:
                d_, ext, piv, fired = 0, k, k, False; lo0 = hi0 = k; continue
            if d_ == 0:
                if L[k] < L[lo0]: lo0 = k
                if H[k] > H[hi0]: hi0 = k
                if H[k] >= L[lo0] * (1 + pct): d_, piv, ext, fired = 1, lo0, k, False
                elif L[k] <= H[hi0] * (1 - pct): d_, piv, ext, fired = -1, hi0, k, False
                continue
            if d_ == 1:
                if H[k] > H[ext]: ext = k
                elif L[k] <= H[ext] * (1 - pct): piv, d_, ext, fired = ext, -1, k, False; continue
            else:
                if L[k] < L[ext]: ext = k
                elif H[k] >= L[ext] * (1 + pct): piv, d_, ext, fired = ext, 1, k, False; continue
            if not fired and k - piv >= N:
                fired = True
                if not pos and k + 1 < n and not newd[k + 1] and 90 <= hm[k] < 1320 and wd[k] < 5:
                    dr = -d_
                    pos.append([O[k + 1] if dr == -1 else O[k + 1] + sp[k + 1], dr, k + 1, 1])
        T_ = pd.DataFrame(baskets, columns=["k", "pnl", "np", "mu"]); T_["t"] = B.index[T_.k.values]
        g, ls = T_.pnl[T_.pnl > 0].sum(), -T_.pnl[T_.pnl < 0].sum()
        l12 = T_.t >= end - pd.Timedelta(days=365)
        daily = T_.groupby(T_.t.dt.normalize()).pnl.sum()
        say(f"\n--- {label} ---")
        say(f"baskets {len(T_):,} ({len(T_) / ndays:.1f}/day), won {100 * (T_.pnl > 0).mean():.1f}%, PF {g / ls if ls else 0:.2f}, "
            f"net ${T_.pnl.sum():+,.0f}; avg win ${T_.pnl[T_.pnl > 0].mean():.2f}, avg loss ${T_.pnl[T_.pnl < 0].mean():.2f}")
        say(f"reached entry 5: {100 * (T_.np >= 5).mean():.1f}% of baskets; biggest lot asked {maxu / 100:.2f}; "
            f"worst floating ${worst_fl:+.0f}; worst day ${daily.min():+.0f}")
        say(f"ACCOUNT $100 STOPPED OUT {blow} times in 6.6 years; last 12 months: net ${T_[l12].pnl.sum():+.0f}, "
            f"stop-outs {sum(1 for q in bt if B.index[q] >= end - pd.Timedelta(days=365))}")

    run(2.0, label="recovery lot, +$1 if price retraces $2 from the last entry")
    run(4.0, label="recovery lot, +$1 if price retraces $4 (one full step)")
    run(4.0, maxn=3, label="recovery lot, retrace $4, max 3 entries")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
