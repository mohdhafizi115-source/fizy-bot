"""Dispatch the next MT5 trading shift when today's trading is not finished
(server time before the close hour on a weekday)."""
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
need = (not done) and t is not None and t.weekday() < 5 and t.hour < 21
print(f"done={done} server={srv} -> next shift: {need}")
if need:
    r = requests.post(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/mt5_trade.yml/dispatches",
                      headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main"}, timeout=30)
    print("dispatch:", r.status_code, r.text[:200])
