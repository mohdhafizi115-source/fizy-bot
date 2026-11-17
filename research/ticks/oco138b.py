# Round 138b: robustness of the only straddle cells that held in both windows (15:30, 16:00, 09:00 server)
import sys; sys.argv = ["x"]
src = open("oco138.py").read().split("print(f\"last 3 months")[0]; exec(src)
exec(open("oco138.py").read().split("# ---------- 2. Hour-open straddle ----------")[1].split("print(\"== 2.")[0])
print(f"last 3 months {A3:%Y-%m-%d} .. {END:%Y-%m-%d} | previous {A6:%Y-%m-%d} .. {A3:%Y-%m-%d}")
for hh in (15.5, 16.0, 9.0):
    print(f"== {hh} grid K x SL x hold (no TP)")
    for K in (0.5, 1, 2, 3):
        for sl in (2, 3, 4, 6):
            for hold in (15, 30, 60):
                row(f"STR {hh:5.2f} K{K} sl{sl} {hold}m", straddle(hh, K, sl, 0, hold))
print("== fake-minute control around each, K1 sl3 30m and K2 sl4 60m")
for base in (15.5, 16.0, 9.0):
    for dm in (-20, -10, -5, -2, -1, 1, 2, 5, 10, 20):
        hh = base + dm / 60
        row(f"FAKE {base}{dm:+d}m K1 sl3 30m", straddle(hh, 1, 3, 0, 30)); row(f"FAKE {base}{dm:+d}m K2 sl4 60m", straddle(hh, 2, 4, 0, 60))
print("== every 15-min slot 01:30-22:00, K2 sl4 60m (the full fake-time distribution)")
for q in range(6, 88):
    hh = q / 4
    if hh < 1.5: continue
    row(f"SLOT {int(hh):02d}:{int(round((hh%1)*60)):02d} K2 sl4 60m", straddle(hh, 2, 4, 0, 60))
