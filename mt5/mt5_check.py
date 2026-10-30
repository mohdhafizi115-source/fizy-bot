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
PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
say(f"terminal file exists: {os.path.exists(PATH)}")
login, pw, srv = os.environ.get("MT5_LOGIN", "").strip(), os.environ.get("MT5_PASSWORD", ""), os.environ.get("MT5_SERVER", "").strip()
say(f"secrets set: login {'yes' if login else 'no'}, password {'yes' if pw else 'no'}, server {'yes (' + srv + ')' if srv else 'no'}")
import threading
def watchdog():
    time.sleep(240)
    say("watchdog: initialize did not return in 240 s, giving up")
    os.makedirs("status", exist_ok=True); open("status/mt5_check.txt", "w").write("\n".join(out) + "\n")
    os._exit(2)
threading.Thread(target=watchdog, daemon=True).start()
if mt5:
    t0 = time.time()
    if login and pw and srv:
        ok = mt5.initialize(path=PATH, login=int(login), password=pw, server=srv, timeout=180000, portable=True)
    else:
        ok = mt5.initialize(path=PATH, timeout=180000, portable=True)
    say(f"initialize: {ok} ({time.time() - t0:.0f} s), last_error {mt5.last_error()}")
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
os.makedirs("status", exist_ok=True)
open("status/mt5_check.txt", "w").write("\n".join(out) + "\n")
