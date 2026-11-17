# Round 140 (part 1): FLIP lane variants on real ticks with the round 131 D1-body filter, plus the news straddle trades
import sys; sys.argv = ["x"]
exec(open("flip133.py").read().split("L = {")[0])
L = {"A": dict(), "B": dict(D=6, K=5), "C": dict(D=5, K=8), "D": dict(start_ms=8 * H)}
out = []
for k, kw in L.items():
    out.append(run3(**dict(kw, maxbody=60)).assign(mod=f"FLIP-{k}s"))            # skip the day after a D1 body > $60
    out.append(run3(**dict(kw, maxbody=60, big_mode=3, big_maxn=1)).assign(mod=f"FLIP-{k}1"))  # one entry after a big day
X = pd.concat(out); X["sym"] = "XAUUSD"; X.to_pickle("lanes140.pkl"); print(X.groupby("mod").net.agg(["count", "sum"]))
