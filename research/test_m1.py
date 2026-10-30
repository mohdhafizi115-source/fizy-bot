"""Replay today's (30 Oct 2026) XAUUSD London breakout minute by minute with the new M1 checks, and
compare with the old M15-only checks: when would each alert have been sent? Also runs the RSI2 and
M5 scalp steps with M1 data once to check they do not crash."""
import os, sys, traceback
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import bbma_scanner_new as S
out = []
def log(*a):
    out.append(" ".join(str(x) for x in a)); print(*a)
try:
    import tempfile, json
    tmp = tempfile.mkdtemp()
    old_sf = S.CFG["STATE_FILE"]; S.CFG["STATE_FILE"] = os.path.join(tmp, "state.json")
    os.makedirs(os.path.join(tmp, "candles")); open(os.path.join(tmp, "candles", "XAUUSD_deriv.csv"), "w").write("x")
    st = {"symbols": {"XAUUSD": {"last_eval": "2026-10-30 16:45:00", "lb": {"day": "2026-10-30", "last_t": "2026-10-30 16:30:00"},
          "rs2": {"last_h1": "2026-10-30 15:00:00", "pos": {"t": "2026-10-30 15:00:00"}}, "m5": {"last": "2026-10-30 16:50:00"}}}}
    S.migrate_broker_tz(st)
    log("migration:", json.dumps(st["symbols"]["XAUUSD"]), "| rule", st.get("broker_tz"),
        "| cache left:", os.path.exists(os.path.join(tmp, "candles", "XAUUSD_deriv.csv")))
    S.migrate_broker_tz(st); log("second call keeps:", st["symbols"]["XAUUSD"]["m5"]["last"])
    S.CFG["STATE_FILE"] = old_sf
    S.set_symbol("XAUUSD")
    m15 = S.fetch_m15("XAUUSD")
    m1 = S.fetch_deriv("XAUUSD", need=1000, max_pages=1, granularity=60)
    m1.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in m1.index])
    m5 = S.fetch_deriv("XAUUSD", need=500, max_pages=1, granularity=300)
    m5.index = pd.DatetimeIndex([S.utc_to_broker(x) for x in m5.index])
    now_b = S.utc_to_broker(pd.Timestamp.now(tz="UTC"))
    log(f"M15 {len(m15)} to {m15.index[-1]} | M1 {len(m1)} {m1.index[0]} to {m1.index[-1]} | M5 {len(m5)} | now {now_b}")
    day = now_b.normalize()
    for mode in ("old (M15 only, scan every 5 min)", "new (M1 checks, scan every 1 min)"):
        new = mode.startswith("new")
        lb = {}
        stepm = 1 if new else 5
        t = day + pd.Timedelta(hours=8)
        log(f"\n=== {mode}")
        while t <= min(now_b, day + pd.Timedelta(hours=21, minutes=1)):
            now = t + pd.Timedelta(seconds=1)
            cur = now.floor("15min")
            m15c = m15[m15.index <= cur]
            sent = []
            S.london_step(m15c, lb, cur, send=lambda text, png=None: sent.append(text),
                          fine=m1 if new else None, now=now if new else None)
            for x in sent:
                lines = x.splitlines()
                log(f"[sent {now:%H:%M:%S}] {lines[0]} | " + " / ".join(lines[2:-2]))
            t += pd.Timedelta(minutes=stepm)
        log(f"final state: {lb.get('status')} - {lb.get('text')}")
    # RSI2 + M5 scalp smoke test (with a fake open position so the M1 SL path runs)
    rs = {}
    S.rsi2_step(m15[m15.index <= now_b.floor('15min')], rs, now_b.floor("15min"), send=lambda *a, **k: None, fine=m1, now=now_b)
    rs["pos"] = dict(dir=1, entry=float(m1.close.iloc[-1]), sl=float(m1.low.iloc[-200:].min()) + 0.5, t="x")
    rs["sl_to"] = str(m1.index[-200])
    sent = []
    S.rsi2_step(m15[m15.index <= now_b.floor('15min')], rs, now_b.floor("15min"), send=lambda text, png=None: sent.append(text), fine=m1, now=now_b)
    log("\nRSI2 M1 SL test:", sent[0].splitlines()[2] if sent else "no SL alert (unexpected)", "| state:", rs.get("text"), rs.get("sl_to"))
    sc = {}
    S.m5_step(m5, sc, now_b.floor("5min"), send=lambda *a, **k: None, fine=m1, now=now_b)
    sc["pos"] = dict(dir=-1, entry=float(m1.close.iloc[-1]), sl=float(m1.high.iloc[-30:].max()) - 0.5, bars=0)
    sc["sl_to"] = str(m1.index[-30])
    sent = []
    S.m5_step(m5, sc, now_b.floor("5min"), send=lambda text, png=None: sent.append(text), fine=m1, now=now_b)
    log("M5 scalp M1 SL test:", sent[0].splitlines()[2] if sent else "no SL alert (unexpected)", "| cool:", sc.get("cool"))
except Exception:
    log(traceback.format_exc())
os.makedirs("status", exist_ok=True)
open("status/research.txt", "w").write("\n".join(out) + "\n")
