"""Check that the MetaTrader 5 terminal runs on a GitHub Windows runner and, when the secrets
MT5_LOGIN / MT5_PASSWORD / MT5_SERVER are set, that it can log in. Read-only: no orders.
Never prints the login number, password or balance (the repo and its logs are public)."""
import os, sys, time
out = []
def say(s):
    print(s, flush=True); out.append(s)
try:
    import MetaTrader5 as mt5
except Exception as e:
    say(f"MetaTrader5 package import failed: {e}"); mt5 = None
PATH = os.environ.get("MT5_PATH") or r"C:\Program Files\MetaTrader 5\terminal64.exe"
say(f"terminal: {os.path.basename(os.path.dirname(PATH))}, exists {os.path.exists(PATH)}")
login, pw, srv = os.environ.get("MT5_LOGIN", "").strip(), os.environ.get("MT5_PASSWORD", ""), os.environ.get("MT5_SERVER", "").strip()
say(f"secrets set: login {'yes' if login else 'no'}, password {'yes' if pw else 'no'}, server {'yes (' + srv + ')' if srv else 'no'}")

def log_tail():
    """Last terminal log lines, with the login and every 5+ digit number masked (public repo)."""
    import glob, re
    files = glob.glob(os.path.join(os.path.dirname(PATH), "logs", "*.log"))
    res = [f"terminal log files: {len(files)}"]
    for f in sorted(files, key=os.path.getmtime)[-2:]:
        res.append(f"== {os.path.basename(f)}")
        try:
            raw = open(f, "rb").read()
            txt = raw.decode("utf-16", errors="ignore") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or raw[1:2] == b"\x00" else raw.decode("utf-8", errors="ignore")
            keep = [x for x in txt.splitlines() if x.strip() and "Cloud Server" not in x]
            for l in keep[-70:]:
                if login:
                    l = l.replace(login, "<login>")
                res.append("  " + re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<ip>", re.sub(r"\d{5,}", "<num>", l.replace("\t", " "))))
        except Exception as e:
            res.append(f"  cannot read {os.path.basename(f)}: {e.__class__.__name__} {e}")
    return res
import threading
def watchdog():
    time.sleep(240)
    say("watchdog: initialize did not return in 240 s, giving up")
    for l in log_tail():
        say(l)
    os.makedirs("status", exist_ok=True); open("status/mt5_check.txt", "w").write("\n".join(out) + "\n")
    os._exit(2)
threading.Thread(target=watchdog, daemon=True).start()
if mt5:
    t0 = time.time()
    ok = mt5.initialize(timeout=60000)                     # attach to the terminal started by the workflow
    say(f"initialize (attach): {ok} ({time.time() - t0:.0f} s), last_error {mt5.last_error()}")
    if not ok:
        t0 = time.time()
        ok = mt5.initialize(path=PATH, portable=True, timeout=120000)
        say(f"initialize (path, portable): {ok} ({time.time() - t0:.0f} s), last_error {mt5.last_error()}")
    if ok and login and pw and srv and (not mt5.account_info() or str(mt5.account_info().login) != login):
        lg = mt5.login(int(login), password=pw, server=srv, timeout=60000)
        say(f"login call: {lg}, last_error {mt5.last_error()}")
    if ok:
        say(f"terminal version: {mt5.version()}")
        ti = mt5.terminal_info()
        if ti:
            say(f"terminal: connected {ti.connected}, algo trading allowed {ti.trade_allowed}, company {ti.company}")
        ai = mt5.account_info()
        if ai:
            say(f"account: server {ai.server}, demo {ai.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO}, trade allowed {ai.trade_allowed}, "
                f"expert trading allowed {ai.trade_expert}, currency {ai.currency}, leverage 1:{ai.leverage}, balance > 0: {ai.balance > 0}")
            for name in ("XAUUSD.m", "XAUUSD"):
                if mt5.symbol_select(name, True):
                    time.sleep(2)
                    si, tk = mt5.symbol_info(name), mt5.symbol_info_tick(name)
                    if si:
                        say(f"symbol {name}: digits {si.digits}, min lot {si.volume_min}, stops level {si.trade_stops_level} points, "
                            f"filling modes {si.filling_mode}, last bid {tk.bid if tk else None}")
                        break
        else:
            say("account: not logged in")
        mt5.shutdown()
for l in log_tail():
    say(l)
os.makedirs("status", exist_ok=True)
open("status/mt5_check.txt", "w").write("\n".join(out) + "\n")
