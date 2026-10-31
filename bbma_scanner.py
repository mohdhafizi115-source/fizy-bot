"""
FIZY BOT - BBMA scanner (cloud, alert only).

Runs on GitHub Actions and scans 1 s after every M15 close. Downloads M15 candles (Deriv, with
Yahoo / Twelve Data as fallback) for every symbol in SYMBOLS (forex pairs and XAUUSD), builds the
M30 / H4 candles on broker time (JustMarkets server time = New York time + 7 hours) and sends a
chart of each setup to Telegram.

Active setup: H4 momentum + retrace to H4 MA5/10 + CSAK (buy shown, sell mirrored):
  1. H4 trend only: EMA 90 below EMA 50, and EMA 50 below Mid BB (no H1, no BB slope check)
  2. H4 momentum: a candle closed above Top BB within the last 10 closed H4 candles
  3. Price then comes back to the H4 MA5/10 Low zone (any number of touches; the first starts the watch)
  4. The first CSAK on M30 or M15 after that (ONE candle breaks Mid BB + EMA 50, not one that already
     closes outside the BB) -> Telegram alert with the M15 chart. One alert per H4 momentum candle.
The old EMA 50 rejection setup is off (REJECTION_SETUP = False).

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
    "TG_TOKEN":       "",            # from the TG_TOKEN GitHub secret when set, else the built-in one below
    "TG_CHAT_ID":     "",
    # market
    # comma separated list, or ALL = the 28 major / cross pairs + XAUUSD
    "SYMBOLS":        "ALL",
    "SPREAD_PIPS_FX": 1.0,           # assumed spread for the sell SL / buy entry (forex, pips)
    "SPREAD_PIPS_XAU": 2.0,          # assumed spread for gold (pips, 1 pip = 0.10)
    "BROKER_OFFSET":  7,             # only used when BROKER_TZ is empty: broker time = New York time + N hours
    "BROKER_TZ":      "Europe/Athens",  # JustMarkets server time: GMT+2 winter / GMT+3 summer, clocks change on the
                                     # EU dates (its M15 export: daily break at 23:00 from 9 to 27 Mar 2026, else 00:00)
    # BBMA model
    "TREND_TF1":      "1h",
    "TREND_TF2":      "4h",
    "TREND_BOTH":     True,          # trend TF 2 must agree with trend TF 1
    "REJ_TF1":        "1h",          # CSAK on ENTRY_TF2 or ENTRY_TF
    "REJ_TF2":        "30min",       # CSAK on ENTRY_TF
    "REJ_LOOKBACK":   12,
    "REJ_MAX_BARS":   6,
    "MOM_TF":         "4h",
    "MOM_LOOKBACK":   5,             # last N closed momentum TF candles to look for momentum
    "TRADES_PER_MOM": 1,             # alerts per momentum candle (0 = unlimited)
    "REQUIRE_RETRACE": False,        # also require a retrace to MA5/10 on the momentum TF
    "MOM_EMA_VS_MID": True,          # momentum TF: EMA 50 below Mid BB for buy, above for sell
    "ENTRY_TF2":      "30min",
    "ENTRY_TF":       "15min",
    "SKIP_MOM_CSAK":  True,          # skip a CSAK candle that already closes outside the BB
    # Setup 2 "retrace": H4 trend + H4 momentum, price back to H4 MA5/10, then M30 / M15 CSAK
    # (no H1, no EMA 50 rejection, no BB slope check)
    "BBMA_ALERTS":    False,         # BBMA scanner on all pairs (turned off 29 Oct: only the XAUUSD London breakout runs)
    "RETRACE_SETUP":  True,
    "REJECTION_SETUP": False,        # setup 1 (EMA 50 rejection, H1 + H4 trend): removed 27 Oct, kept here only as an off switch
    "M1_CHECKS":      True,          # check fills / BE / TP / SL on M1 candles (alerts within ~1 min) instead of M15
    "M5_SCALP":       False,         # XAUUSD M5 RSI(2) scalp alerts: OFF since 31 Oct (lost on 3.7 years of JustMarkets M5, PF 0.94)
    "M5_SESSION":     [8, 20],       # entries only between these chart hours
    "M5_MAX_BARS":    24,            # time exit after this many M5 candles (2 hours)
    "RSI2_ALERTS":    True,          # XAUUSD H1 RSI(2) pullback alerts (entry / exit / SL), added 30 Oct at the user's request
    "RSI2_LO":        10,
    "RSI2_HI":        90,
    "RSI2_SL_ATR":    2.0,
    "LONDON_BREAKOUT": True,         # XAUUSD London breakout alerts (place orders / filled / BE / close)
    "LB_RANGE":       [3, 8],        # Asian range hours (chart time), orders at the end hour
    "LB_CLOSE_HOUR":  21,            # close any open trade at this chart hour
    "LB_MIN_MAX_PCT": [0.30, 1.60],  # trade only when the range is this % of price
    "LB_CAP_PCT":     0.6,           # SL at the other side of the range, at most this % of price
    "LB_TP_R":        2.5,
    "LB_BE_R":        1.5,
    "LB_BUFFER":      0.10,          # entry this far beyond the range high / low
    "LB_SQUEEZE_ATR": 0.6,
    "LB_WARN_MIN":    60,            # reminder this many minutes before the close hour (0 = off)           # trade only when the Asian range < this x daily ATR(14) (0 = off)
    "CSAK_MA510":     True,          # retrace setup: CSAK must also close beyond MA5/10 Low (sell) / High (buy)
    "FETCH_WORKERS":  6,             # parallel Deriv downloads per scan (1 = one by one)
    "ZONE_ALERT":     True,          # alert 1: price entered the H4 MA5/10 zone (with the H4 chart)
    "ZONE_ALERT_MAX_AGE": 60,        # minutes; an older first touch is not alerted (e.g. after a restart)
    "RT_MOM_LOOKBACK": 10,           # last N closed H4 candles to look for the momentum candle
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
    "HEARTBEAT_HOURS": [0, 4, 8, 12, 16, 20],  # "still alive" message at these Malaysia hours ([] = off)
    "STATE_FILE":     "state/state.json",
}
_TG_BUILTIN = "REMOVED"   # bot token, encoded so it is not stored as plain text


def _tg_builtin():
    import base64
    return base64.b64decode(_TG_BUILTIN).decode()[::-1]


for k in list(CFG):
    v = os.environ.get(k)
    if v not in (None, ""):
        CFG[k] = type(CFG[k])(v) if not isinstance(CFG[k], bool) else v.lower() in ("1", "true", "yes")
if not CFG["TG_TOKEN"]:
    CFG["TG_TOKEN"] = _tg_builtin()

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


def scan_list():
    """symbols downloaded each scan: all pairs when the BBMA scanner is on, else only XAUUSD (London breakout)"""
    return symbol_list() if CFG["BBMA_ALERTS"] else [n for n in symbol_list() if n == "XAUUSD"] or ["XAUUSD"]


def symbol_list():
    raw = ALL_PAIRS if CFG["SYMBOLS"].strip().upper() == "ALL" else CFG["SYMBOLS"]
    return [x.strip().upper() for x in raw.split(",") if x.strip()]


TF_MIN = {"15min": 15, "30min": 30, "1h": 60, "4h": 240}
TF_NAME = {"15min": "M15", "30min": "M30", "1h": "H1", "4h": "H4"}
MYT = ZoneInfo("Asia/Kuala_Lumpur")
NY = ZoneInfo("America/New_York")


def broker_to_myt(t):
    """Broker time (naive, chart time) -> Malaysia time."""
    if CFG.get("BROKER_TZ"):
        return pd.Timestamp(t).tz_localize(ZoneInfo(CFG["BROKER_TZ"]), ambiguous=False,
                                           nonexistent="shift_forward").tz_convert(MYT)
    ny = pd.Timestamp(t) - pd.Timedelta(hours=CFG["BROKER_OFFSET"])
    return ny.tz_localize(NY, ambiguous=False, nonexistent="shift_forward").tz_convert(MYT)


def when(t, now):
    """'14:00 chart time, 3h 15m ago' for a broker-time (MT5 chart) candle open `t`, seen at broker time `now`."""
    m, n = pd.Timestamp(t), pd.Timestamp(now)
    mins = max(0, int((n - m).total_seconds() // 60))
    ago = f"{mins // 60}h {mins % 60:02d}m ago" if mins >= 60 else f"{mins}m ago"
    day = "" if m.date() == n.date() else f"{m:%d/%m} "
    return f"{day}{m:%H:%M} chart time, {ago}"


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


def csak_ma510(d, dr):
    """Retrace setup: the CSAK candle must also close beyond the MA5/10 of its own TF:
    sell -> below both MA5 Low and MA10 Low, buy -> above both MA5 High and MA10 High."""
    if not CFG["CSAK_MA510"]:
        return True
    if not d.valid(1) or d.ma10l[1] <= 0 or d.ma10h[1] <= 0:
        return False
    if dr == 1:
        return d.c[1] > max(d.ma5h[1], d.ma10h[1])
    return d.c[1] < min(d.ma5l[1], d.ma10l[1])


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
        return None, (f"H1 EMA 50 {k1} ({when(rT1, T)}), {why1}" if r1 >= 0
                      else f"M30 EMA 50 {k2} ({when(rT2, T)}), {why2}")
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
    # a rejection that already gave an alert does not count as "waiting" any more
    done1 = okR1 and str(rT1) == state.get("last_rej")
    done2 = okR2 and str(rT2) == state.get("last_rej")
    if (okR1 or okR2) and (not okR1 or done1) and (not okR2 or done2):
        at = state.get("last_alert_t", "")
        return None, "alert already sent for this setup" + (f" ({when(at, T)})" if at else "") + \
            ", waiting for a new rejection"
    if not csakE2 and not csakE1:
        w1 = okR1 and not done1
        return None, (f"H1 EMA 50 rejection ({when(rT1, T)})" if w1 else f"M30 EMA 50 rejection ({when(rT2, T)})") + \
            " + H4 momentum, waiting for CSAK"

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
    state["last_alert_t"] = f"{dC.t[1]:%Y-%m-%d %H:%M}"
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


#==================================================================
# Setup 2: H4 momentum + retrace to H4 MA5/10 + CSAK (buy shown, sell mirrored)
#   1. H4 trend: EMA 90 below EMA 50, and EMA 50 below Mid BB
#   2. H4 momentum: a candle closed above Top BB within the last RT_MOM_LOOKBACK closed H4 candles
#      (momentum the other way after it cancels)
#   3. After that candle, price comes back to the H4 MA5/10 Low (low <= the higher of MA5 / MA10 Low);
#      how many times it touches does not matter, the first touch starts the watch
#   4. Then the first CSAK on M30 or M15 (whichever comes first; Mid BB + EMA 50, and the close also
#      beyond MA5/10 Low for a sell / MA5/10 High for a buy, on the CSAK TF) at or after the
#      first touch -> alert with the M15 chart. One alert per H4 momentum candle.
#   5. Cancelled for good when price breaks the H4 EMA 50 the other way after the momentum (H4 candle
#      closed below it for a buy / above for a sell, or the live H4 price there at an M15 close)
#==================================================================
RT_RULE = 2   # CSAK rule version; an alert sent under an older rule does not block a new one


def evaluate_retrace(m15, T, state):
    C = CFG; B = C["BARS"]
    tfs = {C["MOM_TF"], C["ENTRY_TF"], C["ENTRY_TF2"]}
    D = {tf: BB(series_as_of(m15, T, tf, B), tf) for tf in tfs}
    if any(D[tf].n < 120 for tf in tfs):
        return None, "not enough history"
    dM, dE, dE2 = D[C["MOM_TF"]], D[C["ENTRY_TF"]], D[C["ENTRY_TF2"]]
    if not dM.valid(1) or dM.ema[1] <= 0 or dM.ema90[1] <= 0:
        return None, "no H4 data"
    e50, e90, mid = dM.ema[1], dM.ema90[1], dM.mid[1]
    if e90 < e50 < mid:
        dr = 1
    elif mid < e50 < e90:
        dr = -1
    else:
        return None, "H4 EMA 50 / EMA 90 / Mid BB not in buy or sell order"
    side = "buy" if dr == 1 else "sell"
    j, why = find_momentum_before(dM, dr, None, C["RT_MOM_LOOKBACK"])
    if j < 0:
        return None, f"H4 {side} trend, {why}"
    momT = dM.t[j]
    # setup cancelled for good once price breaks the H4 EMA 50 against the trade after the momentum:
    # an H4 candle closed beyond it, or the forming H4 candle is beyond it at the last M15 close
    brokeT = None
    if state.get("rt_dead_mom") == str(momT):
        brokeT = pd.Timestamp(state.get("rt_dead_t", str(momT)))
    else:
        for k in range(j - 1, -1, -1):
            if dM.ema[k] > 0 and ((dM.c[k] < dM.ema[k]) if dr == 1 else (dM.c[k] > dM.ema[k])):
                brokeT = dM.t[k] if k > 0 else T
                state["rt_dead_mom"] = str(momT); state["rt_dead_t"] = str(brokeT)
                break
    if brokeT is not None:
        return None, (f"H4 {side} setup cancelled: price broke H4 EMA 50 ({when(brokeT, T)}), "
                      f"waiting for a new H4 momentum")
    # first H4 candle after the momentum that reaches the MA5/10 zone, then the exact M15 touch
    touchT = None
    for k in range(j - 1, -1, -1):
        line = max(dM.ma5l[k], dM.ma10l[k]) if dr == 1 else min(dM.ma5h[k], dM.ma10h[k])
        if line <= 0:
            continue
        hit = dM.l[k] <= line if dr == 1 else dM.h[k] >= line
        if not hit:
            continue
        end = dM.t[k] + timedelta(hours=4)
        for i in range(dE.n - 1, 0, -1):            # oldest -> newest closed M15 candles
            if dE.t[i] < dM.t[k] or dE.t[i] >= end:
                continue
            if (dE.l[i] <= line) if dr == 1 else (dE.h[i] >= line):
                touchT = dE.t[i]
                break
        if touchT is not None:
            break
    if touchT is None:
        return None, f"H4 {side} momentum ({when(momT, T)}), waiting for retrace to H4 MA5/10 {'Low' if dr == 1 else 'High'}"
    if C["ZONE_ALERT"] and state.get("rt_zone_mom") != str(momT) and str(momT) != state.get("rt_last_mom"):
        state["rt_zone_mom"] = str(momT)
        if (T - touchT) <= pd.Timedelta(minutes=C["ZONE_ALERT_MAX_AGE"]):
            state["_zone_sig"] = dict(setup="zone", dir=dr, time=T, entry=float(dE.o[0]), mom_t=momT,
                                      touch_t=touchT, data=dM, chart_tf=C["MOM_TF"], csak_tf=C["MOM_TF"])
    if str(momT) == state.get("rt_last_mom") and state.get("rt_rule") == RT_RULE:
        return None, (f"CSAK alert already sent for this H4 momentum ({when(state.get('rt_last_alert_t', str(momT)), T)}), "
                      f"waiting for a new H4 momentum")
    csakE2 = fresh_close(dE2, dE) and dE2.t[1] >= touchT.floor("30min") and is_csak(dE2, dr) and csak_ma510(dE2, dr)
    csakE1 = dE.t[1] >= touchT and is_csak(dE, dr) and csak_ma510(dE, dr)
    if not csakE2 and not csakE1:
        return None, (f"H4 {side} momentum ({when(momT, T)}) + retrace to MA5/10 ({when(touchT, T)}), "
                      f"waiting for M30 / M15 CSAK (Mid BB + EMA 50 + MA5/10)")
    cTF = C["ENTRY_TF2"] if csakE2 else C["ENTRY_TF"]
    csakT = dE2.t[1] if csakE2 else dE.t[1]
    entry = float(dE.o[0]) + (CUR["spread"] if dr == 1 else 0)
    state["rt_last_mom"] = str(momT)
    state["rt_rule"] = RT_RULE
    state["rt_last_alert_t"] = f"{csakT:%Y-%m-%d %H:%M}"
    state["last_alert_t"] = state["rt_last_alert_t"]
    sig = dict(setup="retrace", dir=dr, time=T, entry=entry, mom_t=momT, touch_t=touchT, csak_tf=cTF,
               csak_t=csakT, data=dE, chart_tf=C["ENTRY_TF"])
    return sig, "SIGNAL (retrace)"


def evaluate_all(m15, T, state):
    """Active setup: H4 momentum + retrace to H4 MA5/10 + first M30 / M15 CSAK after the retrace.
    Setup 1 (EMA 50 rejection) runs only when REJECTION_SETUP is turned back on."""
    if not CFG["REJECTION_SETUP"]:
        return evaluate_retrace(m15, T, state)
    sig, st1 = evaluate(m15, T, state)
    if sig or not CFG["RETRACE_SETUP"]:
        return sig, st1
    sig2, st2 = evaluate_retrace(m15, T, state)
    if sig2:
        return sig2, st2
    return None, f"{st1}  ||  retrace: {st2}"


def message_zone(sig):
    side = "BUY" if sig["dir"] == 1 else "SELL"
    sep = "=============================\n"
    return (f"FIZY BOT | {CUR['name']} {side} - price in H4 MA5/10 zone (alert 1/2)\n" + sep +
            f"Setup: BBMA H4 momentum + retrace MA5/10\n"
            f"Trend: H4 {'bullish' if sig['dir'] == 1 else 'bearish'} (EMA 90 {'below' if sig['dir'] == 1 else 'above'} EMA 50, "
            f"EMA 50 {'below' if sig['dir'] == 1 else 'above'} Mid BB)\n"
            f"H4 momentum: {sig['mom_t']:%Y-%m-%d %H:%M}\n"
            f"Price entered H4 MA5/10 {'Low' if sig['dir'] == 1 else 'High'}: {sig['touch_t']:%Y-%m-%d %H:%M} (M15 candle)\n"
            f"Next: waiting for CSAK on M30 / M15 (alert 2/2)\n" + sep +
            f"Broker time: {sig['time']:%Y-%m-%d %H:%M}  |  data: {CUR.get('source', '-')}")


def message_retrace(sig):
    side = "BUY" if sig["dir"] == 1 else "SELL"
    sep = "=============================\n"
    return (f"FIZY BOT | {CUR['name']} {side} - CSAK (alert 2/2)\n" + sep +
            f"Setup: BBMA H4 momentum + retrace MA5/10 + CSAK\n"
            f"Trend: H4 {'bullish' if sig['dir'] == 1 else 'bearish'} (EMA 90 {'below' if sig['dir'] == 1 else 'above'} EMA 50, "
            f"EMA 50 {'below' if sig['dir'] == 1 else 'above'} Mid BB)\n"
            f"H4 momentum: {sig['mom_t']:%Y-%m-%d %H:%M}\n"
            f"Retrace to H4 MA5/10 {'Low' if sig['dir'] == 1 else 'High'}: {sig['touch_t']:%Y-%m-%d %H:%M}\n"
            f"CSAK: {TF_NAME[sig['csak_tf']]} candle broke Mid BB + EMA 50 + MA5/10 {'High' if sig['dir'] == 1 else 'Low'}\n" + sep +
            f"Broker time: {sig['time']:%Y-%m-%d %H:%M}  |  data: {CUR.get('source', '-')}")


def message(sig):
    side = "BUY" if sig["dir"] == 1 else "SELL"
    myt = sig["time"]  # broker time
    fut = CUR["name"].startswith("XAU") and CUR.get("source") == "yahoo"
    note = "\nNote: gold prices are COMEX futures (GC=F); JustMarkets XAUUSD differs by a few dollars" if fut else ""
    sep = "=============================\n"
    return (f"FIZY BOT | {CUR['name']} {side} (alert only)\n" + sep +
            f"Setup: BBMA EMA 50 rejection + CSAK\n"
            f"Trend: H1 + H4 {'bullish' if sig['dir'] == 1 else 'bearish'} (EMA 50 vs EMA 90)\n"
            f"EMA 50 {sig['rej_kind']}: {sig['rej_tf']} at {sig['rej_t']:%Y-%m-%d %H:%M}\n"
            f"H4 momentum: {sig['mom_t']:%Y-%m-%d %H:%M}\n"
            f"CSAK: {TF_NAME[sig['csak_tf']]} candle broke Mid BB + EMA 50\n" + sep +
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
    if sig.get("setup") == "zone":
        ax.axhline(sig["entry"], color="#ffffff", linewidth=1.0, linestyle="--")
        ax.text(len(x) + 0.5, sig["entry"], f" Price {px(sig['entry'])}", color="#ffffff", va="center", fontsize=9)
        pos = {t: xi for xi, t in zip(x, [d.t[i] for i in idx])}
        for label, t, top in (("MOM", sig["mom_t"], sig["dir"] == 1), ("ZONE", sig["touch_t"].floor("4h"), sig["dir"] != 1)):
            if t in pos:
                i = d.t.index(t)
                ax.annotate(label, (pos[t], d.h[i] if top else d.l[i]), color="#ffd700", fontsize=9, ha="center",
                            xytext=(0, 12 if top else -16), textcoords="offset points")
    else:
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
    ax.set_title(f"FIZY BOT  {CUR['name']} {TF_NAME[sig.get('chart_tf', sig['csak_tf'])]}  BBMA "
                 f"{ {'retrace': 'retrace ', 'zone': 'H4 zone '}.get(sig.get('setup'), '') }{side}",
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
    if CFG.get("BROKER_TZ"):
        return ts_utc.tz_convert(ZoneInfo(CFG["BROKER_TZ"])).tz_localize(None)
    ny = ts_utc.tz_convert(NY)
    return (ny + pd.Timedelta(hours=CFG["BROKER_OFFSET"])).tz_localize(None)


def _old_broker(ts_utc):
    return (ts_utc.tz_convert(NY) + pd.Timedelta(hours=CFG["BROKER_OFFSET"])).tz_localize(None)


def migrate_broker_tz(state):
    """Once, when the chart-time rule changes (New York + 7 -> BROKER_TZ): move the times kept in the
    state by the difference right now and drop the candle caches (their index is chart time)."""
    rule = CFG.get("BROKER_TZ") or f"NY+{CFG['BROKER_OFFSET']}"
    if state.get("broker_tz") == rule:
        return
    nowu = pd.Timestamp.now(tz="UTC")
    shift = (utc_to_broker(nowu) - _old_broker(nowu)).round("1h") if CFG.get("BROKER_TZ") else pd.Timedelta(0)
    if state.get("broker_tz") and state["broker_tz"] != rule:
        shift = pd.Timedelta(0)                   # switched again later: no reliable shift, keep the times
    keys = {None: ("last_eval",), "lb": ("last_t", "done_to"), "rs2": ("last_h1", "last_m15", "sl_to"),
            "m5": ("last", "sl_to", "cool")}
    if shift != pd.Timedelta(0):
        for st in state.get("symbols", {}).values():
            for sub, ks in keys.items():
                d = st if sub is None else st.get(sub)
                if not isinstance(d, dict):
                    continue
                for k in ks:
                    if d.get(k):
                        try:
                            d[k] = str(pd.Timestamp(d[k]) + shift)
                        except (ValueError, TypeError):
                            pass
            p = (st.get("rs2") or {}).get("pos")
            if isinstance(p, dict) and p.get("t"):
                p["t"] = str(pd.Timestamp(p["t"]) + shift)
    dropped = 0
    for name in set(symbol_list()) | {"XAUUSD"}:
        for prov in [p.strip().lower() for p in CFG["PROVIDER"].split(",") if p.strip()]:
            try:
                os.remove(_cache_path(name, prov)); dropped += 1
            except OSError:
                pass
    print(f"chart time rule -> {rule}: state times moved {shift}, {dropped} candle caches dropped")
    state["broker_tz"] = rule


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


import threading
_deriv_tls = threading.local()       # one Deriv websocket per thread (data is downloaded in parallel)


class _WsSlot:
    """Per-thread websocket holder, used like the old one-element list (_deriv_ws[0])."""
    def __getitem__(self, i):
        return getattr(_deriv_tls, "ws", None)

    def __setitem__(self, i, v):
        _deriv_tls.ws = v


_deriv_ws = _WsSlot()
_prefetch = {}                       # name -> future with the newest Deriv candles (filled by run_live)
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


def fetch_deriv(name, need=5000, max_pages=12, granularity=900):
    """Deriv public market data: 15-minute candles, no account needed. Deriv returns about 800
    candles per request, so older candles are fetched page by page (end = oldest candle - 1)."""
    got = {}
    end = "latest"
    for page in range(max_pages):
        req = {"ticks_history": "frx" + name, "style": "candles", "granularity": granularity,
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
                fut = _prefetch.pop(name, None)
                df = None
                if fut is not None:
                    try:
                        df = fut.result(timeout=60)
                    except Exception as e:      # retry below on this thread's own connection
                        print(f"{name}: parallel download failed ({e}), retrying")
                if df is None or (not cache_ok and len(df) < 3000):
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
#==================================================================
# XAUUSD London breakout (alerts only), same rules as the backtest:
#   Asian range 03:00-08:00 chart time; at 08:00 buy stop above the high and sell stop below the
#   low (OCO); SL at the other side of the range (max 0.6% of price); TP 2.5R; SL to entry at
#   1.5R; close at 21:00. Trade only when the range is 0.30%-1.60% of price and narrower than
#   0.6 x the daily ATR(14) (squeeze filter, added 29 Oct after testing 12 indicator filters).
#==================================================================
def _lb_levels(hi, lo):
    C = CFG; buf = C["LB_BUFFER"]
    mid = (hi + lo) / 2; capd = mid * C["LB_CAP_PCT"] / 100
    b_in, s_in = hi + buf, lo - buf
    b_sl = max(lo, b_in - capd); s_sl = min(hi, s_in + capd)
    rb, rs = b_in - b_sl, s_sl - s_in
    return dict(hi=hi, lo=lo, pct=(hi - lo) / mid * 100,
                b_in=b_in, b_sl=b_sl, b_tp=b_in + C["LB_TP_R"] * rb, b_be=b_in + C["LB_BE_R"] * rb, b_risk=rb,
                s_in=s_in, s_sl=s_sl, s_tp=s_in - C["LB_TP_R"] * rs, s_be=s_in - C["LB_BE_R"] * rs, s_risk=rs)


def _lb_head(title):
    return f"FIZY BOT | XAUUSD London breakout - {title}\n=============================\n"


def _lb_foot(t):
    return f"=============================\nBroker time: {t:%Y-%m-%d %H:%M}  |  data: {CUR.get('source', '-')}"


def lb_chart_png(m15, L, day):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = m15[(m15.index >= day - pd.Timedelta(hours=4)) & (m15.index < day + pd.Timedelta(hours=CFG["LB_RANGE"][1]))]
    x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    bg = "#0f1115"; fig.patch.set_facecolor(bg); ax.set_facecolor(bg)
    for xi, (t, r) in zip(x, d.iterrows()):
        col = "#26a69a" if r.close >= r.open else "#ef5350"
        ax.vlines(xi, r.low, r.high, color=col, linewidth=0.8)
        ax.add_patch(plt.Rectangle((xi - 0.32, min(r.open, r.close)), 0.64, max(abs(r.close - r.open), 1e-6), color=col))
    r0 = int(np.searchsorted(d.index, day + pd.Timedelta(hours=CFG["LB_RANGE"][0])))
    ax.add_patch(plt.Rectangle((r0 - 0.5, L["lo"]), len(d) - r0, L["hi"] - L["lo"], color="#3a6ea5", alpha=0.18))
    right = len(d) + 10
    for y, txt, col, st in ((L["b_in"], f"BUY STOP {px(L['b_in'])}", "#26a69a", "-"),
                            (L["b_tp"], f"BUY TP {px(L['b_tp'])}", "#26a69a", ":"),
                            (L["s_in"], f"SELL STOP {px(L['s_in'])}", "#ef5350", "-"),
                            (L["s_tp"], f"SELL TP {px(L['s_tp'])}", "#ef5350", ":")):
        ax.hlines(y, r0 - 0.5, right, color=col, linewidth=1.2, linestyle=st)
        ax.text(right + 0.3, y, " " + txt, color=col, va="center", fontsize=9)
    ys = [d.low.min(), d.high.max(), L["b_tp"], L["s_tp"]]
    pad = (max(ys) - min(ys)) * 0.05
    ax.set_ylim(min(ys) - pad, max(ys) + pad); ax.set_xlim(-1, right + 12)
    step = max(1, len(d) // 8)
    ax.set_xticks(x[::step]); ax.set_xticklabels([f"{t:%d/%m %H:%M}" for t in d.index][::step], color="#9aa0a6", fontsize=8)
    ax.tick_params(axis="y", colors="#9aa0a6", labelsize=8)
    for sp_ in ax.spines.values():
        sp_.set_color("#2a2e36")
    ax.grid(color="#1c1f26", linewidth=0.6)
    ax.set_title(f"FIZY BOT  XAUUSD M15  London breakout  {day:%d/%m}  (Asian range shaded)", color="#ffd700",
                 fontsize=12, loc="left")
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png", facecolor=bg); plt.close(fig)
    return buf.getvalue()


def _fine_closed(fine, now, done_to):
    """Closed candles of `fine` (M1, chart-time index) before `now`, and the candle length, when they
    cover everything from `done_to`; (None, None) otherwise (caller falls back to M15)."""
    if fine is None or now is None or len(fine) < 2:
        return None, None
    step = pd.Timedelta(fine.index.to_series().diff().median())
    if step <= pd.Timedelta(0):
        return None, None
    fb = fine[fine.index + step <= now]
    if not len(fb) or fb.index[0] > done_to.floor(step):
        return None, None
    return fb, step


def mt5_auto_on():
    """mt5_trade.txt line 1 = "on": the FizyLB EA trades the London breakout on the demo account."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mt5_trade.txt")) as f:
            return f.readline().strip().lower() == "on"
    except OSError:
        return False


def mt5_daily_dispatch(state, broker_now):
    """Start the first MT5 trading shift of the day (GitHub workflow mt5_trade.yml) at about 07:25 chart time.
    Retries every scan until 08:20 if the dispatch fails. Needs GH_TOKEN with actions: write (scan.yml)."""
    if not mt5_auto_on() or broker_now.dayofweek >= 5:
        return
    key = f"{broker_now:%Y-%m-%d}"
    hm = broker_now.hour * 60 + broker_now.minute
    if not (7 * 60 + 25 <= hm < 8 * 60 + 20) or state.get("mt5_dispatch") == key:
        return
    tok, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        print("MT5 dispatch: no GH_TOKEN / GITHUB_REPOSITORY"); return
    try:
        r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/mt5_trade.yml/dispatches",
                          headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                          json={"ref": "main"}, timeout=20)
    except requests.RequestException as e:
        print("MT5 dispatch error:", e); return
    if r.status_code == 204:
        state["mt5_dispatch"] = key
        print("MT5 trading shift 1 dispatched")
    else:
        print("MT5 dispatch failed:", r.status_code, r.text[:200])


def london_step(m15, lb, cur, send=None, fine=None, now=None):
    """Advance the London breakout state `lb` (dict, kept in the XAUUSD state) using the M15 candles
    closed before `cur` (the open of the forming candle, chart time). Fills, BE, TP and SL are checked on
    the closed M1 candles of `fine` before `now` (chart time) when given. Sends Telegram alerts."""
    send = send or tg_send
    tnow = now.floor("1min") if now is not None else cur
    C = CFG; h0, h1 = C["LB_RANGE"]; hc = C["LB_CLOSE_HOUR"]
    day = cur.normalize()
    if day.dayofweek >= 5:
        return
    if lb.get("day") != str(day.date()):
        lb.clear(); lb.update(day=str(day.date()), status="waiting", text=f"waiting for the Asian range ({h0:02d}:00-{h1:02d}:00)")
    t_open, t_close = day + pd.Timedelta(hours=h1), day + pd.Timedelta(hours=hc)
    closed = m15[m15.index < cur]
    if lb["status"] == "waiting":
        if cur < t_open:
            return
        if cur > t_open + pd.Timedelta(minutes=30):
            # (re)started after 08:30: no stale alerts for today's earlier moves
            lb.update(status="done", text=f"started after {h1:02d}:30 today, alerts start next trading day"); return
        rng = closed[(closed.index >= day + pd.Timedelta(hours=h0)) & (closed.index < t_open)]
        if len(rng) < (h1 - h0) * 4 - 2:
            lb.update(status="done", text="not enough Asian range data today"); return
        L = _lb_levels(float(rng.high.max()), float(rng.low.min()))
        lo_p, hi_p = C["LB_MIN_MAX_PCT"]
        # squeeze filter: the Asian range must be narrow compared with the usual daily move
        d1 = m15[m15.index < day].resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        d1 = d1[d1.index.dayofweek < 5]
        tr_ = np.maximum(d1.high - d1.low, np.maximum(abs(d1.high - d1.close.shift()), abs(d1.low - d1.close.shift())))
        datr = float(tr_.rolling(14).mean().iloc[-1]) if len(d1) >= 15 else float("nan")
        L["ratio"] = (L["hi"] - L["lo"]) / datr if datr == datr and datr > 0 else float("nan")
        sq = C["LB_SQUEEZE_ATR"]
        if sq > 0 and L["ratio"] == L["ratio"] and L["ratio"] >= sq:
            lb.update(status="done", text=f"no trade today: Asian range {L['ratio']:.2f}x daily ATR (needs < {sq:.2f}x)")
            send(_lb_head("NO TRADE TODAY") +
                 f"Asian range {h0:02d}:00-{h1:02d}:00: high {px(L['hi'])} / low {px(L['lo'])} = ${L['hi'] - L['lo']:.2f}\n"
                 f"That is {L['ratio']:.2f}x the daily ATR(14) of ${datr:.2f} (needs < {sq:.2f}x): the range is already\n"
                 f"too wide, so no orders today.\n" + _lb_foot(tnow))
            return
        if not (lo_p <= L["pct"] <= hi_p):
            lb.update(status="done", text=f"no trade today: Asian range {L['pct']:.2f}% (needs {lo_p:.2f}-{hi_p:.2f}%)")
            send(_lb_head("NO TRADE TODAY") +
                 f"Asian range {h0:02d}:00-{h1:02d}:00: high {px(L['hi'])} / low {px(L['lo'])} ({L['pct']:.2f}% of price)\n"
                 f"Needs {lo_p:.2f}%-{hi_p:.2f}%, so no orders today.\n" + _lb_foot(tnow))
            return
        lb.update(status="placed", L=L, last_t=str(t_open - pd.Timedelta(minutes=15)),
                  text=f"orders placed: BUY STOP {px(L['b_in'])} / SELL STOP {px(L['s_in'])}")
        send(_lb_head("PLACE ORDERS") +
             f"Asian range {h0:02d}:00-{h1:02d}:00: high {px(L['hi'])} / low {px(L['lo'])} ({L['pct']:.2f}%, "
             + (f"{L['ratio']:.2f}x daily ATR)\n" if L["ratio"] == L["ratio"] else "daily ATR n/a)\n") +
             f"BUY STOP  {px(L['b_in'])} | SL {px(L['b_sl'])} | TP {px(L['b_tp'])} | BE at {px(L['b_be'])}\n"
             f"SELL STOP {px(L['s_in'])} | SL {px(L['s_sl'])} | TP {px(L['s_tp'])} | BE at {px(L['s_be'])}\n"
             f"Risk per 0.01 lot: buy ${L['b_risk']:.2f} / sell ${L['s_risk']:.2f}\n"
             f"OCO: when one fills, delete the other. Close any open trade at {hc:02d}:00 chart time.\n"
             f"Check the range high / low on your own MT5 chart (data source can differ by a few points).\n"
             + ("AUTO TRADE is ON (demo): the bot places its own orders from the broker's prices, do not place these by hand.\n"
                if mt5_auto_on() else "")
             + _lb_foot(tnow), lb_chart_png(m15, L, day))
    if lb["status"] in ("placed", "open"):
        L = lb["L"]
        # fills / BE / TP / SL on the closed M1 candles when available (alert within about a minute),
        # else on the closed M15 candles. `done_to` = end of the last candle already checked.
        done_to = (pd.Timestamp(lb["done_to"]) if lb.get("done_to")
                   else pd.Timestamp(lb["last_t"]) + pd.Timedelta(minutes=15))
        bars_, step = _fine_closed(fine, now, done_to)
        if bars_ is None:
            bars_, step = closed, pd.Timedelta(minutes=15)
        tfl = f"M{int(step.total_seconds() // 60)}"
        todo = bars_[(bars_.index >= done_to.floor(step)) & (bars_.index < t_close)]
        for t, r in todo.iterrows():
            o_, h_, l_, c_ = float(r.open), float(r.high), float(r.low), float(r.close)
            path = [o_, l_, h_, c_] if c_ >= o_ else [o_, h_, l_, c_]
            for a_, b_ in zip(path[:-1], path[1:]):
                lo_, hi_ = min(a_, b_), max(a_, b_)
                if lb["status"] == "placed":
                    if hi_ >= L["b_in"] and (a_ <= b_ or lo_ > L["s_in"]):
                        dr = 1
                    elif lo_ <= L["s_in"]:
                        dr = -1
                    else:
                        continue
                    k = "b" if dr == 1 else "s"
                    lb.update(status="open", dir=dr, entry=L[k + "_in"], sl=L[k + "_sl"], tp=L[k + "_tp"], be=L[k + "_be"],
                              be_done=False, text=f"{'BUY' if dr == 1 else 'SELL'} open from {px(L[k + '_in'])}")
                    send(_lb_head(f"{'BUY' if dr == 1 else 'SELL'} STOP FILLED") +
                         f"Filled at {px(lb['entry'])} ({tfl} candle {t:%H:%M} chart time)\n"
                         f"Delete the {'SELL' if dr == 1 else 'BUY'} STOP now.\n"
                         f"SL {px(lb['sl'])} | TP {px(lb['tp'])} | move SL to entry at {px(lb['be'])}\n" + _lb_foot(tnow))
                    lo_, hi_ = (min(lb["entry"], b_), max(lb["entry"], b_))
                if lb["status"] == "open":
                    dr = lb["dir"]
                    hit_sl = lo_ <= lb["sl"] if dr == 1 else hi_ >= lb["sl"]
                    hit_tp = hi_ >= lb["tp"] if dr == 1 else lo_ <= lb["tp"]
                    if hit_sl or hit_tp:
                        ex = lb["sl"] if hit_sl else lb["tp"]
                        pips = (ex - lb["entry"]) * dr / 0.10
                        what = "TP HIT" if hit_tp and not hit_sl else ("BREAKEVEN" if lb["be_done"] else "SL HIT")
                        lb.update(status="done", text=f"{what.lower()} ({pips:+.0f} pips)")
                        send(_lb_head(what) + f"{'BUY' if dr == 1 else 'SELL'} from {px(lb['entry'])} closed at {px(ex)} "
                             f"({pips:+.0f} pips, ${pips * 0.10:+.2f} per 0.01 lot), {tfl} candle {t:%H:%M}\n"
                             f"Done for today.\n" + _lb_foot(tnow))
                        break
                    if not lb["be_done"] and ((hi_ >= lb["be"]) if dr == 1 else (lo_ <= lb["be"])):
                        lb["be_done"] = True; lb["sl"] = lb["entry"] + dr * 0.10
                        lb["text"] = f"{'BUY' if dr == 1 else 'SELL'} open from {px(lb['entry'])}, SL at breakeven"
                        send(_lb_head("MOVE SL TO ENTRY") +
                             f"Price reached {px(lb['be'])} (1.5R). Move the SL to {px(lb['sl'])} (entry).\n"
                             f"TP stays at {px(lb['tp'])}.\n" + _lb_foot(tnow))
            lb["last_t"] = str(t); lb["done_to"] = str(t + step)
            if lb["status"] == "done":
                break
    if fine is not None and now is not None:
        fc = fine[fine.index + pd.Timedelta(minutes=1) <= now]
        if len(fc) and (now - fc.index[-1]) < pd.Timedelta(minutes=10):
            closed = fc                       # latest price for the reminder / 21:00 messages
    wm = C.get("LB_WARN_MIN", 0)
    if wm and lb["status"] in ("placed", "open") and t_close - pd.Timedelta(minutes=wm) <= cur < t_close and not lb.get("warned"):
        lb["warned"] = True
        price = float(closed["close"].iloc[-1])
        if lb["status"] == "open":
            dr = lb["dir"]; pips = (price - lb["entry"]) * dr / 0.10
            send(_lb_head(f"{wm} MIN TO CLOSE") + f"The {'BUY' if dr == 1 else 'SELL'} from {px(lb['entry'])} is still open "
                 f"(now {px(price)}, about {pips:+.0f} pips).\nClose it at {hc:02d}:00 chart time if TP / SL is not hit before.\n"
                 + _lb_foot(tnow))
        else:
            send(_lb_head(f"{wm} MIN TO CLOSE") + f"Neither stop order has filled yet. Delete both at {hc:02d}:00 chart time "
                 f"if they are still not filled.\n" + _lb_foot(tnow))
    if lb["status"] in ("placed", "open") and cur >= t_close:
        price = float(closed["close"].iloc[-1])
        if lb["status"] == "placed":
            lb.update(status="done", text="no breakout today")
            send(_lb_head("NO BREAKOUT") + f"{hc:02d}:00 chart time: neither order filled. Delete both stop orders.\n"
                 + _lb_foot(tnow))
        else:
            dr = lb["dir"]; pips = (price - lb["entry"]) * dr / 0.10
            lb.update(status="done", text=f"closed at {hc:02d}:00 ({pips:+.0f} pips)")
            send(_lb_head(f"CLOSE AT {hc:02d}:00") + f"Close the {'BUY' if dr == 1 else 'SELL'} now. Price {px(price)}, "
                 f"about {pips:+.0f} pips (${pips * 0.10:+.2f} per 0.01 lot) from entry {px(lb['entry'])}.\n"
                 + _lb_foot(tnow))


#==================================================================
# XAUUSD H1 RSI(2) pullback alerts (same rules as the backtest `rsi2` in research/strategies.py):
#   buy when the H1 close is above the H1 SMA 200 and RSI(2) < 10 (sell: below SMA 200, RSI(2) > 90);
#   SL = 2 x ATR14(H1) from the signal close; exit when an H1 close crosses back over the SMA 5.
#   One signal at a time. Backtest: PF 1.22 on JustMarkets M15 (Jan-Oct 2026), PF 1.05 on GC=F 2 years.
#==================================================================
def _rsi2_frame(closed):
    h1 = closed.resample("1h", label="left", closed="left", origin="start_day").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d = h1.close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    h1["rsi2"] = 100 - 100 / (1 + up / dn)
    h1["sma200"] = h1.close.rolling(200).mean(); h1["sma5"] = h1.close.rolling(5).mean()
    tr = np.maximum(h1.high - h1.low, np.maximum(abs(h1.high - h1.close.shift()), abs(h1.low - h1.close.shift())))
    h1["atr"] = tr.rolling(14).mean()
    return h1


def _rs_head(title):
    return f"FIZY BOT | XAUUSD RSI2 pullback (H1) - {title}\n=============================\n"


def rsi2_step(m15, rs, cur, send=None, fine=None, now=None):
    """Advance the RSI(2) state `rs` with the M15 candles closed before `cur`; send alerts. The SL is
    checked on the closed M1 candles of `fine` before `now` when given (alert within about a minute)."""
    send = send or tg_send
    C = CFG
    closed = m15[m15.index < cur]
    if len(closed) < 4 * 260:
        return
    h1 = _rsi2_frame(closed)
    h1 = h1[h1.index + pd.Timedelta(hours=1) <= cur]          # complete H1 candles only
    if len(h1) < 210:
        return
    last_t = h1.index[-1]
    if not rs.get("last_h1"):                                  # first run: no alerts for the past
        rs.update(last_h1=str(last_t), last_m15=str(closed.index[-1]), pos=None, text="watching")
        return
    pos = rs.get("pos")
    # SL check on the new M1 candles (else M15); `sl_to` = end of the last candle already checked
    if pos:
        sl_to = (pd.Timestamp(rs["sl_to"]) if rs.get("sl_to")
                 else pd.Timestamp(rs.get("last_m15", str(closed.index[0]))) + pd.Timedelta(minutes=15))
        new, step = _fine_closed(fine, now, sl_to)
        if new is None:
            new, step = closed, pd.Timedelta(minutes=15)
        new = new[new.index >= sl_to.floor(step)]
        for t, r in new.iterrows():
            rs["sl_to"] = str(t + step)
            if (pos["dir"] == 1 and r.low <= pos["sl"]) or (pos["dir"] == -1 and r.high >= pos["sl"]):
                pips = (pos["sl"] - pos["entry"]) * pos["dir"] / 0.10
                send(_rs_head("SL HIT") + f"{'BUY' if pos['dir'] == 1 else 'SELL'} from {px(pos['entry'])} stopped at {px(pos['sl'])} "
                     f"({pips:+.0f} pips, ${pips * 0.10:+.2f} per 0.01 lot), M{int(step.total_seconds() // 60)} candle {t:%H:%M}\n"
                     f"=============================\nBroker time: {(now.floor('1min') if now is not None else cur):%Y-%m-%d %H:%M}")
                rs["pos"] = pos = None; rs["text"] = "watching (last trade: SL)"
                break
    rs["last_m15"] = str(closed.index[-1])
    if str(last_t) == rs.get("last_h1"):
        return
    rs["last_h1"] = str(last_t)
    b = h1.iloc[-1]
    if any(np.isnan(b[k]) for k in ("rsi2", "sma200", "sma5", "atr")):
        return
    if pos:
        if (pos["dir"] == 1 and b.close > b.sma5) or (pos["dir"] == -1 and b.close < b.sma5):
            pips = (b.close - pos["entry"]) * pos["dir"] / 0.10
            send(_rs_head("EXIT NOW") + f"H1 candle {last_t:%H:%M} closed {'above' if pos['dir'] == 1 else 'below'} the SMA 5 "
                 f"({px(b.sma5)}).\nClose the {'BUY' if pos['dir'] == 1 else 'SELL'} from {px(pos['entry'])} at market "
                 f"(now {px(b.close)}, about {pips:+.0f} pips).\n=============================\nBroker time: {cur:%Y-%m-%d %H:%M}")
            rs["pos"] = None; rs["text"] = f"watching (last trade closed {pips:+.0f} pips)"
        return
    dr = 0
    if b.close > b.sma200 and b.rsi2 < C["RSI2_LO"]:
        dr = 1
    elif b.close < b.sma200 and b.rsi2 > C["RSI2_HI"]:
        dr = -1
    if not dr:
        return
    sl = b.close - dr * C["RSI2_SL_ATR"] * b.atr
    rs["pos"] = dict(dir=dr, entry=float(b.close), sl=float(sl), t=str(last_t))
    rs["sl_to"] = str(last_t + pd.Timedelta(hours=1))           # SL checks start at the signal candle close
    rs["text"] = f"{'BUY' if dr == 1 else 'SELL'} open from {px(b.close)}, SL {px(sl)}"
    send(_rs_head("BUY NOW" if dr == 1 else "SELL NOW") +
         f"H1 candle {last_t:%H:%M}: close {px(b.close)} {'above' if dr == 1 else 'below'} SMA 200 ({px(b.sma200)}), "
         f"RSI(2) {b.rsi2:.1f}\n"
         f"Entry: market now (about {px(b.close)})\n"
         f"SL: {px(sl)} ({C['RSI2_SL_ATR']:.0f} x ATR, ${abs(b.close - sl):.2f} per 0.01 lot)\n"
         f"Exit: wait for the EXIT alert (H1 close back over the SMA 5, now {px(b.sma5)}), no fixed TP\n"
         f"Backtest: PF 1.22 (JustMarkets 10 months), PF 1.05 (gold futures 2 years): small edge\n"
         f"=============================\nBroker time: {cur:%Y-%m-%d %H:%M}")


#==================================================================
# XAUUSD M5 scalp (RSI(2) pullback on M5, research/m5_scalp.py setup "B"), alerts only:
#   buy when the M5 close is above EMA 200 and RSI(2) < 10 (sell: below, > 90), 08:00-20:00 chart time;
#   SL 2 x ATR14(M5); exit when an M5 close crosses back over the SMA 5, or after 24 candles (2 hours).
#   Test (30 Oct): Deriv 5m 100 days PF 1.00 (+$3), Yahoo GC=F 5m 50 days PF 0.86 (-$110): no proven edge.
#==================================================================
def _m5_head(title):
    return f"FIZY BOT | XAUUSD M5 scalp - {title}\n=============================\n"


def m5_step(m5, sc, cur5, send=None, fine=None, now=None):
    """M5 scalp state `sc`: entries / exits on the closed M5 candles before `cur5`; the SL is also checked
    on the closed M1 candles of `fine` before `now` when given (SL alert within about a minute)."""
    send = send or tg_send
    C = CFG
    d = m5[m5.index < cur5]
    if len(d) < 260:
        return
    c = d.close
    e200 = c.ewm(span=200, adjust=False).mean()
    dl = c.diff(); up = dl.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi2 = 100 - 100 / (1 + up / dn); sma5 = c.rolling(5).mean()
    tr = np.maximum(d.high - d.low, np.maximum(abs(d.high - c.shift()), abs(d.low - c.shift())))
    atr = tr.rolling(14).mean()
    if not sc.get("last"):
        sc.update(last=str(d.index[-1]), pos=None, text="watching"); return
    new = d.index[d.index > pd.Timestamp(sc["last"])]
    s0, s1 = C["M5_SESSION"]
    for t in new:
        b = d.loc[t]; pos = sc.get("pos")
        foot = f"=============================\nBroker time: {t + pd.Timedelta(minutes=5):%Y-%m-%d %H:%M}"
        if not pos and sc.get("cool") and t < pd.Timestamp(sc["cool"]):
            continue                          # the SL was hit (M1 check) inside this candle: no new entry on it
        if pos:
            dr = pos["dir"]
            if not sc.get("sl_to") or pd.Timestamp(sc["sl_to"]) < t + pd.Timedelta(minutes=5):
                sc["sl_to"] = str(t + pd.Timedelta(minutes=5))
            if (dr == 1 and b.low <= pos["sl"]) or (dr == -1 and b.high >= pos["sl"]):
                pips = (pos["sl"] - pos["entry"]) * dr / 0.10
                send(_m5_head("SL HIT") + f"{'BUY' if dr == 1 else 'SELL'} from {px(pos['entry'])} stopped at {px(pos['sl'])} "
                     f"({pips:+.0f} pips, ${pips * 0.10:+.2f} per 0.01 lot)\n" + foot)
                sc["pos"] = None; sc["text"] = "watching (last: SL)"; continue
            pos["bars"] = pos.get("bars", 0) + 1
            cross = (dr == 1 and b.close > sma5[t]) or (dr == -1 and b.close < sma5[t])
            if cross or pos["bars"] >= C["M5_MAX_BARS"]:
                pips = (b.close - pos["entry"]) * dr / 0.10
                why = "M5 close back over the SMA 5" if cross else f"{C['M5_MAX_BARS']} candles (time exit)"
                send(_m5_head("EXIT NOW") + f"{why}. Close the {'BUY' if dr == 1 else 'SELL'} from {px(pos['entry'])} at market "
                     f"(now {px(b.close)}, about {pips:+.0f} pips)\n" + foot)
                sc["pos"] = None; sc["text"] = f"watching (last {pips:+.0f} pips)"
            continue
        if not (s0 <= t.hour < s1) or np.isnan(atr[t]):
            continue
        dr = 1 if (b.close > e200[t] and rsi2[t] < 10) else (-1 if (b.close < e200[t] and rsi2[t] > 90) else 0)
        if not dr:
            continue
        sl = b.close - dr * 2 * atr[t]
        sc["pos"] = dict(dir=dr, entry=float(b.close), sl=float(sl), bars=0)
        sc["sl_to"] = str(t + pd.Timedelta(minutes=5))
        sc["text"] = f"{'BUY' if dr == 1 else 'SELL'} open from {px(b.close)}, SL {px(sl)}"
        send(_m5_head("BUY NOW" if dr == 1 else "SELL NOW") +
             f"M5 candle {t:%H:%M}: close {px(b.close)} {'above' if dr == 1 else 'below'} EMA 200 ({px(e200[t])}), RSI(2) {rsi2[t]:.1f}\n"
             f"Entry: market now (about {px(b.close)})\n"
             f"SL: {px(sl)} (${abs(b.close - sl):.2f} per 0.01 lot)\n"
             f"Exit: wait for EXIT NOW (M5 close back over the SMA 5, or after 2 hours)\n"
             f"Note: this scalp tested about breakeven, use a small lot\n" + foot)
    sc["last"] = str(d.index[-1])
    pos = sc.get("pos")
    if pos:                                   # SL between M5 closes, on the M1 candles
        sl_to = pd.Timestamp(sc["sl_to"]) if sc.get("sl_to") else pd.Timestamp(sc["last"]) + pd.Timedelta(minutes=5)
        fb, step = _fine_closed(fine, now, sl_to)
        if fb is not None:
            dr = pos["dir"]
            for t, r in fb[fb.index >= sl_to.floor(step)].iterrows():
                sc["sl_to"] = str(t + step)
                if (dr == 1 and r.low <= pos["sl"]) or (dr == -1 and r.high >= pos["sl"]):
                    pips = (pos["sl"] - pos["entry"]) * dr / 0.10
                    send(_m5_head("SL HIT") + f"{'BUY' if dr == 1 else 'SELL'} from {px(pos['entry'])} stopped at {px(pos['sl'])} "
                         f"({pips:+.0f} pips, ${pips * 0.10:+.2f} per 0.01 lot), M1 candle {t:%H:%M}\n"
                         f"=============================\nBroker time: {now.floor('1min'):%Y-%m-%d %H:%M}")
                    sc["pos"] = None; sc["text"] = "watching (last: SL)"
                    sc["cool"] = str(t.floor("5min") + pd.Timedelta(minutes=5))
                    break


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
    if not CFG["BBMA_ALERTS"]:
        todo = []
        st["last_status"] = "BBMA alerts off"
    for T in todo:
        sig, status = evaluate_all(m15, T, st)
        print(f"{name}  {T}  {status}")
        zs = st.pop("_zone_sig", None)
        if zs:
            ok = tg_send(message_zone(zs), chart_png(zs, bars=80))
            print("  zone alert sent" if ok else "  zone alert FAILED")
        if sig:
            text = message_retrace(sig) if sig.get("setup") == "retrace" else message(sig)
            ok = tg_send(text, chart_png(sig))
            print("  telegram sent" if ok else "  telegram FAILED")
        st["last_eval"] = str(T)
        st["last_status"] = status
    m1 = None
    if name == "XAUUSD" and CFG.get("M1_CHECKS", True) and (CFG["M5_SCALP"] or CFG["RSI2_ALERTS"] or CFG["LONDON_BREAKOUT"]):
        try:                                  # M1 candles: fills / BE / TP / SL alerts within about a minute
            m1 = fetch_deriv("XAUUSD", need=1000, max_pages=1, granularity=60)
            m1.index = pd.DatetimeIndex([utc_to_broker(x) for x in m1.index])
        except Exception as e:
            print("M1 fetch error (falling back to M5 / M15 checks):", e)
            m1 = None
    if name == "XAUUSD" and CFG["M5_SCALP"]:
        try:
            m5 = fetch_deriv("XAUUSD", need=500, max_pages=1, granularity=300)
            m5.index = pd.DatetimeIndex([utc_to_broker(x) for x in m5.index])
            m5_step(m5, st.setdefault("m5", {}), broker_now.floor("5min"), fine=m1, now=broker_now)
        except Exception as e:
            print("M5 scalp error:", e)
    if name == "XAUUSD" and CFG["RSI2_ALERTS"]:
        try:
            rsi2_step(m15, st.setdefault("rs2", {}), cur, fine=m1, now=broker_now)
        except Exception as e:
            print("RSI2 error:", e)
    if name == "XAUUSD" and CFG["LONDON_BREAKOUT"]:
        try:
            london_step(m15, st.setdefault("lb", {}), cur, fine=m1, now=broker_now)
        except Exception as e:
            print("London breakout error:", e)


def run_live():
    global RUN_START
    RUN_START = datetime.now(timezone.utc)
    state = load_state()
    migrate_broker_tz(state)
    syms = state.setdefault("symbols", {})
    now_myt = datetime.now(MYT)
    broker_now = utc_to_broker(pd.Timestamp.now(tz="UTC"))
    try:
        mt5_daily_dispatch(state, broker_now)
    except Exception as e:
        print("MT5 dispatch error:", e)
    errors = []
    # download every symbol in parallel (several Deriv connections); each symbol is evaluated and
    # alerted as soon as its own data is in, in list order (XAUUSD first)
    from concurrent.futures import ThreadPoolExecutor
    pool = None
    provs = [p.strip().lower() for p in CFG["PROVIDER"].split(",") if p.strip()]
    if provs and provs[0] == "deriv" and CFG["FETCH_WORKERS"] > 1:
        pool = ThreadPoolExecutor(max_workers=CFG["FETCH_WORKERS"])
        for name in scan_list():
            c = _load_cache(name, "deriv")
            ok = c is not None and len(c) >= 3000 and (broker_now - c.index[-1]) < pd.Timedelta(days=6)
            _prefetch[name] = pool.submit(fetch_deriv, name, 700 if ok else 5000)
    for name in scan_list():
        st = syms.setdefault(name, {})
        try:
            scan_symbol(name, st, broker_now)
        except Exception as e:
            print(f"{name} error: {e}")
            errors.append(f"{name}: {e}")
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)
        _prefetch.clear()
    # one-time welcome: confirms Telegram works and shows a chart of the latest past XAUUSD setup
    if not state.get("welcome_sent"):
        ok = tg_send("FIZY BOT cloud scanner is set up.\nScanning " + str(len(scan_list())) +
                     " symbols every 15 minutes (Sunday-Friday). Alerts only, no trades.\n"
                     "'Alive' message every 4 hours (8 am, 12 pm, 4 pm, 8 pm, 12 am, 4 am Malaysia time).")
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
            f.write(f"run (UTC): started {RUN_START:%Y-%m-%d %H:%M:%S}  finished {datetime.now(timezone.utc):%H:%M:%S}"
                    f"  broker time: {broker_now:%Y-%m-%d %H:%M}\n")
            for n in scan_list():
                st = syms.get(n, {})
                la = st.get("last_alert_t")
                f.write(f"{n:8s} {st.get('source', '-'):10s} {st.get('candles', 0):5d}  {st.get('last_status', '-')}"
                        + (f"  [last alert {la}]" if la else "") + "\n")
                if n == "XAUUSD" and st.get("lb", {}).get("text"):
                    f.write(f"XAUUSD London breakout: {st['lb']['text']}\n")
                if n == "XAUUSD" and st.get("rs2", {}).get("text"):
                    f.write(f"XAUUSD RSI2 pullback: {st['rs2']['text']}\n")
                if n == "XAUUSD" and st.get("m5", {}).get("text"):
                    f.write(f"XAUUSD M5 scalp: {st['m5']['text']}\n")
            for e in errors:
                f.write(f"ERROR {e}\n")
            f.write(f"welcome telegram ok: {state.get('welcome_telegram_ok')}  example: {state.get('welcome_example')}\n")
            try:
                me_ok = requests.get(f"https://api.telegram.org/bot{CFG['TG_TOKEN']}/getMe", timeout=15).ok
            except requests.RequestException:
                me_ok = False
            f.write(f"telegram token valid: {me_ok}  |  from GitHub secret: {'yes' if os.environ.get('TG_TOKEN') else 'no'}"
                    f"  |  chat id from secret: {'yes' if os.environ.get('TG_CHAT_ID') else 'no'}\n")
    except OSError:
        pass
    # daily heartbeat
    # heartbeat every 4 hours (8 am, 12 pm, 4 pm, 8 pm, 12 am, 4 am Malaysia time)
    hb_key = f"{now_myt:%Y-%m-%d} {now_myt.hour:02d}"
    if now_myt.hour in CFG["HEARTBEAT_HOURS"] and state.get("heartbeat_slot") != hb_key:
        lines = []
        for n in scan_list():
            s = syms.get(n, {})
            line = f"{n}: {s.get('last_status', '-')}"
            le = s.get("last_eval")
            if le and (broker_now - pd.Timestamp(le)) > pd.Timedelta(minutes=30):
                line += f"  [old status, last checked {pd.Timestamp(le):%d/%m %H:%M} chart time]"
            lines.append(line)
            if n == "XAUUSD" and CFG["LONDON_BREAKOUT"] and s.get("lb", {}).get("text"):
                lines.append(f"XAUUSD London breakout: {s['lb']['text']}")
            if n == "XAUUSD" and CFG["RSI2_ALERTS"] and s.get("rs2", {}).get("text"):
                lines.append(f"XAUUSD RSI2 pullback: {s['rs2']['text']}")
            if n == "XAUUSD" and CFG["M5_SCALP"] and s.get("m5", {}).get("text"):
                lines.append(f"XAUUSD M5 scalp: {s['m5']['text']}")
        msg = f"FIZY BOT is alive (cloud scanner)  |  chart time {broker_now:%H:%M}"
        for line in lines:                 # Telegram limit is 4096 characters: split, never cut
            if len(msg) + 1 + len(line) > 4000:
                tg_send(msg)
                msg = "(continued)"
            msg += "\n" + line
        tg_send(msg)
        state["heartbeat_slot"] = hb_key
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


def run_audit(since="2026-10-23 00:00"):
    """Replay every pair from `since` (broker time) with the current rules, no Telegram: lists each
    setup that should have alerted and the status now (to compare with the live scanner)."""
    out = os.path.join(os.path.dirname(CFG["STATE_FILE"]) or ".", "audit.txt")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    t_since = pd.Timestamp(since)
    lines = [f"audit from {since} (broker time), rules: RT_MOM_LOOKBACK={CFG['RT_MOM_LOOKBACK']}, run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"]
    for name in symbol_list():
        try:
            set_symbol(name)
            m15 = fetch_m15(name)
            n = int((m15.index >= t_since).sum()) + 1
            ts = sorted(t for t in (_csak_candidates(m15, CFG["ENTRY_TF"], n) | _csak_candidates(m15, CFG["ENTRY_TF2"], n))
                        if t >= t_since)
            st, sigs = {}, []
            for T in ts:
                sig, _ = evaluate_all(m15, T, st)
                st.pop("_zone_sig", None)
                if sig:
                    sigs.append(sig)
            _, now_status = evaluate_all(m15, m15.index[-1], st)
            st.pop("_zone_sig", None)
            lines.append(f"{name:8s} {len(sigs)} setup(s) | now: {now_status}")
            for g in sigs:
                extra = (f"retrace {g['touch_t']:%m-%d %H:%M}" if g.get("setup") == "retrace"
                         else f"rej {g['rej_tf']} {g['rej_t']:%m-%d %H:%M}")
                lines.append(f"    {g.get('setup', 'rejection'):9s} {'BUY ' if g['dir'] == 1 else 'SELL'} CSAK {TF_NAME[g['csak_tf']]}"
                             f" {g['csak_t']:%m-%d %H:%M}  alert at {g['time']:%m-%d %H:%M}  {extra}  H4 mom {g['mom_t']:%m-%d %H:%M}")
        except Exception as e:
            lines.append(f"{name:8s} error: {e}")
        print(lines[-1])
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")


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
    ap.add_argument("--audit", help="replay all pairs from this broker time, no Telegram")
    ap.add_argument("--example", action="store_true", help="send the most recent past setup as an example")
    a = ap.parse_args()
    if a.audit:
        run_audit(a.audit)
    elif a.example:
        run_example()
    elif a.test:
        print("ok" if tg_send("FIZY BOT: test message from the cloud scanner") else "failed")
    elif a.csv:
        run_csv(a.csv, a.chart, a.start, a.name)
    else:
        run_live()
