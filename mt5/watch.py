"""Runs next to the FizyLB EA (London breakout + RSI2 H1) on the GitHub Windows runner: forwards
the EA events (MQL5/Files/flb_events.txt and rsi2_events.txt) to Telegram until the time budget
of this shift is used up (the EA trades 24/7, so the shift never stops early). Writes
mt5_shift.txt (server time) for the next-shift step. Never prints account numbers, balances or
passwords (public logs)."""
import os, sys, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S

ap = argparse.ArgumentParser()
ap.add_argument("--dir", required=True)
ap.add_argument("--minutes", type=float, default=340)
a = ap.parse_args()
files = os.path.join(a.dir, "MQL5", "Files")
ev_paths = [os.path.join(files, "flb_events.txt"), os.path.join(files, "rsi2_events.txt"), os.path.join(files, "nr7_events.txt")]
st_path = os.path.join(files, "flb_state.txt")
TITLES = {"ORDERS PLACED": "ORDERS PLACED", "NO TRADE TODAY": "NO TRADE TODAY", "POSITION OPEN": "STOP FILLED",
          "ORDER DELETED": "ORDER DELETED", "SL MOVED TO ENTRY": "SL MOVED TO ENTRY", "TP HIT": "TP HIT", "SL HIT": "SL HIT",
          "BREAKEVEN": "BREAKEVEN", "CLOSED": "CLOSED", "STARTED": "BOT ONLINE", "STOPPED": "STOPPED", "ERROR": "ERROR"}
# RSI2 kinds ("RSI2 BUY EURUSD.m", "RSI2 EXIT ...", "RSI2 SL HIT ...", "RSI2 ONLINE") are used as the title as they are


def send(line):
    parts = [p.strip() for p in line.split("|")]
    img = next((p[4:].strip() for p in parts if p.startswith("IMG:")), "")
    parts = [p for p in parts if not p.startswith("IMG:")]
    when, kind, rest = parts[0], parts[1] if len(parts) > 1 else "", parts[2:]
    title = TITLES.get(kind, kind)
    head = "RSI2 H1 (demo)" if kind.startswith("RSI2") else ("NR7 BREAKOUT D1 (demo)" if kind.startswith("NR7") else "LONDON BREAKOUT XAUUSD (demo)")
    body = "\n".join(rest)
    msg = (f"FIZY BOT | {head} - {title}\n=============================\n{body}\n"
           f"=============================\nBroker time: {when}")
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


def send_status(lines):
    """One status message a day: London breakout + RSI2 start lines merged."""
    day = lines[0].split("|")[0].strip().split(" ")[0]
    if online_sent_today(day):
        print("status message already sent today", flush=True); return
    body = []
    for l in lines:
        p = [x.strip() for x in l.split("|") if not x.strip().startswith("IMG:")]
        body.append(("London breakout: " if "STARTED" in p[1] else ("RSI2 H1: " if "RSI2" in p[1] else "NR7 D1: ")) + " | ".join(p[2:]))
    msg = ("FIZY BOT | AUTO TRADE (demo) - BOT ONLINE (daily status)\n=============================\n" + "\n".join(body) +
           f"\n=============================\nBroker time: {lines[0].split('|')[0].strip()}")
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
            if not status_done and ("| STARTED |" in l or "| RSI2 ONLINE |" in l or "| NR7 ONLINE |" in l) and "IMG:" not in l:
                status_lines.append(l)             # merged into one daily status message below
                continue
            send(l)
        sent[path] = len(lines)
    if not status_done and (len(status_lines) >= 3 or (status_lines and time.time() - t0 > 120)):
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
