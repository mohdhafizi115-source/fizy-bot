"""Round 99 (13 Nov 2026): better exits for the live reversal CSAK (v2.20, FizyRCS.mqh), last 2 years, the live
portfolio (28 forex pairs + XAUUSD, no BTC).  Owner: "kau tak boleh perbaiki lagi ke sl, tp dan be?" and "macam mana
boleh open posisi 8 serentak?".

Entries are exactly the live rule (round 98 centre).  Only the exit changes:
  SL     swing 12 (live) / swing + 0.25 / 0.5 ATR(M15) buffer / a plain ATR stop 1.0 / 1.5 / 2.0 / 3.0 ATR
  BE     SL to the entry price once price has been +0.5 / 1 / 1.5 / 2 R in profit (set after the bar that reached it)
  trail  once +act R is reached, SL = best price since entry - dist R (moved after each closed M5 bar only)
  TP     none (live) / 1.5 / 2 / 3 / 4 R / the opposite M15 Bollinger band at the CSAK (BBMA's own target)
  hold   8 h (live), 12 h, 24 h with BE / trail
Then position caps on the portfolio: at most 3 / 5 open at once, at most 2 positions on the same currency the same way.
Tuning rule: settings are chosen on the first 18 months (IS) and judged on the last 6 months (OOS).
Every line has the same exit with a RANDOM direction on the same entries.  R = profit / initial risk, pooled.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import ind23 as R23
import bbma87 as B87
import bbma97 as B97

DATA = B97.DATA
say = lambda s="": print(s, flush=True)
T0 = time.time()
pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0.0
SYMS = [s for s in B87.SYMS if s != "BTCUSD"]
C = dict(sl="sw", slk=0.0, be=0.0, tr=None, tp=0, hold=8)
V = [("LIVE: swing SL, no TP, 8 h", {})]
V += [(f"BE at +{b}R", {"be": b}) for b in (0.5, 1.0, 1.5, 2.0)]
V += [(f"BE +1R, hold {h} h", {"be": 1.0, "hold": h}) for h in (12, 24)]
V += [(f"trail from +{a}R, {d}R behind", {"tr": (a, d)}) for a, d in ((1, 1), (1, 1.5), (1.5, 1), (2, 1), (2, 1.5))]
V += [(f"trail +1R/1R, hold {h} h", {"tr": (1, 1), "hold": h}) for h in (12, 24)]
V += [(f"TP {t}R", {"tp": t}) for t in (1.5, 2, 3, 4)]
V += [(f"TP {t}R + BE +1R", {"tp": t, "be": 1.0}) for t in (2, 3)]
V += [("TP opposite M15 band", {"tp": "band"}), ("TP band + BE +1R", {"tp": "band", "be": 1.0})]
V += [(f"SL swing + {b} ATR", {"sl": "swb", "slk": b}) for b in (0.25, 0.5)]
V += [(f"SL {k} ATR", {"sl": "atr", "slk": k}) for k in (1.0, 1.5, 2.0, 3.0)]
V += [(f"SL 2 ATR + BE +1R", {"sl": "atr", "slk": 2.0, "be": 1.0})]


def sim(cx, sw, mt, mask, p, rand, rg):
    O, H, L, S, T, ts, day, wd, n, usd = (cx[k] for k in ("O", "H", "L", "S", "T", "ts", "day", "wd", "n", "usd"))
    ks, dr, at, swl, swh, top, bot, atr = cx["ks"], cx["dr"], cx["at"], cx["swl"], cx["swh"], cx["top"], cx["bot"], cx["atr15"]
    res = []; busy = -1
    for idx in np.where(mask)[0]:
        k, cd = ks[idx], dr[idx]; i = at[k]
        if i >= n or i <= busy: continue
        e0 = O[i] + (S[i] if cd == 1 else 0); a = atr[k]
        if p["sl"] == "atr": sl0 = e0 - cd * p["slk"] * a
        else:
            b = p["slk"] * a if p["sl"] == "swb" else 0.0
            sl0 = swl[idx] - S[i] - b if cd == 1 else swh[idx] + S[i] + b
        risk = (e0 - sl0) * cd
        if risk <= S[i]: continue
        tpd = None
        if p["tp"] == "band": tpd = (top[k] - e0) if cd == 1 else (e0 - bot[k]); tpd = tpd if tpd > 0 else None
        elif p["tp"]: tpd = p["tp"] * risk
        d_ = cd if not rand else (1 if rg.random() < 0.5 else -1)
        e = O[i] + (S[i] if d_ == 1 else 0); sl = e - d_ * risk; tp = e + d_ * tpd if tpd else None
        best = e; x = None; z = i; nights = 0
        while z < n:
            if z > i and day[z] != day[z - 1]: nights += 3 if (sw and 1 <= sw["d3"] <= 5 and wd[z - 1] == sw["d3"] - 1) else 1
            if ts[z] - ts[i] >= p["hold"] * 3600: x = O[z] + (S[z] if d_ == -1 else 0); break
            if d_ == 1:
                if L[z] <= sl: x = min(O[z], sl) if z > i else sl; break
                if tp is not None and z > i and H[z] >= tp: x = max(O[z], tp); break
                best = max(best, H[z])
                if p["be"] and best >= e + p["be"] * risk: sl = max(sl, e)
                if p["tr"] and best >= e + p["tr"][0] * risk: sl = max(sl, best - p["tr"][1] * risk)
            else:
                if H[z] + S[z] >= sl: x = max(O[z] + S[z], sl) if z > i else sl; break
                if tp is not None and z > i and L[z] + S[z] <= tp: x = min(O[z] + S[z], tp); break
                best = min(best, L[z] + S[z])
                if p["be"] and best <= e - p["be"] * risk: sl = min(sl, e)
                if p["tr"] and best <= e - p["tr"][0] * risk: sl = min(sl, best + p["tr"][1] * risk)
            z += 1
        if x is None: break
        swp = (sw["long"] if d_ == 1 else sw["short"]) * mt["point"] * nights * usd if sw and sw["mode"] == 1 else 0.0
        net = (x - e) * d_ * usd + swp; rk = risk * usd
        res.append((T[i], T[min(z, n - 1)], net, net / rk, (net - 0.5 * S[i] * usd) / rk, d_, rk))
        busy = z
    return pd.DataFrame(res, columns=["t", "tx", "net", "r", "rs", "d", "risk"])


def cap(R, mx=None, ccy=None):
    """portfolio caps, by entry time: at most mx open at once; at most ccy positions on one currency the same way"""
    R = R.sort_values("t"); keep = []; opn = []
    for row in R.itertuples():
        opn = [o for o in opn if o[0] > row.t]
        if mx and len(opn) >= mx: keep.append(False); continue
        if ccy:
            b, q = row.sym[:3], row.sym[3:]
            ex = {}
            for _, s, d in opn: ex[s[:3]] = ex.get(s[:3], 0) + d; ex[s[3:]] = ex.get(s[3:], 0) - d
            if abs(ex.get(b, 0) + row.d) > ccy or abs(ex.get(q, 0) - row.d) > ccy: keep.append(False); continue
        keep.append(True); opn.append((row.tx, row.sym, row.d))
    return R[np.array(keep, bool)]


def line(name, x, xr, END):
    mid = END - pd.Timedelta(days=365); oos = END - pd.Timedelta(days=182); a3, a6 = END - pd.Timedelta(days=91), END - pd.Timedelta(days=182)
    P, P1, P2, PS, PR = pf(x.r.values), pf(x.r[x.t < mid].values), pf(x.r[x.t >= mid].values), pf(x.rs.values), pf(xr.r.values) if len(xr) else 0
    PI, PO = pf(x.r[x.t < oos].values), pf(x.r[x.t >= oos].values)
    l12 = x.r[x.t >= mid].sum()
    ok = len(x) >= 150 and P >= 1.15 and P1 >= 1.05 and P2 >= 1.05 and PS >= 1.05 and l12 > 0 and (not len(xr) or P >= PR + 0.10)
    dd = x.groupby(x.tx.dt.normalize()).net.sum(); eq = dd.cumsum(); mdd = (eq - eq.cummax()).min()
    ev = pd.concat([pd.Series(1, index=x.t), pd.Series(-1, index=x.tx)]).sort_index().cumsum()
    g = x[x.sym == "XAUUSD"]
    say(f"{name:44s} {len(x):4d} {100 * (x.r > 0).mean():4.0f} {P:5.2f} {P1:5.2f} {P2:5.2f} {PS:5.2f} | {PI:5.2f} {PO:5.2f} | {l12:+6.1f} {x.r[x.t >= a3].sum():+5.1f} "
        f"{x.r[(x.t >= a6) & (x.t < a3)].sum():+5.1f} | {x.net.sum():+6.0f} {g.net.sum():+5.0f} {x.net.sum() - g.net.sum():+5.0f} {mdd:+6.0f} {dd.min():+5.0f} {int(ev.max()):3d} | "
        f"{PR:5.2f} {'PASS' if ok else ''}")


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt")); SW = R23.load_swaps(); rg = np.random.default_rng(99)
    B97.CTX_ONLY = True
    ALL = {}; END = None
    for sym in SYMS:
        if sym not in meta or not os.path.exists(os.path.join(DATA, sym + ".csv")): continue
        cx = B97.run(sym, meta[sym], SW.get(sym), rg); END = cx["end"] if END is None else max(END, cx["end"])
        ks, dr = cx["ks"], cx["dr"]
        exa = np.where(dr == 1, cx["roll"](cx["exd"], 8)[ks - 1], cx["roll"](cx["exu"], 8)[ks - 1])
        m = (cx["h4pos"] <= -0.5) & (exa == 1) & (cx["spr"] <= 0.20)
        for name, ch in V:
            p = dict(C, **ch)
            for rand in (False, True):
                df = sim(cx, SW.get(sym), meta[sym], m, p, rand, rg)
                if len(df): ALL.setdefault((name, rand), []).append(df.assign(sym=sym))
        say(f"{sym} done [{time.time() - T0:.0f} s]")
    say(f"\nwindow {END - pd.Timedelta(days=730):%Y-%m-%d} .. {END:%Y-%m-%d}; 28 forex + XAUUSD (the live portfolio); entries = live rule.")
    say("IS = first 18 months (choose here), OOS = last 6 months (judge here).  $ per 0.01 lot, all symbols together.")
    hdr = (f"{'exit':44s} {'n':>4} {'win%':>4} {'PF':>5} {'yr1':>5} {'yr2':>5} {'strs':>5} | {'IS':>5} {'OOS':>5} | {'12m R':>6} {'3m R':>5} {'p3m':>5} | "
           f"{'net $':>6} {'gold':>5} {'fx':>5} {'maxDD':>6} {'wDay':>5} {'opn':>3} | {'RAND':>5}")
    say(hdr)
    E = lambda name, rand: pd.concat(ALL[(name, rand)]) if (name, rand) in ALL else pd.DataFrame(columns=["t", "tx", "net", "r", "rs", "d", "risk", "sym"])
    for name, _ in V: line(name, E(name, False), E(name, True), END)
    oos = END - pd.Timedelta(days=182)
    ranked = sorted(((pf(E(nm, False).r[E(nm, False).t < oos].values), nm) for nm, _ in V), reverse=True)
    say("\nranked on IS PF only (top 6) -> their OOS PF:")
    for pi, nm in ranked[:6]:
        x = E(nm, False); say(f"  {nm:44s} IS {pi:5.2f}  OOS {pf(x.r[x.t >= oos].values):5.2f}  (live OOS {pf(E(V[0][0], False).r[E(V[0][0], False).t >= oos].values):.2f})")
    say("\nportfolio caps (approximate: a skipped trade does not free its symbol for a later signal)")
    say(hdr)
    for nm in [V[0][0]] + [n for _, n in ranked[:2] if n != V[0][0]]:
        x, xr = E(nm, False), E(nm, True)
        for cn, kw in (("", {}), (" | max 5 open", {"mx": 5}), (" | max 3 open", {"mx": 3}), (" | max 2 per ccy", {"ccy": 2}),
                       (" | max 1 per ccy", {"ccy": 1}), (" | max 5 + 2 per ccy", {"mx": 5, "ccy": 2})):
            line(nm + cn, cap(x, **kw) if kw else x, cap(xr, **kw) if kw else xr, END)
        say()
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
