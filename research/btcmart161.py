"""Round 161: the live MART basket (v2.57) on BTCUSD, with distances scaled for BTC (owner 22 Nov: "aku nak btc run sama
macam ea live sekarang. tapi kau cari cara macam mana nak setting sebab spread btc berbeza dengan gold").

Live gold v2.57: when flat a BUY STOP ask + K and a SELL STOP bid - K (OCO, the first fill opens the basket), every S against
the LAST entry adds the next lot (k x 0.01), unlimited layers, basket TP where the whole basket nets +Tgt, no SL, 24 h,
held overnight, no daily target. Gold: K = S = $3, Tgt = $3 at 0.01 lot ($1 per $1 per 0.01 lot).

BTCUSD.m: 0.01 lot = $0.01 per $1 of price. Scalings tried:
  * S in price $ (BTC 50 .. 600), K = S (as gold), Tgt = one step at 0.01 lot (S x 0.01 $) or a fixed $3 (gold's money).
  * new baskets every day (BTC trades 7 days) or Monday-Friday only (an open basket always keeps running).
Swap long -0.85 / short -0.56 $ per 0.01 lot per night (round 103), margin 1:100 (round 133 assumption), stop-out at 40%
margin level, $1000 account refilled after a blow-up. Simulated on BTC M1 bars (bid OHLC + spread); a bar touching both
OCO levels is resolved by its colour (bullish O->L->H->C, bearish O->H->L->C); adds are checked before the TP in a bar
(same convention as the gold rounds 146-159). Last 3 months / the 3 before; survival = a $1000 start on every 2nd weekday
of the 6 months, run to the end, counted as blown if it ever stops out (gold live v2.57 on the same test: 26 / 63).
"""
import os, sys
import numpy as np, pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import wti104 as W

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
W.DATA = DATA
SWL, SWS = -0.85, -0.56
LEV = 100.0


def say(s): print(s, flush=True)


@njit(cache=True)
def sim(O, H, L, C, SP, DAY, WD, i0, i1, K, S, Tgt, usd, wdonly, B0):
    bal = B0; blown = 0; nb = 0; net = 0.0; wf = 0.0; first = -1
    npos = 0; d = 0
    lot = np.zeros(4000); ent = np.zeros(4000)
    pend = False; p1 = 0.0; p2 = 0.0; lastday = -1
    maxn = 0
    for i in range(max(i0, 1), i1):
        sp = SP[i]
        if DAY[i] != lastday:
            if npos > 0 and lastday >= 0:
                u = 0.0
                for k in range(npos): u += lot[k]
                bal += u * (SWL if d == 1 else SWS)
            lastday = DAY[i]
        if npos == 0 and not pend:
            if wdonly and WD[i] >= 5:
                continue
            ask = C[i - 1] + sp; bid = C[i - 1]
            p1 = ask + K; p2 = bid - K; pend = True
        if npos == 0 and pend:
            bull = C[i] >= O[i]
            hb = H[i] + sp >= p1; hs = L[i] <= p2
            fd = 0; fp = 0.0
            if hb and hs:
                if bull:
                    fd = -1; fp = min(p2, O[i])
                else:
                    fd = 1; fp = max(p1, O[i] + sp)
            elif hb:
                fd = 1; fp = max(p1, O[i] + sp)
            elif hs:
                fd = -1; fp = min(p2, O[i])
            if fd != 0:
                d = fd; npos = 1; lot[0] = 1.0; ent[0] = fp; pend = False
        if npos > 0:
            while npos < 4000:
                le = ent[npos - 1]
                lvl = le - S if d == 1 else le + S
                if d == 1:
                    hit = L[i] + sp <= lvl
                else:
                    hit = H[i] + sp >= lvl
                if not hit: break
                lot[npos] = npos + 1.0; ent[npos] = lvl; npos += 1
            if npos > maxn: maxn = npos
            nl = 0.0; se = 0.0
            for k in range(npos):
                nl += lot[k]; se += lot[k] * ent[k]
            adv = L[i] if d == 1 else H[i] + sp
            fl = 0.0
            for k in range(npos): fl += lot[k] * (adv - ent[k]) * d * usd
            if fl < wf: wf = fl
            margin = nl * C[i] * 0.01 / LEV
            if bal + fl <= 0.4 * margin:
                loss = -bal; net += loss; nb += 1; blown += 1
                if first < 0: first = i
                bal = B0; npos = 0; pend = False
                continue
            # price where the basket nets +Tgt
            if d == 1:
                tp = (Tgt / usd + se) / nl
                fav = H[i]
                if fav >= tp:
                    pnl = 0.0
                    for k in range(npos): pnl += lot[k] * (tp - ent[k]) * usd
                    bal += pnl; net += pnl; nb += 1; npos = 0
            else:
                tp = (se - Tgt / usd) / nl
                fav = L[i] + sp
                if fav <= tp:
                    pnl = 0.0
                    for k in range(npos): pnl += lot[k] * (ent[k] - tp) * usd
                    bal += pnl; net += pnl; nb += 1; npos = 0
    return nb, net, blown, first, wf, maxn


def main():
    mt, sw = W.read_meta("BTCUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=2)]
    O, H, L, C, SP = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index
    DAY = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    WD = T.dayofweek.values.astype(np.int64)
    dd = d.resample("1D").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).dropna()
    tr = np.maximum(dd.h - dd.l, np.maximum((dd.h - dd.c.shift()).abs(), (dd.l - dd.c.shift()).abs()))
    say(f"ROUND 161  LIVE MART (v2.57) ON BTCUSD, last 3 months {a3:%Y-%m-%d} .. {end:%Y-%m-%d} / previous {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}")
    say(f"BTC: median price {np.median(C):.0f}, median spread {np.median(SP):.1f} (= ${np.median(SP) * usd:.2f} at 0.01 lot), "
        f"median D1 range {np.nanmedian(tr):.0f}; $ per 1.0 of price per 0.01 lot {usd:.4f}; swap {SWL}/{SWS} per 0.01 per night; 1:{LEV:.0f}")
    say("gold live for scale: step $3 = 11.5 spreads ($0.26) = ~4% of a $80 D1 range, $3 per step per 0.01 lot")
    say("")
    ix = lambda t: int(np.searchsorted(T.values, np.datetime64(t)))
    i_a6, i_a3, i_end = ix(a6), ix(a3), len(T)
    starts = [s for s in pd.date_range(a6.normalize(), end.normalize() - pd.Timedelta(days=10), freq="B")][::2]
    si = [ix(s) for s in starts]
    say(f"{'step S':>7} {'spreads':>7} {'%D1':>5} {'TP $':>5} {'days':>4} | last: bask   net$  blown worstfl maxL | prev: bask   net$  blown worstfl maxL | $1000 starts blown")
    rows = []
    for S in (50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 400.0, 600.0):
        for tpm in ("step", "fix3"):
            Tgt = S * usd if tpm == "step" else 3.0
            for wdo in (False, True):
                a = sim(O, H, L, C, SP, DAY, WD, i_a3, i_end, S, S, Tgt, usd, wdo, 1000.0)
                b = sim(O, H, L, C, SP, DAY, WD, i_a6, i_a3, S, S, Tgt, usd, wdo, 1000.0)
                nbl = sum(1 for i in si if sim(O, H, L, C, SP, DAY, WD, i, i_end, S, S, Tgt, usd, wdo, 1000.0)[3] >= 0)
                fa = T[a[3]].strftime("%m-%d") if a[3] >= 0 else "-"
                fb = T[b[3]].strftime("%m-%d") if b[3] >= 0 else "-"
                say(f"{S:7.0f} {S / np.median(SP):7.1f} {100 * S / np.nanmedian(tr):5.1f} {Tgt:5.2f} {'M-F' if wdo else '7d':>4} | "
                    f"{a[0]:5d} {a[1]:+7.0f} {a[2]:3d} {fa:>5} {a[4]:7.0f} {a[5]:4d} | {b[0]:5d} {b[1]:+7.0f} {b[2]:3d} {fb:>5} {b[4]:7.0f} {b[5]:4d} | "
                    f"{nbl:2d} / {len(si)}")
                rows.append((S, tpm, wdo, nbl, a, b))
    say("")
    ok = [r for r in rows if r[3] == 0]
    say(f"cells with 0 of {len(si)} $1000 starts blown: {len(ok)}")
    for S, tpm, wdo, nbl, a, b in sorted(ok, key=lambda r: -(r[4][1] + r[5][1])):
        say(f"  S {S:.0f} TP {tpm} {'M-F' if wdo else '7d'}: last {a[0]} baskets {a[1]:+.0f}, worst floating {a[4]:.0f}, max layers {a[5]} / "
            f"prev {b[0]} baskets {b[1]:+.0f}, worst floating {b[4]:.0f}, max layers {b[5]}")


main()
