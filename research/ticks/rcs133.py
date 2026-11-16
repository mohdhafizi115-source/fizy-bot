import os, sys
sys.argv = ["x", sys.argv[1]]
sys.path.insert(0, "/home/claude/fizy-bot/research")
import numpy as np, pandas as pd
import bbma99 as B
meta = B.SA.load_meta(os.path.join(B.DATA, "meta.txt")); SW = B.R23.load_swaps(); rg = np.random.default_rng(99)
B.B97.CTX_ONLY = True
ch = dict(B.V)[[n for n, _ in B.V if n.startswith("SL 2.0 ATR")][0]]
out = []
for sym in B.SYMS:
    if sym not in meta or not os.path.exists(os.path.join(B.DATA, sym + ".csv")): continue
    cx = B.B97.run(sym, meta[sym], SW.get(sym), rg)
    ks, dr = cx["ks"], cx["dr"]
    exa = np.where(dr == 1, cx["roll"](cx["exd"], 8)[ks - 1], cx["roll"](cx["exu"], 8)[ks - 1])
    m = (cx["h4pos"] <= -0.5) & (exa == 1) & (cx["spr"] <= 0.20)
    df = B.sim(cx, SW.get(sym), meta[sym], m, dict(B.C, **ch), False, rg)
    if len(df): out.append(df.assign(sym=sym))
X = pd.concat(out); X["mod"] = np.where(X.sym == "XAUUSD", "RCS-gold", "RCS-fx")
X[["mod", "sym", "t", "tx", "d", "net"]].to_pickle(sys.argv[1] + "/../rcs133.pkl"); print(X.groupby("mod").net.agg(["count", "sum"]), X.t.min(), X.t.max())
