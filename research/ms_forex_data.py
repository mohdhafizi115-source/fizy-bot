"""Shared data helper for the research scripts."""
import pandas as pd


def yahoo_h1(name):
    """2 years of H1 candles from Yahoo (no key). Gold = GC=F futures (fine for R-based results)."""
    import requests
    ysym = "GC=F" if name.startswith("XAU") else name + "=X"
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}",
                     params={"interval": "60m", "range": "730d"},
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}, timeout=40)
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
                      index=pd.to_datetime(res["timestamp"], unit="s", utc=True)).dropna()
    df.index = df.index.floor("1h")
    return df.groupby(level=0).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
