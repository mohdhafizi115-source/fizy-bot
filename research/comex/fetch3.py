# Round 153 data: free daily / hourly series of the usual gold 'direction tools' (Yahoo) + SPDR GLD holdings.
import os, requests, pandas as pd
OUT = 'data/tools'; os.makedirs(OUT, exist_ok=True); log = []
def note(s): print(s, flush=True); log.append(s)
import yfinance as yf
T = {'GVZ': '^GVZ', 'IRX': '^IRX', 'FVX': '^FVX', 'CNH': 'CNH=X', 'N225': '^N225', 'HSI': '^HSI', 'BTC': 'BTC-USD', 'AUDUSD': 'AUDUSD=X',
     'DXY': 'DX-Y.NYB', 'US10Y': '^TNX', 'TIP': 'TIP', 'GLD': 'GLD', 'GDX': 'GDX', 'SILVER': 'SI=F', 'VIX': '^VIX',
     'SPX': '^GSPC', 'ES': 'ES=F', 'EURUSD': 'EURUSD=X', 'USDJPY': 'JPY=X', 'GOLD': 'GC=F', 'COPPER': 'HG=F', 'OIL': 'CL=F'}
for k, t in T.items():
    for iv, per in (('1d', '5y'), ('1h', '730d')):
        try:
            d = yf.download(t, interval=iv, period=per, auto_adjust=False, progress=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            d.to_csv(f'{OUT}/{k}_{iv}.csv'); note(f'{k} {iv}: {len(d)} rows {d.index.min()} .. {d.index.max()}')
        except Exception as e: note(f'{k} {iv} failed {e!r}')
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
for u in () and ('https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv',
          'https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.xlsx'):
    try:
        r = requests.get(u, headers=H, timeout=60); fn = f'{OUT}/gld_holdings.' + u.rsplit('.', 1)[1]
        open(fn, 'wb').write(r.content); note(f'spdr {u}: status {r.status_code}, {len(r.content)} bytes, head {r.content[:80]!r}')
    except Exception as e: note(f'spdr failed {e!r}')
open(f'{OUT}/fetch_log.txt', 'w').write('\n'.join(log) + '\n')
