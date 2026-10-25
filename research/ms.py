"""Market structure strategy (pullbackforextrading 'Teknik Market Structure', turned into rules).
Buy shown, sell mirrored:
  1. Swings on the trend TF: fractal with L candles on each side (confirmed L candles later)
  2. Uptrend: last two swing highs HH and last two swing lows HL; close above EMA 50 (trend TF)
  3. SNR zones: the last HL (swing low) and the broken previous swing high (resistance -> support),
     each +/- zone_atr x ATR(trend TF)
  4. Entry TF candle touches a zone and confirms: bullish engulfing or bullish pin bar, closing above
     the zone; enter at the next candle open
  5. SL below the zone / candle low - sl_atr x ATR(entry TF); TP at the last swing high (resistance)
     or a fixed RR
  6. Uptrend cancelled when a trend TF candle closes below the last HL (point X)"""
import itertools, numpy as np, pandas as pd
from bt import load, resample, atr, report, metrics, SPLIT
from strategies import run_bars, first_bar


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def trend_states(d, L):
    """per trend-TF bar i (as of its close): dir, last HL / LH, previous swing high/low, last swing high/low"""
    n = len(d); h, l = d.high.values, d.low.values
    out = [None] * n
    sh, sl = [], []          # confirmed swings (index, price)
    for i in range(n):
        k = i - L            # bar k is confirmed as a swing once L bars after it are closed
        if k - L >= 0:
            if all(h[k] > h[k - q] for q in range(1, L + 1)) and all(h[k] >= h[k + q] for q in range(1, L + 1)):
                sh.append((k, h[k]))
            if all(l[k] < l[k - q] for q in range(1, L + 1)) and all(l[k] <= l[k + q] for q in range(1, L + 1)):
                sl.append((k, l[k]))
        if len(sh) >= 2 and len(sl) >= 2:
            up = sh[-1][1] > sh[-2][1] and sl[-1][1] > sl[-2][1]
            dn = sh[-1][1] < sh[-2][1] and sl[-1][1] < sl[-2][1]
            out[i] = dict(up=up, dn=dn, sh1=sh[-2][1], sh2=sh[-1][1], sl1=sl[-2][1], sl2=sl[-1][1])
    return out


def market_structure(m, ttf="4h", etf="1h", L=3, use_ema=True, zone_atr=0.25, sl_atr=0.25, tp_mode="swing",
                     rr=2.0, min_rr=1.0, zones=("hl", "flip"), confirm=("engulf", "pin")):
    d = resample(m, ttf); e = resample(m, etf)
    dE = ema(d.close, 50); dA = atr(d); eA = atr(e)
    st = trend_states(d, L)
    tper = pd.Timedelta(ttf); eper = pd.Timedelta(etf)
    d_end = d.index + tper
    sig = {}; used = set(); j_t = 0
    for j in range(2, len(e) - 1):
        t_close = e.index[j] + eper
        while j_t + 1 < len(d) and d_end[j_t + 1] <= t_close:
            j_t += 1
        if d_end[j_t] > t_close:
            continue
        s = st[j_t]
        if s is None or np.isnan(dA.iloc[j_t]) or np.isnan(eA.iloc[j]):
            continue
        c_t = d.close.iloc[j_t]
        o, h, l, c = e.open.iloc[j], e.high.iloc[j], e.low.iloc[j], e.close.iloc[j]
        po, pc = e.open.iloc[j - 1], e.close.iloc[j - 1]
        body = abs(c - o); rng = h - l
        if rng <= 0:
            continue
        for dr in (1, -1):
            if dr == 1 and not (s["up"] and (not use_ema or c_t > dE.iloc[j_t]) and c_t > s["sl2"]):
                continue
            if dr == -1 and not (s["dn"] and (not use_ema or c_t < dE.iloc[j_t]) and c_t < s["sh2"]):
                continue
            w = zone_atr * dA.iloc[j_t]
            zl = []
            if "hl" in zones:
                lvl = s["sl2"] if dr == 1 else s["sh2"]
                zl.append(("hl", lvl - w, lvl + w))
            if "flip" in zones:
                lvl = s["sh1"] if dr == 1 else s["sl1"]
                zl.append(("flip", lvl - w, lvl + w))
            for name, zlo, zhi in zl:
                if dr == 1:
                    touch = l <= zhi and c > zhi
                    eng = pc < po and c > o and c >= po and o <= pc
                    pin = (min(o, c) - l) >= 2 * body and c >= l + 0.66 * rng
                else:
                    touch = h >= zlo and c < zlo
                    eng = pc > po and c < o and c <= po and o >= pc
                    pin = (h - max(o, c)) >= 2 * body and c <= h - 0.66 * rng
                ok = touch and (("engulf" in confirm and eng) or ("pin" in confirm and pin))
                key = (dr, name, round(zlo, 2))
                if not ok or key in used:
                    continue
                entry_t = first_bar(m, e.index[j + 1])
                if entry_t is None:
                    continue
                ref = min(l, zlo) if dr == 1 else max(h, zhi)
                sl = ref - sl_atr * eA.iloc[j] if dr == 1 else ref + sl_atr * eA.iloc[j]
                risk = (c - sl) * dr
                if risk <= 0:
                    continue
                if tp_mode == "swing":
                    tp = s["sh2"] if dr == 1 else s["sl2"]
                    if (tp - c) * dr < min_rr * risk:
                        continue
                else:
                    tp = c + dr * rr * risk
                used.add(key)
                sig[entry_t] = [dict(type="market", dir=dr, price=None, sl=sl, tp=tp, tag="MS-" + name)]
                break
    return run_bars(m, sig, lambda pos, t, n: None)


if __name__ == "__main__":
    m = load()
    print("== base rules ==")
    base = market_structure(m)
    report("MS H4 trend / H1 entry, TP swing high", base)
    report("MS H4 / H1, TP 2R", market_structure(m, tp_mode="rr", rr=2.0))
    report("MS H4 / M15 entry, TP swing high", market_structure(m, etf="15min"))
    report("MS H4 / M15 entry, TP 2R", market_structure(m, etf="15min", tp_mode="rr"))
    report("MS H1 trend / M15 entry, TP swing", market_structure(m, ttf="1h", etf="15min"))
    report("MS D1 trend / H1 entry, TP swing", market_structure(m, ttf="1D", etf="1h"))
    print("== variants (H4 / H1) ==")
    rows = []
    for L, ue, za, tpm, zs, cf in itertools.product([2, 3, 5], [True, False], [0.15, 0.25, 0.5], ["swing", "rr"],
                                                    [("hl", "flip"), ("hl",), ("flip",)], [("engulf", "pin"), ("engulf",), ("pin",)]):
        tr = market_structure(m, L=L, use_ema=ue, zone_atr=za, tp_mode=tpm, zones=zs, confirm=cf)
        a = metrics(tr); A = metrics(tr[tr.open < SPLIT]) if len(tr) else a; B = metrics(tr[tr.open >= SPLIT]) if len(tr) else a
        rows.append(dict(L=L, ema=ue, zone=za, tp=tpm, zones="+".join(zs), conf="+".join(cf), n=a["n"], pf=a["pf"], net=a["net"], dd=a["dd"], pfA=A["pf"], pfB=B["pf"]))
    v = pd.DataFrame(rows); v.to_csv("ms_grid.csv", index=False)
    v2 = v[v.n >= 20]
    print("variants with >=20 trades:", len(v2), " profitable in both halves:", int(((v2.pfA > 1) & (v2.pfB > 1)).sum()),
          f"({((v2.pfA > 1) & (v2.pfB > 1)).mean() * 100:.0f}%)  median PF {v2.pf.median():.2f}")
    pd.set_option("display.width", 220)
    print(v2.assign(minpf=v2[["pfA", "pfB"]].min(axis=1)).sort_values("minpf", ascending=False).head(12).to_string(index=False))
    for col in ["L", "ema", "zone", "tp", "zones", "conf"]:
        print(col, v2.groupby(col).pf.median().round(2).to_dict())
