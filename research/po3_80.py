"""Round 80 (10 Nov 2026): the owner's POWER OF 3 daily setup on gold (accumulation, manipulation, distribution).

Owner's rules (BUY day; SELL is the mirror):
  1 direction  D1: today's open above EMA 20 of the daily closes AND yesterday's candle closed up -> buy only
  2 levels     today's open, the Asian session low, yesterday's high (target)
  3 trap       price must go below today's open AND below the Asian low; until then, nothing
  4 entry      an M15 candle closes back above the Asian low -> BUY at that close
  5 SL         $2-3 under the trap low
  6 manage     at 1:1 move the SL to entry; target yesterday's high; if not reached, close before 4 am MYT
One trade a day.  The setup is a DAILY trade; intraday bars (M15 built from the broker's M1 export) are needed only to
see the order of events (when the trap happened, which M15 closed back, whether SL or target came first).
Server time Europe/Athens.  Asian session = 01:00-09:00 server (07:00-15:00 MYT, Tokyo + Singapore), variant 02:00-10:00.
Trap / entry allowed from the end of Asia until ENTRY_END.  4 am MYT = 22:00 server in winter (23:00 in summer);
22:00 is used, variant 23:30.  Buys pay the ask (bar spread), exits on the bid; SL checked before target in a bar.
$ per 0.01 lot.  Controls: the same entries with the direction flipped; the same days entering at a random M15 close in
the same window with the same SL distance and target (no trap); a fake Asian level shifted by +/- 1 x the Asian range.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scalp_all as SA
import daytrade as DT

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
T0 = time.time()
say = lambda s="": print(s, flush=True)


def main():
    meta = SA.load_meta(os.path.join(DATA, "meta.txt"))
    mt = meta["XAUUSD"]; usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    M = DT.bars(d, "1min"); del d
    end = M.index[-1]
    say(f"XAUUSD M1 {M.index[0]:%Y-%m-%d} .. {end:%Y-%m-%d}, {len(M):,} bars")
    # ---- daily bars (server day) and the D1 filter, known at the day's open
    g = M.groupby(M.index.normalize())
    D = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last()})
    D = D[M.groupby(M.index.normalize()).size() > 300]                          # drop stub days
    D["ema"] = D.c.ewm(span=20, adjust=False).mean().shift(1)
    D["pc"], D["po"], D["ph"], D["pl"] = D.c.shift(1), D.o.shift(1), D.h.shift(1), D.l.shift(1)
    D["up"] = (D.o > D.ema) & (D.pc > D.po)
    D["dn"] = (D.o < D.ema) & (D.pc < D.po)
    days = {k: v for k, v in M.groupby(M.index.normalize())}
    rg = np.random.default_rng(80)

    def day_trade(day, dr, x, asia=(60, 540), ent_end=1260, sl_add=2.5, be=True, close_hm=1320, need_open=True,
                  mode="real", shift=0.0):
        """returns (net $, risk $, outcome) or None.  dr +1 buy / -1 sell."""
        hm = x.hm.values
        O, H, L, C, S = (x[c].values.astype(float) for c in ("o", "h", "l", "c", "s"))
        a = (hm >= asia[0]) & (hm < asia[1])
        if a.sum() < 60: return None
        op = D.at[day, "o"]
        alo, ahi = L[a].min(), H[a].max()
        rng_a = ahi - alo
        lvl = (alo if dr == 1 else ahi) + shift * rng_a
        tgt = D.at[day, "ph"] if dr == 1 else D.at[day, "pl"]
        after = np.where((hm >= asia[1]) & (hm < ent_end))[0]
        if len(after) == 0: return None
        # M15 closes after Asia: indices of the last M1 bar of each 15-minute block
        q15 = (hm // 15)
        ends = [i for i in after if i + 1 >= len(hm) or q15[i + 1] != q15[i]]
        trapped = False; ext = None; k_e = None
        if mode == "rand":
            if not ends: return None
            k_e = int(rg.choice(ends))
            ext = L[after[0]:k_e + 1].min() if dr == 1 else H[after[0]:k_e + 1].max()
        else:
            j0 = after[0]
            for i in after:
                if dr == 1:
                    if L[i] < lvl and (L[i] < op or not need_open): trapped = True
                    if trapped: ext = L[i] if ext is None else min(ext, L[i])
                else:
                    if H[i] > lvl and (H[i] > op or not need_open): trapped = True
                    if trapped: ext = H[i] if ext is None else max(ext, H[i])
                if trapped and i in ends:
                    if (dr == 1 and C[i] > lvl) or (dr == -1 and C[i] < lvl):
                        k_e = i; break
            if k_e is None: return None
        if k_e + 1 >= len(O): return None
        e = O[k_e + 1] + (S[k_e + 1] if dr == 1 else 0)                                   # buys at the ask
        sl = ext - sl_add if dr == 1 else ext + sl_add + S[k_e + 1]
        risk = (e - sl) * dr
        if risk <= 0: return None
        if mode == "flip":
            dr = -dr; e = O[k_e + 1] + (S[k_e + 1] if dr == 1 else 0); sl = e - dr * risk
            tgt = e + dr * (abs(tgt - e) if np.isfinite(tgt) else risk)
        if (tgt - e) * dr <= 0: return None                                            # target already passed
        moved = False; out = None
        for i in range(k_e + 1, len(O)):
            if hm[i] >= close_hm or i == len(O) - 1:
                px = O[i] + (S[i] if dr == -1 else 0); out = "time"; break
            bl, bh = L[i], H[i]
            if dr == 1:
                if bl <= sl: px = min(O[i], sl) if i > k_e + 1 else sl; out = "BE" if moved else "SL"; break
                if bh >= tgt: px = max(O[i], tgt) if i > k_e + 1 else tgt; out = "TP"; break
                if be and not moved and bh >= e + risk: sl = e; moved = True
            else:
                if bh + S[i] >= sl: px = max(O[i] + S[i], sl) if i > k_e + 1 else sl; out = "BE" if moved else "SL"; break
                if bl + S[i] <= tgt: px = min(O[i] + S[i], tgt) if i > k_e + 1 else tgt; out = "TP"; break
                if be and not moved and bl + S[i] <= e - risk: sl = e; moved = True
        return ((px - e) * dr * usd, risk * usd, abs(tgt - e) / risk, out)

    def run(name, both=True, trend=True, **kw):
        rows = []
        for day in D.index[25:]:
            if day not in days: continue
            x = days[day]
            if day.dayofweek >= 5: continue
            drs = []
            if trend:
                if D.at[day, "up"]: drs = [1]
                elif D.at[day, "dn"] and both: drs = [-1]
            else:
                drs = [1, -1] if both else [1]
            for dr in drs:
                r = day_trade(day, dr, x, **kw)
                if r: rows.append((day, dr) + r); break                            # one trade a day
        R = pd.DataFrame(rows, columns=["t", "dr", "net", "risk", "rr", "out"])
        return R

    pf = lambda v: v[v > 0].sum() / max(-v[v < 0].sum(), 1e-9) if len(v) else 0
    mid = D.index[len(D) // 2]
    ndays = len(D.index[25:])

    def show(name, R):
        if len(R) == 0: say(f"\n--- {name} ---\nno trades"); return
        w = lambda a, b=None: R[(R.t >= a) & (R.t < (b if b is not None else end + pd.Timedelta(days=1)))].net
        eq = R.net.cumsum(); dd = (eq - eq.cummax()).min()
        say(f"\n--- {name} ---")
        oc = R.out.value_counts()
        say(f"{len(R)} trades ({len(R) / ndays * 5:.1f} a week; buys {int((R.dr == 1).sum())}, sells {int((R.dr == -1).sum())}), win {100 * (R.net > 0).mean():.0f}%, "
            f"PF {pf(R.net):.2f}, halves {pf(R.net[R.t < mid]):.2f} / {pf(R.net[R.t >= mid]):.2f}, net ${R.net.sum():+,.0f}, "
            f"avg risk ${R.risk.mean():.2f}, median planned reward {R.rr.median():.1f}R, max DD ${dd:+.0f}, worst trade ${R.net.min():+.0f}")
        say(f"   exits: " + ", ".join(f"{k} {v}" for k, v in oc.items()))
        lm, mb = w(end - pd.Timedelta(days=30)), w(end - pd.Timedelta(days=60), end - pd.Timedelta(days=30))
        m3, p3, y1 = w(end - pd.Timedelta(days=91)), w(end - pd.Timedelta(days=182), end - pd.Timedelta(days=91)), w(end - pd.Timedelta(days=365))
        say(f"   last month {len(lm)} trades ${lm.sum():+.0f} | month before {len(mb)} ${mb.sum():+.0f} | last 3 months {len(m3)} ${m3.sum():+.0f} "
            f"(PF {pf(m3):.2f}) | 3 before ${p3.sum():+.0f} | last 12 months {len(y1)} ${y1.sum():+.0f} (PF {pf(y1):.2f})")
        say("   by year: " + " ".join(f"{y}:{pf(v.net):.2f}({v.net.sum():+.0f})" for y, v in R.groupby(R.t.dt.year)))

    show("OWNER'S RULE: D1 trend + yesterday's candle, trap under open AND Asian low, M15 close back, SL $2.5, BE at 1:1, target yesterday's high, out 22:00 server", run("base"))
    show("same, BUY days only", run("buy", both=False))
    for sa in (2.0, 3.0):
        show(f"SL ${sa:.0f} under the trap", run("sl", sl_add=sa))
    show("no breakeven", run("nobe", be=False))
    show("Asian session 02:00-10:00 server", run("asia2", asia=(120, 600)))
    show("entries only until 16:00 server (London morning)", run("lon", ent_end=960))
    show("out at 23:30 server instead of 22:00", run("late", close_hm=1410))
    show("trap only needs the Asian level (not also today's open)", run("noopen", need_open=False))
    show("NO D1 FILTER (trade whichever side traps first)", run("notrend", trend=False))
    say("\n===== CONTROLS =====")
    show("CONTROL: same entries, direction FLIPPED", run("flip", mode="flip"))
    show("CONTROL: same trend days, entry at a RANDOM M15 close after Asia (no trap), SL under the low so far", run("rand", mode="rand"))
    for sh in (-1.0, 1.0):
        show(f"CONTROL: FAKE Asian level shifted {sh:+.0f} x the Asian range", run("fake", shift=sh))
    say(f"\ndone in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
