# Round 139: news straddles at EVERY calendar release time (currency x New York clock minute), on real ticks.
# OCO placed 2 s before the release minute at the previous M1 close +/- K (spread added to the buy side), SL $sl, out after hold min.
import sys; sys.argv = ["x"]
exec(open("oco138.py").read().split("print(f\"last 3 months")[0])
cal = pd.read_csv("/home/claude/fizy-bot/data/calendar.csv"); cal = cal[cal.importance >= 2]
cal["utc"] = pd.to_datetime(cal.time - 7200, unit="s").dt.tz_localize("UTC")
cal["srv"] = cal.utc.dt.tz_convert("Europe/Athens").dt.tz_localize(None); cal["ny"] = cal.utc.dt.tz_convert("America/New_York")
cal = cal[(cal.srv >= D.index[0] + pd.Timedelta(hours=1)) & (cal.srv <= D.index[-1]) & (cal.srv.dt.dayofweek < 5)]
cal["key"] = cal.currency + " " + cal.ny.dt.strftime("%H:%M") + " NY"
ev = cal.groupby(["key", "srv"]).importance.max().reset_index()
def mk(srvtimes, K, sl, hold, exp=6):
    i = D.index.get_indexer(pd.DatetimeIndex(srvtimes)); i = i[i > 0]
    tp = TM[i] - 2000; o = C[i - 1]
    return (tp, o + K + SP[i - 1], o - K, np.full(len(i), sl, float), np.zeros(len(i)), tp + exp * MS, tp + hold * MS)
def quick(s):
    x = s[s.index >= A3]; y = s[(s.index >= A6) & (s.index < A3)]
    return len(x), pf(x), x.sum(), len(y), pf(y), y.sum()
print(f"last 3 months {A3:%Y-%m-%d} .. {END:%Y-%m-%d} | previous {A6:%Y-%m-%d} .. {A3:%Y-%m-%d}")
rows = []
for key, g in ev.groupby("key"):
    tt = sorted(set(g.srv))
    if len(tt) < 12: continue
    for K, sl, hold in ((1, 3, 15), (2, 3, 15), (3, 3, 15), (2, 4, 30)):
        s, _ = sim(*mk(tt, K, sl, hold)); r = quick(s)
        rows.append((key, len(tt), K, sl, hold) + r)
R = pd.DataFrame(rows, columns=["key", "events", "K", "sl", "hold", "n3", "pf3", "net3", "np", "pfp", "netp"])
R.to_csv("oco139_groups.csv", index=False)
best = R.assign(mn=np.minimum(R.pf3, R.pfp)).sort_values("mn", ascending=False)
print("groups tested:", R.key.nunique(), "| cells:", len(R), "| cells PF>=1.15 both windows with >=8 trades each:", ((R.pf3 >= 1.15) & (R.pfp >= 1.15) & (R.n3 >= 8) & (R.np >= 8)).sum())
g2 = R.groupby("key").apply(lambda d: ((d.pf3 >= 1.15) & (d.pfp >= 1.15) & (d.n3 >= 8) & (d.np >= 8)).sum())
print("groups with >=3 of 4 cells passing:"); 
for k in g2[g2 >= 3].index: print("  ", R[R.key == k].to_string(index=False, header=False))
print("top 25 by min PF:"); print(best.head(25).to_string(index=False))
