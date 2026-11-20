import sys, os, zipfile, io, urllib.request, datetime as dt
import pandas as pd, numpy as np
out='min'; os.makedirs(out, exist_ok=True)
d=dt.date(2026,5,1); end=dt.date(2026,11,19)
while d<=end:
    f=f'{out}/{d}.pkl'
    if not os.path.exists(f):
        url=f'https://data.binance.vision/data/futures/um/daily/aggTrades/XAUUSDT/XAUUSDT-aggTrades-{d}.zip'
        try:
            b=urllib.request.urlopen(url,timeout=120).read()
            z=zipfile.ZipFile(io.BytesIO(b)); df=pd.read_csv(z.open(z.namelist()[0]))
            df['usd']=df.price*df.quantity
            sell=df.is_buyer_maker.values  # True -> aggressive sell
            # taker orders: same ms & side
            g=df.groupby(['transact_time','is_buyer_maker']).agg(usd=('usd','sum'),px=('price','last')).reset_index()
            g['m']=g.transact_time//60000
            df['m']=df.transact_time//60000
            df['bu']=np.where(~sell,df.usd,0.); df['su']=np.where(sell,df.usd,0.)
            M=df.groupby('m').agg(o=('price','first'),h=('price','max'),l=('price','min'),c=('price','last'),bu=('bu','sum'),su=('su','sum'),n=('usd','size'))
            for th in (100e3,250e3,500e3,1e6):
                k=int(th/1e3)
                big=g[g.usd>=th]
                M[f'bb{k}']=big[~big.is_buyer_maker].groupby('m').usd.sum()
                M[f'sb{k}']=big[big.is_buyer_maker].groupby('m').usd.sum()
            M=M.fillna(0.)
            M.to_pickle(f); print(d,len(df),flush=True)
        except Exception as e:
            print(d,'ERR',e,flush=True)
    d+=dt.timedelta(days=1)
