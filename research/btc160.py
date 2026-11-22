"""Round 160 (22 Nov 2026): a HIGH-WIN-RATE BTCUSD scalper?  Owner: "carikan aku teknik scalping btc yang win rate tinggi".
Judged on the LAST 3 MONTHS, the 3 months before as a repeat check, on the broker's BTCUSD M1 (fresh export).
A high win rate alone is easy: a small TP and a wide SL win most trades whatever the entry.  So every cell is shown with
(a) its PF / net / DD / worst day and (b) the SAME entries with a RANDOM direction (2 seeds) and (c) RANDOM entry times with
the same exit, so the part of the win rate that comes from the TP / SL ratio alone is visible.
Signals on CLOSED M5 bars (built from M1), entry at the next M5 open (ask for buys = bid + spread), exits checked on M1
(SL first when both hit in one minute), TP / SL in ATR(14, M5) of the signal bar, time cap, broker swap per night,
one position per cell, no entries 23:45-01:30 server.  0.01 lot.
Families: BB 20,2 / 20,2.5 close-outside fade; RSI(2) 5/95 fade (+- H1 EMA 50 side); big M5 candle fade / follow;
H1 EMA 20/50 trend + M5 Stoch 5,3,3 cross out of 20/80 (the live STO idea); 12-bar (1 h) breakout follow; 1 h high / low sweep
and close back inside (fade)."""
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
def sim(O, H, L, S, dayid, eidx, edir, tpd, sld, maxb, usd):
    n = len(eidx); pn = np.zeros(n); xi = np.full(n, -1, np.int64); last = -1; N = len(O)
    for k in range(n):
        j0 = eidx[k]
        if j0 <= last or j0 >= N - 2: continue
        d = edir[k]
        ent = O[j0] + S[j0] if d == 1 else O[j0]
        sl = ent - d * sld[k]; tp = ent + d * tpd[k]
        pnl = 0.0; done = False; j = j0; jend = min(j0 + maxb, N - 1)
        while j < jend:
            if j > j0 and dayid[j] != dayid[j - 1]:
                pnl += SWL if d == 1 else SWS
            if d == 1:
                if L[j] <= sl:
                    pnl += (min(O[j], sl) - ent) * usd; done = True; break
                if H[j] >= tp:
                    pnl += (max(O[j], tp) - ent) * usd if O[j] >= tp else (tp - ent) * usd; done = True; break
            else:
                if H[j] + S[j] >= sl:
                    pnl += (ent - max(O[j] + S[j], sl)) * usd; done = True; break
                if L[j] + S[j] <= tp:
                    pnl += (ent - tp) * usd; done = True; break
            j += 1
        if not done:
            px = O[j] if d == 1 else O[j] + S[j]
            pnl += (px - ent) * d * usd
        pn[k] = pnl; xi[k] = j0; last = j
    return pn, xi


def ema(x, n): return x.ewm(span=n, adjust=False).mean()


def rsi(c, n):
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
    say(f"ROUND 160  BTCUSD HIGH-WIN-RATE SCALP, LAST 3 MONTHS {a3:%Y-%m-%d} .. {end:%Y-%m-%d} (repeat {a6:%Y-%m-%d} .. {a3:%Y-%m-%d}), 0.01 lot")
    agg = dict(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    m5 = d.resample("5min", label="left", closed="left").agg(**agg).dropna()
    c1 = m5.c.shift()
    tr = np.maximum(m5.h - m5.l, np.maximum((m5.h - c1).abs(), (m5.l - c1).abs()))
    m5["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    say(f"median price {np.median(C):.0f}, median spread ${np.median(S) * usd:.2f}, median ATR(M5) ${m5.atr.median() * usd:.2f} at 0.01 lot")
    say("")
    c, o, h, l, atr = (m5[x].values for x in ("c", "o", "h", "l", "atr"))
    sma = m5.c.rolling(20).mean().values; sd = m5.c.rolling(20).std(ddof=0).values
    r2 = rsi(m5.c, 2).values
    ll = m5.l.rolling(5).min(); hh = m5.h.rolling(5).max()
    kk = ((m5.c - ll) / (hh - ll) * 100).rolling(3).mean(); dd_ = kk.rolling(3).mean()
    k_, d_ = kk.values, dd_.values
    k1, d1 = np.roll(k_, 1), np.roll(d_, 1)
    stoU = (k_ > d_) & (k1 <= d1) & (np.minimum(k1, d1) < 20)
    stoD = (k_ < d_) & (k1 >= d1) & (np.maximum(k1, d1) > 80)
    agg2 = d.resample("1h", label="left", closed="left").agg(**agg).dropna()
    def htf(series):
        s = series.copy(); s.index = agg2.index + pd.Timedelta(hours=1)
        return s.reindex(m5.index + pd.Timedelta(minutes=5), method="ffill").values
    h1tr = htf(np.sign(ema(agg2.c, 20) - ema(agg2.c, 50)))
    h1e50 = htf(ema(agg2.c, 50))
    hi12 = m5.h.shift(1).rolling(12).max().values; lo12 = m5.l.shift(1).rolling(12).min().values
    body = (c - o) / atr
    hm = m5.index.hour * 60 + m5.index.minute
    roll = ((hm >= 23 * 60 + 40) | (hm < 85))      # signal bars whose entry falls 23:45-01:30
    pos = pd.Series(np.arange(len(T)), index=T)
    nxt = pos.reindex(m5.index + pd.Timedelta(minutes=5), method="bfill").values
    ok0 = np.isfinite(nxt) & np.isfinite(atr) & ~roll
    nd3 = (T >= a3).sum() / 1440 / 7

    fam = {
        "BB20,2 fade": (c < sma - 2 * sd, c > sma + 2 * sd),
        "BB20,2.5 fade": (c < sma - 2.5 * sd, c > sma + 2.5 * sd),
        "RSI2 5/95 fade": (r2 < 5, r2 > 95),
        "RSI2 5/95 fade H1 EMA50 side": ((r2 < 5) & (c > h1e50), (r2 > 95) & (c < h1e50)),
        "big candle >=2 ATR fade": (body <= -2, body >= 2),
        "big candle >=2.5 ATR follow": (body >= 2.5, body <= -2.5),
        "H1 trend + Stoch 20/80": ((h1tr > 0) & stoU, (h1tr < 0) & stoD),
        "1h breakout follow": (c > hi12, c < lo12),
        "1h sweep + close back fade": ((l < lo12) & (c > lo12), (h > hi12) & (c < hi12)),
    }
    exits = [(0.3, 1.5), (0.5, 1.5), (0.5, 2.0), (0.5, 3.0), (1.0, 2.0), (1.0, 1.0)]
    holds = [60, 240]
    hdr = (f"{'family':30s} {'TP':>4}/{'SL':<4}{'hold':>5} | {'trd':>4} {'/wk':>5} {'win%':>4} {'PF':>5} {'strs':>5} {'net$':>6} {'DD':>5} {'wDay':>5} "
           f"| {'prev':>4} {'win%':>4} {'PF':>5} {'net$':>6} | rnd dir win/PF (2 seeds)  | rnd time win/PF")
    rows = []

    def run(ei, ed, tpa, sla, hold):
        p, xi = sim(O, H, L, S, dayid, ei, ed, tpa, sla, hold, usd)
        okk = xi >= 0; te = T[xi[okk]]; p = p[okk]
        return p, te

    def stats(p, te):
        m = te >= a3; m2 = (te >= a6) & (te < a3); x = p[m]; y = p[m2]
        if len(x) == 0: return None
        dp = pd.Series(x, index=te[m].normalize()).groupby(level=0).sum(); eq = dp.cumsum(); ddn = min((eq - eq.cummax()).min(), 0)
        return dict(n=len(x), wk=len(x) / nd3, win=100 * (x > 0).mean(), pf=pf(x), net=x.sum(), dd=ddn, wd=dp.min(),
                    n2=len(y), win2=100 * (y > 0).mean() if len(y) else 0, pf2=pf(y), net2=y.sum())

    def wp(z): return f"{z['win']:3.0f}/{z['pf']:4.2f}" if z else "  -/  - "

    rng_t = np.random.default_rng(7)
    for fn, (B, Sx) in fam.items():
        say(hdr if fn == list(fam)[0] else "")
        sig = np.where(B, 1, np.where(Sx, -1, 0))
        idx = np.where((sig != 0) & ok0)[0]
        ei = nxt[idx].astype(np.int64); ed = sig[idx].astype(np.int64); a = atr[idx]
        # random entry times: as many M5 bars as signals, drawn from the allowed bars
        pool = np.where(ok0)[0]
        ridx = np.sort(rng_t.choice(pool, size=min(len(idx), len(pool)), replace=False))
        rei = nxt[ridx].astype(np.int64); red = rng_t.choice([-1, 1], len(ridx)).astype(np.int64); ra = atr[ridx]
        for tpk, slk in exits:
            for hold in holds:
                st = stats(*run(ei, ed, a * tpk, a * slk, hold))
                if st is None: continue
                pS, xS = sim(O, H, L, S * 1.5, dayid, ei, ed, a * tpk, a * slk, hold, usd)
                okS = xS >= 0; strs = pf(pS[okS][T[xS[okS]] >= a3])
                rr = []
                for sd_ in (1, 2):
                    r = np.random.default_rng(sd_).choice([-1, 1], len(ed)).astype(np.int64)
                    rr.append(stats(*run(ei, r, a * tpk, a * slk, hold)))
                rt = stats(*run(rei, red, ra * tpk, ra * slk, hold))
                say(f"{fn:30s} {tpk:4.1f}/{slk:<4.1f}{hold:5d} | {st['n']:4d} {st['wk']:5.1f} {st['win']:4.0f} {st['pf']:5.2f} {strs:5.2f} {st['net']:+6.0f} "
                    f"{st['dd']:+5.0f} {st['wd']:+5.0f} | {st['n2']:4d} {st['win2']:4.0f} {st['pf2']:5.2f} {st['net2']:+6.0f} | "
                    f"{wp(rr[0])} {wp(rr[1])}          | {wp(rt)}")
                rows.append((fn, tpk, slk, hold, st, strs, rr, rt))

    say("")
    say("CELLS with win >= 60% and PF >= 1.15 and stress >= 1.05 and >= 30 trades in the last 3 months, and PF >= 1.0 in the 3 before:")
    hit = 0
    for fn, tpk, slk, hold, st, strs, rr, rt in rows:
        if st["win"] >= 60 and st["pf"] >= 1.15 and strs >= 1.05 and st["n"] >= 30 and st["pf2"] >= 1.0:
            hit += 1
            say(f"  {fn} TP {tpk} / SL {slk} ATR, {hold} min: {st['n']} trades, win {st['win']:.0f}%, PF {st['pf']:.2f} / prev {st['pf2']:.2f}, "
                f"+${st['net']:.0f} / {st['net2']:+.0f}, DD {st['dd']:.0f}, worst day {st['wd']:.0f}; random dir {wp(rr[0])} {wp(rr[1])}, random time {wp(rt)}")
    if not hit: say("  none")
    say("")
    nr = sum(1 for *_, rr, rt in rows for z in rr if z and z["win"] >= 60 and z["pf"] >= 1.15)
    say(f"random-direction twins with win >= 60% and PF >= 1.15 in the last 3 months: {nr} of {2 * len(rows)}")
    w = [st["win"] for *_, st, s_, rr, rt in rows]
    say(f"median win% of all cells {np.median(w):.0f}, median PF {np.median([r[4]['pf'] for r in rows]):.2f}, "
        f"median random-time PF {np.median([r[7]['pf'] for r in rows if r[7]]):.2f}")


if __name__ == "__main__":
    main()
