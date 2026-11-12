"""Round 83c: run bbma83b.py (funnel + TP 2R) with longer MOM / REJ windows (8/6, 16/12, 32/24, 96/48)."""
import os, sys, subprocess
d = sys.argv[1] if len(sys.argv) > 1 else "m5data"
here = os.path.dirname(os.path.abspath(__file__))
for m, r in ((8, 6), (16, 12), (32, 24), (96, 48)):
    print(f"\n===== MOM window {m} M15 bars ({m * 15 // 60} h), REJ window {r} M5 bars ({r * 5} min) =====", flush=True)
    out = subprocess.run([sys.executable, os.path.join(here, "bbma83b.py"), d], env=dict(os.environ, MOMB=str(m), REJB=str(r)),
                         capture_output=True, text=True).stdout
    print("\n".join(l for l in out.splitlines() if "FUNNEL" in l or "BBMA" in l or "CONTROL" in l or "variant" in l), flush=True)
