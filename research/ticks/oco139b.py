# Round 139b: union slots (any listed currency releasing at that New York minute), same-minute no-release control, portfolio
import sys; sys.argv = ["x"]
exec(open("oco139.py").read().split("print(f\"last 3 months")[0])
ny_all = D.index.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT").tz_convert("America/New_York")
nyhm = pd.Series(np.asarray(ny_all.strftime("%H:%M")), index=D.index)
def slot(curs, hm):
    m = cal[cal.currency.isin(curs) & (cal.ny.dt.strftime("%H:%M") == hm)]
    rel = sorted(set(m.srv)); days = set(pd.DatetimeIndex(rel).normalize())
    allm = D.index[(nyhm.values == hm) & (wd < 5)]
    non = [x for x in allm if x.normalize() not in days]
    return rel, non
print(f"last 3 months {A3:%Y-%m-%d} .. {END:%Y-%m-%d} | previous {A6:%Y-%m-%d} .. {A3:%Y-%m-%d}")
SL = {}
for lab, curs, hm in (("08:30 NY  USD/CAD", ["USD", "CAD"], "08:30"), ("02:00 NY  EUR/GBP", ["EUR", "GBP"], "02:00"), ("03:00 NY  EUR", ["EUR"], "03:00"),
                      ("04:00 NY  EUR", ["EUR"], "04:00"), ("04:30 NY  GBP", ["GBP"], "04:30"), ("10:00 NY  USD", ["USD"], "10:00"), ("14:00 NY  USD", ["USD"], "14:00"),
                      ("19:30 NY  AUD/JPY", ["AUD", "JPY"], "19:30"), ("21:30 NY  CNY/AUD", ["CNY", "AUD"], "21:30")):
    rel, non = slot(curs, hm); SL[lab] = rel
    for K, sl, hold in ((2, 3, 15), (3, 3, 15), (2, 4, 30)):
        row(f"{lab} release K{K} sl{sl} {hold}m", mk(rel, K, sl, hold))
        if K == 2 and hold == 15: row(f"{lab} NO-release same minute", mk(non, K, sl, hold))
print("== portfolio: one position at a time across slots, K2 sl3 15m")
for combo in (["08:30 NY  USD/CAD", "02:00 NY  EUR/GBP"], ["08:30 NY  USD/CAD", "02:00 NY  EUR/GBP", "03:00 NY  EUR", "04:00 NY  EUR", "04:30 NY  GBP"]):
    tt = sorted(set().union(*[SL[c] for c in combo])); row(" + ".join(c.split()[0] for c in combo), mk(tt, 2, 3, 15)); row("   same, K3 sl3 15m", mk(tt, 3, 3, 15))
    s, d = sim(*mk(tt, 2, 3, 15)); dpl = s.groupby(s.index.normalize()).sum(); top = dpl.sort_values(ascending=False)
    print(f"   K2: {len(s)} trades on {len(dpl)} days ({len(dpl)/ (len(set(D.index.normalize()))) *5:.1f} a week), top 5 days {top.head(5).sum():+.0f} of {dpl.sum():+.0f}; months", " ".join(f"{p}:{v:+.0f}" for p, v in dpl.groupby(dpl.index.to_period('M')).sum().items()))
