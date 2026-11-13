"""Round 99d (13 Nov 2026): counter the reversal CSAK's losing days without switching it off.
Owner, after a day where every RCS trade hit the SL in a strong USD rally: "cari jalan la bro counter balik loss. bukan off kan".
No lot increase (martingale / recovery lots failed in rounds 60 / 72).  Portfolio rules tested on the live rule (SL 2 ATR,
no TP, 8 h), last 2 years, 28 forex + XAUUSD, one position per symbol, in time order:
  STOP n    after n SL hits today (server day), no more RCS entries today
  CCY COOL  after a losing trade today that was long / short a currency, no new trade on that side of it today
  FLIP n    after n SL hits today, the rest of today's signals are taken the OTHER way (with the trend)
  TREND k   skip a signal when its own symbol has already moved >= k x ATR14(D1) against it since today's open
  TFLIP k   the same signals are FLIPPED instead of skipped
Every outcome (normal and flipped) is simulated on the bars; the rules only choose which one is taken."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bbma99 as B

say = B.say; pf = B.pf
T0 = time.time()


def outcomes(cx, sw, mt, mask):
    """for every signal: entry time, both directions' net $ / exit time / reason, and the day-move-against feature"""
    O, H, L, S, T, ts, day, wd, n, usd = (cx[k] for k in ("O", "H", "L", "S", "T", "ts", "day", "wd", "n", "usd"))
    ks, dr, at, atr = cx["ks"], cx["dr"], cx["at"], cx["atr15"]
    # daily open (first M5 bar of the server day) and ATR14 of completed days
    dd = pd.Series(day)
    first = np.r_[True, day[1:] != day[:-1]]
    dopen = pd.Series(np.where(first, O, np.nan)).ffill().values
    D = pd.DataFrame({"h": H, "l": L, "c": cx["O"], "d": day}).groupby("d").agg(h=("h", "max"), l=("l", "min"))
    D["c"] = pd.Series(O).groupby(day).last().values
    pc = D.c.shift()
    tr = np.maximum(D.h - D.l, np.maximum((D.h - pc).abs(), (D.l - pc).abs()))
    datr = tr.rolling(14).mean().shift(1)
    datr_bar = datr.reindex(day).values
    rows = []
    for idx in np.where(mask)[0]:
        k, cd = ks[idx], dr[idx]; i = at[k]
        if i >= n - 1: continue
        a = atr[k]; out = []
        for d_ in (cd, -cd):
            e = O[i] + (S[i] if d_ == 1 else 0); risk = 2.0 * a; sl = e - d_ * risk
            x = None; z = i; nights = 0; why = "time"
            while z < n:
                if z > i and day[z] != day[z - 1]: nights += 3 if (sw and 1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
                if ts[z] - ts[i] >= 8 * 3600: x = O[z] + (S[z] if d_ == -1 else 0); break
                if d_ == 1:
                    if L[z] <= sl: x = min(O[z], sl) if z > i else sl; why = "sl"; break
                else:
                    if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; why = "sl"; break
                z += 1
            if x is None: x = O[n - 1]; z = n - 1
            swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
            out.append(((x - e) * d_ * usd + swp, T[min(z, n - 1)], why, risk * usd))
        against = -cd * (O[i] - dopen[i]) / datr_bar[i] if np.isfinite(datr_bar[i]) and datr_bar[i] > 0 else 0.0
        rows.append((T[i], cd, out[0][0], out[0][1], out[0][2], out[1][0], out[1][1], out[1][2], out[0][3], against))
    return pd.DataFrame(rows, columns=["t", "d", "net", "tx", "why", "fnet", "ftx", "fwhy", "risk", "against"])


def portfolio(X, rule=None, par=None):
    """walk the signals in time order; returns the trades taken (net, t, tx, sym, d) under the rule"""
    X = X.sort_values("t").reset_index(drop=True)
    busy = {}; closed = []                                                  # closed: (tx, day, why, net, sym, d)
    out = []
    for r in X.itertuples():
        if busy.get(r.sym, pd.Timestamp(0)) > r.t: continue
        today = r.t.normalize()
        done = [c for c in closed if c[0] <= r.t and c[1] == today]
        nsl = sum(1 for c in done if c[2] == "sl")
        flip = False
        if rule == "stop" and nsl >= par: continue
        if rule == "flip" and nsl >= par: flip = True
        if rule == "cool":
            b, q = r.sym[:3], r.sym[3:]
            bad = set()
            for c in done:
                if c[3] < 0:
                    bad.add((c[4][:3], c[5])); bad.add((c[4][3:], -c[5]))       # (currency, side) that lost: +1 long it, -1 short it
            if (b, r.d) in bad or (q, -r.d) in bad: continue
        if rule == "trend" and r.against >= par: continue
        if rule == "tflip" and r.against >= par: flip = True
        if flip: net, tx, why, d_ = r.fnet, r.ftx, r.fwhy, -r.d
        else: net, tx, why, d_ = r.net, r.tx, r.why, r.d
        busy[r.sym] = tx
        closed.append((tx, tx.normalize(), why, net, r.sym, d_))
        out.append((r.t, tx, net, net / r.risk, d_, r.sym, flip))
    return pd.DataFrame(out, columns=["t", "tx", "net", "r", "d", "sym", "flip"])


def report(name, x, END):
    mid = END - pd.Timedelta(days=365); oos = END - pd.Timedelta(days=182); a3 = END - pd.Timedelta(days=91)
    p = x.net.values
    day_pnl = x.groupby(x.tx.dt.normalize()).net.sum(); eq = day_pnl.cumsum(); mdd = (eq - eq.cummax()).min()
    bad = int((day_pnl <= -20).sum())
    g = x[x.sym == "XAUUSD"]
    ok = len(x) >= 150 and pf(p) >= 1.15 and pf(p[x.t < mid]) >= 1.05 and pf(p[x.t >= mid]) >= 1.05 and p[x.t >= mid].sum() > 0
    say(f"{name:40s} {len(x):4d} {100 * (p > 0).mean():4.0f} {pf(p):5.2f} {pf(p[x.t < mid]):5.2f} {pf(p[x.t >= mid]):5.2f} {pf(p[x.t >= oos]):5.2f} | "
        f"{p.sum():+6.0f} {p[x.t >= mid].sum():+6.0f} {p[x.t >= a3].sum():+5.0f} | {mdd:+5.0f} {day_pnl.min():+5.0f} {bad:4d} | "
        f"{g.net.sum():+5.0f} {x.net.sum() - g.net.sum():+5.0f} {int(x.flip.sum()):4d} {'PASS' if ok else ''}")


def main():
    meta = B.SA.load_meta(os.path.join(B.DATA, "meta.txt")); SW = B.R23.load_swaps(); rg = np.random.default_rng(99)
    B.B97.CTX_ONLY = True
    ALL = []; END = None
    for sym in B.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(B.DATA, sym + ".csv")): continue
        cx = B.B97.run(sym, meta[sym], SW.get(sym), rg); END = cx["end"] if END is None else max(END, cx["end"])
        ks, dr = cx["ks"], cx["dr"]
        exa = np.where(dr == 1, cx["roll"](cx["exd"], 8)[ks - 1], cx["roll"](cx["exu"], 8)[ks - 1])
        m = (cx["h4pos"] <= -0.5) & (exa == 1) & (cx["spr"] <= 0.20)
        df = outcomes(cx, SW.get(sym), meta[sym], m)
        if len(df): ALL.append(df.assign(sym=sym))
    X = pd.concat(ALL)
    say(f"window {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; {len(X)} signals; $ per 0.01 lot; worst day and days <= -$20 counted on exit days\n")
    say(f"{'rule':40s} {'n':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'OOS':>5} | {'net$':>6} {'12m$':>6} {'3m$':>5} | {'maxDD':>5} {'wDay':>5} {'d<-20':>4} | "
        f"{'gold':>5} {'fx':>5} {'flip':>4}")
    report("LIVE (all signals)", portfolio(X), END)
    for n_ in (2, 3, 4): report(f"STOP after {n_} SL today", portfolio(X, "stop", n_), END)
    report("CCY COOL (no repeat of a losing side)", portfolio(X, "cool"), END)
    for n_ in (1, 2, 3): report(f"FLIP after {n_} SL today", portfolio(X, "flip", n_), END)
    for k in (0.3, 0.5, 0.75, 1.0): report(f"TREND skip if day moved >= {k} ATR against", portfolio(X, "trend", k), END)
    for k in (0.5, 0.75, 1.0, 1.5): report(f"TFLIP flip if day moved >= {k} ATR against", portfolio(X, "tflip", k), END)
    report("ALL FLIPPED (control)", portfolio(X, "flip", 0), END)
    # what the bad days look like
    L = portfolio(X); dp = L.groupby(L.tx.dt.normalize()).net.sum()
    say(f"\nLIVE: {len(dp)} trading days with an exit, worst 5 days: " + ", ".join(f"{d:%Y-%m-%d} {v:+.0f}" for d, v in dp.nsmallest(5).items()))
    say(f"days with >= 4 SL hits: {int((L.assign(sl=L.net < 0).groupby(L.tx.dt.normalize()).sl.sum() >= 4).sum())}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
