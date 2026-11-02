"""Gold H1 detail for the round-19 passes (2 Nov 2026): Ichimoku Kumo breakout, RSI divergence, MACD divergence.
Adds what round19.py left out: swap for positions held overnight (long -4% / short -1% of the price a year, triple on
Wednesdays, $ per 0.01 lot), a day-trade variant (flat at 23:00 server, no swap), long / short split, years, the
holding time and the drawdown. Also the RAND baseline with the same treatment."""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import round19 as R19

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"


def sim2(o, h, l, c, sp, sigs, flat):
    """sigs: list of dicts with k0 (first bar the order is live), kind mkt/stop/oco, dir, P (stop price),
    P2/sl2 (sell leg of an oco), sl, tp or tp_r, exp (last bar the order is live), maxb, xl/xs exit flags,
    end (bar index at which to flatten at the open). Returns a list of trades."""
    n = len(o)
    out = []
    busy = -1
    for g in sigs:
        k0 = g["k0"]
        if k0 <= busy or k0 >= n:
            continue
        kind = g["kind"]
        end = min(g.get("end", n), n)
        exp = min(g.get("exp", k0), n - 1)
        pos = None
        k = k0
        # ---- pending / fill
        while k <= exp and k < end:
            if flat[k]:
                break
            a = o[k]
            path = (o[k], l[k], h[k], c[k]) if c[k] >= o[k] else (o[k], h[k], l[k], c[k])
            fill = None
            if kind == "mkt":
                fill, dr, sl, seg = a, g["dir"], g["sl"], 0
            else:
                for si in range(3):
                    x, y = path[si], path[si + 1]
                    # buy leg
                    if (kind == "oco" or g["dir"] == 1):
                        P = g["P"]
                        if si == 0 and x >= P:
                            fill, dr, sl, seg = x, 1, g["sl"], si; break
                        if y >= P > x:
                            fill, dr, sl, seg = P, 1, g["sl"], si; break
                    if (kind == "oco" or g["dir"] == -1):
                        P = g["P2"] if kind == "oco" else g["P"]
                        sl_ = g["sl2"] if kind == "oco" else g["sl"]
                        if si == 0 and x <= P:
                            fill, dr, sl, seg = x, -1, sl_, si; break
                        if y <= P < x:
                            fill, dr, sl, seg = P, -1, sl_, si; break
            if fill is not None:
                risk = (fill - sl) * dr
                if risk <= 0:
                    fill = None
                    break
                tp = g.get("tp")
                if g.get("tp_r"):
                    tp = fill + dr * g["tp_r"] * risk
                if tp is not None and (tp - fill) * dr <= 0:
                    fill = None
                    break
                pos = dict(k=k, dir=dr, e=fill, sl=sl, tp=tp, risk=risk, sp=sp[k], seg=seg)
                break
            k += 1
        if pos is None:
            busy = max(busy, min(k, exp))
            continue
        # ---- position
        dr, sl, tp, e = pos["dir"], pos["sl"], pos["tp"], pos["e"]
        xl, xs = g.get("xl"), g.get("xs")
        maxb = g.get("maxb", 10 ** 9)
        k = pos["k"]
        first = True
        ex = None
        why = ""
        while k < n:
            if not first:
                if k - pos["k"] >= maxb or flat[k] or k >= end:
                    ex, why = o[k], "time"; break
                if (dr == 1 and xl is not None and xl[k - 1]) or (dr == -1 and xs is not None and xs[k - 1]):
                    ex, why = o[k], "exit"; break
                if (o[k] - sl) * dr <= 0:
                    ex, why = o[k], "SL"; break
                if tp is not None and (o[k] - tp) * dr >= 0:
                    ex, why = o[k], "TP"; break
            path = (o[k], l[k], h[k], c[k]) if c[k] >= o[k] else (o[k], h[k], l[k], c[k])
            s0 = pos["seg"] if first else 0
            for si in range(s0, 3):
                x, y = path[si], path[si + 1]
                if first and si == s0:
                    x = e
                if dr == 1:
                    if y < x and y <= sl:
                        ex, why = sl, "SL"; break
                    if y > x and tp is not None and y >= tp:
                        ex, why = tp, "TP"; break
                else:
                    if y > x and y >= sl:
                        ex, why = sl, "SL"; break
                    if y < x and tp is not None and y <= tp:
                        ex, why = tp, "TP"; break
            if ex is not None:
                break
            first = False
            k += 1
        if ex is None:
            ex, why, k = c[n - 1], "end", n - 1
        out.append((pos["k"], dr, (ex - e) * dr, pos["sp"], pos["risk"], why, k))
        busy = k
    return out




def report(name, B, res, mid, end):
    if not res:
        print(f"{name}: no trades"); return
    T = pd.DataFrame(res, columns=["k", "dir", "pnl", "sp", "risk", "why", "kx"])
    idx = B.index
    dates = B.date.values
    nights, swap = [], []
    for k, dr, kx in zip(T.k, T.dir, T.kx):
        ds = pd.unique(dates[k:kx + 1])
        nn = len(ds) - 1
        wed = sum(1 for d in ds[1:] if pd.Timestamp(d).dayofweek == 3)      # rollover into Thursday = triple
        nights.append(nn)
        rate = 0.04 if dr == 1 else 0.01
        swap.append(-rate / 360 * B.c.values[k] * (nn + 2 * wed))
    T["swap"] = swap
    T["net"] = T.pnl - T.sp + T.swap
    t = idx[T.k.values]
    h2 = t >= mid
    l12 = t >= end - pd.Timedelta(days=365)
    net = T.net.values
    R = net / T.risk.values
    eq = np.cumsum(net)
    dd = (eq - np.maximum.accumulate(eq)).min()
    st = (T.pnl - 1.5 * T.sp + T.swap).values
    print(f"{name:26s} {len(T):5d} trades, hold {np.mean(T.kx - T.k):5.1f} bars, nights {np.mean(nights):.2f}, swap ${T.swap.sum():+.0f} | "
          f"PF(R) {SA.f2(SA.pf(R))} halves {SA.f2(SA.pf(R[~h2]))} {SA.f2(SA.pf(R[h2]))} stress {SA.f2(SA.pf(st / T.risk.values))} | "
          f"net ${net.sum():+.0f} per 0.01 lot, last 12 months ${net[l12].sum():+.0f}, max DD ${dd:.0f}")
    for dr, nm in ((1, "BUY"), (-1, "SELL")):
        m = T.dir.values == dr
        print(f"{'':26s} {nm:4s} {m.sum():5d} trades PF(R) {SA.f2(SA.pf(R[m]))} net ${net[m].sum():+.0f}")
    yrs = pd.Series(net, index=t).groupby(t.year).sum()
    print(f"{'':26s} by year $: " + " ".join(f"{y}:{v:+.0f}" for y, v in yrs.items()))


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    d5 = SA.load(os.path.join(DATA, "XAUUSD.csv"), meta["XAUUSD"]["point"])
    B = DT.bars(d5, "1h")
    mid, end = d5.index[len(d5) // 2], d5.index[-1]
    dates = B.date.values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    rng = np.random.default_rng(19)
    for mode, flat, maxb in (("hold up to 48 h", np.zeros(len(B), bool), 48), ("day trade (flat 23:00)", (B.hm.values >= 1380) | newday, 10 ** 6)):
        print(f"\n==== XAUUSD H1, {mode} ====")
        S, _ = R19.build(B, maxb, rng)
        for r in ("ICHI_KUMO", "DIV_RSI", "DIV_MACD", "ICHI_TK"):
            report(f"{r} ({mode.split()[0]})", B, sim2(*arr, sorted(S[r], key=lambda g: g["k0"]), flat), mid, end)
        hm = B.hm.values
        A = B.atr.values
        cand = np.where((hm >= 90) & (hm < 1320) & np.isfinite(A))[0]
        cand = cand[cand < len(B) - 2]
        for seed in range(3):
            rr = np.random.default_rng(100 + seed)
            pick = np.sort(rr.choice(cand, size=1000, replace=False))
            sig = [dict(k0=i + 1, kind="mkt", dir=(1 if rr.random() < 0.5 else -1), sl=0.0, tp_r=2.0, exp=i + 1, maxb=maxb) for i in pick]
            for g in sig:
                g["sl"] = B.c.values[g["k0"] - 1] - g["dir"] * 1.5 * A[g["k0"] - 1]
            report(f"RAND seed {seed}", B, sim2(*arr, sig, flat), mid, end)


if __name__ == "__main__":
    main()
