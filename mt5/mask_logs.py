"""Copy the last lines of the MT5 terminal logs to status/mt5_logs.txt with every 5+ digit number masked
(the account number must never reach the public repo)."""
import glob, os, re
files = glob.glob(r"C:\Program Files\MetaTrader 5\logs\*.log") + glob.glob(r"C:\Program Files\MetaTrader 5\MQL5\Logs\*.log") + glob.glob(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\*\logs\*.log"))
login = os.environ.get("MT5_LOGIN", "").strip()
out = []
for f in sorted(files, key=os.path.getmtime)[-3:]:
    try:
        import shutil, tempfile
        tmp = os.path.join(tempfile.gettempdir(), "mt5log.tmp"); shutil.copyfile(f, tmp)
        raw = open(tmp, "rb").read()
        txt = raw.decode("utf-16-le", errors="ignore") if raw[:2] == b"\xff\xfe" or raw[1:2] == b"\x00" else raw.decode("utf-8", errors="ignore")
    except OSError as e:
        out.append(f"== {os.path.basename(f)}: cannot read ({e.__class__.__name__})"); continue
    lines = [l for l in txt.splitlines() if l.strip()][-40:]
    out.append(f"== {os.path.basename(f)}")
    for l in lines:
        if login:
            l = l.replace(login, "<login>")
        out.append(re.sub(r"\d{5,}", "<num>", l))
os.makedirs("status", exist_ok=True)
open("status/mt5_logs.txt", "w").write("\n".join(out) + "\n")
out.insert(0, f"log files found: {len(files)}"); open("status/mt5_logs.txt", "w").write("\n".join(out) + "\n")
print(f"{len(files)} log files, {len(out)} lines kept")
