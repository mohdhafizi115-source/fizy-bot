"""Round 55 (6 Nov 2026): turn round 54's leg pattern into M1 rules, ONLINE, and test them.

Owner: "kau cipta ea di m1 berkaitan dengan pola dan kekerapan gold ni".

Round 54 found two non-random things about gold's M1 zigzag legs (0.10% reversal):
  - mature legs continue more than chance: a leg already 45-60 candles old goes 10 more 75-79% of the
    time, against 70-72% in shuffled data
  - fresh legs die more than chance: at 5 candles 58-59% go 10 more, against 63-64% shuffled
Both were measured in hindsight. Here the zigzag is run ONLINE: a leg's start is only known once price
has reversed pct from the previous extreme, exactly as an EA would see it.

  MATURE  when the current leg reaches age N candles (counted from its confirmed start), enter in its
          direction at the next open. Stop = the zigzag reversal level (pct back from the leg's extreme,
          from CLOSED bars only), so the trade ends when the leg ends. Cap 120 min.
  FRESH   when a new leg is confirmed, fade it: enter against it, TP back at the old extreme (where the
          new leg started), SL another pct further in the new leg's direction, cap 30 min.
Each by session (MYT) and with / without the cost gate (ATR >= 8 x spread). Controls: the same rule on
the day-shuffled price path (must fail if the pattern is real), and random direction at the same times.

Pass rule: >= 150 trades, PF >= 1.15 after spread, both halves >= 1.05, stress (1.5x spread) >= 1.05,
last 12 months positive. Also the worst day and max drawdown against a $100 account. 0.01 lot.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
pf = SA.pf
say = lambda s="": print(s, flush=True)
HDR = ("variant                              trades /day win%   PF  half1 half2 stress last12$   net$"
       "  maxDD$ worstday  pass")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    B = DT.bars(d, "1min")
    del d
    O, H, L, C = (B[x].values.astype(float) for x in ("o", "h", "l", "c"))
    n = len(C)
    hm = B.hm.values
    day = B.date.values
    newd = np.r_[True, day[1:] != day[:-1]]
    flat = (hm >= 1350) | newd | np.r_[newd[1:], True]
    sp = B.s.values.astype(float)
    c1 = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - c1), np.abs(L - c1)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().shift(1).values
    gate = np.where(sp > 0, atr / sp, np.nan)
    myt = ((hm // 60) + 6) % 24
    days = B.index.normalize().nunique()
    mid_t, end_t = B.index[n // 2], B.index[-1]
    say(f"XAUUSD M1, {n:,} bars, {days} days, halves split at {mid_t:%Y-%m-%d}.")

    # day-shuffled control path (same returns inside each day, order destroyed)
    rng = np.random.default_rng(55)
    lr = np.r_[0.0, np.diff(np.log(C))]
    lr[newd] = 0.0
    st = np.where(newd)[0]
    en = np.r_[st[1:], n]
    Cs = np.empty(n)
    for a, b in zip(st, en):
        seg = lr[a + 1:b].copy(); rng.shuffle(seg)
        Cs[a] = C[a]
        Cs[a + 1:b] = C[a] * np.exp(np.cumsum(seg))
    # shuffled bars: keep each bar's range around the new close
    half = (H - L) / 2
    Os = np.r_[Cs[0], Cs[:-1]]; Os[newd] = Cs[newd]
    Hs = np.maximum(Os, Cs) + 0.5 * half
    Ls = np.minimum(Os, Cs) - 0.5 * half

    def signals(c, pct, mode, N):
        """online zigzag on closes; returns list of (bar, dir, kind) at the moment the rule fires"""
        out = []
        d_ = 0; ext = 0; piv = 0; fired = False
        for k in range(n):
            if newd[k]:
                d_, ext, piv, fired = 0, k, k, False
                continue
            if d_ == 0:
                if c[k] >= c[piv] * (1 + pct):
                    d_, ext, fired = 1, k, False
                elif c[k] <= c[piv] * (1 - pct):
                    d_, ext, fired = -1, k, False
                continue
            if d_ == 1:
                if c[k] > c[ext]:
                    ext = k
                elif c[k] <= c[ext] * (1 - pct):
                    piv, d_, ext, fired = ext, -1, k, False
                    if mode == "fresh":
                        out.append((k, 1, piv))                  # fade the new DOWN leg: buy
                    continue
            else:
                if c[k] < c[ext]:
                    ext = k
                elif c[k] >= c[ext] * (1 + pct):
                    piv, d_, ext, fired = ext, 1, k, False
                    if mode == "fresh":
                        out.append((k, -1, piv))                 # fade the new UP leg: sell
                    continue
            if mode == "mature" and not fired and k - piv >= N:
                out.append((k, d_, piv)); fired = True
        return out

    def run(sigs, o, h, l, c, pct, mode, filt=None, rand=False):
        res, busy = [], -1
        rg = np.random.default_rng(7)
        for k, dr, piv in sigs:
            if k <= busy or k + 1 >= n or flat[k + 1]:
                continue
            if hm[k] < 90 or hm[k] >= 1320 or not np.isfinite(atr[k]):
                continue
            if filt is not None and not filt[k]:
                continue
            if rand:
                dr = 1 if rg.random() < 0.5 else -1
            e = o[k + 1]; q0 = k + 1
            if mode == "mature":
                extp = c[k]                                   # leg extreme so far (closed bars)
                for j in range(piv, k + 1):
                    extp = max(extp, c[j]) if dr == 1 else min(extp, c[j])
                cap = 120
                tp = None
            else:
                cap = 30
                tp = c[piv]
                slp = c[k] * (1 - dr * pct)                    # another pct in the new leg's direction
                if (tp - e) * dr <= 0 or (e - slp) * dr <= 0:
                    continue
            ex = None; q = q0
            while q < n:
                if flat[q] or q - q0 >= cap:
                    ex = o[q]; break
                stop = (extp * (1 - pct) if dr == 1 else extp * (1 + pct)) if mode == "mature" else slp
                if (o[q] - stop) * dr <= 0:
                    ex = o[q]; break
                if tp is not None and (o[q] - tp) * dr >= 0:
                    ex = o[q]; break
                if dr == 1:
                    if l[q] <= stop:
                        ex = stop; break
                    if tp is not None and h[q] >= tp:
                        ex = tp; break
                else:
                    if h[q] >= stop:
                        ex = stop; break
                    if tp is not None and l[q] <= tp:
                        ex = tp; break
                if mode == "mature":                          # update the extreme from the CLOSED bar
                    extp = max(extp, c[q]) if dr == 1 else min(extp, c[q])
                q += 1
            if ex is None:
                continue
            res.append((k + 1, (ex - e) * dr, sp[k + 1]))
            busy = q
        if len(res) < 50:
            return None
        T = pd.DataFrame(res, columns=["k", "pnl", "sp"])
        T["t"] = B.index[T.k.values]
        T["net"] = (T.pnl - T.sp) * usd
        T["st"] = (T.pnl - 1.5 * T.sp) * usd
        return T

    def line(lab, T, mark=True):
        if T is None or len(T) < 50:
            say(f"{lab:36s} {0 if T is None else len(T):6d} (too few)"); return
        P, P1, P2, PS = pf(T.net.values), pf(T[T.t < mid_t].net.values), pf(T[T.t >= mid_t].net.values), pf(T.st.values)
        l12 = T[T.t >= end_t - pd.Timedelta(days=365)].net.sum()
        eq = T.net.cumsum().values
        dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
        wd = T.groupby(T.t.dt.normalize()).net.sum().min()
        ok = len(T) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0
        say(f"{lab:36s} {len(T):6d} {len(T) / days:4.2f} {100 * (T.net > 0).mean():4.1f} {SA.f2(P)} {SA.f2(P1)} "
            f"{SA.f2(P2)} {SA.f2(PS)} {l12:+7.0f} {T.net.sum():+6.0f} {dd:+7.0f} {wd:+8.1f}  {'PASS' if ok and mark else ''}")

    g8 = gate >= 8
    ny = (myt >= 21) | (myt < 1)
    lon = (myt >= 15) & (myt < 21)
    asia = (myt >= 7) & (myt < 15)
    for pct in (0.0005, 0.0010, 0.0020):
        say(f"\n=== zigzag {pct * 100:.2f}% (about ${pct * 4000:.0f}) ===")
        say("MATURE: follow a leg once it is N candles old, stop = the zigzag reversal level")
        say(HDR)
        Ns = (10, 20, 30) if pct == 0.0005 else ((20, 30, 45, 60) if pct == 0.0010 else (45, 60, 90))
        for N in Ns:
            s = signals(C, pct, "mature", N)
            line(f"N{N} all day", run(s, O, H, L, C, pct, "mature"))
            line(f"N{N} gate>=8", run(s, O, H, L, C, pct, "mature", filt=g8))
            line(f"N{N} NY 21-01 MYT", run(s, O, H, L, C, pct, "mature", filt=ny))
            line(f"N{N} random direction", run(s, O, H, L, C, pct, "mature", rand=True), mark=False)
            s2 = signals(Cs, pct, "mature", N)
            line(f"N{N} SHUFFLED path (control)", run(s2, Os, Hs, Ls, Cs, pct, "mature"), mark=False)
        say("FRESH: fade a newly confirmed leg, TP back at its start, SL one more step")
        say(HDR)
        s = signals(C, pct, "fresh", 0)
        line("fresh fade all day", run(s, O, H, L, C, pct, "fresh"))
        line("fresh fade gate>=8", run(s, O, H, L, C, pct, "fresh", filt=g8))
        line("fresh fade NY", run(s, O, H, L, C, pct, "fresh", filt=ny))
        line("fresh fade London", run(s, O, H, L, C, pct, "fresh", filt=lon))
        line("fresh fade Asia", run(s, O, H, L, C, pct, "fresh", filt=asia))
        s2 = signals(Cs, pct, "fresh", 0)
        line("fresh fade SHUFFLED (control)", run(s2, Os, Hs, Ls, Cs, pct, "fresh"), mark=False)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
