"""Print the export's meta.txt (symbol specs incl. swap) and the bar count per file; used for quick spec-only exports."""
import os, sys
DATA = sys.argv[1] if len(sys.argv) > 1 else "m5data"
print(open(os.path.join(DATA, "meta.txt"), encoding="latin-1").read())
