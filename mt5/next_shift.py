"""Dispatch the next MT5 trading shift: the EA trades 24/7 (RSI2 on BTCUSD at weekends), so the
chain always continues while mt5_trade.txt says "on"."""
import os, sys, datetime, requests
try:
    st = open("mt5_shift.txt").read().split("\n")
except OSError:
    st = ["open", ""]
done, srv = st[0].strip() == "done", st[1].strip()
try:
    t = datetime.datetime.strptime(srv, "%Y.%m.%d %H:%M:%S")
except ValueError:
    t = None
try:
    need = open("mt5_trade.txt").readline().strip().lower() == "on"
except OSError:
    need = False
print(f"done={done} server={srv} -> next shift: {need}")
if need:
    r = requests.post(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/mt5_trade.yml/dispatches",
                      headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main"}, timeout=30)
    print("dispatch:", r.status_code, r.text[:200])
