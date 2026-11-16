# Round 133: only lists the exported files (the data is used locally for the portfolio stop-out test).
import os, sys
d = sys.argv[1]
for f in sorted(os.listdir(d)):
    print(f, os.path.getsize(os.path.join(d, f)))
