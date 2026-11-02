"""Round 20 (3 Nov 2026): gold M15 support / resistance flip (RBS / SBR) retest with a rejection candle.

The owner's rule ("support become resistant atau resistance become support, price datang tunggu candle reject lepas tu
next candle entry. tp pada resistant/support seterusnya atau snd terdekat. guna tf m15"), made exact before the run
(server time, M15 bars, buy side shown, sell side mirrored):
  Levels    swing highs / lows: a high that is the highest of K bars on each side (K = 5); known only K bars later.
            Kept for 10 trading days (960 bars).
  Flip      a resistance (swing high) flips to support when an M15 candle closes 0.1 ATR(M15) above it (RBS);
            a support (swing low) flips to resistance on a close 0.1 ATR below it (SBR).
  Retest    after the flip the price first moves away (a high at least 0.5 ATR beyond the level), then comes back:
            a candle touches the level (low <= level + 0.2 ATR). The flip fails on a close 0.2 ATR back through the
            level, and expires after 96 bars (one day). One trade per flipped level.
  Reject    the touching candle closes back above the level, with a lower wick >= 40% of its range and the close in
            the upper half (REJ). Entry at the open of the next candle.
  SL        0.1 ATR beyond the rejection candle's wick.
  TP        the nearest of: the next S/R level above (any kept swing high / low at least 0.3 ATR above the close) or
            the nearest fresh supply zone (M15 SnD: 1-3 base candles, then a leg-out candle >= 1.5 ATR with body
            >= 60%; target = its proximal line). No level above: 2R.
  Flat      signal candles 01:30-21:30, everything closed at 23:00 or at the day's last candle (Friday 22:45 in
            winter), so nothing is held overnight or over the weekend.
Variants: REJ_RR1 (skip when the TP is < 1R away), PIN (lower wick >= 60%), TOUCH (any touch that closes back
above the level: does the rejection matter?), REJ_SRONLY (TP only at S/R, no SnD), REJ_2R (fixed 2R), REJ_K3 /
REJ_K10 (smaller / bigger swings). Control: FAKE = REJ on fake levels (every swing moved 1 ATR up or down at random;
targets still from the real levels). Costs: the M15 bar's median spread on every trade; STRESS = 1.5x spread.
Fixed 0.01 lot, so the PF is in dollars (a $1 gold move = $1 at 0.01 lot).
The owner asked for 1 month first; the last 3 months and the whole 2020-2026 export are shown too, with the usual pass
rule (>= 150 trades, PF >= 1.15, halves >= 1.05, stress >= 1.05, last 12 months positive, PF 0.10 above FAKE).
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYM = "XAUUSD"
T0 = time.time()
KEEP = 960


def say(s=""):
    print(s, flush=True)


def swings(h, l, K):
    """(confirm bar, level, +1 swing high / -1 swing low, swing bar), in confirm order (online: known after bar p+K)"""
    n = len(h)
    out = []
    for p in range(K, n - K):
        if h[p] > h[p - K:p].max() and h[p] >= h[p + 1:p + K + 1].max():
            out.append((p + K, h[p], 1, p))
        if l[p] < l[p - K:p].min() and l[p] <= l[p + 1:p + K + 1].min():
            out.append((p + K, l[p], -1, p))
    out.sort()
    return out


def snd_zones(o, h, l, c, A, max_base=3, base_body=0.5, base_atr=1.0, legout_atr=1.5, max_h=1.5):
    """M15 SnD zones: (leg-out bar, dir +1 demand / -1 supply, proximal, distal)"""
    rng = h - l
    body = np.abs(c - o)
    out = []
    for i in range(20, len(o)):
        a = A[i]
        if not np.isfinite(a) or rng[i] <= 0 or body[i] < 0.6 * rng[i] or rng[i] < legout_atr * a:
            continue
        dr = 1 if c[i] > o[i] else -1
        k = 0
        while k < max_base and i - k - 1 >= 0:
            j = i - k - 1
            if rng[j] > 0 and body[j] <= base_body * rng[j] and rng[j] <= base_atr * a:
                k += 1
            else:
                break
        if k == 0:
            continue
        b = np.arange(i - k, i)
        if dr == 1:
            if c[i] <= h[b].max():
                continue
            prox, dist = np.maximum(o[b], c[b]).max(), min(l[b].min(), l[i])
        else:
            if c[i] >= l[b].min():
                continue
            prox, dist = np.minimum(o[b], c[b]).min(), max(h[b].max(), h[i])
        if 0 < abs(prox - dist) <= max_h * a:
            out.append((i, dr, prox, dist))
    return out


def signals(B, K, rej, tp_mode, rr_min=0.0, fake=False, seed=5):
    o, h, l, c, A, hm = (B[x].values for x in ("o", "h", "l", "c", "atr", "hm"))
    n = len(B)
    sw = swings(h, l, K)
    zs = snd_zones(o, h, l, c, A)
    rs = np.random.default_rng(seed)
    real = []                                   # (confirm bar, price) of the real levels, for the targets
    watch = []                                  # unflipped levels: [price, type, born]
    flips = []                                  # flipped levels: dict
    zones = []                                  # fresh SnD zones: [dir, prox, dist]
    si = zi = 0
    out = []
    for i in range(1, n - 1):
        a = A[i]
        # zones that are used / broken by this bar (a zone formed earlier than bar i)
        if zones:
            keep = []
            for z in zones:
                dr, prox, dist = z
                if (dr == -1 and h[i] >= prox) or (dr == 1 and l[i] <= prox):
                    continue                    # touched: no longer fresh
                keep.append(z)
            zones = keep
        while zi < len(zs) and zs[zi][0] <= i:
            zones.append([zs[zi][1], zs[zi][2], zs[zi][3]]); zi += 1
        while si < len(sw) and sw[si][0] <= i:
            cb, px, tp_, p = sw[si]; si += 1
            real.append((cb, px))
            if fake and np.isfinite(A[p]):
                px = px + rs.choice([-1.0, 1.0]) * A[p]
            watch.append([px, tp_, cb])
        if not np.isfinite(a):
            continue
        # flips: a close 0.1 ATR beyond an unflipped level (levels added at bar i act from bar i+1)
        keep = []
        for w in watch:
            px, tp_, born = w
            if i - born > KEEP:
                continue
            if born < i and ((tp_ == 1 and c[i] > px + 0.1 * a) or (tp_ == -1 and c[i] < px - 0.1 * a)):
                flips.append(dict(px=px, dir=tp_, k=i, a=a, away=False))   # dir +1: old resistance, now support (buy)
                continue
            keep.append(w)
        watch = keep
        # retests of flipped levels
        keep = []
        for f in flips:
            if f["k"] == i:
                keep.append(f); continue
            if i - f["k"] > 96:
                continue
            px, dr, fa = f["px"], f["dir"], f["a"]
            if (dr == 1 and c[i] < px - 0.2 * fa) or (dr == -1 and c[i] > px + 0.2 * fa):
                continue                                                  # flip failed
            if not f["away"]:
                if (dr == 1 and h[i] >= px + 0.5 * fa) or (dr == -1 and l[i] <= px - 0.5 * fa):
                    f["away"] = True
                keep.append(f); continue
            touch = (dr == 1 and l[i] <= px + 0.2 * fa) or (dr == -1 and h[i] >= px - 0.2 * fa)
            if not touch:
                keep.append(f); continue
            rg = h[i] - l[i]
            back = (dr == 1 and c[i] > px) or (dr == -1 and c[i] < px)
            wick = (min(o[i], c[i]) - l[i]) if dr == 1 else (h[i] - max(o[i], c[i]))
            upper = (c[i] >= l[i] + 0.5 * rg) if dr == 1 else (c[i] <= h[i] - 0.5 * rg)
            if rej == "touch":
                ok = back
            elif rej == "pin":
                ok = back and rg > 0 and wick >= 0.6 * rg
            else:
                ok = back and rg > 0 and wick >= 0.4 * rg and upper
            if not ok:
                keep.append(f); continue
            if not (90 <= hm[i] <= 1290):
                continue                                                  # level used up outside the trading hours
            sl = (l[i] - 0.1 * a) if dr == 1 else (h[i] + 0.1 * a)
            ref = c[i]
            cand, src = [], []
            if tp_mode in ("sr", "srsnd"):
                for cb, lv in real:
                    if i - cb <= KEEP and (lv - ref) * dr >= 0.3 * a:
                        cand.append(lv); src.append("SR")
            if tp_mode == "srsnd":
                for zd, prox, dist in zones:
                    if zd == -dr and (prox - ref) * dr >= 0.3 * a:
                        cand.append(prox); src.append("SnD")
            g = dict(k0=i + 1, kind="mkt", dir=dr, sl=sl, exp=i + 1, maxb=10 ** 6, lvl=px, sig=i)
            if tp_mode == "2r" or not cand:
                g["tp_r"] = 2.0; g["src"] = "2R"
            else:
                j = int(np.argmin([(x - ref) * dr for x in cand]))
                g["tp"] = cand[j]; g["src"] = src[j]
                if rr_min > 0 and (cand[j] - ref) * dr < rr_min * (ref - sl) * dr:
                    continue
            out.append(g)
        flips = keep
        if len(real) > 4000:
            real = [x for x in real if i - x[0] <= KEEP]
    return out


VARIANTS = {
    "REJ":        dict(K=5, rej="rej", tp_mode="srsnd"),
    "REJ_RR1":    dict(K=5, rej="rej", tp_mode="srsnd", rr_min=1.0),
    "PIN":        dict(K=5, rej="pin", tp_mode="srsnd"),
    "TOUCH":      dict(K=5, rej="touch", tp_mode="srsnd"),
    "REJ_SRONLY": dict(K=5, rej="rej", tp_mode="sr"),
    "REJ_2R":     dict(K=5, rej="rej", tp_mode="2r"),
    "REJ_K3":     dict(K=3, rej="rej", tp_mode="srsnd"),
    "REJ_K10":    dict(K=10, rej="rej", tp_mode="srsnd"),
    "FAKE":       dict(K=5, rej="rej", tp_mode="srsnd", fake=True),
}


def flat_mask(B):
    """close at 23:00 server, and at the last candle before any gap (Friday's gold close is at 22:45 in winter)"""
    dates = B.date.values
    newday = np.r_[True, dates[1:] != dates[:-1]]
    lastbar = np.r_[dates[1:] != dates[:-1], True]
    return (B.hm.values >= 1380) | newday | lastbar


def stats(x, usd):
    if len(x) == 0:
        return None
    net = (x.pnl - x.sp).values
    st = (x.pnl - 1.5 * x.sp).values
    return dict(n=len(x), win=100 * (net > 0).mean(), pf=SA.pf(net), st=SA.pf(st), usd=net.sum() * usd)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    m = meta[SYM]
    usd = m["tick_value"] / m["tick_size"] * 0.01 if m["tick_size"] > 0 else 1.0
    d5 = SA.load(os.path.join(DATA, SYM + ".csv"), m["point"])
    B = DT.bars(d5, "15min")
    flat = flat_mask(B)
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    end = B.index[-1]
    mid = B.index[len(B) // 2]
    t1m, t3m, t12 = end - pd.Timedelta(days=31), end - pd.Timedelta(days=92), end - pd.Timedelta(days=365)
    days = B.index.normalize().nunique()
    days1 = B.index[B.index >= t1m].normalize().nunique()
    say(f"{SYM} M15 {B.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d %H:%M} server, {days} days; last month = {t1m:%Y-%m-%d} .. "
        f"{end:%Y-%m-%d} ({days1} trading days); median spread ${np.median(B.s.values):.2f}; $ per 1.00 move at 0.01 lot = {usd:.2f}")
    res = {}
    for name, kw in VARIANTS.items():
        S = signals(B, **kw)
        info = {g["k0"]: g for g in S}
        tr = SA.sim(*arr, sorted(S, key=lambda g: g["k0"]), flat)
        T = pd.DataFrame(tr, columns=["k", "dir", "pnl", "sp", "risk", "why"])
        T["t"] = B.index[T.k.values]
        T["src"] = [info[k]["src"] if k in info else "?" for k in T.k]
        T["lvl"] = [info[k]["lvl"] if k in info else np.nan for k in T.k]
        T["slp"] = [info[k]["sl"] for k in T.k]
        T["e"] = [arr[0][k] for k in T.k]
        T["tpp"] = [info[k].get("tp", np.nan) for k in T.k]
        T["tpp"] = T.tpp.fillna(T.e + T.dir * 2.0 * T.risk)                # 2R targets
        res[name] = T
        say(f"  {name} done: {len(S)} signals, {len(T)} trades, {time.time() - T0:.0f} s")

    def line(name, T, lab):
        s = stats(T, usd)
        if s is None:
            return f"{name:11s} {lab:5s} no trades"
        return (f"{name:11s} {lab:5s} {s['n']:5d} {s['n'] / (days1 if lab == '1M' else (92 * 5 / 7 if lab == '3M' else days)):5.2f} "
                f"{s['win']:5.1f} {SA.f2(s['pf'])} {SA.f2(s['st'])} {s['usd']:+9.2f}")

    say("\nrule        period trades /day  win%  PF$  stress  net $ (0.01 lot)")
    for name, T in res.items():
        say(line(name, T[T.t >= t1m], "1M"))
        say(line(name, T[T.t >= t3m], "3M"))
        say(line(name, T, "ALL"))
    say("\nWhole export, pass rule:")
    say("rule        trades  PF$  half1 half2 stress last12$  vsFAKE  by year (PF$)")
    fk = stats(res["FAKE"], usd)
    for name, T in res.items():
        s = stats(T, usd)
        if s is None:
            continue
        net = (T.pnl - T.sp).values
        h1, h2 = SA.pf(net[(T.t < mid).values]), SA.pf(net[(T.t >= mid).values])
        l12 = net[(T.t >= t12).values].sum() * usd
        yr = " ".join(f"{y % 100}:{SA.f2(SA.pf(net[(T.t.dt.year == y).values])).strip()}" for y in sorted(T.t.dt.year.unique()))
        ok = s["n"] >= 150 and s["pf"] >= 1.15 and h1 >= 1.05 and h2 >= 1.05 and s["st"] >= 1.05 and l12 > 0 and \
            (name == "FAKE" or s["pf"] - fk["pf"] >= 0.10)
        say(f"{name:11s} {s['n']:6d} {SA.f2(s['pf'])} {SA.f2(h1)} {SA.f2(h2)} {SA.f2(s['st'])} {l12:+8.0f} "
            f"{s['pf'] - fk['pf']:+6.2f}  {yr} {'PASS' if ok and name != 'FAKE' else ''}")
    T = res["REJ"]
    say("\nREJ by side and target (whole export / last month):")
    for lab, X in (("ALL", T), ("1M", T[T.t >= t1m])):
        for side, nm in ((1, "BUY (RBS)"), (-1, "SELL (SBR)")):
            s = stats(X[X.dir == side], usd)
            if s:
                say(f"  {lab:3s} {nm:10s} {s['n']:5d} trades, win {s['win']:.0f}%, PF$ {SA.f2(s['pf']).strip()}, {s['usd']:+.2f} $")
        for src in ("SR", "SnD", "2R"):
            s = stats(X[X.src == src], usd)
            if s:
                say(f"  {lab:3s} TP {src:7s} {s['n']:5d} trades, win {s['win']:.0f}%, PF$ {SA.f2(s['pf']).strip()}, {s['usd']:+.2f} $")
        rr = ((X.tpp - X.e) * X.dir / X.risk).dropna()
        if len(rr):
            say(f"  {lab:3s} planned reward / risk: median {rr.median():.2f}, {100 * (rr < 1).mean():.0f}% of trades below 1R; "
                f"median risk ${X.risk.median() * usd:.2f}, median spread ${X.sp.median() * usd:.2f}")
    say("\nREJ trades in the last month (Malaysia time):")
    X = T[T.t >= t1m]
    for _, r in X.iterrows():
        tm = r.t.tz_localize("Europe/Athens", ambiguous=True, nonexistent="shift_forward").tz_convert("Asia/Kuala_Lumpur")
        say(f"  {tm:%a %d/%m %H:%M} {'BUY ' if r.dir == 1 else 'SELL'} level {r.lvl:.2f}  entry {r.e:.2f}  SL {r.slp:.2f}  "
            f"TP {r.tpp:.2f} ({r.src})  -> {r.why:4s} {(r.pnl - r.sp) * usd:+7.2f} $")
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
