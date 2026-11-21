# Round 158c: check the low cells of round 158b against exposure and a random side that switches at the same TF.
import os, numpy as np, pandas as pd
from multiprocessing import Pool
import mart158b as M
END = M.END
def side_rand(tf, seed):
    K_ = M.DAYK if tf == "D1" else M.T.floor(M.TFS[tf])
    u = pd.Index(K_).unique(); r = np.random.default_rng(seed).choice([-1, 1], len(u))
    return pd.Series(r, index=u).reindex(K_).values
def job(a):
    nm, hs = a
    nb = sum(1 for st in M.starts if M.sim('hbias', 3, st, END + pd.Timedelta(minutes=1), hside=hs)[3] is not None)
    x = M.sim('hbias', 3, M.A3, END + pd.Timedelta(minutes=1), hside=hs); y = M.sim('hbias', 3, M.A6, M.A3, hside=hs)
    sell = np.mean(hs[(M.T >= M.A6)] == -1)
    return f"{nm:22s} | sell share {sell:.0%} | baskets last {x[0]} prev {y[0]} | starts blown {nb}/{len(M.starts)}"
if __name__ == "__main__":
    J = []
    for tf, N, sg in (("M1", 1, -1), ("M1", 3, -1), ("M5", 6, -1), ("M30", 3, -1), ("H1", 3, -1), ("D1", 6, -1)):
        J.append((f"{tf} last {N} fade", M.side_from(tf, N, sg)[0]))
    for tf in ("M1", "M5", "M30", "D1"):
        for sd in range(5): J.append((f"RANDOM {tf} seed {sd}", side_rand(tf, sd)))
    J.append(("always SELL", -np.ones(len(M.T))))
    with Pool(2) as p:
        for r in p.imap(job, J): print(r, flush=True)
