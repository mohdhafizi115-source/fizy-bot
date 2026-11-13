"""Round 99c (13 Nov 2026): reversal CSAK - cut the trade when a NEW M15 momentum candle forms against it.
Owner: "minta cek balik csak reverse tu, aku rasa sebab sl, cuba ubah kalau candle buat mom baru cut loss. test jp".
Momentum (BBMA): an M15 candle that CLOSES beyond the Bollinger band (20, 2).  For a BUY the exit is the first M15 close
below the bottom band after the entry, for a SELL the first close above the top band; the trade is closed at the next
M5 open.  Variants: live (SL 2 ATR, 8 h) with / without the momentum cut, no SL + momentum cut (8 h / 24 h, a 10-ATR
disaster stop only), swing SL + cut, SL 3 ATR + cut.  Last 2 years, 28 forex + XAUUSD (the live portfolio)."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bbma99 as B

say = B.say; pf = B.pf
T0 = time.time()


def sim(cx, sw, mt, mask, p, rand, rg):
    O, H, L, S, T, ts, day, wd, n, usd = (cx[k] for k in ("O", "H", "L", "S", "T", "ts", "day", "wd", "n", "usd"))
    ks, dr, at, swl, swh, top, bot, atr, c15 = cx["ks"], cx["dr"], cx["at"], cx["swl"], cx["swh"], cx["top"], cx["bot"], cx["atr15"], cx["c15"]
    momL = np.zeros(n + 1, bool); momS = np.zeros(n + 1, bool)            # an M15 bar closed beyond the band, flagged at the M5 bar after it
    qa = np.where(c15 < bot)[0]; momL[np.minimum(at[qa], n)] = True       # bad for a BUY
    qb = np.where(c15 > top)[0]; momS[np.minimum(at[qb], n)] = True       # bad for a SELL
    res = []; busy = -1
    for idx in np.where(mask)[0]:
        k, cd = ks[idx], dr[idx]; i = at[k]
        if i >= n or i <= busy: continue
        e0 = O[i] + (S[i] if cd == 1 else 0); a = atr[k]
        if p["sl"] == "atr": sl0 = e0 - cd * p["slk"] * a
        else: sl0 = swl[idx] - S[i] if cd == 1 else swh[idx] + S[i]
        risk = (e0 - sl0) * cd
        if risk <= S[i]: continue
        d_ = cd if not rand else (1 if rg.random() < 0.5 else -1)
        e = O[i] + (S[i] if d_ == 1 else 0); sl = e - d_ * risk
        x = None; z = i; nights = 0; why = "time"; worst = 0.0
        while z < n:
            if z > i and day[z] != day[z - 1]: nights += 3 if (sw and 1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
            if ts[z] - ts[i] >= p["hold"] * 3600: x = O[z] + (S[z] if d_ == -1 else 0); break
            if p["mom"] and z > i and (momL[z] if d_ == 1 else momS[z]):
                x = O[z] + (S[z] if d_ == -1 else 0); why = "mom"; break
            if d_ == 1:
                if L[z] <= sl: x = min(O[z], sl) if z > i else sl; why = "sl"; break
                worst = min(worst, L[z] - e)
            else:
                if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; why = "sl"; break
                worst = min(worst, e - H[z] - S[z])
            z += 1
        if x is None: break
        swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
        net = (x - e) * d_ * usd + swp
        rk = risk * usd if p["sl"] != "atr" or p["slk"] < 9 else 2.0 * a * usd   # R measured against a 2-ATR stop when the SL is only a disaster stop
        res.append((T[i], T[min(z, n - 1)], net, net / rk, (net - 0.5 * S[i] * usd) / rk, d_, rk, why, worst * usd))
        busy = z
    return pd.DataFrame(res, columns=["t", "tx", "net", "r", "rs", "d", "risk", "why", "mae"])


V = [("LIVE: SL 2 ATR, 8 h", dict(sl="atr", slk=2.0, hold=8, mom=False)),
     ("SL 2 ATR + cut on opposite M15 MOM, 8 h", dict(sl="atr", slk=2.0, hold=8, mom=True)),
     ("SL 3 ATR + cut on MOM, 8 h", dict(sl="atr", slk=3.0, hold=8, mom=True)),
     ("swing SL + cut on MOM, 8 h", dict(sl="sw", slk=0.0, hold=8, mom=True)),
     ("NO SL (10-ATR disaster) + cut on MOM, 8 h", dict(sl="atr", slk=10.0, hold=8, mom=True)),
     ("NO SL (10-ATR disaster) + cut on MOM, 24 h", dict(sl="atr", slk=10.0, hold=24, mom=True)),
     ("NO SL (10-ATR disaster), no cut, 8 h", dict(sl="atr", slk=10.0, hold=8, mom=False))]


def main():
    meta = B.SA.load_meta(os.path.join(B.DATA, "meta.txt")); SW = B.R23.load_swaps(); rg = np.random.default_rng(99)
    B.B97.CTX_ONLY = True
    ALL = {}; END = None
    for sym in B.SYMS:
        if sym not in meta or not os.path.exists(os.path.join(B.DATA, sym + ".csv")): continue
        cx = B.B97.run(sym, meta[sym], SW.get(sym), rg); END = cx["end"] if END is None else max(END, cx["end"])
        ks, dr = cx["ks"], cx["dr"]
        exa = np.where(dr == 1, cx["roll"](cx["exd"], 8)[ks - 1], cx["roll"](cx["exu"], 8)[ks - 1])
        m = (cx["h4pos"] <= -0.5) & (exa == 1) & (cx["spr"] <= 0.20)
        for name, p in V:
            for rand in (False, True):
                df = sim(cx, SW.get(sym), meta[sym], m, p, rand, rg)
                if len(df): ALL.setdefault((name, rand), []).append(df.assign(sym=sym))
    say(f"window {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; 28 forex + XAUUSD; entries = the live rule; $ per 0.01 lot\n")
    hdr = (f"{'exit':44s} {'n':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'IS':>5} {'OOS':>5} | {'12m R':>6} {'3m R':>5} {'p3m':>5} | "
           f"{'net $':>6} {'gold':>5} {'fx':>5} {'maxDD':>6} {'wDay':>5} {'opn':>3} | {'RAND':>5}")
    say(hdr)
    E = lambda name, rand: pd.concat(ALL[(name, rand)])
    for name, _ in V:
        B.line(name, E(name, False), E(name, True), END)
    say("\nhow the trades end, average $ by exit reason, worst trade, average worst floating (MAE)")
    for name, _ in V:
        x = E(name, False)
        parts = "  ".join(f"{w}: {100 * (x.why == w).mean():3.0f}% avg ${x.net[x.why == w].mean():+.2f}" for w in ("sl", "mom", "time") if (x.why == w).any())
        say(f"  {name:44s} {parts} | worst ${x.net.min():.0f}, avg MAE ${x.mae.mean():.2f}, worst MAE ${x.mae.min():.0f}")
    say("\ngold vs forex PF")
    for name, _ in V:
        x = E(name, False); g = x[x.sym == "XAUUSD"]; f = x[x.sym != "XAUUSD"]
        say(f"  {name:44s} gold {len(g):3d} PF {pf(g.net.values):.2f} ${g.net.sum():+.0f} | forex {len(f):3d} PF {pf(f.net.values):.2f} ${f.net.sum():+.0f}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
