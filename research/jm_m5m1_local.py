"""All gold scalping rules on the user's JustMarkets exports: M5 (Jun 2025 - Oct 2026) and M1 (Jul - Oct 2026).
Per-bar spread from the export. Chart time = server time (Europe/Athens)."""
import sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/fizy-bot/research")
import scalp2 as X, scalp3 as Y, flag as FL

UP = "/mnt/user-data/uploads/Desktop/"
FILES = {"M5": UP + "XAUUSD.m_M5_202506042130_202610301850", "M1": UP + "XAUUSD.m_M1_202607220257_202610301849"}
out = []
def say(s=""):
    print(s, flush=True); out.append(s)


def load(path):
    df = pd.read_csv(path, sep="\t"); df.columns = [c.strip("<>").lower() for c in df.columns]
    idx = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df.index = idx.dt.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC").values
    df.index = pd.DatetimeIndex(df.index, tz="UTC")
    df = df[df.index.notna()]
    d = df[["open", "high", "low", "close"]].astype(float).copy(); d["volume"] = df["tickvol"].astype(float).values
    d["spr"] = df["spread"].astype(float).values * 0.01
    return d[~d.index.duplicated()]


def rsi2_m5(d):
    """The live M5 scalp: close > EMA 200 and RSI(2) < 10 -> buy next open (sell mirrored), SL 2 ATR,
    exit when a close crosses back over the SMA 5 or after 24 candles."""
    c = d.close
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    r = (100 - 100 / (1 + up / dn)).values; s5 = c.rolling(5).mean().values; cc = c.values
    A = d.atr.values; e200 = d.e200.values; chh = d.ch_h.values
    sig = {}
    for i in range(210, len(d) - 1):
        if not (8 <= chh[i] < 20) or np.isnan(A[i]):
            continue
        dr = 1 if (cc[i] > e200[i] and r[i] < 10) else (-1 if (cc[i] < e200[i] and r[i] > 90) else 0)
        if dr:
            sig[i] = dict(type="market", dir=dr, price=None, sl=cc[i] - dr * 2 * A[i], tp=None, exp=i + 1, maxb=24)
    return sig, cc > s5, cc < s5


def stats(tr, d, name, days):
    if not len(tr):
        say(f"  {name:34s} no trades"); return None
    x = tr.pnl.values
    t = tr.t.dt.tz_convert("Europe/Athens")
    mid = d.index[len(d) // 2]
    h1, h2 = tr[tr.t < mid].pnl.values, tr[tr.t >= mid].pnl.values
    mon = tr.groupby(t.dt.strftime("%Y-%m")).pnl.sum()
    dayp = tr.groupby(t.dt.date).pnl.sum()
    cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
    say(f"  {name:34s} {len(tr):5d} tr ({len(tr) / days:4.1f}/day) win {np.mean(x > 0) * 100:3.0f}% PF {X.pf(x):.2f} "
        f"net ${x.sum():+6.0f} | halves {X.pf(h1):.2f}/{X.pf(h2):.2f} | months + {int((mon > 0).sum())}/{len(mon)} "
        f"| days + {np.mean(dayp > 0) * 100:.0f}% | DD ${dd:.0f}")
    return dict(name=name, n=len(tr), pf=X.pf(x), net=x.sum(), h1=X.pf(h1), h2=X.pf(h2), mpos=(mon > 0).mean(), mon=mon)


def run_all(d, label, sets):
    sp = d.spr.values
    days = d.ch_day.nunique()
    say(f"\n{label}: {len(d)} candles {d.index[0]:%Y-%m-%d}..{d.index[-1]:%Y-%m-%d}, {days} days, "
        f"spread median ${np.median(sp):.2f}")
    res = []
    t0 = time.time()
    if "r2" in sets:
        for key, name, fn in X.VARIANTS:
            sig, flat = fn(d)
            res.append(stats(X.run(d, sig, sp, flat), d, "R2 " + key + " " + name[:20], days))
    if "r3" in sets:
        for kind, ema in Y.VARIANTS:
            sig, xl, xs = Y.signals(d, kind, ema)
            res.append(stats(Y.run3(d, sig, sp, xl, xs), d, "R3 " + kind + ("+ema200" if ema else ""), days))
    if "flag" in sets:
        for name, kw in FL.VARIANTS:
            res.append(stats(Y.run3(d, FL.flag_signals(d, **kw), sp), d, "FLAG " + name, days))
    if "rsi2" in sets:
        sig, xl, xs = rsi2_m5(d)
        res.append(stats(Y.run3(d, sig, sp, xl, xs), d, "LIVE M5 RSI(2) scalp", days))
    say(f"  ({time.time() - t0:.0f} s)")
    return [r for r in res if r]


if __name__ == "__main__":
    m5 = load(FILES["M5"])
    d5 = Y.prep(m5.copy())
    r5 = run_all(d5, "JustMarkets XAUUSD.m M5", {"r2", "r3", "flag", "rsi2"})
    m1 = load(FILES["M1"])
    d1 = Y.prep(m1.copy())
    r1 = run_all(d1, "JustMarkets XAUUSD.m M1", {"r3", "rsi2"})
    good = [r for r in r5 if r["pf"] > 1.1 and r["h1"] > 1 and r["h2"] > 1 and r["n"] >= 100]
    say("\nM5 rules with PF > 1.1, both halves > 1 and 100+ trades: " + (", ".join(f"{r['name']} (PF {r['pf']:.2f})" for r in good) or "none"))
    for r in good:
        say(f"  {r['name']} by month: " + ", ".join(f"{m[2:]} {v:+.0f}" for m, v in r["mon"].items()))
    open("/tmp/claude-0/-home-claude/a70dd1f2-1b74-5de3-a201-59cd75c0f86b/scratchpad/jm_m5m1_results.txt", "w").write("\n".join(out) + "\n")
