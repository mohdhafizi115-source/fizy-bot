# FIZY BOT – BBMA cloud scanner

Cloud version of the FizyIsm2026 MT5 EA (v6.01, alert only). GitHub Actions runs `bbma_scanner.py`
every 15 minutes, checks every symbol in `SYMBOLS` (forex pairs and XAUUSD) for the BBMA setup and
sends a chart with the full BBMA indicators (BB 20/2, LWMA 5/10 High and Low, EMA 50, EMA 90) to
Telegram.

Data sources (`PROVIDER`, tried in order for every symbol until one works):
- `deriv` (default first): Deriv public market data, no account or key. Forex + spot gold.
- `yahoo`: Yahoo Finance, no account or key. All forex pairs; gold is the COMEX future (GC=F).
- `twelvedata`: needs `TWELVEDATA_KEY` (free, 800 requests a day).
- `oanda`: needs `OANDA_TOKEN` (free demo account).

## Setup
1. (Optional) Create a free Twelve Data account for spot XAUUSD prices (https://twelvedata.com).
2. Create a **public** GitHub repository and upload these files (keep the `.github/workflows` folder).
3. Settings → Secrets and variables → Actions → New repository secret:
   `TG_TOKEN`, `TG_CHAT_ID` (and optionally `TWELVEDATA_KEY` or `OANDA_TOKEN`).
   Optional, in the Variables tab: `PROVIDER` (`twelvedata` / `oanda`), `SYMBOLS` (e.g. `ALL`).
4. Actions tab → enable workflows → "BBMA scanner" → Run workflow (first manual run).

The settings are at the top of `bbma_scanner.py` (`CFG`).

## Test on MT5 history
`python bbma_scanner.py --csv XAUUSD.m_M15_export.csv --name XAUUSD --start 2026-09-01 --chart last.png`
