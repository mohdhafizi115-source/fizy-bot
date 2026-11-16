# Several FLIP "lanes" (independent magic numbers) running at once, each a profitable frozen-stop variant.
H_ = H
L = {
 "A D4 K3":            dict(),
 "B D6 K5":            dict(D=6, K=5),
 "C D5 K8":            dict(D=5, K=8),
 "D D4 K3 start 08":   dict(start_ms=8 * H_),
 "E D4 K3 start 15:30":dict(start_ms=int(15.5 * H_)),
 "F D8 K12":           dict(D=8, K=12),
 "G D4 K5 +add $10":   dict(K=5, pyr_at=10, pyr_max=1),
 "H fixed-ish D5 K2":  dict(D=5, K=2),
}
R = {}
for k, kw in L.items():
    te, p, _, _ = run(**kw); ts, ps, _, _ = run(**dict(kw, spm=1.5)); R[k] = (te, p, ts, ps)
    row(k, **kw)
def combo(lab, keys):
    te = pd.DatetimeIndex(np.concatenate([R[k][0].values for k in keys])); p = np.concatenate([R[k][1] for k in keys])
    ts = pd.DatetimeIndex(np.concatenate([R[k][2].values for k in keys])); ps = np.concatenate([R[k][3] for k in keys])
    o = np.argsort(te.values); te, p = te[o], p[o]
    print(f"{lab:44s} | {st(te, p, a3, end + pd.Timedelta(days=1))} {pf(ps[ts >= a3]):5.2f} | {st(te, p, a6, a3)}", flush=True)
print("-- lanes together (sum of all positions) --")
combo("A+B", ["A D4 K3", "B D6 K5"])
combo("A+B+C", ["A D4 K3", "B D6 K5", "C D5 K8"])
combo("A+D+E (same rule, 3 start times)", ["A D4 K3", "D D4 K3 start 08", "E D4 K3 start 15:30"])
combo("A+B+C+D", ["A D4 K3", "B D6 K5", "C D5 K8", "D D4 K3 start 08"])
combo("A+B+C+D+E", ["A D4 K3", "B D6 K5", "C D5 K8", "D D4 K3 start 08", "E D4 K3 start 15:30"])
combo("A+B+C+D+E+F", ["A D4 K3", "B D6 K5", "C D5 K8", "D D4 K3 start 08", "E D4 K3 start 15:30", "F D8 K12"])
combo("all 8", list(L))
