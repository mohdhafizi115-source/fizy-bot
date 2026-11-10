"""Runs next to the FizyLB EA (London breakout, NR7, Gotobi, month-end fix, gold auction, volatility breakout, USDJPY day trades, S/R zone alerts) on the
GitHub Windows runner: forwards the EA events (MQL5/Files/*_events.txt) to Telegram, one readable block per item, until the time budget
of this shift is used up (the EA trades 24/7, so the shift never stops early). Writes
mt5_shift.txt (server time) for the next-shift step. Never prints account numbers, balances or
passwords (public logs)."""
import os, sys, time, argparse, re
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S

ap = argparse.ArgumentParser()
ap.add_argument("--dir", required=True)
ap.add_argument("--minutes", type=float, default=340)
a = ap.parse_args()
# keep shift changes away from the Tokyo fix (09:55 JST = 00:55 UTC, Gotobi entries): a shift that would end
# between 00:25 and 01:05 UTC ends at 00:20 UTC instead, so the next shift is trading by 00:55
import datetime as _dt
_end = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=a.minutes)
_m = _end.hour * 60 + _end.minute
if 25 <= _m <= 65:
    a.minutes -= (_m - 20)
    print(f"shift shortened by {_m - 20} min to keep the change away from the Tokyo fix", flush=True)
files = os.path.join(a.dir, "MQL5", "Files")
ev_paths = [os.path.join(files, n) for n in ("flb_events.txt", "nr7_events.txt", "gtb_events.txt", "gau_events.txt", "wvb_events.txt", "sr_events.txt", "dtj_events.txt", "kumo_events.txt", "tk_events.txt", "spk_events.txt", "leg_events.txt", "ha_events.txt", "klt_events.txt")]
# Only the modules that are switched on announce themselves, so only those may be listed here: the daily status waits
# for every kind in this tuple and otherwise falls back to a 120 s timeout, which truncates it. Since 5 Nov the owner
# keeps six modules, so NR7, VOLBO, PDHL, NYCONT (switched off) and SR (alerts off since 2 Nov) are out of the list.
STATUS_KINDS = ("| STARTED |", "| GOTOBI ONLINE |", "| MONTHEND ONLINE |", "| AUCTION ONLINE |", "| KUMO ONLINE |", "| LEG ONLINE |", "| SPIKE ONLINE |", "| KELT ONLINE |")
st_path = os.path.join(files, "flb_state.txt")
TITLES = {"ORDERS PLACED": "ORDERS PLACED", "NO TRADE TODAY": "NO TRADE TODAY", "POSITION OPEN": "STOP FILLED",
          "ORDER DELETED": "ORDER DELETED", "SL MOVED TO ENTRY": "SL MOVED TO ENTRY", "TP HIT": "TP HIT", "SL HIT": "SL HIT",
          "BREAKEVEN": "BREAKEVEN", "CLOSED": "CLOSED", "STARTED": "BOT ONLINE", "STOPPED": "STOPPED", "ERROR": "ERROR"}
# NR7 / GOTOBI / AUCTION kinds ("NR7 FILLED USDJPY.m", "GOTOBI SELL ...", "AUCTION CLOSED ...") are used as the title as they are


LINE = "━━━━━━━━━━━━━━━━━━"
MODS = [  # kind prefix, emoji, title
    ("NR7", "📊", "NR7 BREAKOUT D1"), ("GOTOBI", "🇯🇵", "GOTOBI TOKYO FIX"), ("MONTHEND", "📅", "MONTH-END TOKYO FIX"),
    ("AUCTION", "🏦", "GOLD AUCTION SCALP · XAUUSD"), ("VOLBO", "⚡", "VOLATILITY BREAKOUT · day trade"),
    ("PDHL", "📏", "PREVIOUS-DAY BREAKOUT · USDJPY"), ("NYCONT", "🗽", "NEW YORK CONTINUATION · USDJPY"),
    ("KUMO", "☁️", "ICHIMOKU CLOUD BREAKOUT · XAUUSD H1"),
    ("TK ", "🌤️", "ICHIMOKU TK CROSS · XAUUSD H1 + M15 · day trade"),
    ("SPIKE", "⚡", "M1 SPIKE FADE · XAUUSD · scalp"),
    ("KELT", "🎯", "M1 KELTNER RE-ENTRY · XAUUSD · scalp"),
    ("LEG", "🌊", "M1 LEG FADE · XAUUSD · no SL"),
    ("HA ", "🕯️", "M1 HEIKIN ASHI · XAUUSD · TP 1:1"),
    ("DAILY TARGET", "🎯", "DAILY TARGET · all modules"),
    ("SR ", "🧱", "S/R ZONES · XAUUSD M15 · alerts only"),
    ("STARTED", "🤖", "FIZY BOT · all modules"), ("STOPPED", "🤖", "FIZY BOT · all modules"),
    ("CLEANUP", "🧹", "SWITCHED-OFF MODULE · cleanup"),
]
BULLETS = (("Idea ", "💡 "), ("If an M15 bar closes", "↩️ "), ("Not a tested edge", "⚠️ "), ("Bias:", "🧭 "),
           ("Resistance:", "🔴 "), ("Next resistance:", "🔴 "), ("Support:", "🟢 "), ("Next support:", "🟢 "))


def module_of(kind):
    for pre, emo, name in MODS:
        if kind.startswith(pre):
            return emo, name
    return "🥇", "LONDON BREAKOUT · XAUUSD"


def clean(t):
    """XAUUSD.m -> XAUUSD, arrows, no doubled spaces"""
    t = re.sub(r"\b([A-Z]{6})\.m\b", r"\1", t)
    return t.replace(" -> ", " → ").replace("  ", " ").strip()


def myt(hhmm, tz):
    """a clock time in a market's time zone, today -> Malaysia time"""
    h, m = (int(x) for x in hhmm.split(":"))
    z = ZoneInfo(tz)
    d = _dt.datetime.now(z).date()
    return _dt.datetime(d.year, d.month, d.day, h, m, tzinfo=z).astimezone(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%H:%M")


def icon_for(kind, text):
    if kind.startswith("SR "):
        return "🗺️" if "MAP" in kind else "🔔"
    if "ERROR" in kind or "STOPPED" in kind:
        return "⚠️"
    m = re.search(r"profit \$(-?[\d.]+)", text)
    if m:
        return "🟢" if float(m.group(1)) >= 0 else "🔴"
    if any(k in kind for k in ("SKIPPED", "NO TRADE", "DELETED")):
        return "⏸️"
    if any(k in kind for k in ("FILLED", "POSITION OPEN", "SELL", "BUY")):
        return "🚀"
    return "📌"


def bullet(x):
    for start, emo in BULLETS:
        if x.startswith(start):
            return emo + x
    return "• " + x


def send(line):
    parts = [p.strip() for p in line.split("|")]
    img = next((p[4:].strip() for p in parts if p.startswith("IMG:")), "")
    parts = [p for p in parts if not p.startswith("IMG:")]
    when, kind, rest = parts[0], parts[1] if len(parts) > 1 else "", parts[2:]
    title = clean(TITLES.get(kind, kind))
    for pre, _, _ in MODS:                            # "VOLBO ORDERS PLACED USDJPY" -> "ORDERS PLACED · USDJPY"
        pre = pre.strip()
        if title.startswith(pre + " "):
            title = title[len(pre) + 1:]
    w = title.split(" ")
    if len(w) > 1 and re.fullmatch(r"[A-Z]{6}", w[-1]):
        title = " ".join(w[:-1]) + " · " + w[-1]
    emo, name = module_of(kind)
    body = "\n".join(bullet(clean(x)) for x in rest if x)
    t_myt = myt(when[-5:], "Europe/Athens") if re.search(r"\d\d:\d\d$", when) else "-"
    msg = f"{emo} {name} (demo)\n{icon_for(kind, line)} {title}\n{LINE}\n{body}\n{LINE}\n🕒 Broker {when} · MYT {t_myt}"
    png = None
    if img and "/" not in img and "\\" not in img:
        path = os.path.join(files, img)
        for _ in range(10):                          # the EA writes the PNG just before the event line
            if os.path.exists(path) and os.path.getsize(path) > 0:
                png = open(path, "rb").read(); break
            time.sleep(0.5)
    ok = S.tg_send(msg, png)
    print(f"telegram {'ok' if ok else 'FAILED'}: {kind}", flush=True)


def read_lines(path):
    try:
        with open(path, "r", encoding="latin-1") as f:
            return [l.rstrip("\r\n") for l in f if l.strip()]
    except OSError:
        return []


ONLINE_FILE = os.path.join(os.path.dirname(__file__), "..", "status", "mt5_online.txt")   # date of the last status message


def online_sent_today(day):
    try:
        return open(ONLINE_FILE).read().strip() == day
    except OSError:
        return False


def _num(rx, t, default="-"):
    m = re.search(rx, t)
    return m.group(1) if m else default


def status_block(kind, text):
    """one readable block per module for the daily status message"""
    t = clean(text)
    lot = _num(r"lot ([\d.]+)", t)
    opened = _num(r"(\d+) open", t, "0")
    pend = _num(r"(\d+) pending", t, "0")
    nxt_g = _num(r"next Gotobi day ([\d.]+)", t)
    nxt_m = _num(r"next ([\d.]+)", t)
    if kind == "STARTED":
        # Since 5 Nov the owner keeps six modules; the breakout ones (London here, NR7, Williams, both USDJPY
        # day trades) are switched off in the EA, so this block reports the shell, not the London breakout.
        return ["🤖 FIZY BOT · EA shell",
                "▫️ OFF: breakouts (London · NR7 · Williams · USDJPY) · TK cross · M1 Heikin Ashi",
                "🎯 Daily target $25 closed profit, then no new trades until 06:00 MYT",
                f"▫️ Open {opened} · pending {pend}"]
    if kind == "NR7 ONLINE":
        syms = _num(r"\(([A-Z,]+)\)", t).replace(",", " · ")
        return ["📊 NR7 BREAKOUT · D1", f"▫️ {syms}", f"▫️ Checks every new day ({myt('00:00', 'Europe/Athens')} MYT)",
                f"▫️ Lot {lot} · open {opened}"]
    if kind == "GOTOBI ONLINE":
        syms = t.split(":")[0].replace(", ", " · ")
        return ["🇯🇵 GOTOBI TOKYO FIX", f"▫️ SELL {syms}",
                f"▫️ 09:55 → 10:15 JST ({myt('09:55', 'Asia/Tokyo')} → {myt('10:15', 'Asia/Tokyo')} MYT)",
                f"▫️ Next Gotobi day: {nxt_g}", f"▫️ Lot {lot} · open {opened}"]
    if kind == "MONTHEND ONLINE":
        trades = _num(r"\): (.+?), SL", t).replace(", ", " · ")
        return ["📅 MONTH-END TOKYO FIX", f"▫️ {trades}",
                f"▫️ 09:40 → 09:55 JST ({myt('09:40', 'Asia/Tokyo')} → {myt('09:55', 'Asia/Tokyo')} MYT), last business day",
                f"▫️ Next: {nxt_m} · Lot {lot}"]
    if kind == "AUCTION ONLINE":
        return ["🏦 GOLD AUCTION SCALP · XAUUSD",
                f"▫️ SELL 10:15 London ({myt('10:15', 'Europe/London')} MYT) before the LBMA auction",
                f"▫️ M1 trailing stop from 10:30, hard exit 10:45 ({myt('10:45', 'Europe/London')} MYT)",
                f"▫️ Every trading day · Lot {lot} · open {opened}"]
    if kind == "PDHL ONLINE":
        return ["📏 PREVIOUS-DAY BREAKOUT · USDJPY",
                f"▫️ From 02:00 broker ({myt('02:00', 'Europe/Athens')} MYT): stops at yesterday's high / low, TP 2R",
                f"▫️ Close 22:30 broker ({myt('22:30', 'Europe/Athens')} MYT) · Lot {lot}"]
    if kind == "NYCONT ONLINE":
        return ["🗽 NEW YORK CONTINUATION · USDJPY",
                f"▫️ 15:30 broker ({myt('15:30', 'Europe/Athens')} MYT): follow the 09:00-15:30 move",
                f"▫️ Close 22:00 broker ({myt('22:00', 'Europe/Athens')} MYT) · Lot {lot} · open {opened}"]
    if kind == "KUMO ONLINE":
        return ["☁️ ICHIMOKU CLOUD BREAKOUT · XAUUSD H1",
                "▫️ Any hour 01:30-22:00 broker: H1 close breaks out of the cloud",
                f"▫️ Exit: close back inside the cloud or 48 h · Lot {lot} · open {opened}"]
    if kind == "TK ONLINE":
        return ["🌤️ ICHIMOKU TK CROSS · XAUUSD H1 + M15 · day trade",
                f"▫️ bars 01:30-21:00 broker ({myt('02:00', 'Europe/Athens')}-{myt('20:00', 'Europe/Athens')} MYT): Tenkan crosses Kijun beyond the cloud",
                f"▫️ Exit: opposite cross or 23:00 broker ({myt('23:00', 'Europe/Athens')} MYT) · Lot {lot} · open {opened}"]
    if kind == "SPIKE ONLINE":
        return ["⚡ M1 SPIKE FADE · XAUUSD · scalp",
                "▫️ BUY right after a down M1 bar of 2x ATR when ATR >= 8x the spread",
                f"▫️ SL 0.2 ATR under the spike, no TP, SL to entry after +1 ATR, out after 45 min · Lot {lot} · open {opened}"]
    if kind == "KELT ONLINE":
        return ["🎯 M1 KELTNER RE-ENTRY · XAUUSD · scalp",
                "▫️ BUY when a bar closes back above EMA 20 - 3 ATR after a close below it, ATR >= 8x the spread",
                f"▫️ SL 0.2 ATR under the bar, no TP, SL to entry after +30 pips, out after 45 min · Lot {lot} · open {opened}"]
    if kind == "LEG ONLINE":
        return ["🌊 M1 LEG FADE · XAUUSD · no SL (owner's rule)",
                "▫️ A 0.10% leg 20 candles old is faded if its peak / trough is $5+ beyond EMA 50; +1 entry every 0.10% further, max 5, lots 1/1/2/2/3",
                f"▫️ TP at the 50% fib of the leg or EMA 50, whichever first; no SL, no time exit · Lot {lot} · open {opened}"]
    if kind == "HA ONLINE":
        return ["🕯️ M1 HEIKIN ASHI · XAUUSD (owner's rule)",
                "▫️ EMA 10/30 aligned + HA indecision, then HA with no lower (upper) shadow + Stoch 14,3,3 not OB (OS)",
                f"▫️ SL at the 10-bar swing, TP 1:1, flat 23:45 broker · Lot {lot} · open {opened}"]
    if kind == "SR ONLINE":
        return ["🧱 S/R ZONES · XAUUSD M15 (alerts only, no trading)",
                f"▫️ Zone map at 01:30, 08:00, 15:00 broker ({myt('01:30', 'Europe/Athens')}, {myt('08:00', 'Europe/Athens')}, "
                f"{myt('15:00', 'Europe/Athens')} MYT)",
                "▫️ 2 nearest zones above and below · chart when the price enters one · ideas untested (PF < 1)"]
    if kind == "VOLBO ONLINE":
        syms = t.split(":")[0].replace(", ", " · ")
        return ["⚡ VOLATILITY BREAKOUT · day trade", f"▫️ {syms}",
                f"▫️ Orders at 01:30 broker ({myt('01:30', 'Europe/Athens')} MYT), close 22:30 broker ({myt('22:30', 'Europe/Athens')} MYT)",
                f"▫️ Lot {lot} · open {opened}"]
    return [f"• {kind}: {t}"]


def send_status(lines):
    """One status message a day: one block per module."""
    day = lines[0].split("|")[0].strip().split(" ")[0]
    if online_sent_today(day):
        print("status message already sent today", flush=True); return
    order = {k: i for i, k in enumerate(("STARTED", "GOTOBI ONLINE", "MONTHEND ONLINE", "AUCTION ONLINE", "KUMO ONLINE", "LEG ONLINE", "SPIKE ONLINE", "KELT ONLINE"))}
    blocks = []
    for l in sorted(lines, key=lambda x: order.get(x.split("|")[1].strip(), 99)):
        p = [x.strip() for x in l.split("|") if not x.strip().startswith("IMG:")]
        blocks.append("\n".join(status_block(p[1], " | ".join(p[2:]))))
    when = lines[0].split("|")[0].strip()
    msg = (f"🤖 FIZY BOT · AUTO TRADE (demo)\n✅ BOT ONLINE · daily status\n{LINE}\n" + f"\n{LINE}\n".join(blocks) +
           f"\n{LINE}\n🕒 Broker {when} · MYT {myt(when[-5:], 'Europe/Athens')}")
    ok = S.tg_send(msg)
    print(f"telegram {'ok' if ok else 'FAILED'}: daily status", flush=True)
    if ok:
        os.makedirs(os.path.dirname(ONLINE_FILE), exist_ok=True)
        open(ONLINE_FILE, "w").write(day + "\n")


t0, started = time.time(), False
sent = {p: 0 for p in ev_paths}
state = ""
status_lines, status_done = [], False
while time.time() - t0 < a.minutes * 60:
    for path in ev_paths:
        lines = read_lines(path)
        for l in lines[sent[path]:]:
            started = started or "| STARTED |" in l or "| STOPPED |" in l
            if not status_done and any(k in l for k in STATUS_KINDS) and "IMG:" not in l:
                status_lines.append(l)             # merged into one daily status message below
                continue
            send(l)
        sent[path] = len(lines)
    if not status_done and (len(status_lines) >= len(STATUS_KINDS) or (status_lines and time.time() - t0 > 120)):
        send_status(status_lines); status_done = True
    st = read_lines(st_path)
    if st:
        state = st[-1]
    if not started and time.time() - t0 > 360:
        S.tg_send("FIZY BOT | AUTO TRADE (demo) - PROBLEM\n=============================\n"
                  "The EA did not start within 6 minutes on GitHub (login / connection problem).\n"
                  "The next shift will try again.\n=============================")
        started = True                       # say it once
    time.sleep(5)
p = state.split("|") if state else []
done = len(p) >= 4 and p[3].strip() == "1"
with open("mt5_shift.txt", "w") as f:
    f.write(f"{'done' if done else 'open'}\n{p[0] if p else ''}\n")
print(f"shift end: done={done}, state={'|'.join(p[:1] + p[1:3]) if p else 'none'}", flush=True)
