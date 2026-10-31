"""Runs next to the FizyLB EA on the GitHub Windows runner: forwards the EA events
(MQL5/Files/flb_events.txt) to Telegram and stops when the trading day is done or the
time budget of this shift is used up. Writes mt5_shift.txt (done flag, server time) for
the next-shift step. Never prints account numbers, balances or passwords (public logs)."""
import os, sys, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bbma_scanner as S

ap = argparse.ArgumentParser()
ap.add_argument("--dir", required=True)
ap.add_argument("--minutes", type=float, default=340)
a = ap.parse_args()
files = os.path.join(a.dir, "MQL5", "Files")
ev_path, st_path = os.path.join(files, "flb_events.txt"), os.path.join(files, "flb_state.txt")
TITLES = {"ORDERS PLACED": "ORDERS PLACED", "NO TRADE TODAY": "NO TRADE TODAY", "POSITION OPEN": "STOP FILLED",
          "ORDER DELETED": "ORDER DELETED", "SL MOVED TO ENTRY": "SL MOVED TO ENTRY", "TP HIT": "TP HIT", "SL HIT": "SL HIT",
          "BREAKEVEN": "BREAKEVEN", "CLOSED": "CLOSED", "STARTED": "BOT ONLINE", "STOPPED": "STOPPED", "ERROR": "ERROR"}


def send(line):
    parts = [p.strip() for p in line.split("|")]
    when, kind, rest = parts[0], parts[1] if len(parts) > 1 else "", parts[2:]
    title = TITLES.get(kind, kind)
    body = "\n".join(rest)
    msg = (f"FIZY BOT | XAUUSD AUTO TRADE (demo) - {title}\n=============================\n{body}\n"
           f"=============================\nBroker time: {when}")
    ok = S.tg_send(msg)
    print(f"telegram {'ok' if ok else 'FAILED'}: {kind}", flush=True)


def read_lines(path):
    try:
        with open(path, "r", encoding="latin-1") as f:
            return [l.rstrip("\r\n") for l in f if l.strip()]
    except OSError:
        return []


t0, sent, started = time.time(), 0, False
state = ""
while time.time() - t0 < a.minutes * 60:
    lines = read_lines(ev_path)
    for l in lines[sent:]:
        started = started or "| STARTED |" in l or "| STOPPED |" in l
        send(l)
    sent = len(lines)
    st = read_lines(st_path)
    if st:
        state = st[-1]
        p = state.split("|")
        if len(p) >= 4 and p[3].strip() == "1":
            print("trading day done", flush=True)
            break
    if not started and time.time() - t0 > 360:
        S.tg_send("FIZY BOT | XAUUSD AUTO TRADE (demo) - PROBLEM\n=============================\n"
                  "The EA did not start within 6 minutes on GitHub (login / connection problem).\n"
                  "Place today's London breakout orders by hand from the alert.\n=============================")
        started = True                       # say it once
    time.sleep(5)
p = state.split("|") if state else []
done = len(p) >= 4 and p[3].strip() == "1"
with open("mt5_shift.txt", "w") as f:
    f.write(f"{'done' if done else 'open'}\n{p[0] if p else ''}\n")
print(f"shift end: done={done}, state={'|'.join(p[:1] + p[1:3]) if p else 'none'}", flush=True)
