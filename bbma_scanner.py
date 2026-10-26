"""
FIZY BOT - BBMA scanner (cloud version of FizyIsm2026.mq5 v6.01, alert only).

Runs every 15 minutes (GitHub Actions). Downloads M15 candles (Twelve Data or OANDA) for every
symbol in SYMBOLS (forex pairs and XAUUSD), builds the
M30 / H1 / H4 candles on broker time (JustMarkets server time = New York time + 7 hours), runs the
same BBMA rules as the EA and sends a chart of the setup to Telegram.

BBMA rules (buy shown, sell mirrored), checked in this order:
  1. EMA 50 rejection on H1 (wick, or up to 6 candles chopping through EMA 50, then a candle closes
     back on the trend side) and on M30, same concept
  2. Then H4: a momentum candle (close outside the BB in the trade direction) within the last 8
     closed H4 candles; H4 EMA 50 below Mid BB for a buy, above for a sell
  3. CSAK: ONE candle breaks Mid BB + EMA 50 together, not one that already closes outside the BB.
     H1 rejection -> CSAK on M30 or M15 (M30 first); M30 rejection -> CSAK on M15
  4. Trend: EMA 50 above EMA 90 for a buy (below for a sell) on H1 and H4
  5. SL 10 pips beyond the Low BB (buy) / Top BB (sell) of the CSAK TF; TP fibo 261.8% from the
     CSAK TF swing to the CSAK candle body; breakeven when price passes the H4 MA5/10 High / Low

Usage:
  python bbma_scanner.py                 live run (what GitHub Actions calls)
  python bbma_scanner.py --csv FILE      replay an MT5 M15 export (broker time), print the signals
  python bbma_scanner.py --csv FILE --chart OUT.png   also draw the chart of the last signal
  python bbma_scanner.py --test          send a test message to Telegram
"""
import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

#==================================================================
# Settings (environment variables override these values)
#==================================================================
CFG = {
    # accounts
    # Data sources tried in this order for every symbol until one works:
    #   deriv      = Deriv public market data (free, no account): forex + spot gold (frxXAUUSD)
    #   yahoo      = Yahoo Finance (free, no account): all forex pairs, gold = COMEX futures GC=F
    #   twelvedata = needs TWELVEDATA_KEY (free: 800 requests a day)
    #   oanda      = needs OANDA_TOKEN (free demo account)
    "PROVIDER":       "deriv,yahoo,twelvedata",
    "DERIV_APP_ID":   "1089",        # public demo app id; register your own at Deriv if it stops working
    "TWELVEDATA_KEY": "PUT_YOUR_TWELVEDATA_API_KEY_HERE",
    "OANDA_TOKEN":    "",            # OANDA fxTrade Practice API token (demo account)
    "OANDA_LIVE":     False,         # True only for a live OANDA account token
    "TG_TOKEN":       "",
    "TG_CHAT_ID":     "",
    # market
    # comma separated list, or ALL = the 28 major / cross pairs + XAUUSD
    "SYMBOLS":        "ALL",
    "SPREAD_PIPS_FX": 1.0,           # assumed spread for the sell SL / buy entry (forex, pips)
    "SPREAD_PIPS_XAU": 2.0,          # assumed spread for gold (pips, 1 pip = 0.10)
    "BROKER_OFFSET":  7,             # broker server time = New York time + N hours (GMT+2 / GMT+3)
    # BBMA model
    "TREND_TF1":      "1h",
    "TREND_TF2":      "4h",
    "TREND_BOTH":     True,          # trend TF 2 must agree with trend TF 1
    "REJ_TF1":        "1h",          # CSAK on ENTRY_TF2 or ENTRY_TF
    "REJ_TF2":        "30min",       # CSAK on ENTRY_TF
    "REJ_LOOKBACK":   12,
    "REJ_MAX_BARS":   6,
    "MOM_TF":         "4h",
    "MOM_LOOKBACK":   8,             # last N closed momentum TF candles to look for momentum
    "TRADES_PER_MOM": 1,             # alerts per momentum candle (0 = unlimited)
    "REQUIRE_RETRACE": False,        # also require a retrace to MA5/10 on the momentum TF
    "MOM_EMA_VS_MID": True,          # momentum TF: EMA 50 below Mid BB for buy, above for sell
    "ENTRY_TF2":      "30min",
    "ENTRY_TF":       "15min",
    "SKIP_MOM_CSAK":  True,          # skip a CSAK candle that already closes outside the BB
    "SLOPE_FILTER":   True,          # BB must slope with the trade (Mid + Top BB up for buy, Mid + Low BB down for sell)
    "SLOPE_TF":       "4h",
    "SLOPE_BARS":     3,
    "SWING_LEN":      2,
    "SL_MODE":        "rejection",   # "rejection" (pips beyond the EMA 50 rejection low/high) or "band"
    "SL_REJ_PIPS":    3,
    "SL_BAND_PIPS":   10,
    "TP_MODE":        "last_high",   # "last_high" (CSAK TF high/low since the momentum candle) or "fibo"
    "TP_BUFFER_PIPS": 0,
    "FIBO_LEVEL":     2.618,
    "BE_TF":          "4h",
    "BE_FIBO":        1.618,         # fallback BE level shown in the alert
    # run
    "BARS":           300,           # bars per timeframe for the indicators (same as the EA)
    "CATCHUP_BARS":   4,             # re-check up to N missed M15 candles when a run was late
    "HEARTBEAT_HOUR": 8,             # daily "still alive" message at this Malaysia hour (-1 = off)
    "STATE_FILE":     "state/state.json",
}
for k in list(CFG):
    v = os.environ.get(k)
    if v not in (None, ""):
        CFG[k] = type(CFG[k])(v) if not isinstance(CFG[k], bool) else v.lower() in ("1", "true", "yes")

ALL_PAIRS = ("XAUUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,"
             "EURCAD,EURNZD,GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,"
             "NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY")

# symbol being scanned (set by set_symbol)
CUR = {"name": "XAUUSD", "pip": 0.10, "digits": 2, "spread": 0.20}


def set_symbol(name):
    name = name.strip().upper()
    gold = name.startswith("XAU")
    jpy = name.endswith("JPY")
    pip = 0.10 if gold else (0.01 if jpy else 0.0001)
    CUR.update(name=name, pip=pip, digits=2 if gold else (3 if jpy else 5),
               spread=(CFG["SPREAD_PIPS_XAU"] if gold else CFG["SPREAD_PIPS_FX"]) * pip)


def symbol_list():
    raw = ALL_PAIRS if CFG["SYMBOLS"].strip().upper() == "ALL" else CFG["SYMBOLS"]
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


TF_MIN = {"15min": 15, "30min": 30, "1h": 60, "4h": 240}
TF_NAME = {"15min": "M15", "30min": "M30", "1h": "H1", "4h": "H4"}
MYT = ZoneInfo("Asia/Kuala_Lumpur")
NY = ZoneInfo("America/New_York")


#==================================================================
# Indicators (same maths as the EA's LoadBB; arrays series-indexed: [0] forming, [1] last closed)
#==================================================================
def lwma_at(x, i, p, n):
    if i + p > n:
        return 0.0
    w = np.arange(p, 0, -1, dtype=float)          # newest bar has the largest weight
    return float((x[i:i + p] * w).sum() / w.sum())


class BB:
    def __init__(self, df, tf):
        d = df.iloc[::-1]                         # newest first
        self.tf = tf
        self.n = n = len(d)
        self.t = list(d.index)
        self.o = d["open"].values.astype(float)
        self.h = d["high"].values.astype(float)
        self.l = d["low"].values.astype(float)
        self.c = d["close"].values.astype(float)
        self.top = np.zeros(n); self.mid = np.zeros(n); self.bot = np.zeros(n)
        self.ema = np.zeros(n); self.ema90 = np.zeros(n)
        # vectorised on the oldest-first series, then flipped back to series order
        ca = self.c[::-1]
        if n >= 20:
            win = np.lib.stride_tricks.sliding_window_view(ca, 20)
            m = win.mean(axis=1); sd = np.sqrt(((win - m[:, None]) ** 2).mean(axis=1))   # population std
            mid = np.zeros(n); mid[19:] = m
            top = np.zeros(n); top[19:] = m + 2 * sd
            bot = np.zeros(n); bot[19:] = m - 2 * sd
            self.mid, self.top, self.bot = mid[::-1].copy(), top[::-1].copy(), bot[::-1].copy()

        def lwma(xa, p):
            out = np.zeros(n)
            if n >= p:
                w = np.arange(p, 0, -1, dtype=float)       # newest bar has the largest weight
                out[p - 1:] = np.convolve(xa, w, "valid") / w.sum()
            return out[::-1].copy()
        ha, la = self.h[::-1], self.l[::-1]
        self.ma5h, self.ma10h = lwma(ha, 5), lwma(ha, 10)
        self.ma5l, self.ma10l = lwma(la, 5), lwma(la, 10)
        for arr, p in ((self.ema, 50), (self.ema90, 90)):
            if n >= p + 10:
                seed = n - p
                arr[seed] = self.c[seed:n].mean()
                a = 2.0 / (p + 1)
                for i in range(seed - 1, -1, -1):
                    arr[i] = arr[i + 1] + a * (self.c[i] - arr[i + 1])

    def valid(self, i):
        return 0 <= i and i + 1 < self.n and self.mid[i + 1] > 0 and self.ma10l[i + 1] > 0

    def lowest(self, a, b):
        return float(self.l[a:min(b, self.n - 1) + 1].min())

    def highest(self, a, b):
        return float(self.h[a:min(b, self.n - 1) + 1].max())


def bbma_trend(d):
    if not d.valid(1) or d.ema[1] <= 0 or d.ema90[1] <= 0:
        return 0
    return 1 if d.ema[1] > d.ema90[1] else (-1 if d.ema[1] < d.ema90[1] else 0)


def touched_ema(d, i, dr):
    if not d.valid(i) or d.ema[i] <= 0:
        return False
    return d.l[i] <= d.ema[i] if dr == 1 else d.h[i] >= d.ema[i]


def find_ema_rejection(d, dr, lookback, max_bars):
    """Same as the EA's FindEMARejection (since = 0). Returns (index, extreme, kind) or (-1, 0, '')."""
    for i in range(1, lookback + 1):
        if not d.valid(i):
            break
        if d.ema[i] <= 0:
            break
        back_in = d.c[i] > d.ema[i] if dr == 1 else d.c[i] < d.ema[i]
        if not back_in:
            continue
        self_touch = touched_ema(d, i, dr)
        prev_below = d.valid(i + 1) and d.ema[i + 1] > 0 and \
            (d.c[i + 1] < d.ema[i + 1] if dr == 1 else d.c[i + 1] > d.ema[i + 1])
        if not self_touch and not prev_below:
            continue
        first = i if self_touch else i + 1
        last = first; m = 0
        while touched_ema(d, last, dr) and m <= max_bars:
            m += 1; last += 1
        last -= 1
        if m == 0 or m > max_bars:
            continue
        held = all((d.c[k] > d.ema[k]) if dr == 1 else (d.c[k] < d.ema[k]) for k in range(1, i))
        if not held:
            continue
        frm = min(i, first)
        ext = d.lowest(frm, last) if dr == 1 else d.highest(frm, last)
        total = last - frm + 1
        kind = "wick rejection" if total == 1 else f"{total}-candle rejection"
        return i, ext, kind
    return -1, 0.0, ""


def find_momentum_before(dm, dr, rej_t, lookback):
    """H4 momentum within the last `lookback` closed H4 candles (counted back from now, checked after
    the rejection is found). Momentum the other way after it cancels the idea."""
    j = -1
    for i in range(1, 1 + lookback):
        if not dm.valid(i):
            break
        if (dm.c[i] > dm.top[i]) if dr == 1 else (dm.c[i] < dm.bot[i]):
            j = i; break
    if j < 0:
        return -1, f"no {TF_NAME[dm.tf]} momentum in the last {lookback} candles"
    for i in range(1, j):
        if (dm.c[i] < dm.bot[i]) if dr == 1 else (dm.c[i] > dm.top[i]):
            return -1, f"{TF_NAME[dm.tf]} momentum against the trend since then"
    return j, ""


def bb_slope(d, bars):
    a, b = 1, 1 + bars
    if not d.valid(b):
        return 0
    if d.mid[a] > d.mid[b] and d.top[a] > d.top[b]:
        return 1
    if d.mid[a] < d.mid[b] and d.bot[a] < d.bot[b]:
        return -1
    return 0


def is_csak(d, dr):
    if not d.valid(1) or d.ema[1] <= 0:
        return False
    lo, hi = min(d.mid[1], d.ema[1]), max(d.mid[1], d.ema[1])
    brk = (d.o[1] < lo and d.c[1] > hi) if dr == 1 else (d.o[1] > hi and d.c[1] < lo)
    if brk and CFG["SKIP_MOM_CSAK"] and ((dr == 1 and d.c[1] > d.top[1]) or (dr == -1 and d.c[1] < d.bot[1])):
        return False
    return brk


def fresh_close(d, de):
    return d.n >= 2 and de.n >= 2 and d.t[1] + timedelta(minutes=TF_MIN[d.tf]) > de.t[1]


def last_swing(d, dr, price, ln, max_bars):
    for i in range(ln + 1, max_bars + 1):
        if i + ln >= d.n:
            break
        sw = True
        for k in range(1, ln + 1):
            sw = (d.l[i] < d.l[i - k] and d.l[i] <= d.l[i + k]) if dr == 1 else \
                 (d.h[i] > d.h[i - k] and d.h[i] >= d.h[i + k])
            if not sw:
                break
        if not sw:
            continue
        if dr == 1 and d.l[i] < price:
            return float(d.l[i])
        if dr == -1 and d.h[i] > price:
            return float(d.h[i])
    return 0.0


#==================================================================
# Candles as of a given moment (the open of M15 candle T, like the EA's first tick)
#==================================================================
def series_as_of(m15, T, tf, bars):
    """Candles of tf as the EA sees them at the first tick of the M15 candle that opens at T:
    closed candles + the forming one (built from the M15 candles since it opened + the open of T)."""
    sub = m15[m15.index < T]
    if tf == "15min":
        agg = sub
    else:
        agg = sub.resample(tf, label="left", closed="left", origin="start_day").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    op = float(m15.loc[T, "open"])
    bin_open = T.floor(tf) if tf != "15min" else T
    agg = agg.copy()
    if len(agg) and agg.index[-1] == bin_open:
        agg.iloc[-1, agg.columns.get_loc("high")] = max(agg.iloc[-1]["high"], op)
        agg.iloc[-1, agg.columns.get_loc("low")] = min(agg.iloc[-1]["low"], op)
        agg.iloc[-1, agg.columns.get_loc("close")] = op
    else:
        agg.loc[bin_open] = {"open": op, "high": op, "low": op, "close": op}
    return agg.iloc[-bars:]


def ma510_line(d, buy):
    return max(d.ma5h[0], d.ma10h[0]) if buy else min(d.ma5l[0], d.ma10l[0])


#==================================================================
# BBMA evaluation (EvaluateBBMA + BBMAPlace of the EA)
#==================================================================
def evaluate(m15, T, state):
    C = CFG; B = C["BARS"]
    tfs = {C["TREND_TF1"], C["TREND_TF2"], C["MOM_TF"], C["REJ_TF1"], C["REJ_TF2"], C["ENTRY_TF"], C["ENTRY_TF2"], C["BE_TF"], C["SLOPE_TF"]}
    D = {tf: BB(series_as_of(m15, T, tf, B), tf) for tf in tfs}
    if any(D[tf].n < 120 for tf in tfs):
        return None, "not enough history"
    dT1, dT2, dM = D[C["TREND_TF1"]], D[C["TREND_TF2"]], D[C["MOM_TF"]]
    dR1, dR2, dE, dE2 = D[C["REJ_TF1"]], D[C["REJ_TF2"]], D[C["ENTRY_TF"]], D[C["ENTRY_TF2"]]

    t1 = bbma_trend(dT1)
    t2 = bbma_trend(dT2) if C["TREND_BOTH"] else t1
    if t1 == 0:
        return None, f"no clear {TF_NAME[C['TREND_TF1']]} trend (EMA 50 vs EMA 90)"
    if t1 != t2:
        return None, f"{TF_NAME[C['TREND_TF1']]} / {TF_NAME[C['TREND_TF2']]} trend not aligned"
    dr = t1
    if C["SLOPE_FILTER"] and bb_slope(D[C["SLOPE_TF"]], C["SLOPE_BARS"]) != dr:
        return None, f"{TF_NAME[C['SLOPE_TF']]} BB not sloping {'up' if dr == 1 else 'down'}, {'buy' if dr == 1 else 'sell'} skipped"

    r1, ext1, k1 = find_ema_rejection(dR1, dr, C["REJ_LOOKBACK"], C["REJ_MAX_BARS"])
    r2, ext2, k2 = find_ema_rejection(dR2, dr, C["REJ_LOOKBACK"], C["REJ_MAX_BARS"])
    if r1 < 0 and r2 < 0:
        return None, "waiting for EMA 50 rejection on H1 / M30"
    rT1 = dR1.t[r1] if r1 >= 0 else None
    rT2 = dR2.t[r2] if r2 >= 0 else None

    j1, why1 = find_momentum_before(dM, dr, rT1, C["MOM_LOOKBACK"]) if r1 >= 0 else (-1, "")
    j2, why2 = find_momentum_before(dM, dr, rT2, C["MOM_LOOKBACK"]) if r2 >= 0 else (-1, "")
    if j1 < 0 and j2 < 0:
        return None, (f"H1 EMA 50 {k1}, {why1}" if r1 >= 0 else f"M30 EMA 50 {k2}, {why2}")
    if C["MOM_EMA_VS_MID"] and dM.valid(1) and dM.ema[1] > 0 and \
            ((dr == 1 and dM.ema[1] >= dM.mid[1]) or (dr == -1 and dM.ema[1] <= dM.mid[1])):
        return None, f"H4 EMA 50 is {'above' if dr == 1 else 'below'} Mid BB, {'buy' if dr == 1 else 'sell'} skipped"
    if C["REQUIRE_RETRACE"]:
        jr = j1 if j1 >= 0 else j2
        touched = any((dM.l[k] <= max(dM.ma5l[k], dM.ma10l[k])) if dr == 1 else
                      (dM.h[k] >= min(dM.ma5h[k], dM.ma10h[k])) for k in range(jr - 1, -1, -1))
        if not touched:
            return None, "H4 momentum, waiting for retrace to MA5/10"

    okR1 = r1 >= 0 and j1 >= 0
    okR2 = r2 >= 0 and j2 >= 0
    csakE2 = okR1 and fresh_close(dE2, dE) and dE2.t[1] >= rT1 and is_csak(dE2, dr)
    e1R1 = okR1 and dE.t[1] >= rT1
    e1R2 = okR2 and dE.t[1] >= rT2
    csakE1 = (e1R1 or e1R2) and is_csak(dE, dr)
    if not csakE2 and not csakE1:
        return None, ("H1" if okR1 else "M30") + " EMA 50 rejection + H4 momentum, waiting for CSAK"

    useR1 = csakE2 or e1R1
    j = j1 if useR1 else j2
    rejT = rT1 if useR1 else rT2
    rejTF = "H1" if useR1 else "M30"
    rejKind = k1 if useR1 else k2
    rejExt = ext1 if useR1 else ext2
    if str(rejT) == state.get("last_rej"):
        return None, "signal for this rejection already sent"
    momT = str(dM.t[j])
    if C["TRADES_PER_MOM"] > 0 and momT == state.get("last_mom") and state.get("mom_trades", 0) >= C["TRADES_PER_MOM"]:
        return None, "alert already sent for this H4 momentum"

    dC, cTF = (dE2, C["ENTRY_TF2"]) if csakE2 else (dE, C["ENTRY_TF"])
    # --- levels (BBMAPlace)
    op = float(dE.o[0]); sp = CUR["spread"]
    entry = op + sp if dr == 1 else op
    rejRef = min(rejExt, dC.lowest(1, 1)) if dr == 1 else max(rejExt, dC.highest(1, 1))
    swRef = last_swing(dC, dr, entry, C["SWING_LEN"], 60)
    pip = CUR["pip"]
    if C["SL_MODE"] == "band":
        band = dC.bot[1] if dr == 1 else dC.top[1]
        sl = band - C["SL_BAND_PIPS"] * pip if dr == 1 else band + C["SL_BAND_PIPS"] * pip + sp
        sl_name = f"{C['SL_BAND_PIPS']} pips beyond {TF_NAME[cTF]} {'Low' if dr == 1 else 'Top'} BB"
    else:
        sl = rejRef - C["SL_REJ_PIPS"] * pip if dr == 1 else rejRef + C["SL_REJ_PIPS"] * pip + sp
        sl_name = f"{C['SL_REJ_PIPS']} pips beyond the {rejTF} EMA 50 rejection {'low' if dr == 1 else 'high'}"
    risk = entry - sl if dr == 1 else sl - entry
    if risk <= 0:
        return None, "SL on the wrong side"
    base = swRef if swRef > 0 else rejRef
    body_end = max(dC.o[1], dC.c[1]) if dr == 1 else min(dC.o[1], dC.c[1])
    rng = body_end - base if dr == 1 else base - body_end
    be_fibo = base + dr * C["BE_FIBO"] * rng if rng > 0 else 0.0
    if C["TP_MODE"] == "fibo":
        if rng <= 0:
            return None, "cannot draw fibo (swing is not beyond the CSAK body)"
        tp = base + dr * C["FIBO_LEVEL"] * rng
        tp_name = f"Fibo {C['FIBO_LEVEL'] * 100:.1f}%"
    else:
        # the high (buy) / low (sell) the pullback started from: CSAK TF candles since the momentum candle
        mom_t = dM.t[j]
        k = max([i for i in range(1, dC.n) if dC.t[i] >= mom_t] or [60])
        ext = dC.highest(1, k) if dr == 1 else dC.lowest(1, k)
        tp = ext - C["TP_BUFFER_PIPS"] * pip if dr == 1 else ext + C["TP_BUFFER_PIPS"] * pip + sp
        tp_name = f"last {TF_NAME[cTF]} {'high' if dr == 1 else 'low'} since the H4 momentum"
    dist = (tp - entry) * dr
    if dist <= 0:
        return None, "target is behind the entry"
    rr = dist / risk
    be_line = ma510_line(D[C["BE_TF"]], dr == 1)

    sig = dict(dir=dr, time=T, entry=entry, sl=sl, tp=tp, rr=rr, be_line=be_line, be_fibo=be_fibo,
               sl_name=sl_name, tp_name=tp_name,
               rej_tf=rejTF, rej_kind=rejKind, rej_t=rejT, mom_t=dM.t[j], csak_tf=cTF,
               swing=base, csak_t=dC.t[1], data=dC)
    state["last_rej"] = str(rejT)
    if momT == state.get("last_mom"):
        state["mom_trades"] = state.get("mom_trades", 0) + 1
    else:
        state["last_mom"] = momT; state["mom_trades"] = 1
    return sig, "SIGNAL"


#==================================================================
# Chart and Telegram
#==================================================================
def px(v):
    return f"{v:.{CUR['digits']}f}"


def message(sig):
    side = "BUY" if sig["dir"] == 1 else "SELL"
    myt = sig["time"]  # broker time
    fut = CUR["name"].startswith("XAU") and CUR.get("source") == "yahoo"
    note = "\nNote: gold prices are COMEX futures (GC=F); JustMarkets XAUUSD differs by a few dollars" if fut else ""
    return (f"FIZY BOT | {CUR['name']} {side} (alert only)\n"
            f"Entry: {px(sig['entry'])}\nSL: {px(sig['sl'])}  ({sig['sl_name']})\n"
            f"TP: {px(sig['tp'])}  (RR 1:{sig['rr']:.1f}, {sig['tp_name']})\n"
            f"Setup: BBMA EMA 50 rejection + CSAK\n"
            f"Trend: H1 + H4 {'bullish' if sig['dir'] == 1 else 'bearish'} (EMA 50 vs EMA 90)\n"
            f"EMA 50 {sig['rej_kind']}: {sig['rej_tf']} at {sig['rej_t']:%Y-%m-%d %H:%M}\n"
            f"H4 momentum: {sig['mom_t']:%Y-%m-%d %H:%M}\n"
            f"CSAK: {TF_NAME[sig['csak_tf']]} candle broke Mid BB + EMA 50\n"
            f"Breakeven: price passes H4 MA5/10 {'High' if sig['dir'] == 1 else 'Low'} (now {px(sig['be_line'])})\n"
            f"Broker time: {myt:%Y-%m-%d %H:%M}  |  data: {CUR.get('source', '-')}" + note)


def chart_png(sig, bars=110):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = sig["data"]
    n = min(bars, d.n - 100)
    idx = list(range(n - 1, -1, -1))              # oldest -> newest
    x = np.arange(len(idx))
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    bg = "#0f1115"
    fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    for xi, i in zip(x, idx):
        up = d.c[i] >= d.o[i]
        col = "#26a69a" if up else "#ef5350"
        ax.vlines(xi, d.l[i], d.h[i], color=col, linewidth=0.8)
        ax.add_patch(plt.Rectangle((xi - 0.32, min(d.o[i], d.c[i])), 0.64, max(abs(d.c[i] - d.o[i]), 1e-6),
                                   color=col))
    lines = [("Top BB", d.top, "#b0b0b0", 1, "-"), ("Mid BB", d.mid, "#ffffff", 1, ":"),
             ("Low BB", d.bot, "#b0b0b0", 1, "-"), ("MA5 High", d.ma5h, "#ff3b30", 1, "-"),
             ("MA10 High", d.ma10h, "#ff2dd4", 1, "-"), ("MA5 Low", d.ma5l, "#00e5ff", 1, "-"),
             ("MA10 Low", d.ma10l, "#1e90ff", 1, "-"), ("EMA 50", d.ema, "#ffd700", 2, "-"),
             ("EMA 90", d.ema90, "#ff9500", 2, "-")]
    for name, arr, col, w, st in lines:
        y = np.array([arr[i] if arr[i] > 0 else np.nan for i in idx])
        ax.plot(x, y, color=col, linewidth=w, linestyle=st, label=name)
    ax.axhline(sig["entry"], color="#ffffff", linewidth=1.2, linestyle="--")
    ax.text(len(x) + 0.5, sig["entry"], f" Entry {px(sig['entry'])}", color="#ffffff", va="center", fontsize=9)
    # CSAK candle marker
    ax.annotate("CSAK", (x[-2], d.h[1] if sig["dir"] == 1 else d.l[1]), color="#ffd700", fontsize=9, ha="center",
                xytext=(0, 12 if sig["dir"] == 1 else -16), textcoords="offset points")
    lo = np.nanmin([min(d.l[i], d.bot[i] or d.l[i]) for i in idx])
    hi = np.nanmax([max(d.h[i], d.top[i] or d.h[i]) for i in idx])
    pad = (hi - lo) * 0.04
    ax.set_ylim(lo - pad, hi + pad); ax.set_xlim(-1, len(x) + 8)
    step = max(1, len(idx) // 8)
    ax.set_xticks(x[::step]); ax.set_xticklabels([f"{d.t[i]:%d/%m %H:%M}" for i in idx][::step], color="#9aa0a6", fontsize=8)
    ax.tick_params(axis="y", colors="#9aa0a6", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#2a2e36")
    ax.grid(color="#1c1f26", linewidth=0.6)
    side = "BUY" if sig["dir"] == 1 else "SELL"
    ax.set_title(f"FIZY BOT  {CUR['name']} {TF_NAME[sig['csak_tf']]}  BBMA {side}",
                 color="#ffd700", fontsize=12, loc="left")
    leg = ax.legend(loc="upper left", fontsize=7, ncol=5, facecolor=bg, edgecolor="#2a2e36", labelcolor="#c8c8c8")
    buf = io.BytesIO()
    fig.tight_layout(); fig.savefig(buf, format="png", facecolor=bg); plt.close(fig)
    return buf.getvalue()


def tg_send(text, png=None):
    tok, chat = CFG["TG_TOKEN"], CFG["TG_CHAT_ID"]
    base = f"https://api.telegram.org/bot{tok}"
    try:
        if png is not None:
            cap = text if len(text) <= 1000 else text[:1000]
            r = requests.post(base + "/sendPhoto", data={"chat_id": chat, "caption": cap},
                              files={"photo": ("chart.png", png, "image/png")}, timeout=30)
            if r.ok and len(text) <= 1000:
                return True
        r = requests.post(base + "/sendMessage", data={"chat_id": chat, "text": text}, timeout=30)
        return r.ok
    except requests.RequestException as e:
        print("Telegram error:", e)
        return False


#==================================================================
# Data
#==================================================================
def utc_to_broker(ts_utc):
    ny = ts_utc.tz_convert(NY)
    return (ny + pd.Timedelta(hours=CFG["BROKER_OFFSET"])).tz_localize(None)


_last_td_call = [0.0]


def td_key_set():
    k = CFG["TWELVEDATA_KEY"]
    return bool(k) and not k.startswith("PUT_YOUR")


def fetch_yahoo(name):
    """Yahoo Finance chart API (no key). 15-minute candles, last 60 days. Gold = GC=F futures."""
    ysym = "GC=F" if name.startswith("XAU") else name + "=X"
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        for attempt in range(2):
            try:
                r = requests.get(f"https://{host}/v8/finance/chart/{ysym}",
                                 params={"interval": "15m", "range": "60d"}, headers=hdr, timeout=30)
                if r.status_code == 429:
                    err = "Yahoo rate limit (429)"
                    time.sleep(3 + 3 * attempt)
                    continue
                js = r.json()
                res = (js.get("chart") or {}).get("result")
                if not res:
                    err = f"Yahoo {ysym}: {(js.get('chart') or {}).get('error')}"
                    break
                q = res[0]["indicators"]["quote"][0]
                df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
                                  index=pd.to_datetime(res[0]["timestamp"], unit="s", utc=True)).dropna()
                # the newest row can carry the time of the last trade: align to 15 minutes and merge
                df.index = df.index.floor("15min")
                df = df.groupby(level=0).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
                if len(df) < 500:
                    err = f"Yahoo {ysym}: only {len(df)} candles"
                    break
                time.sleep(0.4)   # be gentle with the free endpoint
                return df
            except (requests.RequestException, ValueError, KeyError) as e:
                err = f"Yahoo {ysym}: {e}"
                time.sleep(2)
    raise RuntimeError(err or f"Yahoo {ysym}: no data")


_deriv_ws = [None]
DERIV_URLS = ("wss://api.derivws.com/trading/v1/options/ws/public?app_id={app}",
              "wss://ws.derivws.com/websockets/v3?app_id={app}",
              "wss://ws.binaryws.com/websockets/v3?app_id={app}")


def _deriv_call(req):
    from websocket import create_connection   # package: websocket-client
    last = None
    for attempt in range(2):
        if _deriv_ws[0] is None:
            for u in DERIV_URLS:
                try:
                    _deriv_ws[0] = create_connection(u.format(app=CFG["DERIV_APP_ID"]), timeout=25)
                    break
                except Exception as e:      # try the next host
                    last = e
            if _deriv_ws[0] is None:
                raise RuntimeError(f"Deriv: cannot connect ({last})")
        try:
            _deriv_ws[0].send(json.dumps(req))
            return json.loads(_deriv_ws[0].recv())
        except Exception as e:
            last = e
            try:
                _deriv_ws[0].close()
            except Exception:
                pass
            _deriv_ws[0] = None
    raise RuntimeError(f"Deriv: {last}")


def fetch_deriv(name, need=5000, max_pages=12):
    """Deriv public market data: 15-minute candles, no account needed. Deriv returns about 800
    candles per request, so older candles are fetched page by page (end = oldest candle - 1)."""
    got = {}
    end = "latest"
    for page in range(max_pages):
        req = {"ticks_history": "frx" + name, "style": "candles", "granularity": 900,
               "count": min(5000, need + 100), "end": end, "adjust_start_time": 1}
        if page == 0:
            req["start"] = int(time.time()) - max(80, need // 80) * 86400
        if page:
            time.sleep(0.5)               # stay under Deriv's request rate limit when paging back
        js = _deriv_call(req)
        if js.get("error"):
            if got:
                break
            raise RuntimeError(f"Deriv frx{name}: {js['error'].get('message', js['error'])}")
        rows = js.get("candles") or []
        new = 0
        for r in rows:
            e = int(r["epoch"])
            if e not in got:
                got[e] = r
                new += 1
        if len(got) >= need or not rows or new == 0:
            break
        end = min(int(r["epoch"]) for r in rows) - 1
    if len(got) < 500:
        raise RuntimeError(f"Deriv frx{name}: only {len(got)} candles")
    df = pd.DataFrame([got[e] for e in sorted(got)])
    df.index = pd.to_datetime(df["epoch"].astype(int), unit="s", utc=True)
    return df[["open", "high", "low", "close"]].astype(float).iloc[-need:]


def _fetch_one(prov, name):
    """Candles with a UTC index from one provider."""
    if prov == "deriv":
        return fetch_deriv(name)
    if prov == "yahoo":
        return fetch_yahoo(name)
    if prov == "oanda":
        if not CFG["OANDA_TOKEN"]:
            raise RuntimeError("no OANDA_TOKEN")
        host = "api-fxtrade.oanda.com" if CFG["OANDA_LIVE"] else "api-fxpractice.oanda.com"
        inst = name[:3] + "_" + name[3:]
        r = requests.get(f"https://{host}/v3/instruments/{inst}/candles",
                         headers={"Authorization": f"Bearer {CFG['OANDA_TOKEN']}"},
                         params={"granularity": "M15", "count": 5000, "price": "M"}, timeout=60)
        js = r.json()
        if r.status_code != 200:
            raise RuntimeError(f"OANDA {inst}: {js.get('errorMessage', js)}")
        rows = [(c["time"][:19], float(c["mid"]["o"]), float(c["mid"]["h"]), float(c["mid"]["l"]), float(c["mid"]["c"]))
                for c in js.get("candles", [])]
        df = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close"])
        t = pd.to_datetime(df["datetime"], format="%Y-%m-%dT%H:%M:%S").dt.tz_localize("UTC")
        df.index = t.values
        return df[["open", "high", "low", "close"]].astype(float)
    if prov == "twelvedata":
        if not td_key_set():
            raise RuntimeError("no TWELVEDATA_KEY")
        # free plan: 8 requests per minute
        wait = 7.6 - (time.time() - _last_td_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_td_call[0] = time.time()
        p = dict(symbol=name[:3] + "/" + name[3:], interval="15min", outputsize=5000, timezone="UTC",
                 order="ASC", apikey=CFG["TWELVEDATA_KEY"])
        js = requests.get("https://api.twelvedata.com/time_series", params=p, timeout=60).json()
        if js.get("status") != "ok":
            raise RuntimeError(f"Twelve Data {name}: {js.get('message', js)}")
        df = pd.DataFrame(js["values"])
        t = pd.to_datetime(df["datetime"]).dt.tz_localize("UTC")
        df.index = t.values
        return df[["open", "high", "low", "close"]].astype(float)
    raise RuntimeError(f"unknown provider {prov}")


def _cache_path(name, prov):
    return os.path.join(os.path.dirname(CFG["STATE_FILE"]) or ".", "candles", f"{name}_{prov}.csv")


def _load_cache(name, prov):
    try:
        c = pd.read_csv(_cache_path(name, prov), index_col=0, parse_dates=True)
        return c[["open", "high", "low", "close"]].astype(float)
    except (OSError, ValueError, KeyError):
        return None


def fetch_m15(name):
    """M15 candles (broker time index) for one symbol: providers in PROVIDER order, first that works.
    Candles are cached between runs (per provider), so a normal run downloads only the newest ones."""
    errs = []
    broker_now = utc_to_broker(pd.Timestamp.now(tz="UTC"))
    for prov in [p.strip().lower() for p in CFG["PROVIDER"].split(",") if p.strip()]:
        cache = _load_cache(name, prov)
        cache_ok = cache is not None and len(cache) >= 3000 and (broker_now - cache.index[-1]) < pd.Timedelta(days=6)
        try:
            if prov == "deriv":
                df = fetch_deriv(name, need=700 if cache_ok else 5000)
            else:
                df = _fetch_one(prov, name)
        except Exception as e:
            errs.append(str(e))
            print(f"{name}: {prov} failed: {e}")
            continue
        CUR["source"] = prov
        df.index = pd.DatetimeIndex([utc_to_broker(pd.Timestamp(x).tz_localize("UTC") if pd.Timestamp(x).tzinfo is None
                                                   else pd.Timestamp(x)) for x in df.index])
        if cache_ok:
            df = pd.concat([cache, df])
        df = df[~df.index.duplicated(keep="last")].sort_index().iloc[-6000:]
        try:
            os.makedirs(os.path.dirname(_cache_path(name, prov)), exist_ok=True)
            df.to_csv(_cache_path(name, prov), float_format="%.6f")
        except OSError:
            pass
        return df
    raise RuntimeError(" | ".join(errs) or "no provider")


def load_csv(path):
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df.index = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    return df[["open", "high", "low", "close"]].astype(float)


def load_state():
    try:
        with open(CFG["STATE_FILE"]) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(CFG["STATE_FILE"]) or ".", exist_ok=True)
    with open(CFG["STATE_FILE"], "w") as f:
        json.dump(st, f, indent=1)


#==================================================================
# Runs
#==================================================================
def scan_symbol(name, st, broker_now):
    """One symbol: download, evaluate the M15 candles not checked yet, send alerts. Updates st."""
    set_symbol(name)
    m15 = fetch_m15(name)
    st["source"] = CUR.get("source", "-")
    st["candles"] = len(m15)
    latest = m15.index[-1]
    if (broker_now - latest) > pd.Timedelta(minutes=45):
        st["last_status"] = f"market closed (last candle {latest:%Y-%m-%d %H:%M})"
        return
    # the candle opening at `cur` is the forming one; if the API does not return it yet, add it
    # as a single tick at the last close (the EA evaluates on the first tick of a new candle)
    cur = broker_now.floor("15min")
    if latest < cur:
        lc = float(m15["close"].iloc[-1])
        m15.loc[cur] = {"open": lc, "high": lc, "low": lc, "close": lc}
    m15 = m15[m15.index <= cur]
    opens = list(m15.index)
    last_eval = pd.Timestamp(st["last_eval"]) if st.get("last_eval") else None
    todo = [t for t in opens[-CFG["CATCHUP_BARS"]:] if last_eval is None or t > last_eval]
    if last_eval is None:
        todo = todo[-1:]
    for T in todo:
        sig, status = evaluate(m15, T, st)
        print(f"{name}  {T}  {status}")
        if sig:
            ok = tg_send(message(sig), chart_png(sig))
            print("  telegram sent" if ok else "  telegram FAILED")
        st["last_eval"] = str(T)
        st["last_status"] = status


def run_live():
    state = load_state()
    syms = state.setdefault("symbols", {})
    now_myt = datetime.now(MYT)
    broker_now = utc_to_broker(pd.Timestamp.now(tz="UTC"))
    errors = []
    for name in symbol_list():
        st = syms.setdefault(name, {})
        try:
            scan_symbol(name, st, broker_now)
        except Exception as e:
            print(f"{name} error: {e}")
            errors.append(f"{name}: {e}")
    # one-time welcome: confirms Telegram works and shows a chart of the latest past XAUUSD setup
    if not state.get("welcome_sent"):
        ok = tg_send("FIZY BOT cloud scanner is set up.\nScanning " + str(len(symbol_list())) +
                     " symbols every 15 minutes (Sunday-Friday). Alerts only, no trades.\n"
                     "Daily 'alive' message at 8:00 am Malaysia time.")
        state["welcome_telegram_ok"] = ok
        try:
            set_symbol("XAUUSD")
            m15 = fetch_m15("XAUUSD")
            tmp, last = {}, None
            for T in list(m15.index)[-600:]:
                sig, _ = evaluate(m15, T, tmp)
                if sig:
                    last = sig
            if last:
                tg_send("EXAMPLE ONLY (a past setup, not a new signal)\n\n" + message(last), chart_png(last))
                state["welcome_example"] = str(last["time"])
        except Exception as e:
            print("welcome example error:", e)
        state["welcome_sent"] = True
    if _deriv_ws[0] is not None:
        try:
            _deriv_ws[0].close()
        except Exception:
            pass
    if errors:
        last = state.get("last_error_msg")
        if not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() > 6 * 3600:
            tg_send("FIZY BOT: data problem, will keep retrying every 15 minutes\n" + "\n".join(errors[:10]))
            state["last_error_msg"] = datetime.now(timezone.utc).isoformat()
    # plain-text summary of this run (the workflow publishes it after manual / push runs)
    try:
        os.makedirs(os.path.dirname(CFG["STATE_FILE"]) or ".", exist_ok=True)
        with open(os.path.join(os.path.dirname(CFG["STATE_FILE"]) or ".", "last_run.txt"), "w") as f:
            f.write(f"run (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M}  broker time: {broker_now:%Y-%m-%d %H:%M}\n")
            for n in symbol_list():
                st = syms.get(n, {})
                f.write(f"{n:8s} {st.get('source', '-'):10s} {st.get('candles', 0):5d}  {st.get('last_status', '-')}\n")
            for e in errors:
                f.write(f"ERROR {e}\n")
            f.write(f"welcome telegram ok: {state.get('welcome_telegram_ok')}  example: {state.get('welcome_example')}\n")
    except OSError:
        pass
    # daily heartbeat
    hb = CFG["HEARTBEAT_HOUR"]
    if hb >= 0 and now_myt.hour == hb and state.get("heartbeat_day") != now_myt.date().isoformat():
        lines = [f"{n}: {syms.get(n, {}).get('last_status', '-')}" for n in symbol_list()]
        tg_send("FIZY BOT is alive (cloud scanner)\n" + "\n".join(lines)[:3500])
        state["heartbeat_day"] = now_myt.date().isoformat()
    save_state(state)


def _csak_candidates(m15, tf, last_n):
    """Opens T right after a candle (of tf) whose body crosses Mid BB: cheap pre-filter for CSAK."""
    if tf == "15min":
        d = m15
    else:
        d = m15.resample(tf, label="left", closed="left", origin="start_day").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    mid = d["close"].rolling(20).mean()
    cross = ((d["open"] < mid) & (d["close"] > mid)) | ((d["open"] > mid) & (d["close"] < mid))
    ends = d.index[cross.values] + pd.Timedelta(minutes=TF_MIN[tf])
    ends = ends[ends >= m15.index[-last_n]]
    return set(t for t in ends if t in m15.index)


def run_example(max_steps=1500, max_seconds=1100):
    """Find the most recent past setup on any symbol and send it to Telegram as an example."""
    data, diag, sources = {}, [], {}
    for name in symbol_list():
        try:
            set_symbol(name)
            data[name] = fetch_m15(name)
            sources[name] = CUR.get("source")
        except Exception as e:
            diag.append(f"{name}: data error {e}")
    for name, m15 in data.items():
        set_symbol(name)
        _, st = evaluate(m15, m15.index[-1], {})
        diag.append(f"{name}: {len(m15)} candles {m15.index[0]:%Y-%m-%d}..{m15.index[-1]:%Y-%m-%d %H:%M}  now: {st}")
    diag.insert(0, "sources: " + ", ".join(f"{n}={src}" for n, src in sources.items()))
    t0 = time.time()
    cand = []
    for name, m15 in data.items():
        n = min(max_steps, len(m15) - 1)
        ts = _csak_candidates(m15, CFG["ENTRY_TF"], n) | _csak_candidates(m15, CFG["ENTRY_TF2"], n)
        cand += [(t, name) for t in ts]
    cand.sort(reverse=True)
    found, checked = None, 0
    for T, name in cand:
        if time.time() - t0 > max_seconds:
            diag.append("stopped: time limit")
            break
        set_symbol(name)
        sig, _ = evaluate(data[name], T, {})
        checked += 1
        if sig:
            found = (name, sig)
            break
    diag.append(f"candidates {len(cand)}, checked {checked}")
    out = os.path.join(os.path.dirname(CFG["STATE_FILE"]) or ".", "example.txt")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        if found:
            name, sig = found
            set_symbol(name)
            ok = tg_send("EXAMPLE ONLY (a past setup, not a new signal)\n\n" + message(sig), chart_png(sig))
            f.write(f"example {name} {sig['time']} sent={ok}\n")
        else:
            f.write(f"no setup found in the last {max_steps} candles\n")
        f.write("\n".join(diag) + "\n")
    print(open(out).read())


def run_csv(path, chart_out=None, start=None, name="XAUUSD"):
    set_symbol(name)
    m15 = load_csv(path)
    state = {}
    opens = list(m15.index)
    t0 = pd.Timestamp(start) if start else opens[0] + pd.Timedelta(days=55)
    sigs = []
    for T in opens:
        if T < t0:
            continue
        sig, st = evaluate(m15, T, state)
        if sig:
            sigs.append(sig)
            print(f"{T}  {'BUY ' if sig['dir'] == 1 else 'SELL'}  entry {px(sig['entry'])}  SL {px(sig['sl'])}  "
                  f"TP {px(sig['tp'])}  RR {sig['rr']:.1f}  rej {sig['rej_tf']}  CSAK {TF_NAME[sig['csak_tf']]}")
    print(f"{len(sigs)} signals")
    if chart_out and sigs:
        with open(chart_out, "wb") as f:
            f.write(chart_png(sigs[-1]))
        print(message(sigs[-1]))
    return sigs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--chart"); ap.add_argument("--start")
    ap.add_argument("--name", default="XAUUSD", help="symbol of the CSV file (for pips / digits)")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--example", action="store_true", help="send the most recent past setup as an example")
    a = ap.parse_args()
    if a.example:
        run_example()
    elif a.test:
        print("ok" if tg_send("FIZY BOT: test message from the cloud scanner") else "failed")
    elif a.csv:
        run_csv(a.csv, a.chart, a.start, a.name)
    else:
        run_live()
