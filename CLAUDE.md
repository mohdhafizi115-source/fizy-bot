# FIZY BOT: notes for Claude Code

## Working with the owner
- Reply in **Malay** (Bahasa Malaysia), casual and short. Code, comments, commit messages and Telegram texts stay in **English**.
- The owner wants only setups that pass a backtest on the broker's own data ("aku tak perlukan trade yang rugi").
  - Test first. Add a setup only if it passes. Remove anything that loses.
  - Say plainly when nothing works.
- Realistic expectations: $100 capital, demo first, then a cent account. Weekly 50% returns are not possible; never build martingale or grid EAs (the owner asked for a gold grid on 2 Nov; it was tested and failed, see the findings).

## Safety rules (always)
- Never ask for, type or commit the MT5 password, login or the Telegram token. They live only in GitHub secrets: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `TG_TOKEN`, `TG_CHAT_ID`.
- This repository is **public**. Anything committed must be masked: account numbers (5+ digits), IP addresses and $ balances (`mt5/mask_logs.py`, the masking in the workflows).
- The EA trades demo accounts only (`InpDemoOnly = true`). Do not change that without the owner's explicit go-ahead.

## What runs
- **`bbma_scanner.py` + `.github/workflows/scan.yml`:** Linux scanner loop (Deriv data, Telegram alerts). London-breakout alerts only; the M5 scalp and RSI2 alerts are off. Its `mt5_watchdog()` restarts the MT5 shift chain if no shift is running.
- **`.github/workflows/mt5_trade.yml`:** the auto trader. A Windows runner installs the JustMarkets MT5 terminal, compiles `mt5/FizyLB.mq5` and runs it for about 335 minutes. `mt5/next_shift.py` then dispatches the next shift, so it runs 24/7.
  - `mt5_trade.txt`: line 1 `on`/`off`. Lines 2–7 are the lots for London breakout, NR7, Gotobi, gold auction, month-end fix and volatility breakout. Line 8 `on`/`off` switches the gold S/R zone alerts (**off since 2 Nov evening**: no S/R level passed). Line 9 is the lot of the USDJPY day trades (`FizyDTJ.mqh`). The gold auction lot (line 5) is **1.0** since 2 Nov on the owner's explicit request (demo); the others are 0.01, London 0.05.
  - `mt5/watch.py` forwards the EA event files (`MQL5/Files/*_events.txt`, with PNG screenshots) to Telegram, with emoji blocks and MYT times. It also sends one "BOT ONLINE" daily status (`status/mt5_online.txt` holds the date sent).
- **EA modules:** `mt5/FizyLB.mq5` (London breakout gold) includes the following.

  | File | Module | Magic |
  |---|---|---|
  | `FizySnap.mqh` | screenshots | – |
  | `FizyCommon.mqh` | symbol names, London time, closes leftover RSI2 positions | – |
  | `FizyNR7.mqh` | NR7 D1 on XAUUSD, USDJPY, AUDJPY | 260310 |
  | `FizyGTB.mqh` | Gotobi Tokyo fix: sell USDJPY, EURJPY, GBPJPY at 09:55 JST, close 10:15 | 260311 |
  | `FizyMEF.mqh` | month-end Tokyo fix: CADCHF / NZDCHF sell, USDCAD / GBPNZD buy, 09:40 → 09:55 JST | 260313 |
  | `FizyGAU.mqh` | gold before the LBMA auction: sell 10:15 → 10:30 London | 260312 |
  | `FizyWVB.mqh` | Williams volatility breakout: k 0.5 on USDJPY, EURJPY, GBPJPY, k 0.7 on XAUUSD (per symbol since v1.80) | 260314 |
  | `FizyDTJ.mqh` | USDJPY day trades: previous-day breakout (PDHL, from 02:00, TP 2R, close 22:30) and New York continuation (NYCONT, 15:30 follow the 09:00–15:30 move, close 22:00) | 260315 / 260316 |
  | `FizySR.mqh` | gold M15 S/R zone **alerts only** (no trading), **switched off** (line 8): slim zones (0.5 ATR clusters, ≤ 1.2 ATR wide, ≥ 3 touches), the 2 nearest above and below; map at 01:30 / 08:00 / 15:00 server, chart when price enters a zone. Turn on again only for a level type that passes | – |

  The London breakout uses magic 260308. Broker/server time is Europe/Athens (GMT+2/+3).

## How to deploy an EA change
1. Edit `mt5/*.mq*`.
2. Touch `run_mt5.txt` and push. `.github/workflows/mt5.yml` compiles everything and writes `status/mt5_check.txt`. Check for `0 errors`.
3. `git rm status/snap_TEST_*.png`, the test screenshots that the check commits.
4. Cancel the running `mt5_trade.yml` run. Its "Next shift" step starts a new shift on the latest `main`. To force a fresh daily status, write any other text into `status/mt5_online.txt` before cancelling.
- The GitHub CLI's `gh workflow run` may fail. Use REST instead: `gh api -X POST repos/<owner>/fizy-bot/actions/workflows/<file>/dispatches -f ref=main`, and `.../actions/runs/<id>/cancel`.

## Research (backtests on the broker's own data)
- **`.github/workflows/mt5_data.yml`:** exports M5 history with `mt5/ExportM5.mq5` (input `symbols`, default 30 instruments) into the artifact `m5data`, then runs `research/<script>.py` on Linux. Results go to `research/status/<script>.txt`.
  - Re-run a script on an earlier export with the inputs `script=research/x.py` and `data_run=<run id>`.
  - Exports: 30 FX / gold / BTC instruments, 2020-03 → 2026-11-02, in run 41443785106 (kept 60 days). WTI, Brent and XNG in run 41330505649. The older 30-instrument export (run 41277285458) was deleted on 2 Nov.
- **Economic calendar:** `mt5/ExportCal.mq5` + `.github/workflows/mt5_cal.yml` → `data/calendar.csv`. Past times are stored at today's server offset (+2 h): treat them as UTC+2, then convert to Europe/Athens.
- **Pass rule used so far:** ≥ 150 trades, PF ≥ 1.15 after spread, both halves ≥ 1.05, stress (1.5× spread) ≥ 1.05, last 12 months positive.
  - Always compare against a random-entry baseline or fake event times.
  - Drop trades in the 23:45–01:30 server rollover; the bid is distorted there.
- **Findings, short version:**
  - **Edges:**
    - Tokyo-fix flows: Gotobi and month-end.
    - Gold before the LBMA AM auction.
    - Breakouts on JPY pairs and gold: London breakout, NR7, Williams; on USDJPY also the previous-day breakout and New York continuation (re-checked on the 2 Nov export with `research/daycheck.py`).
  - **No edge:**
    - Every M5 indicator scalp, on all 30 instruments.
    - Round 15 (`research/round15.py`, 2 Nov, for more trades a day): H1 / H4 NR7 and inside-bar breakouts, H1 Donchian 20/10, H1 z-score reversion on all 30 (0 of 180 pass); new gold event times (Shanghai Gold Benchmark AM / PM, SHFE night open, MCX open; 0 kept).
    - Gold M5 scalping, round 16 (`research/goldscalp16.py`, 2 Nov): lead-lag from the USD basket (EURUSD, USDJPY, AUDUSD) or BTC to gold, 5–15 min holds, and tick-volume spikes. Gold does catch up with the dollar (first-half t up to 4.6) but the move is smaller than the $0.18 spread: PF 0.84–1.04, 0 of 24 pass. The only gold scalp with an edge is the LBMA pre-auction sell (live).
    - RSI2 on forex.
    - The walk-forward ML model.
    - COT positioning.
    - Following news surprises.
    - Smart-money / "bank jerung" fades.
    - Every WTI, Brent or XNG setup.
    - Gold M15 S/R zone entries (bounce, rejection, break; PF 0.83–1.01, random 0.94) and reference levels (`research/srlevels.py`: previous day / week / month high-low-close, daily / weekly open, Asian range, floor pivots, $50 round numbers; 0 of 64 pass against fake levels). Real levels hold *less* often than random ones (37–50% vs about 50%). Closest: PDH break buy PF 1.28 but first half < 1.05. The owner wants only tested zones, so the S/R alerts are off.
    - Gold fixed-lot grid (`research/grid.py`, 48 variants: long / short / both / trend, $10 / $20 / $40 steps, 10 levels or no limit, $100 standard and cent accounts, swaps, 1:500, stop-out 50%). Standard: every variant blows the $100 account 16–677 times in 6.6 years, mostly within days. Cent: the best survivor made $0.33 a week with a 61% drawdown. 0 pass.
    - Gold martingale grid started only on reasoned signals (`research/martingale.py`: Williams breakout, London breakout, pullback to yesterday's low/high with the D1 trend; ×1.5 / ×2 lots, 6 levels, SL or hold, 0.5 / 1 D1 ATR steps; 5 random-start controls). Standard $100: every variant blows the account 8–65 times. Cent: one cell survives (WVB, 1 ATR, ×1.5, SL: +$47 in 6.6 years = $0.14 a week, max DD 37%, last 12 months +$1) and its neighbours fail. Not built: the edge is the Williams signal itself, already live without martingale.
  - The full write-ups are in the owner's claude.ai project "Trade", in the `claude/*.md` docs.
