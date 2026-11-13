"""Round 107b (13 Nov 2026): robustness of the two round-107 ATR survivors on gold, last 2 years (data run 43406389671).
  B  open-band breakout: OCO stop at today's 01:30 open +- k x ATR(D1), first touch only, SL back toward the open, out 23:30
     grid: k 0.15-0.8; SL as a share of the band 0.25 / 0.5 / 0.75 / 1.0; TP none / 1R / 2R; ATR period 5 / 10 / 14 / 20;
     anchor 01:30 / 03:00 / London 08:00 / 12:00 server; yesterday's range instead of ATR (Williams); buys / sells
  X  range exhaustion fade: today's range reaches X x ATR(D1) at a new extreme -> fade; X 0.8-1.2, SL / TP grids, the hour
     it fires, buys / sells
Every row: worst day, months positive and quarters positive.  $ per 0.01 lot."""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import btc103 as M
import scalp_all as SA
import wti104 as W
import gold106 as G

DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
M.DATA = DATA; W.DATA = DATA; G.DATA = DATA
say = M.say; pf = M.pf
T0 = time.time()


def main():
    mt, sw = W.read_meta("XAUUSD")
    usd = mt["tick_value"] / mt["tick_size"] * 0.01
    d = SA.load(os.path.join(DATA, "XAUUSD.csv"), mt["point"])
    end = d.index[-1]; start = end - pd.Timedelta(days=730); mid = end - pd.Timedelta(days=365)
    Bw = d[d.index >= start - pd.Timedelta(days=60)][["o", "h", "l", "c", "s"]].copy()
    bk = M.Book(Bw, usd, 0.0, 0.0, start, mid, end)
    O, H, L, C, S = bk.O, bk.H, bk.L, bk.C, bk.S
    T = Bw.index; tv = T.values.astype("datetime64[ns]"); n = len(Bw)
    day = T.normalize()
    D = pd.DataFrame({"h": H, "l": L, "c": C, "d": day}).groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    c1 = D.c.shift()
    tr = np.maximum(D.h - D.l, np.maximum((D.h - c1).abs(), (D.l - c1).abs()))
    days = D.index[D.index >= start.normalize()]
    s1 = np.searchsorted(tv, (days + pd.Timedelta(minutes=1410)).values)
    ATR = {p: tr.rolling(p).mean().shift(1).reindex(days).values for p in (5, 10, 14, 20)}
    YR = (D.h - D.l).shift(1).reindex(days).values
    ldn8 = W.ldn_to_server(days, 8, 0)
    res = []

    def go(name, sg):
        sg = sg[(sg.sl > 0) & np.isfinite(sg.sl) & (sg.i < n - 1)]
        r = bk.run(sg)
        x = M.line(name, r, mid, end)
        if not x: return
        p = pd.Series(r["pnl"], index=r["t"])
        x["wday"] = float(p.groupby(p.index.normalize()).sum().min())
        mo = p.groupby(p.index.to_period("M")).sum(); q = p.groupby(p.index.to_period("Q")).sum()
        x["mpos"] = f"{int((mo > 0).sum())}/{len(mo)}"; x["qpos"] = f"{int((q > 0).sum())}/{len(q)}"
        res.append(x); M.show(x)
        say(f"{'':52s} worst day {x['wday']:+.0f}, months + {x['mpos']}, quarters + {x['qpos']}")

    def band(k, A, anchor_min=90, slf=1.0, tp=None, side=None, anchors=None):
        rows = []
        st_ = anchors if anchors is not None else (days + pd.Timedelta(minutes=anchor_min))
        s0 = np.searchsorted(tv, pd.DatetimeIndex(st_).values.astype("datetime64[ns]"))
        for a, b, AA in zip(s0, s1, A):
            if not np.isfinite(AA) or b - a < 30 or a >= n: continue
            o = O[a]; up, dn = o + k * AA, o - k * AA
            j, dr, fp = G.scan_oco(O, H, L, S, a, b, up, dn)
            if j >= 0: rows.append((j, dr, fp, k * AA, b))
        if not rows: return None
        f = np.array(rows); ii = f[:, 0].astype(np.int64); dr = f[:, 1].astype(int); fp = f[:, 2]; bw = f[:, 3]; bb = f[:, 4].astype(np.int64)
        sl = slf * bw
        sg = pd.DataFrame({"i": ii, "d": dr, "ep": fp, "sl": sl, "tp": sl * tp if tp else np.nan, "x": bb})
        if side: sg = sg[sg.d == side]
        return sg

    say("== B: open-band breakout (centre k 0.4, ATR 14, anchor 01:30, SL = the band (back to the open), out 23:30)"); say(M.HDR)
    for k in (0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8):
        go(f"B k {k} SL band out 23:30", band(k, ATR[14]))
    say("-- SL as a share of the band, TP"); say(M.HDR)
    for k in (0.25, 0.4):
        for slf in (0.25, 0.5, 0.75):
            go(f"B k {k} SL {slf} band out 23:30", band(k, ATR[14], slf=slf))
        for tp in (1.0, 2.0, 3.0):
            go(f"B k {k} SL band TP {tp}R", band(k, ATR[14], tp=tp))
    say("-- ATR period / Williams (yesterday's range)"); say(M.HDR)
    for p in (5, 10, 20):
        go(f"B k 0.4 ATR {p}", band(0.4, ATR[p]))
    for k in (0.3, 0.5, 0.7):
        go(f"B k {k} x YESTERDAY's range (Williams)", band(k, YR))
    say("-- anchor time"); say(M.HDR)
    for am, nm in ((180, "03:00"), (720, "12:00")):
        go(f"B k 0.4 anchor {nm} server", band(0.4, ATR[14], anchor_min=am))
    go("B k 0.4 anchor London 08:00", band(0.4, ATR[14], anchors=ldn8.fillna(days[0])))
    say("-- side"); say(M.HDR)
    go("B k 0.4 BUYS only", band(0.4, ATR[14], side=1))
    go("B k 0.4 SELLS only", band(0.4, ATR[14], side=-1))
    go("B k 0.25 BUYS only", band(0.25, ATR[14], side=1))
    go("B k 0.25 SELLS only", band(0.25, ATR[14], side=-1))

    say("\n== X: range exhaustion fade (today's range from 01:30 reaches X x ATR14(D1) at a new extreme)"); say(M.HDR)
    s0 = np.searchsorted(tv, (days + pd.Timedelta(minutes=90)).values)
    A = ATR[14]

    def exh(X, slm, tpm, hold, side=None, hr=None):
        rows = []
        for a, b, AA in zip(s0, s1, A):
            if not np.isfinite(AA) or b - a < 30: continue
            hh = np.maximum.accumulate(H[a:b]); ll = np.minimum.accumulate(L[a:b])
            kk = np.where(hh - ll >= X * AA)[0]
            if not len(kk): continue
            kk = kk[0]; j = a + kk
            rows.append((j, 1 if H[j] >= hh[kk] else -1, AA, b))
        f = np.array(rows); j = f[:, 0].astype(np.int64); dr = -f[:, 1].astype(int); AA = f[:, 2]; bb = f[:, 3].astype(np.int64)
        ii = j + 1
        sg = pd.DataFrame({"i": ii, "d": dr, "ep": np.nan, "sl": slm * AA, "tp": tpm * AA if tpm else np.nan, "x": np.minimum(ii + hold, bb)})
        if side: sg = sg[sg.d == side]
        if hr is not None:
            h_ = T[sg.i.values].hour
            sg = sg[(h_ >= hr[0]) & (h_ < hr[1])]
        return sg

    for X in (0.8, 0.9, 1.0, 1.1, 1.2):
        for slm, tpm in ((0.2, 0.2), (0.3, 0.3), (0.2, 0.3), (0.3, None)):
            go(f"X {X} ATR fade SL {slm} TP {tpm} 120m", exh(X, slm, tpm, 120))
    say("-- hold / side / when it fires (X 1.0, SL 0.3, TP 0.3)"); say(M.HDR)
    for hold in (60, 240):
        go(f"X 1.0 SL 0.3 TP 0.3 {hold}m", exh(1.0, 0.3, 0.3, hold))
    go("X 1.0 SL 0.3 TP 0.3 BUYS (fading a down day)", exh(1.0, 0.3, 0.3, 120, side=1))
    go("X 1.0 SL 0.3 TP 0.3 SELLS (fading an up day)", exh(1.0, 0.3, 0.3, 120, side=-1))
    for hr in ((1, 15), (15, 18), (18, 24)):
        go(f"X 1.0 SL 0.3 TP 0.3 fires {hr[0]:02d}-{hr[1]:02d} server", exh(1.0, 0.3, 0.3, 120, hr=hr))

    R = pd.DataFrame(res)
    say(f"\n{len(R)} rows, PASS {int(R.ok.sum())}")
    say(f"done in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
