"""Quasimodo (QM / QML) on the broker's history (2 Nov 2026).

The owner asked for "teknik Quasimodo oleh cikgu Bahar". The teacher's own rules are not public (search found only
the generic QM pattern: Capital.com, TradingView QML ideas), so the standard pattern is tested; the teacher's exact
rules can be tested when the owner sends them.
Pattern (5-bar fractal swings, alternating highs and lows, confirmed 2 bars after the swing):
  Bearish QM: high H1, low L1, higher high H2 (> H1), lower low L2 (< L1, the break of structure).
              QML = H1 (the left shoulder). Sell limit at QML, SL 0.1 ATR above H2 (the head).
  Bullish QM: the mirror (low L1, high H1, lower low L2, higher high H2): buy limit at L1, SL below L2.
  The order is live for 48 bars after the pattern is confirmed and is cancelled if a bar closes beyond the break
  (below L2 / above H2) before the fill. One trade at a time.
Variants (fixed before the run):
  QM_2R     TP 2R
  QM_BOS    TP at the break-of-structure swing (L2 / H2 of the bullish case); skipped if that is < 1R
  QM_CONF   no limit: wait for a bar that trades into the QML and closes back on the other side, enter at the next
            open, SL beyond the head, TP 2R
  FAKE_2R   control for limit-order fill effects: every QM setup moved by 0.5 ATR up or down at random (QML, head and
            break together), then traded like QM_2R. A real QM must beat it, not only be profitable
  RAND      random market entries at the same rate as QM_2R, SL 1.5 ATR, TP 2R (chance baseline)
Timeframes M5, M15 (day trades, flat 23:00 server) and H1 (at most 48 bars, swap not counted). Fills: a limit fills
when the price reaches the level; on the fill bar only the SL, or a close beyond the TP, is counted (the bar's other
extreme may come before the fill). Later bars: SL first when both are hit. Costs: the fill bar's spread; stress 1.5x.
Usual pass rule per instrument and timeframe.
"""
import os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP", "BTCUSD"]
TFS = [("M5", "5min"), ("M15", "15min"), ("H1", "1h")]
VARS = ["QM_2R", "QM_BOS", "QM_CONF", "FAKE_2R", "RAND"]
T0 = time.time()


def say(s=""):
    print(s, flush=True)


def setups(B):
    """QM patterns: (bar when confirmed, side, qml, head, bos)"""
    h, l = B.h.values, B.l.values
    n = len(B)
    sw = []                                     # alternating swings: (type 'H'/'L', price, bar)
    out = []
    for k in range(4, n):
        i = k - 2                               # the swing bar, confirmed now
        new = []
        if h[i] > max(h[i - 2], h[i - 1], h[i + 1], h[i + 2]):
            new.append(("H", h[i], i))
        if l[i] < min(l[i - 2], l[i - 1], l[i + 1], l[i + 2]):
            new.append(("L", l[i], i))
        for s in new:
            if sw and sw[-1][0] == s[0]:
                if (s[0] == "H" and s[1] > sw[-1][1]) or (s[0] == "L" and s[1] < sw[-1][1]):
                    sw[-1] = s
                else:
                    continue
            else:
                sw.append(s)
            if len(sw) >= 4:
                a, b, c, d = sw[-4:]
                if a[0] == "H" and c[1] > a[1] and d[1] < b[1]:          # H1 L1 H2 L2: higher high, then lower low
                    out.append((k, -1, a[1], c[1], d[1]))
                if a[0] == "L" and c[1] < a[1] and d[1] > b[1]:          # L1 H1 L2 H2: lower low, then higher high
                    out.append((k, 1, a[1], c[1], d[1]))
    return out


def sim_limit(B, S, A, flat, tp_mode, maxb):
    o, h, l, c, sp = (B[x].values for x in ("o", "h", "l", "c", "s"))
    n = len(B)
    res, busy = [], -1
    for k, dr, qml, head, bos in S:
        if k <= busy or k + 1 >= n or not np.isfinite(A[k]):
            continue
        a = A[k]
        sl = head - dr * 0.1 * a                    # dr = +1 buy: head is the low below
        risk0 = (qml - sl) * dr
        if risk0 <= 0.2 * a:
            continue
        tp = qml + dr * 2 * risk0 if tp_mode == "2R" else bos
        if tp_mode == "BOS" and (tp - qml) * dr < risk0:
            continue
        if (c[k] - qml) * dr <= 0:                  # price already at / through the QML when confirmed
            continue
        fill = None
        for j in range(k + 1, min(k + 48, n)):
            if flat[j]:
                break
            if (dr == -1 and c[j - 1] < bos) or (dr == 1 and c[j - 1] > bos):
                break                               # the break continued: setup cancelled
            if (dr == -1 and h[j] >= qml) or (dr == 1 and l[j] <= qml):
                fill = j; break
        if fill is None:
            busy = max(busy, k)
            continue
        j = fill
        e = max(o[j], qml) if dr == -1 else min(o[j], qml)
        risk = (e - sl) * dr
        if risk <= 0:
            busy = j; continue
        ex = None
        if (dr == -1 and h[j] >= sl) or (dr == 1 and l[j] <= sl):
            ex = sl
        elif (dr == -1 and c[j] <= tp) or (dr == 1 and c[j] >= tp):
            ex = tp
        m = j + 1
        while ex is None and m < n:
            if flat[m] or m - j > maxb:
                ex = o[m]; break
            if (o[m] - sl) * dr <= 0 or (o[m] - tp) * dr >= 0:
                ex = o[m]; break
            if (dr == -1 and h[m] >= sl) or (dr == 1 and l[m] <= sl):
                ex = sl; break
            if (dr == -1 and l[m] <= tp) or (dr == 1 and h[m] >= tp):
                ex = tp; break
            m += 1
        if ex is None:
            ex, m = c[-1], n - 1
        res.append((j, dr, (ex - e) * dr, sp[j], risk, ""))
        busy = m
    return res


def conf_signals(B, S, A):
    """QM_CONF: a bar trades into the QML and closes back on the other side -> enter at the next open"""
    h, l, c = B.h.values, B.l.values, B.c.values
    n = len(B)
    sig = []
    for k, dr, qml, head, bos in S:
        if not np.isfinite(A[k]):
            continue
        for j in range(k + 1, min(k + 48, n - 1)):
            if (dr == -1 and c[j - 1] < bos) or (dr == 1 and c[j - 1] > bos):
                break
            if (dr == -1 and h[j] >= head) or (dr == 1 and l[j] <= head):
                break                               # through the head: pattern failed
            if (dr == -1 and h[j] >= qml and c[j] < qml) or (dr == 1 and l[j] <= qml and c[j] > qml):
                sl = head - dr * 0.1 * A[k]
                sig.append(dict(k0=j + 1, kind="mkt", dir=dr, sl=sl, tp_r=2.0, exp=j + 1, maxb=48))
                break
    return sorted(sig, key=lambda g: g["k0"])


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    rows, info = [], {}
    rng = np.random.default_rng(23)
    for sym in SYMS:
        f = os.path.join(DATA, sym + ".csv")
        if sym not in meta or not os.path.exists(f):
            continue
        d5 = SA.load(f, meta[sym]["point"])
        info[sym] = dict(mid=d5.index[len(d5) // 2], end=d5.index[-1], days=d5.index.normalize().nunique(),
                         usd=meta[sym]["tick_value"] / meta[sym]["tick_size"] * 0.01 if meta[sym]["tick_size"] > 0 else 0.0)
        for tf, rule in TFS:
            B = DT.bars(d5, rule)
            A = B.atr.values
            dates = B.date.values
            newday = np.r_[True, dates[1:] != dates[:-1]]
            flat = ((B.hm.values >= 1380) | newday) if tf != "H1" else np.zeros(len(B), bool)
            maxb = 10 ** 6 if tf != "H1" else 48
            hm = B.hm.values
            S = [x for x in setups(B) if 90 <= hm[x[0]] < 1320]
            arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
            r2 = sim_limit(B, S, A, flat, "2R", maxb)
            sh = rng.choice([-0.5, 0.5], size=len(S))
            SF = [(k, dr, q + x * A[k], hd + x * A[k], bo + x * A[k]) for (k, dr, q, hd, bo), x in zip(S, sh)]
            for name, res in (("QM_2R", r2), ("QM_BOS", sim_limit(B, S, A, flat, "BOS", maxb)),
                              ("QM_CONF", SA.sim(*arr, conf_signals(B, S, A), flat)),
                              ("FAKE_2R", sim_limit(B, SF, A, flat, "2R", maxb))):
                for (k, dr, pnl, s_, risk, why) in res:
                    rows.append((sym, tf, name, B.index[k], pnl, s_, risk))
            # random baseline at the QM_2R rate
            cand = np.where((hm >= 90) & (hm < 1320) & np.isfinite(A))[0]
            cand = cand[cand < len(B) - 2]
            pick = np.sort(rng.choice(cand, size=min(len(cand), max(len(r2), 1)), replace=False))
            sig = [dict(k0=i + 1, kind="mkt", dir=(1 if rng.random() < 0.5 else -1), sl=0.0, tp_r=2.0, exp=i + 1, maxb=maxb) for i in pick]
            for g in sig:
                g["sl"] = B.c.values[g["k0"] - 1] - g["dir"] * 1.5 * A[g["k0"] - 1]
            for (k, dr, pnl, s_, risk, why) in SA.sim(*arr, sig, flat):
                rows.append((sym, tf, "RAND", B.index[k], pnl, s_, risk))
        say(f"  {sym:7s} done, {time.time() - T0:5.0f} s")
    T = pd.DataFrame(rows, columns=["sym", "tf", "rule", "t", "pnl", "sp", "risk"])
    T["R"] = (T.pnl - T.sp) / T.risk
    T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = (T.pnl - T.sp) * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [t >= info[s]["mid"] for s, t in zip(T.sym, T.t)]
    T["l12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    pf, f2 = SA.pf, SA.f2
    say("\n== All 12 instruments together (R after spread) ==")
    say("tf   rule       trades /sym/day  win%    PF  half1 half2 stress  syms PF>1  pass")
    passes = []
    for tf, _ in TFS:
        for v in VARS:
            g = T[(T.tf == tf) & (T.rule == v)]
            if g.empty:
                continue
            npass = 0
            for s, x in g.groupby("sym"):
                P, P1, P2, PS = pf(x.R.values), pf(x[~x.half].R.values), pf(x[x.half].R.values), pf(x.Rs.values)
                ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and x[x.l12].R.sum() > 0
                if ok and v.startswith("QM"):               # a QM pass must also beat its fake twin by 0.10 PF
                    fk = T[(T.tf == tf) & (T.rule == "FAKE_2R") & (T.sym == s)]
                    ok = len(fk) > 0 and P - pf(fk.R.values) >= 0.10
                if ok:
                    npass += 1
                    passes.append(f"{tf:3s} {v:8s} {s:7s} {len(x):5d} trades PF {f2(P)} halves {f2(P1)} {f2(P2)} stress {f2(PS)} net ${x.usd.sum():+.0f}/0.01 lot")
            days = np.mean([info[s]["days"] for s in g.sym.unique()])
            npos = sum(1 for s, x in g.groupby("sym") if pf(x.R.values) > 1)
            say(f"{tf:4s} {v:9s} {len(g):7d} {len(g) / days / g.sym.nunique():7.2f} {100 * (g.R > 0).mean():5.1f} {f2(pf(g.R.values))} "
                f"{f2(pf(g[~g.half].R.values))} {f2(pf(g[g.half].R.values))} {f2(pf(g.Rs.values))} {npos:3d}/{g.sym.nunique():2d}  {npass:3d}")
    say("\n== Gold (XAUUSD) ==")
    for tf, _ in TFS:
        for v in VARS:
            x = T[(T.sym == "XAUUSD") & (T.tf == tf) & (T.rule == v)]
            if len(x):
                say(f"  {tf:3s} {v:8s} {len(x):5d} trades ({len(x) / info['XAUUSD']['days']:.2f}/day) win {100 * (x.R > 0).mean():4.1f}% "
                    f"PF {f2(pf(x.R.values))} halves {f2(pf(x[~x.half].R.values))} {f2(pf(x[x.half].R.values))} net ${x.usd.sum():+.0f}/0.01 lot")
    say("\n== Per instrument PF (R), QM_2R / QM_BOS / QM_CONF / FAKE_2R / RAND ==")
    for tf, _ in TFS:
        say(f"  {tf}: " + " | ".join(f"{s} " + "/".join(f2(pf(T[(T.sym == s) & (T.tf == tf) & (T.rule == v)].R.values)).strip() for v in VARS)
                                     for s in SYMS if s in info))
    say("\n== Passed ==")
    for p in passes:
        say("  " + p)
    nr = sum(1 for p in passes if " RAND " in p)
    nf = sum(1 for p in passes if " FAKE_2R " in p)
    say(f"  {len(passes) - nr - nf} QM passes (incl. beating the fake twin) of {3 * 3 * len(info)}; FAKE_2R passed the base rule {nf}, "
        f"RAND {nr} of {3 * len(info)}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
