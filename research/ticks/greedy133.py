exec(open("port133.py").read().split("ALLM = sorted")[0])
ALLM = sorted(set(G["mod"]) | set(Z["mod"]))
hi = end + pd.Timedelta(minutes=1)
def full(mods): return curve(mods, a6, hi)
print("6 months together (18 May - 16 Nov), worst peak-to-trough drop incl. floating (any start date):")
for m in ALLM:
    r = full([m]); print(f"  {m:10s} n {r['n']:5d} net {r['net']:+6.0f} maxDD {r['dd']:+5.0f} worst day {r['worst']:+5.0f}")
for lim in (-60, -80, -100):
    cur = []; print(f"\nGREEDY: add the module that adds the most money while the 6-month max drawdown stays above ${lim}")
    while True:
        best = None
        for m in ALLM:
            if m in cur: continue
            r = full(cur + [m])
            if r["dd"] >= lim and (best is None or r["net"] > best[1]["net"]): best = (m, r)
        if best is None: break
        cur.append(best[0]); r = best[1]
        print(f"  + {best[0]:10s} -> {len(cur):2d} modules, {r['n']:5d} trades, net {r['net']:+6.0f}, maxDD {r['dd']:+5.0f}, worst day {r['worst']:+5.0f}")
    print("  left out:", [m for m in ALLM if m not in cur])
r = full(ALLM); print(f"\nALL LIVE 6 months: net {r['net']:+.0f}, maxDD {r['dd']:+.0f}, worst day {r['worst']:+.0f}")
