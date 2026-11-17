# Round 138c: the 08:30 New York straddle on the New York clock; news / no-news days; concentration; by month
import sys; sys.argv = ["x"]
exec(open("oco138.py").read().split("print(f\"last 3 months")[0])
exec(open("oco138.py").read().split("# ---------- 2. Hour-open straddle ----------")[1].split("print(\"== 2.")[0])
ny = D.index.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT").tz_convert("America/New_York")
nyh = np.asarray(ny.hour) + np.asarray(ny.minute) / 60.0
def nymins(h): return np.flatnonzero((np.abs(nyh - h) < 1e-6) & (wd < 5))
cal = pd.read_csv("/home/claude/fizy-bot/data/calendar.csv"); cal = cal[(cal.currency == "USD") & (cal.importance >= 2)]
cu = pd.to_datetime(cal.time - 7200, unit="s").dt.tz_localize("UTC").dt.tz_convert("America/New_York")
hi = pd.to_datetime(pd.read_csv("/home/claude/fizy-bot/data/calendar.csv").query("currency=='USD' and importance==3").time - 7200, unit="s").dt.tz_localize("UTC").dt.tz_convert("America/New_York")
d830 = set(cu[(cu.dt.hour == 8) & (cu.dt.minute == 30)].dt.date); h830 = set(hi[(hi.dt.hour == 8) & (hi.dt.minute == 30)].dt.date)
i0 = nymins(8.5); days = np.array([x.date() for x in ny[i0]])
print(f"last 3 months {A3:%Y-%m-%d} .. {END:%Y-%m-%d} | previous {A6:%Y-%m-%d} .. {A3:%Y-%m-%d}; {len(i0)} days at 08:30 NY, of which {sum(d in d830 for d in days)} with a USD medium/high release at 08:30, {sum(d in h830 for d in days)} high")
for K, sl, hold in ((3, 3, 15), (2, 4, 30), (0.5, 3, 30), (1, 4, 30), (3, 2, 30)):
    row(f"NY 08:30 K{K} sl{sl} {hold}m (server 15:30 rule)", straddle(15.5, K, sl, 0, hold))
    row(f"NY 08:30 K{K} sl{sl} {hold}m NY clock", straddle(0, K, sl, 0, hold, mins=i0))
    m = np.array([d in d830 for d in days]); row(f"   release days only", straddle(0, K, sl, 0, hold, mins=i0[m])); row(f"   no-release days", straddle(0, K, sl, 0, hold, mins=i0[~m]))
    mh = np.array([d in h830 for d in days]); row(f"   HIGH-impact days only", straddle(0, K, sl, 0, hold, mins=i0[mh])); row(f"   no high-impact", straddle(0, K, sl, 0, hold, mins=i0[~mh]))
for hh in (8.0, 8.25, 8.4, 8.75, 9.0, 9.5, 10.0):
    row(f"NY {int(hh):02d}:{int(round(hh%1*60)):02d} K3 sl3 15m (NY clock control)", straddle(0, 3, 3, 0, 15, mins=nymins(hh)))
s, dd = sim(*straddle(0, 3, 3, 0, 15, mins=i0)); dpl = s.groupby(s.index.normalize()).sum()
print("K3 sl3 15m by month:", " ".join(f"{p}:{v:+.0f}({n})" for (p, v), n in zip(dpl.groupby(dpl.index.to_period('M')).sum().items(), dpl.groupby(dpl.index.to_period('M')).size())))
top = dpl.sort_values(ascending=False); print(f"days {len(dpl)}, +{(dpl>0).sum()} / -{(dpl<0).sum()}, total {dpl.sum():+.0f}, top 5 days {top.head(5).sum():+.0f} ({', '.join(f'{d:%m-%d} {v:+.0f}' for d, v in top.head(5).items())}), without top 5 {top.iloc[5:].sum():+.0f}; worst 5 {', '.join(f'{d:%m-%d} {v:+.0f}' for d, v in top.tail(5).items())}")
print(f"buys {pf(s[dd==1]):.2f} ({(dd==1).sum()}, {s[dd==1].sum():+.0f}) / sells {pf(s[dd==-1]):.2f} ({(dd==-1).sum()}, {s[dd==-1].sum():+.0f})")
