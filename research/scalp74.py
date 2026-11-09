"""Round 74 (9 Nov 2026): a frequent gold scalper judged on the last 3 months (owner: "kau bina ea scalping trade banyak
kali yang profitable, test dalam 3 bulan").

Many scalping rule families on gold M1 and M5, each scored month by month over the last 3 months, with the 3 months
before as a repeat check and a random-entry control at the same trade times. One position at a time, entry at the
next bar's open, spread charged once (buys pay the ask), entries 01:30-22:00 server, everything flat by 23:45.
$ per 0.01 lot.

PASS (owner's frame): >= 3 trades a day, every one of the last 3 months positive, PF >= 1.15 over the 3 months, and
the 3 months before also positive (so a lucky quarter is not mistaken for an edge).
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def ind(X):
    O, H, L, C = (X[c].values.astype(float) for c in ("o", "h", "l", "c"))
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    d = np.diff(C, prepend=C[0])
    def rsi(p):
        up = pd.Series(np.maximum(d, 0)).ewm(alpha=1 / p, adjust=False).mean()
        dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1 / p, adjust=False).mean()
        return (100 - 100 / (1 + up / dn.replace(0, np.nan))).values
    ema = lambda p: pd.Series(C).ewm(span=p, adjust=False).mean().values
    ma20 = pd.Series(C).rolling(20).mean().values; sd20 = pd.Series(C).rolling(20).std().values
    ll = pd.Series(L).rolling(5).min().values; hh = pd.Series(H).rolling(5).max().values
    k5 = 100 * (C - ll) / np.where(hh - ll > 0, hh - ll, np.nan)
    K = pd.Series(k5).rolling(3).mean().values; Dd = pd.Series(K).rolling(3).mean().values
    return dict(O=O, H=H, L=L, C=C, atr=atr, rsi14=rsi(14), rsi7=rsi(7), rsi2=rsi(2), e9=ema(9), e21=ema(21),
                e50=ema(50), e200=ema(200), bbu=ma20 + 2 * sd20, bbl=ma20 - 2 * sd20, mid=ma20, K=K, D=Dd,
                hi20=pd.Series(H).rolling(20).max().shift(1).values, lo20=pd.Series(L).rolling(20).min().shift(1).values)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B1 = DT.bars(d, "1min")
    del d
    B1 = B1[B1.index >= B1.index[-1] - pd.Timedelta(days=200)]
    end = B1.index[-1]
    edges = [end - pd.Timedelta(days=30 * i) for i in range(6, -1, -1)]          # 6 monthly windows
    say(f"XAUUSD {B1.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}; last 3 months from {edges[3]:%d %b}, repeat check from {edges[0]:%d %b}")

    rows = []
    for tfm in (1, 5):
        if tfm == 1:
            X = B1[["o", "h", "l", "c", "s"]].copy()
        else:
            g = B1.resample("5min", label="left", closed="left")
            X = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "s": g.s.median()}).dropna()
        I = ind(X)
        O, H, L, C, atr = I["O"], I["H"], I["L"], I["C"], I["atr"]
        S = X.s.values.astype(float)
        T = X.index; n = len(C)
        hm = T.hour.values * 60 + T.minute.values
        wd = T.dayofweek.values
        a1 = np.r_[np.nan, atr[:-1]]                       # ATR known before bar k closes
        gate = a1 / np.where(S > 0, S, np.nan)
        rng = H - L; body = C - O
        ok = (hm >= 90) & (hm < 1320) & (wd < 5)
        days = pd.Series(T.normalize()).nunique()

        def sim(sig, slm, tpm, hold, sl_mode="atr", tp_mode="atr", rand=False):
            """sig: array of -1/0/+1 decided at the CLOSE of bar k; trade from the open of k+1"""
            res = []; busy = -1; rg = np.random.default_rng(74)
            idx = np.where((sig != 0) & ok)[0]
            for k in idx:
                if k <= busy or k + 1 >= n: continue
                dr = int(sig[k])
                if rand: dr = 1 if rg.random() < 0.5 else -1
                e = O[k + 1]
                a = atr[k]
                if not np.isfinite(a) or a <= 0: continue
                if sl_mode == "atr": sl = e - dr * slm * a
                elif sl_mode == "bar": sl = (L[k] - slm * a) if dr == 1 else (H[k] + slm * a)
                if (e - sl) * dr <= 0: continue
                if tp_mode == "atr": tp = e + dr * tpm * a if tpm else None
                elif tp_mode == "r": tp = e + dr * tpm * abs(e - sl)
                elif tp_mode == "mid": tp = I["mid"][k]
                if tp is not None and (tp - e) * dr <= 0: tp = None
                x = None; q = k + 1
                while q < n:
                    if q - (k + 1) >= hold or hm[q] >= 1425 or T[q].date() != T[k + 1].date():
                        x = O[q] if q > k + 1 else C[q]; break
                    if dr == 1:
                        if L[q] <= sl: x = min(O[q], sl) if q > k + 1 else sl; break
                        if tp is not None and H[q] >= tp: x = max(O[q], tp) if q > k + 1 else tp; break
                    else:
                        if H[q] >= sl: x = max(O[q], sl) if q > k + 1 else sl; break
                        if tp is not None and L[q] <= tp: x = min(O[q], tp) if q > k + 1 else tp; break
                    q += 1
                if x is None: continue
                res.append((T[k + 1], ((x - e) * dr - S[k + 1]) * usd)); busy = q
            return pd.DataFrame(res, columns=["t", "net"])

        def rec(name, sig, *a, **kw):
            R = sim(sig, *a, **kw); Rr = sim(sig, *a, rand=True, **kw)
            if len(R) == 0: return
            m = [R[(R.t >= edges[i]) & (R.t < edges[i + 1])].net.sum() for i in range(6)]
            l3 = R[R.t >= edges[3]]; p3 = R[(R.t >= edges[0]) & (R.t < edges[3])]
            g_, l_ = l3.net[l3.net > 0].sum(), -l3.net[l3.net < 0].sum()
            pf = g_ / l_ if l_ else 9.99
            rr = Rr[Rr.t >= edges[3]]; pfr = rr.net[rr.net > 0].sum() / max(-rr.net[rr.net < 0].sum(), 1e-9) if len(rr) else 0
            per_day = len(l3) / max(1, pd.Series(l3.t.dt.normalize()).nunique()) if len(l3) else 0
            wday = l3.groupby(l3.t.dt.normalize()).net.sum().min() if len(l3) else 0
            ok_ = per_day >= 3 and min(m[3:]) > 0 and pf >= 1.15 and p3.net.sum() > 0
            rows.append((f"M{tfm} {name}", per_day, 100 * (l3.net > 0).mean() if len(l3) else 0, pf, m[3], m[4], m[5],
                         l3.net.sum(), p3.net.sum(), wday, pfr, "PASS" if ok_ else ""))

        down = body < 0; up = body > 0
        for k_ in (1.5, 2.0, 2.5):
            for g_ in (4, 6, 8):
                spk = np.where((rng >= k_ * a1) & down & (gate >= g_), 1, 0)
                rec(f"spike fade BUY k{k_} gate{g_} SL 0.2ATR TP none 45bar", spk, 0.2, 0, 45 if tfm == 1 else 9, sl_mode="bar")
                rec(f"spike fade BUY k{k_} gate{g_} SL 0.2ATR TP 1ATR", spk, 0.2, 1.0, 45 if tfm == 1 else 9, sl_mode="bar")
                both = np.where((rng >= k_ * a1) & (gate >= g_), np.where(down, 1, -1), 0)
                rec(f"spike fade BOTH k{k_} gate{g_} SL 0.2ATR TP 1ATR", both, 0.2, 1.0, 45 if tfm == 1 else 9, sl_mode="bar")
        e9, e21, e50 = I["e9"], I["e21"], I["e50"]
        x = np.sign(e9 - e21); xc = np.r_[0, np.diff(x)]
        for g_ in (0, 8):
            gm = gate >= g_ if g_ else np.ones(n, bool)
            rec(f"EMA 9/21 cross follow gate{g_} SL1 TP1.5 ATR", np.where((xc != 0) & gm, np.sign(xc), 0), 1.0, 1.5, 60)
            rec(f"EMA 9/21 cross + EMA50 side gate{g_} SL1 TP1.5", np.where((xc > 0) & (C > e50) & gm, 1, np.where((xc < 0) & (C < e50) & gm, -1, 0)), 1.0, 1.5, 60)
            rec(f"BB(20,2) + RSI7 fade gate{g_} SL1 TP mid", np.where((C < I["bbl"]) & (I["rsi7"] < 25) & gm, 1, np.where((C > I["bbu"]) & (I["rsi7"] > 75) & gm, -1, 0)), 1.0, 0, 30, tp_mode="mid")
            rec(f"RSI2 <5 / >95 fade gate{g_} SL1 TP1", np.where((I["rsi2"] < 5) & gm, 1, np.where((I["rsi2"] > 95) & gm, -1, 0)), 1.0, 1.0, 30)
            rec(f"20-bar breakout follow gate{g_} SL1 TP2 ATR", np.where((C > I["hi20"]) & gm, 1, np.where((C < I["lo20"]) & gm, -1, 0)), 1.0, 2.0, 60)
            Kc = np.r_[0, np.diff(np.sign(I["K"] - I["D"]))]
            rec(f"Stoch 5,3,3 cross out of OB/OS gate{g_} SL1 TP1", np.where((Kc > 0) & (I["K"] < 25) & gm, 1, np.where((Kc < 0) & (I["K"] > 75) & gm, -1, 0)), 1.0, 1.0, 30)
            rec(f"pullback to EMA21 in EMA50/200 trend gate{g_} SL1 TP1.5", np.where((C > I["e200"]) & (e21 > e50) & (L <= e21) & (C > e21) & gm, 1,
                np.where((C < I["e200"]) & (e21 < e50) & (H >= e21) & (C < e21) & gm, -1, 0)), 1.0, 1.5, 60)
        mom = np.where(rng >= 1.5 * a1, np.sign(body), 0)
        rec("momentum bar (>=1.5 ATR) follow SL1 TP1", mom, 1.0, 1.0, 30)
        rec("momentum bar (>=1.5 ATR) fade SL1 TP1", -mom, 1.0, 1.0, 30)

    rows.sort(key=lambda r: -r[7])
    say(f"\n{'variant':62s} {'/day':>5} {'win%':>5} {'PF3m':>5} | {'month1':>7} {'month2':>7} {'month3':>7} | {'3 mths':>7} {'prev 3m':>8} {'worst d':>8} {'rand PF':>7}")
    for r in rows:
        say(f"{r[0]:62s} {r[1]:5.1f} {r[2]:5.0f} {r[3]:5.2f} | {r[4]:+7.0f} {r[5]:+7.0f} {r[6]:+7.0f} | {r[7]:+7.0f} {r[8]:+8.0f} {r[9]:+8.0f} {r[10]:7.2f} {r[11]}")
    say(f"\n{sum(1 for r in rows if r[11])} of {len(rows)} pass. done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
