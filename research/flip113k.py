"""Round 113k (15 Nov 2026): can ATR or an indicator help GOLD FLIP?  Owner: "aku rasa 4 lebih better. adakah atr atau apa2 indikator membantu".
Live v2.31 rule (OCO at the 01:30 open +- $3, stop trailed until +lock then frozen, reverse when hit, out 23:30, own $25 target).
A) gap per trade from ATR instead of a fixed $: k x ATR14(D1) (previous 14 completed days), k x Wilder ATR14(M15) / ATR14(H1) of the
   last closed bar at entry; lock $1 or 0.25 x gap.
B) direction filter: a new trade (OCO fill or reversal) only in the direction of the last closed H1 close vs EMA 50 (H1), M15 close vs
   EMA 200, H4 EMA 50 slope, or (ADX14 H1 >= 20 and +DI/-DI side); a reversal against the filter -> flat, re-arm OCO at the exit +- $3
   and take only the allowed side.  Also "only when ADX(H1) >= 20 / < 20" (any direction).
C) day filter: ATR14(D1) vs its 60-day mean above / below 1; yesterday's range vs ATR14(D1).
Gold M1, last 2 years, 0.01 lot, data run 43620182422."""
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


@jit
def sim(O, H, L, S, Dg, LKf, LKabs, live, dayid, usd, K, tgt, tf):
    """Dg[j] = gap if a trade opens on bar j; lock = LKabs if > 0 else LKf * gap.  tf[j] = allowed direction (0 = both)."""
    n = len(O); xi = np.zeros(2 * n, np.int64); pn = np.zeros(2 * n); m = 0
    pos = 0; ent = 0.0; stop = 0.0; gp = 0.0; lk = 0.0; locked = False; wait = False; up = 0.0; dn = 0.0; dsum = 0.0; done = False
    for j in range(n):
        if not live[j]:
            if pos != 0:
                px = O[j] if pos == 1 else O[j] + S[j]
                xi[m] = j; pn[m] = (px - ent) * pos * usd; m += 1; pos = 0
            wait = False
            continue
        if j == 0 or not live[j - 1] or dayid[j] != dayid[j - 1]:
            dsum = 0.0; done = False
            if pos == 0:
                wait = True; up = O[j] + K; dn = O[j] - K
        if done: continue
        if pos == 0 and wait:
            hb = H[j] + S[j] >= up and tf[j] >= 0; hs = L[j] <= dn and tf[j] <= 0
            if not hb and not hs: continue
            if hb and hs:
                if up - (O[j] + S[j]) <= O[j] - dn: hs = False
                else: hb = False
            wait = False; locked = False; gp = Dg[j]; lk = LKabs if LKabs > 0 else LKf * gp
            if hb:
                pos = 1; ent = max(up, O[j] + S[j]); stop = ent - S[j] - gp
            else:
                pos = -1; ent = min(dn, O[j]); stop = ent + S[j] + gp
            continue
        if pos == 1:
            if L[j] <= stop:
                px = min(O[j], stop); v = (px - ent) * usd; xi[m] = j; pn[m] = v; m += 1; dsum += v
                if tgt > 0 and dsum >= tgt:
                    pos = 0; done = True
                elif tf[j] > 0:
                    pos = 0; wait = True; up = px + S[j] + K; dn = px - K
                else:
                    gp = Dg[j]; lk = LKabs if LKabs > 0 else LKf * gp
                    pos = -1; ent = px; stop = px + S[j] + gp; locked = False
            elif not locked:
                stop = max(stop, H[j] - gp)
                if H[j] - ent >= lk: locked = True
        elif pos == -1:
            ah = H[j] + S[j]; al = L[j] + S[j]
            if ah >= stop:
                px = max(O[j] + S[j], stop); v = (ent - px) * usd; xi[m] = j; pn[m] = v; m += 1; dsum += v
                if tgt > 0 and dsum >= tgt:
                    pos = 0; done = True
                elif tf[j] < 0:
                    pos = 0; wait = True; up = px + K; dn = px - S[j] - K
                else:
                    gp = Dg[j]; lk = LKabs if LKabs > 0 else LKf * gp
                    pos = 1; ent = px; stop = px - S[j] - gp; locked = False
            elif not locked:
                stop = min(stop, al + gp)
                if ent - al >= lk: locked = True
    return xi[:m], pn[:m]


def wilder_atr(h, l, c, n=14):
    pc = c.shift(); tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def to_m1(series_closed, T, freq):
    """value of the last CLOSED bar of frequency freq at each M1 bar time."""
    s = series_closed.copy(); s.index = s.index + pd.Timedelta(freq)       # available from the bar's close
    return s.reindex(T, method="ffill").values


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    a3 = end - pd.Timedelta(days=91); a6 = end - pd.Timedelta(days=182)
    full = d[["o", "h", "l", "c", "s"]]
    agg = dict(o="first", h="max", l="min", c="last")
    bars = {f: full.resample(f).agg(agg).dropna() for f in ("15min", "1h", "4h")}
    day = full.groupby(full.index.normalize()).agg(agg)
    pcd = day.c.shift(); trd = np.maximum(day.h - day.l, np.maximum((day.h - pcd).abs(), (day.l - pcd).abs()))
    atrd = trd.rolling(14).mean().shift(1)                                  # completed days only
    reg = (atrd / atrd.rolling(60).mean())
    yr = (day.h - day.l).shift(1) / atrd
    B = full[full.index >= start]
    O, H, L, S = (B[k].values.astype(float) for k in ("o", "h", "l", "s"))
    T = B.index; one = 1.0 / usd; N = len(O)
    hm = T.hour.values * 60 + T.minute.values; wd = T.day_of_week.values < 5
    dayid = T.normalize().values.astype("datetime64[D]").astype(np.int64)
    live = wd & (hm >= 90) & (hm < 1410)
    days = pd.DatetimeIndex(np.unique(T[live].normalize())); nd = len(days)
    ATRD = atrd.reindex(T.normalize()).values; REG = reg.reindex(T.normalize()).values; YR = yr.reindex(T.normalize()).values
    b15, b1h, b4h = bars["15min"], bars["1h"], bars["4h"]
    A15 = to_m1(wilder_atr(b15.h, b15.l, b15.c), T, "15min"); A1H = to_m1(wilder_atr(b1h.h, b1h.l, b1h.c), T, "1h")
    e50h = b1h.c.ewm(span=50, adjust=False).mean(); c1h = to_m1(b1h.c, T, "1h"); E50H = to_m1(e50h, T, "1h")
    e200m = b15.c.ewm(span=200, adjust=False).mean(); c15 = to_m1(b15.c, T, "15min"); E200M = to_m1(e200m, T, "15min")
    e50h4 = b4h.c.ewm(span=50, adjust=False).mean(); SL4 = to_m1(np.sign(e50h4.diff()), T, "4h")
    # ADX / DI on H1
    hh, ll, cc = b1h.h, b1h.l, b1h.c
    upm = hh.diff(); dnm = -ll.diff()
    pdm = pd.Series(np.where((upm > dnm) & (upm > 0), upm, 0.0), index=hh.index); mdm = pd.Series(np.where((dnm > upm) & (dnm > 0), dnm, 0.0), index=hh.index)
    atrh = wilder_atr(hh, ll, cc); pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atrh; mdi = 100 * mdm.ewm(alpha=1 / 14, adjust=False).mean() / atrh
    adx = (100 * (pdi - mdi).abs() / (pdi + mdi)).ewm(alpha=1 / 14, adjust=False).mean()
    ADX = to_m1(adx, T, "1h"); DIS = to_m1(np.sign(pdi - mdi), T, "1h")
    f = lambda x: np.nan_to_num(x, nan=0.0)
    TF0 = np.zeros(N, np.int64)
    filters = {
        "none": TF0,
        "H1 close vs EMA50": np.sign(f(c1h - E50H)).astype(np.int64),
        "M15 close vs EMA200": np.sign(f(c15 - E200M)).astype(np.int64),
        "H4 EMA50 slope": f(SL4).astype(np.int64),
        "H1 ADX>=20 + DI side": np.where(f(ADX) >= 20, f(DIS), 0).astype(np.int64),
        "H1 ADX>=25 + DI side": np.where(f(ADX) >= 25, f(DIS), 0).astype(np.int64),
    }
    say(f"GOLD FLIP + ATR / indicators: gold M1 {days[0]:%Y-%m-%d} .. {days[-1]:%Y-%m-%d}, {nd} days, OCO +-$3, own $25 target, $ at 0.01 lot")
    say(f"median ATR14(D1) ${np.nanmedian(ATRD[live]) * usd:.1f}, ATR14(M15) ${np.nanmedian(A15[live]) * usd:.2f}, ATR14(H1) ${np.nanmedian(A1H[live]) * usd:.2f}")
    hdr = (f"{'variant':44s} {'gap$':>5} {'trades':>6} {'/day':>5} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'net$':>6} {'12m$':>6} {'3m$':>5} {'pr3m':>5} | "
           f"{'DD':>5} {'wDay':>5} {'lossD':>5} {'d<-100':>6}")

    def run(nm, Dg, lkf=0.0, lkabs=1.0, tf=TF0, lv=live):
        Dg = np.nan_to_num(Dg, nan=5 * one); Dg = np.maximum(Dg, 0.5 * one)
        args = (lkf, lkabs * one if lkabs > 0 else 0.0, lv, dayid, usd, 3 * one, 25.0, tf)
        xi, p = sim(O, H, L, S, Dg, *args)
        if len(p) < 30: return
        _, ps = sim(O, H, L, S * 1.5, Dg, *args)
        te = T[xi]; dl = pd.DatetimeIndex(np.unique(T[lv].normalize()))
        dp = pd.Series(p, index=te.normalize()).groupby(level=0).sum().reindex(dl, fill_value=0.0)
        eq = dp.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"{nm:44s} {np.median(Dg[lv]) * usd:5.1f} {len(p):6d} {len(p) / len(dl):5.1f} {pf(p):5.2f} {pf(p[te < mid]):5.2f} {pf(p[te >= mid]):5.2f} {pf(ps):5.2f} | "
            f"{p.sum():+6.0f} {p[te >= mid].sum():+6.0f} {p[te >= a3].sum():+5.0f} {p[(te >= a6) & (te < a3)].sum():+5.0f} | "
            f"{dd:+5.0f} {dp.min():+5.0f} {(dp < 0).sum():5d} {(dp < -100).sum():6d}")

    ones = np.ones(N)
    say("\n== A) fixed gap (reference)\n" + hdr)
    for g in (4, 5): run(f"fixed ${g}, lock $1", ones * g * one)
    say("\n== A) gap from ATR, lock $1 / lock 0.25 x gap\n" + hdr)
    for k in (0.06, 0.08, 0.10, 0.12, 0.15):
        run(f"{k:g} x ATR14(D1), lock $1", k * ATRD); run(f"{k:g} x ATR14(D1), lock 0.25 gap", k * ATRD, 0.25, 0)
    for k in (1.0, 1.5, 2.0, 3.0):
        run(f"{k:g} x ATR14(M15), lock $1", k * A15); run(f"{k:g} x ATR14(M15), lock 0.25 gap", k * A15, 0.25, 0)
    for k in (0.5, 0.75, 1.0, 1.5):
        run(f"{k:g} x ATR14(H1), lock $1", k * A1H); run(f"{k:g} x ATR14(H1), lock 0.25 gap", k * A1H, 0.25, 0)
    for g in (4, 5):
        say(f"\n== B) direction filter, fixed ${g}\n" + hdr)
        for nm, tf in filters.items():
            run(f"${g} {nm}", ones * g * one, tf=tf)
        say(f"\n== C) day / regime filter, fixed ${g}\n" + hdr)
        run(f"${g} all days", ones * g * one)
        run(f"${g} ATR(D1) above its 60-day mean", ones * g * one, lv=live & (f(REG) >= 1))
        run(f"${g} ATR(D1) below its 60-day mean", ones * g * one, lv=live & (f(REG) < 1) & (f(REG) > 0))
        run(f"${g} yesterday range >= ATR", ones * g * one, lv=live & (f(YR) >= 1))
        run(f"${g} yesterday range < ATR", ones * g * one, lv=live & (f(YR) < 1) & (f(YR) > 0))
        run(f"${g} only when H1 ADX >= 20", ones * g * one, lv=live & (f(ADX) >= 20))
        run(f"${g} only when H1 ADX < 20", ones * g * one, lv=live & (f(ADX) < 20) & (f(ADX) > 0))


if __name__ == "__main__":
    main()
