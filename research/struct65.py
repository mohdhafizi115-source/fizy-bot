"""Round 65 (7 Nov 2026): a gold scalper from market structure, chosen on the LAST MONTH.

Owner: "kau create ea scalping dalam tempoh 1 bulan dari corak structure gold".
Swings: fractal pivots of n bars each side, known only n bars later (online). Trend: up = last swing high
above the one before AND last swing low above the one before (HH+HL); down = mirror.
Rules (mirror for the other side), entry at the next bar's open:
  BOS      a close beyond the last swing high -> buy; SL at the last swing low
  BOS_T    the same, only when the trend already points that way
  CHOCH    trend up and a close below the last swing low -> sell; SL at the last swing high
  HL       trend up and a new higher low is confirmed -> buy; SL just under that low
  SFP      the bar's high takes the last swing high but closes back below it -> sell; SL above that high
TP R x risk (1R / 2R), out after 60 min, one trade at a time, risk between 3x spread and $10, rollover out.
Run on M1 and M5 (M5 bars built from M1, trades still simulated on M1 bars), n = 3 / 5 / 10, +/- cost gate.
Chosen on the LAST MONTH, then checked on the MONTH BEFORE (owner's 1-month rule, with a repeat check) and,
as one extra line only, the last 12 months. Random-direction control at the same entries.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
say = lambda s="": print(s, flush=True)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min"); del d
    B = B[B.index >= B.index[-1] - pd.Timedelta(days=370)]
    end = B.index[-1]; m1 = end - pd.Timedelta(days=30); m0 = end - pd.Timedelta(days=60); y1 = end - pd.Timedelta(days=365)
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C); hm = B.hm.values; day = B.date.values; sp = B.s.values.astype(float)
    newd = np.r_[True, day[1:] != day[:-1]]
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = atr / np.where(sp > 0, sp, np.nan)
    T = B.index
    say(f"XAUUSD M1, last month {m1:%d %b}..{end:%d %b %Y}, month before {m0:%d %b}..{m1:%d %b}")

    def frame(tf):
        if tf == 1:
            idx = np.arange(n); return O, H, L, C, idx
        g = (np.arange(n) // tf)                                     # simple M5 bars on the M1 index
        df = pd.DataFrame({"o": O, "h": H, "l": L, "c": C, "g": g})
        a = df.groupby("g").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
        last = df.reset_index().groupby("g")["index"].last().values  # M1 bar where each M5 bar closes
        return a.o.values, a.h.values, a.l.values, a.c.values, last

    def signals(tf, nn, rule):
        o, h, l, c, last = frame(tf); m = len(c); out = []
        SH = []; SL_ = []                                             # confirmed swings (price)
        for j in range(2 * nn, m):
            p = j - nn
            if h[p] == h[p - nn:j + 1].max(): SH.append(h[p]); newH = True
            else: newH = False
            if l[p] == l[p - nn:j + 1].min(): SL_.append(l[p]); newL = True
            else: newL = False
            if len(SH) < 2 or len(SL_) < 2: continue
            up = SH[-1] > SH[-2] and SL_[-1] > SL_[-2]
            dn = SH[-1] < SH[-2] and SL_[-1] < SL_[-2]
            k = last[j]                                               # M1 bar index of this close
            if rule in ("BOS", "BOS_T"):
                if c[j] > SH[-1] and c[j - 1] <= SH[-1] and (rule == "BOS" or up): out.append((k, 1, SL_[-1]))
                if c[j] < SL_[-1] and c[j - 1] >= SL_[-1] and (rule == "BOS" or dn): out.append((k, -1, SH[-1]))
            elif rule == "CHOCH":
                if up and c[j] < SL_[-1] and c[j - 1] >= SL_[-1]: out.append((k, -1, SH[-1]))
                if dn and c[j] > SH[-1] and c[j - 1] <= SH[-1]: out.append((k, 1, SL_[-1]))
            elif rule == "HL":
                if newL and up: out.append((k, 1, SL_[-1]))
                if newH and dn: out.append((k, -1, SH[-1]))
            elif rule == "SFP":
                if h[j] > SH[-1] and c[j] < SH[-1]: out.append((k, -1, h[j]))
                if l[j] < SL_[-1] and c[j] > SL_[-1]: out.append((k, 1, l[j]))
        return out

    def trade(sig, R, g, rand=False):
        res = []; busy = -1; rg = np.random.default_rng(65)
        for k, dr, slp in sig:
            if k <= busy or k + 1 >= n or newd[k + 1] or not (90 <= hm[k] < 1320): continue
            if g and not gate[k] >= 8: continue
            e = O[k + 1]
            if rand:
                dist = abs(e - slp); dr = 1 if rg.random() < 0.5 else -1; slp = e - dr * dist
            sl = slp - dr * sp[k]
            risk = (e - sl) * dr
            if risk < 3 * sp[k] or risk > 10: continue
            tp = e + dr * R * risk; ex = None; q = k + 1
            while q < n and q <= k + 60:
                if newd[q]: ex = O[q]; break
                if dr == 1:
                    if L[q] <= sl: ex = min(O[q], sl); break
                    if H[q] >= tp: ex = tp; break
                else:
                    if H[q] >= sl: ex = max(O[q], sl); break
                    if L[q] <= tp: ex = tp; break
                q += 1
            if ex is None: ex = C[min(q, n - 1)]
            res.append((k + 1, ((ex - e) * dr - sp[k + 1]) * usd)); busy = q
        R_ = pd.DataFrame(res, columns=["k", "net"]); R_["t"] = T[R_.k.values] if len(R_) else []
        return R_

    def stat(R_, a, b):
        x = R_.net[(R_.t >= a) & (R_.t < b)] if len(R_) else pd.Series(dtype=float)
        if len(x) < 5: return None
        g, l = x[x > 0].sum(), -x[x < 0].sum()
        wd = x.groupby(R_.t[(R_.t >= a) & (R_.t < b)].dt.normalize().values).sum().min()
        return dict(n=len(x), win=100 * (x > 0).mean(), pf=g / l if l else 9.99, net=x.sum(), wd=wd)

    rows = []
    for tf in (1, 5):
        for nn in (3, 5, 10):
            for rule in ("BOS", "BOS_T", "CHOCH", "HL", "SFP"):
                sig = signals(tf, nn, rule)
                for R in (1.0, 2.0):
                    for g in (False, True):
                        r = trade(sig, R, g)
                        a = stat(r, m1, end + pd.Timedelta(minutes=1)); b = stat(r, m0, m1); y = stat(r, y1, end + pd.Timedelta(minutes=1))
                        if a is None: continue
                        rr = trade(sig, R, g, rand=True); ar = stat(rr, m1, end + pd.Timedelta(minutes=1))
                        rows.append(dict(rule=f"M{tf} {rule} n{nn} TP{R:.0f}R{' gate8' if g else ''}", **{f"L_{k}": v for k, v in a.items()},
                                         B_pf=b["pf"] if b else 0, B_net=b["net"] if b else 0, Y_pf=y["pf"] if y else 0, Y_net=y["net"] if y else 0,
                                         RND_pf=ar["pf"] if ar else 0))
    D = pd.DataFrame(rows).sort_values("L_net", ascending=False)
    say(f"\n{len(D)} variants. Sorted by LAST MONTH net $ (0.01 lot). Columns: last month trades/day, win%, PF, net, worst day | "
        f"month before PF, net | last 12 months PF, net | random direction PF last month")
    ndays = 22
    for _, r in D.head(25).iterrows():
        say(f"{r.rule:>28} | {r.L_n / ndays:5.1f}/day {r.L_win:3.0f}% PF {r.L_pf:4.2f} {r.L_net:+6.0f} wd {r.L_wd:+5.0f} | "
            f"before PF {r.B_pf:4.2f} {r.B_net:+6.0f} | 12m PF {r.Y_pf:4.2f} {r.Y_net:+7.0f} | rnd {r.RND_pf:4.2f}")
    both = D[(D.L_net > 0) & (D.B_net > 0)]
    say(f"\nprofitable in BOTH months: {len(both)} of {len(D)}")
    for _, r in both.iterrows():
        say(f"   {r.rule}: last {r.L_net:+.0f} (PF {r.L_pf:.2f}, {r.L_n / ndays:.1f}/day), before {r.B_net:+.0f} (PF {r.B_pf:.2f}), 12m {r.Y_net:+.0f} (PF {r.Y_pf:.2f})")
    say(f"profitable last month: {(D.L_net > 0).sum()} of {len(D)}; of those also the month before: {len(both)}")


if __name__ == "__main__":
    main()
