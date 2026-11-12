"""Round 95 (12 Nov 2026): the ORIGINAL scanner SOP, exactly as bbma_scanner.py's evaluate_retrace(), last 2 years,
all 30 instruments.

Owner: "sah kan dulu, biar kita cari punca sampai ke lubang cacing".  BUY (SELL mirrored), all on broker data:
  1 H4 trend      last closed H4: EMA 90 < EMA 50 < mid BB
  2 H4 momentum   the most recent of the last 10 closed H4 candles that closed above the top BB; no H4 close below
                  the bottom BB since (opposite momentum)
  3 cancel        any closed H4 candle since the momentum closed below the H4 EMA 50, or the M15 close at the signal
                  below it -> dead until a new momentum
  4 retrace       the first M15 candle after the momentum whose low reaches the H4 MA5/10 Low zone
                  (low <= max(LWMA5 low, LWMA10 low) of the last closed H4 candle) starts the watch
  5 CSAK          the first M30 or M15 candle at / after the touch that opens below min(mid BB, EMA 50), closes above
                  max(mid BB, EMA 50) and above max(LWMA5 high, LWMA10 high) of its own TF, not above its top BB
  6 one signal per H4 momentum candle; entry at the next M15 open (= the scanner's alert 2/2)
The scanner sends alerts only, so exits are tested in several forms:
  A  SL beyond the CSAK candle, TP 1R / 2R, 48 h
  B  SL beyond the retrace extreme (lowest low from the touch to the CSAK), TP 1R / 2R, 48 h
  C  SL as B, TP at the highest high of the CSAK TF since the H4 momentum (the scanner's old TP_MODE "last_high")
  D  the owner's latest exit: no SL, out at the next open after an M15 close below the bottom BB, TP Fibo 161.8 of
     the leg from the retrace extreme to the CSAK high
Spread paid, broker swaps, SL before TP inside an M5 bar, R = profit / risk (D: profit / leg), pooled over the 30
symbols; each line also with the same entries in a RANDOM direction.  Also: the funnel (how many momentum candles,
retraces, CSAKs) and gold on its own.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0


def frame(B, m):
    g = B.resample(f"{m}min", label="left", closed="left")
    X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
    I = B87.ind(X)
    for nm, src, p in (("m5h", "h", 5), ("m10h", "h", 10), ("m5l", "l", 5), ("m10l", "l", 10)):
        I[nm] = B87.lwma(X[src].values, p)
    return X, I, (X.index + pd.Timedelta(minutes=m)).values


def run(sym, mt, sw, rg):
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    B = d[["o", "h", "l", "c", "s"]].copy(); del d
    T = B.index; n = len(B); end = T[-1]; start = end - pd.Timedelta(days=730)
    O, H, L, C, S = (B[x].values.astype(float) for x in ("o", "h", "l", "c", "s"))
    ts = T.values.astype("datetime64[s]").astype(np.int64); day = T.normalize().values; wd = T.day_of_week.values
    X4, I4, cl4 = frame(B, 240); X15, I15, cl15 = frame(B, 15); X30, I30, cl30 = frame(B, 30)
    c4, top4, bot4, e50_4, e90_4, mid4 = X4.c.values, I4.top.values, I4.bot.values, I4.e50.values, I4.e90.values, I4.mid.values
    l15, h15, c15 = X15.l.values, X15.h.values, X15.c.values
    k4_15 = np.searchsorted(cl4, cl15, side="right") - 1                # last closed H4 at each M15 close
    zb = np.maximum(I4.m5l.values, I4.m10l.values); zs = np.minimum(I4.m5h.values, I4.m10h.values)
    lineb = np.where(k4_15 >= 0, zb[np.maximum(k4_15, 0)], np.nan); lines = np.where(k4_15 >= 0, zs[np.maximum(k4_15, 0)], np.nan)
    hm15 = X15.index.hour.values * 60 + X15.index.minute.values

    def csak_mask(X, I):
        o, c = X.o.values, X.c.values
        lo, hi = np.minimum(I.mid.values, I.e50.values), np.maximum(I.mid.values, I.e50.values)
        b = (o < lo) & (c > hi) & (c <= I.top.values) & (c > np.maximum(I.m5h.values, I.m10h.values))
        s = (o > hi) & (c < lo) & (c >= I.bot.values) & (c < np.minimum(I.m5l.values, I.m10l.values))
        return b, s
    cb15, cs15 = csak_mask(X15, I15); cb30, cs30 = csak_mask(X30, I30)
    # candidate signal times: M15 closes where an M15 or an M30 CSAK just closed
    j30 = np.searchsorted(cl30, cl15) ; has30 = (j30 < len(cl30)) & (cl30[np.minimum(j30, len(cl30) - 1)] == cl15)
    cand = []
    for k in range(len(cl15)):
        if pd.Timestamp(cl15[k]) < start or not (90 <= hm15[k] + 15 < 1320): continue
        for dr in (1, -1):
            m15c = cb15[k] if dr == 1 else cs15[k]
            m30c = has30[k] and (cb30[j30[k]] if dr == 1 else cs30[j30[k]])
            if m15c or m30c: cand.append((k, dr, "M30" if m30c else "M15"))
    used = {1: set(), -1: set()}; sigs = []; funnel = {"csak": len(cand), "trend": 0, "mom": 0, "alive": 0, "touch": 0}
    for k, dr, tfn in cand:
        a = k4_15[k]
        if a < 120: continue
        if not ((e90_4[a] < e50_4[a] < mid4[a]) if dr == 1 else (mid4[a] < e50_4[a] < e90_4[a])): continue
        funnel["trend"] += 1
        win = np.arange(a, a - 10, -1)
        mom = [i for i in win if (c4[i] > top4[i] if dr == 1 else c4[i] < bot4[i])]
        if not mom: continue
        j = mom[0]
        if any((c4[i] < bot4[i]) if dr == 1 else (c4[i] > top4[i]) for i in range(j + 1, a + 1)): continue
        funnel["mom"] += 1
        if j in used[dr]: continue
        if any((c4[i] < e50_4[i]) if dr == 1 else (c4[i] > e50_4[i]) for i in range(j + 1, a + 1)): continue
        k0 = np.searchsorted(cl15, cl4[j], side="right")                  # first M15 bar after the momentum closed
        seg = np.arange(k0, k + 1)
        e4s = e50_4[k4_15[seg]]                                            # live check at every M15 close since (the scanner's forming H4)
        if ((c15[seg] < e4s) if dr == 1 else (c15[seg] > e4s)).any(): continue
        funnel["alive"] += 1
        hit = seg[(l15[seg] <= lineb[seg]) if dr == 1 else (h15[seg] >= lines[seg])]
        if len(hit) == 0: continue
        kt = hit[0]
        csak_t0 = (X15.index[k] if tfn == "M15" else X30.index[j30[k]])
        if csak_t0 < (X15.index[kt] if tfn == "M15" else X15.index[kt].floor("30min")): continue
        funnel["touch"] += 1
        used[dr].add(j)
        cd = (X15 if tfn == "M15" else X30); ci = k if tfn == "M15" else j30[k]
        ext = l15[kt:k + 1].min() if dr == 1 else h15[kt:k + 1].max()
        tpl = h15[k0:k + 1].max() if dr == 1 else l15[k0:k + 1].min()
        sigs.append(dict(k=k, dr=dr, tf=tfn, csl=cd.l.values[ci], csh=cd.h.values[ci], ext=ext, tpl=tpl))
    at = np.searchsorted(T.values, cl15)
    cutB = np.zeros(n + 1, bool); cutS = np.zeros(n + 1, bool)
    ib = at[np.nan_to_num(c15 < I15.bot.values).astype(bool)]; cutB[ib[ib < n]] = True
    is_ = at[np.nan_to_num(c15 > I15.top.values).astype(bool)]; cutS[is_[is_ < n]] = True

    def sim(mode, tpR, rand):
        res = []; busy = -1
        for s in sigs:
            k, cd = s["k"], s["dr"]; i = at[k]
            if i >= n or i <= busy: continue
            e0 = O[i] + (S[i] if cd == 1 else 0)
            if mode == "A": sl0 = s["csl"] - S[i] if cd == 1 else s["csh"] + S[i]
            else: sl0 = s["ext"] - S[i] if cd == 1 else s["ext"] + S[i]
            risk = (e0 - sl0) * cd
            if mode == "D":
                top = s["csh"] if cd == 1 else s["csl"]; leg = (top - s["ext"]) * cd
                if leg <= S[i]: continue
                dist = (s["ext"] + cd * 1.618 * leg - e0) * cd; risk = leg
            elif mode == "C": dist = (s["tpl"] - e0) * cd
            else: dist = tpR * risk
            if risk <= S[i] or dist <= 0: continue
            d_ = cd if not rand else (1 if rg.random() < 0.5 else -1)
            e = O[i] + (S[i] if d_ == 1 else 0); tp = e + d_ * dist; sl = e - d_ * risk
            x = None; z = i; nights = 0; worst = 0.0
            while z < n:
                if z > i and day[z] != day[z - 1]: nights += 3 if (sw and 1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
                if mode != "D" and ts[z] - ts[i] >= 48 * 3600: x = O[z] + (S[z] if d_ == -1 else 0); break
                if d_ == 1:
                    if mode == "D":
                        if z > i and cutB[z]: x = O[z]; break
                    elif L[z] <= sl: x = min(O[z], sl) if z > i else sl; break
                    if z > i and H[z] >= tp: x = max(O[z], tp); break
                    worst = min(worst, L[z] - e)
                else:
                    if mode == "D":
                        if z > i and cutS[z]: x = O[z] + S[z]; break
                    elif H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; break
                    if z > i and L[z] + S[z] <= tp: x = min(O[z] + S[z], tp); break
                    worst = min(worst, e - H[z] - S[z])
                z += 1
            if x is None: break
            swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
            net = (x - e) * d_ * usd + swp
            res.append((T[i], net, net / (risk * usd), (net - 0.5 * S[i] * usd) / (risk * usd), d_, s["tf"], worst * usd, (ts[z] - ts[i]) / 3600))
            busy = z
        return pd.DataFrame(res, columns=["t", "net", "r", "rs", "d", "tf", "mae", "hours"])

    out = {}
    for mode, tps in (("A", (1, 2)), ("B", (1, 2)), ("C", (0,)), ("D", (0,))):
        for tpR in tps:
            out[(mode, tpR, False)] = sim(mode, tpR, False); out[(mode, tpR, True)] = sim(mode, tpR, True)
    return out, funnel, end


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(95)
    ALL = {}; END = None; FUN = {}
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        res, fun, end = run(sym, meta[sym], SW.get(sym), rg); END = end if END is None else max(END, end)
        FUN[sym] = fun
        for k, df in res.items():
            if len(df): ALL.setdefault(k, []).append(df.assign(sym=sym))
        say(f"{sym}: CSAK candidates {fun['csak']}, in H4 trend order {fun['trend']}, with H4 momentum {fun['mom']}, not cancelled {fun['alive']}, "
            f"after the MA5/10 retrace = SIGNALS {fun['touch']}  [{time.time() - T0:.0f} s]")
    tot = {k: sum(f[k] for f in FUN.values()) for k in ("csak", "trend", "mom", "alive", "touch")}
    say(f"\nFUNNEL, 30 instruments, 2 years: {tot['csak']:,} M15/M30 CSAK candles -> {tot['trend']:,} in the H4 EMA90/EMA50/mid order -> "
        f"{tot['mom']:,} with H4 momentum -> {tot['alive']:,} not cancelled -> {tot['touch']:,} after the H4 MA5/10 retrace (one per momentum)")
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    names = {"A": "SL CSAK", "B": "SL retrace", "C": "SL retrace, TP last high", "D": "no SL, cut opp. M15 mom, TP fib 161.8"}
    say(f"\nPASS = >=150 trades, PF >= 1.15, both years >= 1.05, stress >= 1.05, last 12 months > 0, PF >= RAND + 0.10.  R pooled; $ per 0.01 lot")
    say(f"{'exit':42s} {'set':10s} {'side':4s} {'n':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'12m R':>6} {'3m R':>5} {'p3m R':>6} | "
        f"{'net $':>7} {'worst$':>7} {'float$':>7} {'hold h':>6} | {'RAND':>5}")
    for (mode, tpR, rand), L in ALL.items():
        if rand: continue
        R = pd.concat(L); Rr = pd.concat(ALL.get((mode, tpR, True), [R.iloc[:0]]))
        for setn, f in (("all 30", lambda x: x), ("gold only", lambda x: x[x.sym == "XAUUSD"]), ("forex", lambda x: x[~x.sym.isin(["XAUUSD", "BTCUSD"])])):
            for side, sd in (("BUY", 1), ("SELL", -1), ("ALL", 0)):
                x = f(R); xr = f(Rr)
                if sd: x = x[x.d == sd]; xr = xr[xr.d == sd]
                if len(x) < 10: continue
                P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values)
                l12 = x.r[x.t >= mid].sum()
                ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
                lab = names[mode] + (f", TP {tpR}R" if mode in "AB" else "")
                say(f"{lab:42s} {setn:10s} {side:4s} {len(x):4d} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | {l12:+6.1f} "
                    f"{x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | {x.net.sum():+7.0f} {x.net.min():+7.0f} {x.mae.min():+7.0f} "
                    f"{x.hours.median():6.1f} | {PR:5.2f} {'PASS' if ok else ''}")
        say()
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
