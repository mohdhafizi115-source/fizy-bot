"""Round 120 (15 Nov 2026): the "Cara scalping di M5 BTCUSD" infographic (richway.id) on the broker's BTCUSD, judged on the LAST 3
MONTHS with the 3 months before as a repeat check.  Owner: "cuba ni".
Rules as drawn: trend from M15 / H1 (EMA 20 vs EMA 50 of the last CLOSED bar); on M5 BUY when (1) price pulled back to EMA 20 / EMA 50
(the low touched EMA 20 in the last 3 bars, or EMA 50 for the "EMA50" variant), (2) Stochastic (5,3,3) %K crosses above %D from
oversold (< 20), (3) RSI 14 > 50, (4) a bullish candle (close > open), (5) enter at the next M5 open; SELL mirrored (> 80, < 50, bearish).
SL 0.5%, TP1 0.8%, TP2 1.5% of the entry; exits: TP1 only / TP2 only / half at TP1 + SL to break-even + half at TP2.  One position,
max 24 h, broker swap per night (long -$0.85 / short -$0.56 at 0.01 lot, round 103).  Variants drop one condition at a time; control:
the same entries with a RANDOM direction.  Simulated on M1 (SL first when both are hit in one minute).  0.01 lot = $0.01 per $1."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
jit = G.jit
SWL, SWS = -0.85, -0.56


@jit
def sim(O, H, L, S, dayid, eidx, edir, slp, tp1, tp2, mode, maxb, usd):
    n = len(eidx); pn = np.zeros(n); xi = np.full(n, -1, np.int64); last = -1; N = len(O)
    for k in range(n):
        j0 = eidx[k]
        if j0 <= last or j0 >= N - 2: continue
        d = edir[k]
        ent = O[j0] + S[j0] if d == 1 else O[j0]
        sl = ent * (1 - d * slp); t1 = ent * (1 + d * tp1); t2 = ent * (1 + d * tp2)
        half = False; be = False; pnl = 0.0; frac = 1.0; done = False; j = j0
        jend = min(j0 + maxb, N - 1)
        while j < jend:
            if j > j0 and dayid[j] != dayid[j - 1]:
                pnl += frac * (SWL if d == 1 else SWS)
            lo = L[j] if d == 1 else L[j] + S[j]
            hi = H[j] if d == 1 else H[j] + S[j]
            if d == 1:
                if lo <= sl:
                    pnl += frac * (min(O[j], sl) - ent) * usd; done = True; break
            else:
                if hi >= sl:
                    pnl += frac * (ent - max(O[j] + S[j], sl)) * usd; done = True; break
            if mode == 0 or mode == 1:
                t = t1 if mode == 0 else t2
                if d == 1 and hi >= t: pnl += (t - ent) * usd; done = True; break
                if d == -1 and lo <= t: pnl += (ent - t) * usd; done = True; break
            else:
                if not half:
                    if (d == 1 and hi >= t1) or (d == -1 and lo <= t1):
                        pnl += 0.5 * abs(t1 - ent) * usd; frac = 0.5; half = True; sl = ent
                else:
                    if (d == 1 and hi >= t2) or (d == -1 and lo <= t2):
                        pnl += 0.5 * abs(t2 - ent) * usd; done = True; break
            j += 1
        if not done:
            px = O[j] if d == 1 else O[j] + S[j]
            pnl += frac * (px - ent) * d * usd
        pn[k] = pnl; xi[k] = j0; last = j
    return pn, xi


def ema(x, n): return x.ewm(span=n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def main():
    mt, sw = W.read_meta("BTCUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "BTCUSD.csv"), mt["point"])
    end = d.index[-1]; a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    d = d[d.index >= a6 - pd.Timedelta(days=20)]
    O, H, L, C, S = (d[k].values.astype(float) for k in ("o", "h", "l", "c", "s"))
    T = d.index; dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    say(f"BTCUSD M5 SCALP (infographic), LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), $ at 0.01 lot")
    say(f"median price {np.median(C):.0f}, median spread ${np.median(S) * usd:.2f}, 0.5% SL ~ ${np.median(C) * 0.005 * usd:.2f}")
    agg = dict(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    m5 = d.resample("5min", label="left", closed="left").agg(**agg).dropna()
    m5["e20"] = ema(m5.c, 20); m5["e50"] = ema(m5.c, 50); m5["rsi"] = rsi(m5.c)
    ll = m5.l.rolling(5).min(); hh = m5.h.rolling(5).max()
    m5["k"] = ((m5.c - ll) / (hh - ll) * 100).rolling(3).mean(); m5["dd"] = m5.k.rolling(3).mean()
    trend = {}
    for nm, fr, per in (("M15", "15min", pd.Timedelta(minutes=15)), ("H1", "1h", pd.Timedelta(hours=1))):
        X = d.resample(fr, label="left", closed="left").agg(**agg).dropna()
        tr = np.sign(ema(X.c, 20) - ema(X.c, 50)); tr.index = X.index + per
        trend[nm] = tr.reindex(m5.index + pd.Timedelta(minutes=5), method="ffill").values
    trend["none"] = np.zeros(len(m5))
    pos = pd.Series(np.arange(len(T)), index=T)
    nxt = pos.reindex(m5.index + pd.Timedelta(minutes=5), method="bfill").values
    k, dd_, r, c, o, l, h, e20, e50 = (m5[x].values for x in ("k", "dd", "rsi", "c", "o", "l", "h", "e20", "e50"))
    up_x = (k > dd_) & (np.roll(k, 1) <= np.roll(dd_, 1)) & (np.minimum(np.roll(k, 1), np.roll(dd_, 1)) < 20)
    dn_x = (k < dd_) & (np.roll(k, 1) >= np.roll(dd_, 1)) & (np.maximum(np.roll(k, 1), np.roll(dd_, 1)) > 80)
    up_x3 = up_x | np.roll(up_x, 1) | np.roll(up_x, 2); dn_x3 = dn_x | np.roll(dn_x, 1) | np.roll(dn_x, 2)
    lmin3 = pd.Series(l).rolling(3).min().values; hmax3 = pd.Series(h).rolling(3).max().values
    pb20_b = lmin3 <= e20; pb20_s = hmax3 >= e20; pb50_b = lmin3 <= e50; pb50_s = hmax3 >= e50
    nd3 = (T >= a3).sum() / 1440 / 7
    hdr = (f"{'variant':46s} | {'trd':>4} {'/wk':>5} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} {'buyPF':>5} {'selPF':>5} | "
           f"{'prev trd':>8} {'PF':>5} {'net$':>6}")
    say(hdr)

    def run(nm, bmask, smask, mode, rng=None):
        sig = np.where(bmask, 1, np.where(smask, -1, 0))
        idx = np.where((sig != 0) & np.isfinite(nxt))[0]
        ei = nxt[idx].astype(np.int64); ed = sig[idx].astype(np.int64)
        if rng is not None: ed = rng.choice([-1, 1], len(ed)).astype(np.int64)
        p, xi = sim(O, H, L, S, dayid, ei, ed, 0.005, 0.008, 0.015, mode, 1440, usd)
        pS, xS = sim(O, H, L, S * 1.5, dayid, ei, ed, 0.005, 0.008, 0.015, mode, 1440, usd)
        ok = xi >= 0; te = T[xi[ok]]; p = p[ok]; dr = ed[ok]
        m = te >= a3; m2 = (te >= a6) & (te < a3); x = p[m]
        if len(x) == 0: say(f"{nm:46s} |    0"); return
        dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = (eq - eq.cummax()).min()
        okS = xS >= 0
        say(f"{nm:46s} | {len(x):4d} {len(x) / nd3:5.1f} {100 * (x > 0).mean():4.0f} {pf(x):5.2f} {pf(pS[okS][T[xS[okS]] >= a3]):5.2f} {x.sum():+6.0f} "
            f"{min(ddn, 0):+5.0f} {dp.min():+5.0f} {pf(x[dr[m] == 1]):5.2f} {pf(x[dr[m] == -1]):5.2f} | {m2.sum():8d} {pf(p[m2]):5.2f} {p[m2].sum():+6.0f}")

    modes = ((0, "TP1 0.8%"), (1, "TP2 1.5%"), (2, "half TP1+BE+TP2"))
    for tf in ("H1", "M15", "none"):
        tr = trend[tf]
        for mode, mn in modes:
            B = (tr >= 0 if tf == "none" else tr > 0) & pb20_b & up_x & (r > 50) & (c > o)
            Sx = (tr <= 0 if tf == "none" else tr < 0) & pb20_s & dn_x & (r < 50) & (c < o)
            run(f"{tf:4s} FULL {mn}", B, Sx, mode)
            if mode == 2:
                run(f"{tf:4s} FULL {mn} RANDOM dir", B, Sx, mode, np.random.default_rng(1))
                run(f"{tf:4s} FULL {mn} RANDOM dir #2", B, Sx, mode, np.random.default_rng(2))
        say("")
    tr = trend["H1"]
    say("H1 trend, half TP1+BE+TP2, one condition changed:")
    base = dict(pb=(pb20_b, pb20_s), x=(up_x, dn_x), r=(r > 50, r < 50), cd=(c > o, c < o))
    vars_ = {"stoch cross within 3 bars": dict(x=(up_x3, dn_x3)), "pullback to EMA 50": dict(pb=(pb50_b, pb50_s)),
             "no pullback": dict(pb=(np.ones_like(up_x), np.ones_like(up_x))), "no stoch": dict(x=(np.ones_like(up_x), np.ones_like(up_x))),
             "no RSI": dict(r=(np.ones_like(up_x), np.ones_like(up_x))), "no candle": dict(cd=(np.ones_like(up_x), np.ones_like(up_x))),
             "stoch 3 + no candle": dict(x=(up_x3, dn_x3), cd=(np.ones_like(up_x), np.ones_like(up_x)))}
    for vn, ch in vars_.items():
        b = dict(base); b.update(ch)
        B = (tr > 0) & b["pb"][0] & b["x"][0] & b["r"][0] & b["cd"][0]
        Sx = (tr < 0) & b["pb"][1] & b["x"][1] & b["r"][1] & b["cd"][1]
        run(f"H1 {vn}", B, Sx, 2)
        run(f"H1 {vn} RANDOM dir", B, Sx, 2, np.random.default_rng(3))


if __name__ == "__main__":
    main()
