"""Runs next to the FizyLB EA (London breakout, NR7, Gotobi, month-end fix, gold auction, volatility breakout, S/R zone alerts) on the
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
ev_paths = [os.path.join(files, n) for n in ("flb_events.txt", "nr7_events.txt", "gtb_events.txt", "gau_events.txt", "wvb_events.txt", "sr_events.txt")]
STATUS_KINDS = ("| STARTED |", "| NR7 ONLINE |", "| GOTOBI ONLINE |", "| MONTHEND ONLINE |", "| AUCTION ONLINE |", "| VOLBO ONLINE |", "| SR ONLINE |")
st_path = os.path.join(files, "flb_state.txt")
TITLES = {"ORDERS PLACED": "ORDERS PLACED", "NO TRADE TODAY": "NO TRADE TODAY", "POSITION OPEN": "STOP FILLED",
          "ORDER DELETED": "ORDER DELETED", "SL MOVED TO ENTRY": "SL MOVED TO ENTRY", "TP HIT": "TP HIT", "SL HIT": "SL HIT",
          "BREAKEVEN": "BREAKEVEN", "CLOSED": "CLOSED", "STARTED": "BOT ONLINE", "STOPPED": "STOPPED", "ERROR": "ERROR"}
# NR7 / GOTOBI / AUCTION kinds ("NR7 FILLED USDJPY.m", "GOTOBI SELL ...", "AUCTION CLOSED ...") are used as the title as they are


LINE = "━━━━━━━━━━━━━━━━━━"
MODS = [  # kind prefix, emoji, title
    ("NR7", "📊", "NR7 BREAKOUT D1"), ("GOTOBI", "🇯🇵", "GOTOBI TOKYO FIX"), ("MONTHEND", "📅", "MONTH-END TOKYO FIX"),
    ("AUCTION", "🏦", "GOLD AUCTION SCALP · XAUUSD"), ("VOLBO", "⚡", "VOLATILITY BREAKOUT · day trade"),
    ("SR ", "🧱", "S/R ZONES · XAUUSD M15 · alerts only"),
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
        return ["🥇 LONDON BREAKOUT · XAUUSD",
                f"▫️ Orders at 08:00 broker ({myt('08:00', 'Europe/Athens')} MYT), close 21:00",
                f"▫️ Lot {lot} · open {opened} · pending {pend}"]
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
                f"▫️ SELL 10:15 → close 10:30 London ({myt('10:15', 'Europe/London')} → {myt('10:30', 'Europe/London')} MYT)",
                f"▫️ Every trading day · Lot {lot} · open {opened}"]
    if kind == "SR ONLINE":
        return ["🧱 S/R ZONES · XAUUSD M15 (alerts only, no trading)",
                f"▫️ Zone map at 01:30, 08:00, 15:00 broker ({myt('01:30', 'Europe/Athens')}, {myt('08:00', 'Europe/Athens')}, "
                f"{myt('15:00', 'Europe/Athens')} MYT)",
                "▫️ Chart alert when the price enters a zone · ideas untested (PF ~0.95)"]
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
    order = {k: i for i, k in enumerate(("STARTED", "NR7 ONLINE", "GOTOBI ONLINE", "MONTHEND ONLINE", "AUCTION ONLINE", "VOLBO ONLINE", "SR ONLINE"))}
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
