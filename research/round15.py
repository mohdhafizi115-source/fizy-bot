"""Round 15 (2 Nov 2026): more trades a day. New rule families not tested before, all 30 instruments.

The owner wants many entries a day ("entry banyak kali dalam sehari at least ada profit", "jangan ulang teknik yang
sama"). M5 indicator scalps already lost everywhere (spread), so this looks one step slower (H1 / H4) where costs
are smaller, plus new gold timed flows. Rules fixed before the run; day trades only (flat 22:30 server, no swap):
  NR7_H1   an H1 bar narrower than the 6 before it (range >= 0.3 ATR) -> OCO stops 0.05 ATR beyond its high / low
           for the next 3 bars, SL at the other side, TP 2R, at most 12 bars
  IB_H1    an H1 inside bar (inside the bar before, range >= 0.3 ATR) -> the same OCO
  NR7_H4 / IB_H4  the same on H4 bars (orders valid 2 bars, at most 6 bars)
  DONCH    H1 close above the last 20 H1 highs -> buy at the next open (shorts mirrored), SL 2 ATR(H1), exit when an
           H1 close falls below the last 10 lows (Turtle style, intraday)
  ZREV     H1 close more than 2.5 standard deviations below its 100-bar mean -> buy at the next open (shorts
           mirrored), exit when back at the mean, SL 2 ATR(H1), at most 48 bars
  RAND     one random H1 entry a day, random side, SL 1.5 ATR, TP 2R (chance baseline)
Signals 02:00-20:00 server. Costs: the fill bar's median spread (MT5 export), stress 1.5x.
Pass rule per instrument (CLAUDE.md): >= 150 trades, PF >= 1.15, both halves >= 1.05, stress >= 1.05, last 12 months
positive.
GOLD FLOWS (XAUUSD only), new event times: Shanghai Gold Benchmark AM 10:15 and PM 14:15 Beijing, SHFE night session
open 21:00 Beijing, India MCX open 09:00 IST. Windows -30/-15/-5 min -> event, event -> +5/+15/+30/+60, +5 -> +30;
the side is chosen on the first half (t >= 3), KEPT if the second half has t >= 2 and PF > 1.1 after spread;
control: the same scan with every event moved by +2h15m.
"""
import os, sys, glob, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT
import flows as FL

T0 = time.time()
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
RULES = ("NR7_H1", "IB_H1", "NR7_H4", "IB_H4", "DONCH", "ZREV", "RAND")


def say(s=""):
    print(s, flush=True)


def compress(B, kind, valid, maxb):
    o, h, l, c, A, hm = (B[x].values for x in ("o", "h", "l", "c", "atr", "hm"))
    rg = h - l
    sig = []
    for i in range(7, len(B) - 1):
        if not (120 <= hm[i] < 1200) or not np.isfinite(A[i]) or rg[i] < 0.3 * A[i]:
            continue
        if kind == "NR7" and not rg[i] < rg[i - 6:i].min():
            continue
        if kind == "IB" and not (h[i] <= h[i - 1] and l[i] >= l[i - 1]):
            continue
        b = 0.05 * A[i]
        sig.append(dict(k0=i + 1, kind="oco", dir=0, P=h[i] + b, sl=l[i], P2=l[i] - b, sl2=h[i], tp_r=2.0,
                        exp=i + valid, maxb=maxb))
    return sig


def donch(B):
    o, h, l, c, A, hm = (B[x].values for x in ("o", "h", "l", "c", "atr", "hm"))
    hh20 = pd.Series(h).rolling(20).max().shift(1).values
    ll20 = pd.Series(l).rolling(20).min().shift(1).values
    hh10 = pd.Series(h).rolling(10).max().shift(1).values
    ll10 = pd.Series(l).rolling(10).min().shift(1).values
    xl = c < ll10                                   # exit long after a close below the last 10 lows
    xs = c > hh10
    sig = []
    for i in range(21, len(B) - 1):
        if not (120 <= hm[i] < 1200) or not np.isfinite(A[i]):
            continue
        if c[i] > hh20[i]:
            sig.append(dict(k0=i + 1, kind="mkt", dir=1, sl=c[i] - 2 * A[i], tp=None, exp=i + 1, maxb=10 ** 6, xl=xl, xs=xs))
        elif c[i] < ll20[i]:
            sig.append(dict(k0=i + 1, kind="mkt", dir=-1, sl=c[i] + 2 * A[i], tp=None, exp=i + 1, maxb=10 ** 6, xl=xl, xs=xs))
    return sig


def zrev(B):
    c, A, hm = B.c.values, B.atr.values, B.hm.values
    m = pd.Series(c).rolling(100).mean().values
    sd = pd.Series(c).rolling(100).std(ddof=0).values
    z = (c - m) / np.where(sd > 0, sd, np.nan)
    xl, xs = z > 0, z < 0
    sig = []
    for i in range(101, len(B) - 1):
        if not (120 <= hm[i] < 1200) or not np.isfinite(A[i]) or not np.isfinite(z[i - 1]):
            continue
        if z[i] < -2.5 <= z[i - 1]:
            sig.append(dict(k0=i + 1, kind="mkt", dir=1, sl=c[i] - 2 * A[i], tp=None, exp=i + 1, maxb=48, xl=xl, xs=xs))
        elif z[i] > 2.5 >= z[i - 1]:
            sig.append(dict(k0=i + 1, kind="mkt", dir=-1, sl=c[i] + 2 * A[i], tp=None, exp=i + 1, maxb=48, xl=xl, xs=xs))
    return sig


def rand(B, seed):
    c, A, hm, d1 = B.c.values, B.atr.values, B.hm.values, B.date.values
    rng = np.random.default_rng(seed)
    sig = []
    for dt in np.unique(d1):
        idx = np.where((d1 == dt) & (hm >= 120) & (hm < 1200))[0]
        if len(idx) < 3:
            continue
        i = int(rng.choice(idx))
        if i + 1 < len(B) and np.isfinite(A[i]):
            dr = 1 if rng.random() < 0.5 else -1
            sig.append(dict(k0=i + 1, kind="mkt", dir=dr, sl=c[i] - dr * 1.5 * A[i], tp_r=2.0, exp=i + 1, maxb=10 ** 6))
    return sig


def flat_of(B):
    d = B.date.values
    return (B.hm.values >= 1350) | np.r_[True, d[1:] != d[:-1]]


def run_sim(B, sig):
    """SA.sim with per-signal exit flags (DONCH / ZREV carry their own arrays)"""
    arr = [B[x].values for x in ("o", "h", "l", "c", "s")]
    return SA.sim(*arr, sorted(sig, key=lambda g: g["k0"]), flat_of(B))


# ---------------------------------------------------------------- gold timed flows
GEV = [("SGE_AM", "Asia/Shanghai", 615), ("SGE_PM", "Asia/Shanghai", 855), ("SHFE_NIGHT", "Asia/Shanghai", 1260),
       ("MCX_OPEN", "Asia/Kolkata", 540)]
WIN = [(-30, 0), (-15, 0), (-5, 0), (0, 5), (0, 15), (0, 30), (0, 60), (5, 30)]


def no_roll(I, tz, a, b):
    keep = []
    for day in I.index:
        ok = True
        for m in (a, b):
            t = pd.Timestamp(day.year, day.month, day.day, m // 60, m % 60, tz=tz).tz_convert("Europe/Athens")
            hm = t.hour * 60 + t.minute
            ok &= not (hm >= 1425 or hm < 90)
        keep.append(ok)
    return I[np.array(keep, bool)] if len(I) else I


def gold_flows(path, point, unit=1.0):
    d = FL.load(path, point)
    say("\n== GOLD FLOWS: new event times (first half picks the side; KEPT = holds on the second half) ==")
    tot = {}
    for shift in (0, 135):
        found = kept = 0
        for nm, tz, m0 in GEV:
            m0 = (m0 + shift) % 1440
            for a, b in WIN:
                ta, tb = m0 + a, m0 + b
                if ta < 0 or tb >= 1440:
                    continue
                I = no_roll(FL.window_trades(d, tz, ta, tb, side=1), tz, ta, tb)
                I = I[I.index.dayofweek < 5] if len(I) else I
                if len(I) < 200:
                    continue
                first = I.index < I.index[len(I) // 2]
                for side in (1, -1):
                    t1 = FL.tstat(side * I.gross.values[first])
                    if not t1 >= 3:
                        continue
                    found += 1
                    g2 = side * I.gross.values[~first]
                    n2 = g2 - I.sp.values[~first]
                    nall = side * I.gross.values - I.sp.values
                    ok = FL.tstat(g2) >= 2 and FL.pf(n2) > 1.1
                    kept += ok
                    if shift == 0:
                        say(f"  {nm:10s} {'BUY ' if side > 0 else 'SELL'} {ta // 60:02d}:{ta % 60:02d}->{tb // 60:02d}:{tb % 60:02d} "
                            f"{tz.split('/')[1]:8s} n {len(I):4d} t1 {t1:+5.2f} t2 {FL.tstat(g2):+5.2f} net2 ${n2.mean() / unit:+5.2f} "
                            f"PF2 {FL.f2(FL.pf(n2))} PF all {FL.f2(FL.pf(nall))} {'KEPT' if ok else ''}")
        tot[shift] = (found, kept)
    say(f"  real times: {tot[0][0]} first-half hits, {tot[0][1]} kept | fake times (+2h15m): {tot[135][0]} hits, {tot[135][1]} kept")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    files = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    rows, info = [], {}
    for f in files:
        base = os.path.basename(f)[:-4]
        if base not in meta:
            continue
        d5 = SA.load(f, meta[base]["point"])
        if len(d5) < 20000:
            continue
        BH, B4 = DT.bars(d5, "1h"), DT.bars(d5, "4h")
        usd = meta[base]["tick_value"] / meta[base]["tick_size"] * 0.01 if meta[base]["tick_size"] > 0 else 0.0
        info[base] = dict(days=d5.index.normalize().nunique(), mid=d5.index[len(d5) // 2], end=d5.index[-1], usd=usd)
        sets = {"NR7_H1": (BH, compress(BH, "NR7", 3, 12)), "IB_H1": (BH, compress(BH, "IB", 3, 12)),
                "NR7_H4": (B4, compress(B4, "NR7", 2, 6)), "IB_H4": (B4, compress(B4, "IB", 2, 6)),
                "DONCH": (BH, donch(BH)), "ZREV": (BH, zrev(BH)), "RAND": (BH, rand(BH, 7))}
        for rule, (B, sig) in sets.items():
            for (k, dr, pnl, s_, risk, why) in run_sim(B, sig):
                rows.append((base, rule, B.index[k], dr, pnl, s_, risk))
        say(f"  {base:7s} done, {time.time() - T0:5.0f} s")
        if base == "XAUUSD":
            gold_path = (f, meta[base]["point"])
    T = pd.DataFrame(rows, columns=["sym", "rule", "t", "dir", "pnl", "sp", "risk"])
    T["R"] = (T.pnl - T.sp) / T.risk
    T["Rs"] = (T.pnl - 1.5 * T.sp) / T.risk
    T["usd"] = (T.pnl - T.sp) * T.sym.map(lambda s: info[s]["usd"])
    T["half"] = [1 if t >= info[s]["mid"] else 0 for s, t in zip(T.sym, T.t)]
    T["last12"] = [t >= info[s]["end"] - pd.Timedelta(days=365) for s, t in zip(T.sym, T.t)]
    T["year"] = T.t.dt.year
    pf, f2 = SA.pf, SA.f2
    say("\n== All instruments together (R units) ==")
    say("rule      trades /sym/day win%    PF  half1 half2 stress  avgR  syms PF>1  pass")
    passes, per_day = [], 0.0
    for rule in RULES:
        g = T[T.rule == rule]
        if g.empty:
            continue
        npass = 0
        for s, x in g.groupby("sym"):
            P, P1, P2, PS = pf(x.R.values), pf(x[x.half == 0].R.values), pf(x[x.half == 1].R.values), pf(x.Rs.values)
            ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and x[x.last12].R.sum() > 0
            if ok:
                npass += 1
                tpd = len(x) / info[s]["days"]
                if rule != "RAND":
                    per_day += tpd
                yr = " ".join(f"{y % 100}:{f2(pf(x[x.year == y].R.values))}" for y in sorted(x.year.unique()))
                passes.append(f"{rule:7s} {s:7s} {len(x):5d} trades ({tpd:.2f}/day) PF {f2(P)} halves {f2(P1)} {f2(P2)} "
                              f"stress {f2(PS)} net ${x.usd.sum():+.0f}/0.01 lot | {yr}")
        days = np.mean([info[s]["days"] for s in g.sym.unique()])
        npos = sum(1 for s, x in g.groupby("sym") if pf(x.R.values) > 1)
        say(f"{rule:8s} {len(g):7d} {len(g) / days / g.sym.nunique():7.2f} {100 * (g.R > 0).mean():5.1f} {f2(pf(g.R.values))} "
            f"{f2(pf(g[g.half == 0].R.values))} {f2(pf(g[g.half == 1].R.values))} {f2(pf(g.Rs.values))} {g.R.mean():+5.3f} "
            f"{npos:3d}/{g.sym.nunique():2d}  {npass:3d}")
    say("\n== Per instrument PF(R) ==")
    say("sym     " + " ".join(f"{r:>7s}" for r in RULES))
    for s in sorted(info):
        say(f"{s:7s} " + " ".join(f"{f2(pf(T[(T.sym == s) & (T.rule == r)].R.values)):>7s}" for r in RULES))
    say("\n== Passed (instrument x rule) ==")
    for p in passes:
        say("  " + p)
    nr = sum(1 for p in passes if p.startswith("RAND"))
    say(f"  {len(passes) - nr} rule passes of {(len(RULES) - 1) * len(info)}; RAND passed on {nr} of {len(info)} instruments")
    say(f"  extra trades a day if every pass were added: {per_day:.1f}")
    if "XAUUSD" in info:
        gold_flows(*gold_path)
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
