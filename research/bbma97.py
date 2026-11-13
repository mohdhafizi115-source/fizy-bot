"""Round 97 (12 Nov 2026): TRADE the reversal CSAKs that round 96 found (M15 CSAK after an Extreme / MHV the other
way), last 2 years, all 30 instruments, executed on the broker's M5 bars.

Round 96 measured that an M15 CSAK moves in its direction only when it comes AFTER price was stretched the other way:
  S1  MHV against      an M15 Extreme against 3-20 candles before, then a failed retest of the band (BBMA "MHV")
  S2  H4 Extreme       the last 3 closed H4 candles hold an Extreme against the CSAK
  S3  H4 far band + M15 Extreme   H4 close in the half of the H4 band opposite to the CSAK (signed position <= -0.5)
                       AND an M15 Extreme against in the last 12 M15 candles
  S4  against H4 trend + the 8 candles before moved more than 1.2 ATR against the CSAK
  S5  M15 Extreme against (last 12 candles)
  S0  every CSAK (base)
Neighbour checks (not chosen on results): S3 with H4 position <= -0.3 / -0.7, Extreme lookback 8 / 16.
Exits: SL beyond the CSAK candle, or beyond the swing (lowest low / highest high of the 12 M15 candles up to the CSAK);
TP 1R / 2R / 3R; time cap 24 h; also pure time exits after 8 h / 24 h with the swing SL.  Cost filter variant: the
CSAK's spread / ATR(M15) <= 0.20.  One position per symbol at a time, spread paid, broker swaps, SL before TP inside a bar.
Each line also with a random direction on the same entries.  R = profit / initial risk, pooled over the 30 symbols.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87
import bbma94 as B94
import bbma96 as B96

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
CTX_ONLY = False     # round 98 uses run() for its context only


def run(sym, mt, sw, rg):
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, sym + ".csv"), mt["point"])
    B = d[["o", "h", "l", "c", "s", "v"]].copy(); del d
    T = B.index; n = len(B); end = T[-1]
    O, H, L, C, S = (B[x].values.astype(float) for x in ("o", "h", "l", "c", "s"))
    ts = T.values.astype("datetime64[s]").astype(np.int64); day = T.normalize().values; wd = T.day_of_week.values
    g = B.resample("15min", label="left", closed="left")
    X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()}).dropna()
    X["v"] = g.v.sum().reindex(X.index).fillna(0).values; X["s"] = g.s.median().reindex(X.index).values
    I, exd, exu = B96.extremes(X); Fm = B94.feats(X)
    o, c, h, l = X.o.values, X.c.values, X.h.values, X.l.values
    bot, top = I.bot.values, I.top.values
    lo, hi = np.minimum(I.mid, I.e50).values, np.maximum(I.mid, I.e50).values
    cb = (o < lo) & (c > hi) & (c <= top); cs = (o > hi) & (c < lo) & (c >= bot)
    hm = X.index.hour.values * 60 + X.index.minute.values; N = len(X)
    ks = np.where((cb | cs) & (hm >= 90) & (hm < 1320) & (X.index >= end - pd.Timedelta(days=730)) & (np.arange(N) > 300) & (np.arange(N) < N - 2))[0]
    dr = np.where(cb[ks], 1, -1)
    def roll(a, nb): return pd.Series(a.astype(float)).rolling(nb, min_periods=1).max().values
    exa = {nb: np.where(dr == 1, roll(exd, nb)[ks - 1], roll(exu, nb)[ks - 1]) for nb in (8, 12, 16)}
    mhv = np.zeros(len(ks))
    for n_, (k, d_) in enumerate(zip(ks, dr)):
        ex = exd if d_ == 1 else exu
        js = np.where(ex[k - 20:k - 2])[0]
        if len(js) == 0: continue
        j = k - 20 + js[-1]; seg = np.arange(j + 1, k)
        if d_ == 1:
            exlow = l[j - 2:j + 1].min()
            if ((l[seg] <= bot[seg]) & (c[seg] > bot[seg]) & (l[seg] >= exlow)).any() and l[j + 1:k].min() >= exlow: mhv[n_] = 1
        else:
            exhigh = h[j - 2:j + 1].max()
            if ((h[seg] >= top[seg]) & (c[seg] < top[seg]) & (h[seg] <= exhigh)).any() and h[j + 1:k].max() <= exhigh: mhv[n_] = 1
    fd4, fu4, pos4 = B96.htf_flags(X, 240, 3)
    h4ex = np.where(dr == 1, fd4[ks], fu4[ks]); h4pos = pos4[ks] * dr
    h4tr = Fm["H4 EMA50vs90"][ks] * dr; prior = Fm["move prior8 ATR"][ks] * dr
    spr = (Fm["spread/ATR"])[ks]
    sets = {
        "S0 every CSAK": np.ones(len(ks), bool),
        "S1 MHV against": mhv == 1,
        "S2 H4 Extreme against": h4ex == 1,
        "S3 H4 far band + M15 Extreme": (h4pos <= -0.5) & (exa[12] == 1),
        "S3a H4 pos<=-0.3 + M15 Ext": (h4pos <= -0.3) & (exa[12] == 1),
        "S3b H4 pos<=-0.7 + M15 Ext": (h4pos <= -0.7) & (exa[12] == 1),
        "S3c H4 far band + M15 Ext(8)": (h4pos <= -0.5) & (exa[8] == 1),
        "S3d H4 far band + M15 Ext(16)": (h4pos <= -0.5) & (exa[16] == 1),
        "S4 against H4 + prior move against": (h4tr == -1) & (prior < -1.2),
        "S5 M15 Extreme against": exa[12] == 1,
    }
    at = np.searchsorted(T.values, (X.index + pd.Timedelta(minutes=15)).values)
    csl = l[ks]; csh = h[ks]
    swl = np.array([l[max(0, k - 11):k + 1].min() for k in ks]); swh = np.array([h[max(0, k - 11):k + 1].max() for k in ks])

    def sim(mask, slm, tpR, hold_h, rand, sw_l=None, sw_h=None):
        sw_l = swl if sw_l is None else sw_l; sw_h = swh if sw_h is None else sw_h
        res = []; busy = -1
        for idx in np.where(mask)[0]:
            k, cd = ks[idx], dr[idx]; i = at[k]
            if i >= n or i <= busy: continue
            e0 = O[i] + (S[i] if cd == 1 else 0)
            if slm == "csak": sl0 = csl[idx] - S[i] if cd == 1 else csh[idx] + S[i]
            else: sl0 = sw_l[idx] - S[i] if cd == 1 else sw_h[idx] + S[i]
            risk = (e0 - sl0) * cd
            if risk <= S[i]: continue
            d_ = cd if not rand else (1 if rg.random() < 0.5 else -1)
            e = O[i] + (S[i] if d_ == 1 else 0); sl = e - d_ * risk; tp = e + d_ * tpR * risk if tpR else None
            x = None; z = i; nights = 0; worst = 0.0
            while z < n:
                if z > i and day[z] != day[z - 1]: nights += 3 if (sw and 1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
                if ts[z] - ts[i] >= hold_h * 3600: x = O[z] + (S[z] if d_ == -1 else 0); break
                if d_ == 1:
                    if L[z] <= sl: x = min(O[z], sl) if z > i else sl; break
                    if tp is not None and z > i and H[z] >= tp: x = max(O[z], tp); break
                    worst = min(worst, L[z] - e)
                else:
                    if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; break
                    if tp is not None and z > i and L[z] + S[z] <= tp: x = min(O[z] + S[z], tp); break
                    worst = min(worst, e - H[z] - S[z])
                z += 1
            if x is None: break
            swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
            net = (x - e) * d_ * usd + swp; rk = risk * usd
            res.append((T[i], net, net / rk, (net - 0.5 * S[i] * usd) / rk, d_, worst * usd, T[min(z, n - 1)], rk))
            busy = z
        return pd.DataFrame(res, columns=["t", "net", "r", "rs", "d", "mae", "tx", "risk"])

    if CTX_ONLY: return dict(ks=ks, dr=dr, roll=roll, exd=exd, exu=exu, h4pos=h4pos, spr=spr, l=l, h=h, at=at, sim=sim, end=end, swl=swl, swh=swh,
                             top=top, bot=bot, atr15=Fm["_atr"], O=O, H=H, L=L, S=S, T=T, ts=ts, day=day, wd=wd, n=n, usd=usd, c15=c)   # bars for round 99 (c15 for 99c)
    exits = [("SL csak", "csak", tp, 24) for tp in (1, 2, 3)] + [("SL swing", "swing", tp, 24) for tp in (1, 2, 3)] + \
            [("SL swing, time 8h", "swing", 0, 8), ("SL swing, time 24h", "swing", 0, 24)]
    out = {}
    for sn, m in sets.items():
        for cost, cm in (("any spread", np.ones(len(ks), bool)), ("spread<=0.20 ATR", spr <= 0.20)):
            mm = m & cm
            if mm.sum() == 0: continue
            for en, slm, tpR, hh in exits:
                key = (sn, cost, en + (f", TP {tpR}R" if tpR else ""))
                out[key] = (sim(mm, slm, tpR, hh, False), sim(mm, slm, tpR, hh, True))
    return out, end


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(97)
    ALL = {}; END = None
    for sym in B87.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        res, end = run(sym, meta[sym], SW.get(sym), rg); END = end if END is None else max(END, end)
        for k, (a, b) in res.items():
            ALL.setdefault(k, ([], []))
            if len(a): ALL[k][0].append(a.assign(sym=sym))
            if len(b): ALL[k][1].append(b.assign(sym=sym))
        say(f"{sym} done [{time.time() - T0:.0f} s]")
    mid = END - pd.Timedelta(days=365); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}.  PASS = >=150 trades, PF >= 1.15, both years >= 1.05, stress >= 1.05, "
        f"last 12 months > 0, PF >= RAND + 0.10.  R pooled over 30 symbols; $ per 0.01 lot")
    say(f"{'set | cost | exit':78s} {'side':4s} {'n':>5} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'12m R':>6} {'3m R':>5} {'p3m R':>6} | "
        f"{'sym>1':>6} {'net $':>7} {'float$':>7} | {'RAND':>5}")
    for key, (La, Lb) in ALL.items():
        if not La: continue
        R = pd.concat(La); Rr = pd.concat(Lb) if Lb else R.iloc[:0]
        for side, sd in (("BUY", 1), ("SELL", -1), ("ALL", 0)):
            x = R if sd == 0 else R[R.d == sd]; xr = Rr if sd == 0 else Rr[Rr.d == sd]
            if len(x) < 30: continue
            P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values)
            l12 = x.r[x.t >= mid].sum()
            gg = [pf(v.net.values) > 1 for _, v in x.groupby("sym") if len(v) >= 10]
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and P >= PR + 0.10
            say(f"{' | '.join(key):78s} {side:4s} {len(x):5d} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | {l12:+6.1f} "
                f"{x.r[x.t >= a3].sum():+5.1f} {x.r[(x.t >= a6) & (x.t < a3)].sum():+6.1f} | {sum(gg):2d}/{len(gg):<3d} {x.net.sum():+7.0f} {x.mae.min():+7.0f} | "
                f"{PR:5.2f} {'PASS' if ok else ''}")
        say()
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
