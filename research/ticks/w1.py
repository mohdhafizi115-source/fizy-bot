row("BASE frozen D $4")
te, p, en, o = run()
for lab, lo, hi in (("last", a3, end + pd.Timedelta(days=1)), ("prev", a6, a3)):
    m = (te >= lo) & (te < hi)
    print(f"-- {lab}: by entry number of the day --")
    for k in (1, 2, 3, 4, 5, 6, 8, 99):
        q = m & ((o == k) if k < 6 else ((o >= (6 if k == 6 else 8 if k == 8 else 12))))
        if k == 6: q = m & (o >= 6) & (o < 8)
        if k == 8: q = m & (o >= 8) & (o < 12)
        if k == 99: q = m & (o >= 12)
        if q.sum(): print(f"   entry #{k:<3d} n {q.sum():4d} win {100*(p[q]>0).mean():3.0f}% PF {pf(p[q]):5.2f} net {p[q].sum():+7.0f}")
    print(f"-- {lab}: by entry hour (server) --")
    for h0 in range(1, 23, 2):
        q = m & (en.hour >= h0) & (en.hour < h0 + 2)
        if q.sum(): print(f"   {h0:02d}-{h0+2:02d}h n {q.sum():4d} win {100*(p[q]>0).mean():3.0f}% PF {pf(p[q]):5.2f} net {p[q].sum():+7.0f}")
