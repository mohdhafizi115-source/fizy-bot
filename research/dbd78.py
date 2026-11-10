"""Round 78 (10 Nov 2026): the owner's trend-break + drop-base-drop rule on gold.

Owner: "1. kena uptrend (ada 2 support, 2 resistance)  2. kena breakout uptrend  3. kena breakout support
4. next kena ada drop base drop  5. entry point kena berada dalam zone drop base drop  6. tp : 100pip".

SELL setup (the BUY setup is the exact mirror: downtrend, break up, rally-base-rally):
  1 uptrend     the last two confirmed swing lows rise (2 supports) and the last two swing highs rise (2 resistances);
                swings are fractals of n bars each side, known only n bars later (online)
  2 trend break a close below the line through those two swing lows
  3 support     a close below the last swing low
  4 DBD         a drop-base-drop completes between the trend break and W bars after the support break:
                drop = bearish candle, body >= 60% of its range, range >= 1 ATR(14);
                base = 1-3 candles each with a body <= 50% of its range;
                second drop closes below the base's low
  5 entry       SELL LIMIT inside the zone (the base: lowest low .. highest high), at the zone's near edge
                ("edge") or its middle ("mid"), valid for V bars, only if the zone has not been touched yet
  6 TP          100 pips = $10.  SL (not given by the owner): above the zone + the spread.
One position at a time, no time exit, simulated on M1 bars, spread paid (buys at the ask), SL before TP when
both fall in one bar, no TP on the fill bar.  $ per 0.01 lot.  Timeframes M1 / M5 / M15, n 3 / 5.
Controls: the same fills with a random direction; and every DBD / RBR zone with steps 1-3 removed.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)
TP = 10.0          # 100 pips on gold
W = 10             # bars after the support break in which the DBD may still complete
V = 60             # bars the limit order stays valid


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); sp = B.s.values.astype(float); T = B.index
    end = T[-1]
    say(f"XAUUSD M1 {T[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {n:,} bars")

    def frame(tf):
        if tf == 1: return O, H, L, C, np.arange(n)
        key = T.floor(f"{tf}min")
        df = pd.DataFrame({"o": O, "h": H, "l": L, "c": C, "i": np.arange(n)}).groupby(key.values)
        a = df.agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), i=("i", "last"))
        return a.o.values, a.h.values, a.l.values, a.c.values, a.i.values

    def zones(tf, nn, structure=True):
        """-> list of (M1 index from which the order is live, dir, near edge, far edge, M1 index of expiry)"""
        o, h, l, c, last = frame(tf); m = len(c)
        c1 = np.r_[c[0], c[:-1]]
        tr = np.maximum(h - l, np.maximum(np.abs(h - c1), np.abs(l - c1)))
        atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
        rng = h - l; body = c - o
        dropc = (body < 0) & (-body >= 0.6 * rng) & (rng >= atr)
        rallc = (body > 0) & (body >= 0.6 * rng) & (rng >= atr)
        basec = (np.abs(body) <= 0.5 * rng) & (rng > 0)
        win = 2 * nn + 1
        isH = pd.Series(h).rolling(win, center=True).max().values == h
        isL = pd.Series(l).rolling(win, center=True).min().values == l
        SH = []; SL_ = []                       # (bar, price)
        out = []
        su = None; sd = None                    # active setups: dict(tl=bar of trend break, sb=bar of support break or None, key)
        lastz = {1: None, -1: None}             # latest zone per direction: (bar completed, near, far)
        for j in range(win, m):
            p = j - nn
            if isH[p]: SH.append((p, h[p]))
            if isL[p]: SL_.append((p, l[p]))
            # ---- a DBD (dir -1) / RBR (dir +1) completing on bar j
            for dr, big in ((-1, dropc), (1, rallc)):
                if not big[j]: continue
                for nb in (1, 2, 3):
                    a = j - nb - 1
                    if a < 0 or not big[a] or not basec[a + 1:j].all(): continue
                    zl = l[a + 1:j].min(); zh = h[a + 1:j].max()
                    if dr == -1 and c[j] < zl: lastz[-1] = (j, zl, zh)
                    elif dr == 1 and c[j] > zh: lastz[1] = (j, zh, zl)
                    break
            if not structure:
                for dr in (-1, 1):
                    z = lastz[dr]
                    if z and z[0] == j and j + 1 < m: out.append((last[j] + 1, dr, z[1], z[2], last[min(j + V, m - 1)]))
                continue
            if len(SH) < 2 or len(SL_) < 2: continue
            # ---- steps 1-3, sell side: uptrend, close under the line, close under the last swing low
            (i1, p1), (i2, p2) = SL_[-2], SL_[-1]
            if su is None and p2 > p1 and SH[-1][1] > SH[-2][1]:
                line = p2 + (p2 - p1) / (i2 - i1) * (j - i2)
                if c[j] < line: su = dict(tl=j, sb=None, lvl=p2, key=i2)
            if su is not None:
                if su["sb"] is None:
                    if c[j] < su["lvl"]: su["sb"] = j
                    elif j - su["tl"] > 5 * V or SL_[-1][0] != su["key"] and SL_[-1][1] > su["lvl"]: su = None   # trend resumed
                if su is not None and su["sb"] is not None:
                    z = lastz[-1]
                    if z and z[0] >= su["tl"] and j + 1 < m and h[z[0] + 1:j + 1].max(initial=-1e18) < z[1]:
                        out.append((last[j] + 1, -1, z[1], z[2], last[min(j + V, m - 1)])); su = None; lastz[-1] = None
                    elif j - su["sb"] >= W: su = None
            # ---- mirror, buy side
            (i1, p1), (i2, p2) = SH[-2], SH[-1]
            if sd is None and p2 < p1 and SL_[-1][1] < SL_[-2][1]:
                line = p2 + (p2 - p1) / (i2 - i1) * (j - i2)
                if c[j] > line: sd = dict(tl=j, sb=None, lvl=p2, key=i2)
            if sd is not None:
                if sd["sb"] is None:
                    if c[j] > sd["lvl"]: sd["sb"] = j
                    elif j - sd["tl"] > 5 * V or SH[-1][0] != sd["key"] and SH[-1][1] < sd["lvl"]: sd = None
                if sd is not None and sd["sb"] is not None:
                    z = lastz[1]
                    if z and z[0] >= sd["tl"] and j + 1 < m and l[z[0] + 1:j + 1].min(initial=1e18) > z[1]:
                        out.append((last[j] + 1, 1, z[1], z[2], last[min(j + V, m - 1)])); sd = None; lastz[1] = None
                    elif j - sd["sb"] >= W: sd = None
        return out

    def trade(zs, mode="edge", rand=False):
        res = []; busy = -1; rg = np.random.default_rng(78)
        for k0, dr, near, far, kx in zs:
            if k0 <= busy or k0 >= n: continue
            lim = near if mode == "edge" else (near + far) / 2
            q = k0; e = None
            while q <= min(kx, n - 1):
                if dr == -1 and H[q] >= lim: e = max(O[q], lim); break                 # sell limit, bid
                if dr == 1 and L[q] + sp[q] <= lim: e = min(O[q] + sp[q], lim); break  # buy limit, ask
                q += 1
            if e is None: continue
            s0 = sp[q]
            risk = abs(far - e) + s0
            d2 = dr
            if rand: d2 = 1 if rg.random() < 0.5 else -1
            sl = e - d2 * risk; tp = e + d2 * TP
            x = None; qq = q
            while qq < n:
                first = qq == q
                if d2 == -1:                                                            # short: exits at the ask
                    if H[qq] + sp[qq] >= sl: x = sl if first else max(O[qq] + sp[qq], sl); break
                    if not first and L[qq] + sp[qq] <= tp: x = min(O[qq] + sp[qq], tp); break
                else:                                                                   # long: exits at the bid
                    if L[qq] <= sl: x = sl if first else min(O[qq], sl); break
                    if not first and H[qq] >= tp: x = max(O[qq], tp); break
                qq += 1
            if x is None: x = C[-1] + (sp[-1] if d2 == -1 else 0); qq = n - 1
            res.append((q, (x - e) * d2 * usd, risk * usd, qq - q)); busy = qq
        R = pd.DataFrame(res, columns=["k", "net", "risk", "hold"])
        R["t"] = T[R.k.values] if len(R) else []
        return R

    spans = (("last month", end - pd.Timedelta(days=30)), ("month before", end - pd.Timedelta(days=60)),
             ("last 12 months", end - pd.Timedelta(days=365)), ("all 6.6 years", T[0]))

    def line(R, a, b):
        x = R[(R.t >= a) & (R.t < b)]
        if len(x) == 0: return "no trades"
        g, lo = x.net[x.net > 0].sum(), -x.net[x.net < 0].sum()
        days = max(1, np.busday_count(a.date(), b.date()))
        wd = x.groupby(x.t.dt.normalize()).net.sum().min()
        return (f"{len(x):5d} trades ({len(x) / days:4.2f}/day) win {100 * (x.net > 0).mean():3.0f}% PF {g / lo if lo else 9.99:4.2f} "
                f"net ${x.net.sum():+8.0f} worst day ${wd:+6.0f}")

    def report(name, R, Rr):
        say(f"\n=== {name} ===")
        if len(R) == 0: say("no trades"); return
        say(f"avg SL ${R.risk.mean():.2f} (median {R.risk.median():.2f}), TP ${TP * usd:.0f}; median hold {R.hold.median():.0f} min, longest {R.hold.max() / 1440:.1f} days")
        for i, (nm, a) in enumerate(spans):
            b = end + pd.Timedelta(minutes=1) if nm != "month before" else end - pd.Timedelta(days=30)
            say(f"  {nm:15s} {line(R, a, b)}")
        g, lo = Rr.net[Rr.net > 0].sum(), -Rr.net[Rr.net < 0].sum()
        say(f"  random direction, all years: {len(Rr)} trades, PF {g / lo if lo else 0:.2f}, net ${Rr.net.sum():+.0f}")
        h1 = R[R.t < T[n // 2]]; h2 = R[R.t >= T[n // 2]]
        pf = lambda x: x.net[x.net > 0].sum() / max(1e-9, -x.net[x.net < 0].sum())
        say(f"  halves PF {pf(h1):.2f} / {pf(h2):.2f}; by year: " + " ".join(f"{y}:{v:+.0f}" for y, v in R.groupby(R.t.dt.year).net.sum().items()))

    for tf in (1, 5, 15):
        for nn in (3, 5):
            zs = zones(tf, nn)
            for mode in ("edge", "mid"):
                report(f"M{tf}, swings n={nn}, entry at the zone {mode}: {len(zs)} setups", trade(zs, mode), trade(zs, mode, rand=True))
            say(f"   [{time.time() - T0:.0f} s]")
    for tf in (1, 5, 15):
        zs = zones(tf, 3, structure=False)
        report(f"CONTROL: every DBD / RBR zone on M{tf}, no trend / break conditions, zone edge: {len(zs)} zones", trade(zs, "edge"), trade(zs, "edge", rand=True))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
