# Round 151 data: free COMEX gold (GC) data, fetched on a GitHub runner (open network).
# Each source is tried on its own; whatever works is saved under data/comex/.
import os, json, time, datetime as dt, traceback
import pandas as pd, requests
OUT = 'data/comex'; os.makedirs(OUT, exist_ok=True)
log = []
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
     'Accept': 'application/json, text/plain, */*', 'Referer': 'https://www.cmegroup.com/'}
def note(s): print(s, flush=True); log.append(s)

# 1) Yahoo GC=F via yfinance: daily (max), hourly (730 d), 5-min (60 d)
try:
    import yfinance as yf
    for iv, per in (('1d', 'max'), ('1h', '730d'), ('5m', '60d')):
        d = yf.download('GC=F', interval=iv, period=per, auto_adjust=False, progress=False)
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        d.to_csv(f'{OUT}/yahoo_gc_{iv}.csv'); note(f'yahoo {iv}: {len(d)} rows {d.index.min()} .. {d.index.max()}')
except Exception as e: note('yahoo failed: ' + repr(e))

# 2) CME volume + open interest by trade date (GC = product 437)
try:
    rows = []; day = dt.date.today(); tried = 0; fails = 0
    while tried < 400 and fails < 40:
        day -= dt.timedelta(days=1)
        if day.weekday() >= 5: continue
        tried += 1
        u = f'https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/437/{day:%Y%m%d}/P?tradeDate={day:%Y%m%d}'
        try:
            r = requests.get(u, headers=H, timeout=20)
            if r.status_code != 200: fails += 1; continue
            j = r.json(); tot = j.get('totals', {})
            rows.append(dict(date=day.isoformat(), **{k: tot.get(k) for k in ('totalVolume', 'globexVolume', 'openInterest', 'changeOI', 'pntVolume')}))
            fails = 0
        except Exception: fails += 1
        time.sleep(0.4)
    pd.DataFrame(rows).to_csv(f'{OUT}/cme_gc_volume_oi.csv', index=False); note(f'cme vol/oi: {len(rows)} days (tried {tried})')
except Exception as e: note('cme failed: ' + repr(e))

# 3) Stooq daily GC futures (may carry open interest)
try:
    r = requests.get('https://stooq.com/q/d/l/?s=gc.f&i=d', headers=H, timeout=30)
    open(f'{OUT}/stooq_gc_d.csv', 'w').write(r.text); note(f'stooq: {len(r.text.splitlines())} lines, head {r.text.splitlines()[0] if r.text else ""}')
except Exception as e: note('stooq failed: ' + repr(e))

open(f'{OUT}/fetch_log.txt', 'w').write('\n'.join(log) + '\n')
