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
- **`bbma_scanner.py` + `.github/workflows/scan.yml`:** Linux scanner loop (Deriv data). **Sends nothing to Telegram since 3 Nov** (owner: drop irrelevant messages): BBMA, M5 scalp, RSI2 and the London-breakout paper alerts are off, the 4-hourly "is alive" heartbeat is off (`HEARTBEAT_HOURS = []`) and data-problem messages only go out while a scanner alert is on. It keeps running for `mt5_watchdog()`, which restarts the MT5 shift chain if no shift is running.
- **`.github/workflows/mt5_trade.yml`:** the auto trader. A Windows runner installs the JustMarkets MT5 terminal, compiles `mt5/FizyLB.mq5` and runs it for about 335 minutes. `mt5/next_shift.py` then dispatches the next shift, so it runs 24/7.
  - `mt5_trade.txt`: line 1 `on`/`off`. Lines 2–7 are the lots for London breakout, NR7, Gotobi, gold auction, month-end fix and volatility breakout. Line 8 `on`/`off` switches the gold S/R zone alerts (**off since 2 Nov evening**: no S/R level passed). Line 9 is the lot of the USDJPY day trades (`FizyDTJ.mqh`). Line 10 is the lot of the gold H1 Ichimoku cloud breakout (`FizyKUMO.mqh`). **All lots are 0.01 since 3 Nov** (owner's request; London was 0.05).
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
  | `FizyKUMO.mqh` | gold H1 Ichimoku cloud breakout (v1.90): H1 close breaks out of the cloud with Tenkan on the same side, SL beyond the cloud, exit on a close back inside or after 48 h; holds overnight | 260317 |
  | `FizySR.mqh` | gold M15 S/R zone **alerts only** (no trading), **switched off** (line 8): slim zones (0.5 ATR clusters, ≤ 1.2 ATR wide, ≥ 3 touches), the 2 nearest above and below; map at 01:30 / 08:00 / 15:00 server, chart when price enters a zone. Turn on again only for a level type that passes | – |

  The London breakout uses magic 260308. Broker/server time is Europe/Athens (GMT+2/+3).
  - **Unfilled stop orders (v1.91):** the EA deletes them itself and reports "ORDER DELETED" to Telegram: London 21:00, Williams and PDHL 20:00, NR7 23:55 server. The broker expiry is set 5 minutes later, only as a backup (before v1.91 the broker expiry fired at the same time and removed them silently). Each day's orders are placed fresh: Williams 01:30, PDHL 02:00, London 08:00 server (07:30 / 08:00 / 14:00 MYT in winter).

## How to deploy an EA change
1. Edit `mt5/*.mq*`.
2. Touch `run_mt5.txt` and push. `.github/workflows/mt5.yml` compiles everything and writes `status/mt5_check.txt`. Check for `0 errors`.
3. `git rm status/snap_TEST_*.png`, the test screenshots that the check commits.
4. Cancel the running `mt5_trade.yml` run. Its "Next shift" step starts a new shift on the latest `main`. To force a fresh daily status, write any other text into `status/mt5_online.txt` before cancelling.
- The GitHub CLI's `gh workflow run` may fail. Use REST instead: `gh api -X POST repos/<owner>/fizy-bot/actions/workflows/<file>/dispatches -f ref=main`, and `.../actions/runs/<id>/cancel`.

## Research (backtests on the broker's own data)
- **`.github/workflows/mt5_data.yml`:** exports M5 history with `mt5/ExportM5.mq5` (input `symbols`, default 30 instruments) into the artifact `m5data`, then runs `research/<script>.py` on Linux. Results go to `research/status/<script>.txt`.
  - Re-run a script on an earlier export with the inputs `script=research/x.py` and `data_run=<run id>`.
  - Input `tf=M1` exports M1 instead of M5 (use with `symbols=XAUUSD`; gold M1 from 2020 is about 2.3 M bars, kept in run 41663561048).
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
    - Gold H1 Ichimoku cloud breakout (`research/round19.py`, `goldh1_detail.py`): 976 trades, PF 1.29 with swap, halves 1.14 / 1.48, every year positive; buys PF 1.60, sells 1.03; the day-trade version fails (first half 0.92). Live since v1.90.
  - **No edge:**
    - Every M5 indicator scalp, on all 30 instruments.
    - Round 15 (`research/round15.py`, 2 Nov, for more trades a day): H1 / H4 NR7 and inside-bar breakouts, H1 Donchian 20/10, H1 z-score reversion on all 30 (0 of 180 pass); new gold event times (Shanghai Gold Benchmark AM / PM, SHFE night open, MCX open; 0 kept).
    - Gold M5 scalping, round 16 (`research/goldscalp16.py`, 2 Nov): lead-lag from the USD basket (EURUSD, USDJPY, AUDUSD) or BTC to gold, 5–15 min holds, and tick-volume spikes. Gold does catch up with the dollar (first-half t up to 4.6) but the move is smaller than the $0.18 spread: PF 0.84–1.04, 0 of 24 pass. The only gold scalp with an edge is the LBMA pre-auction sell (live).
    - Round 17, scalping systems taught on the web (`research/webscalp.py`, 2 Nov, M5, 12 instruments incl. gold): FXOpen Momo, EMA 9/55/200 + RSI, EMA 5/20 + MACD + Bollinger, Babypips 3 Ducks, Williams %R zones (± EMA 200), CCI ±100, Stochastic 5-3-3, SMA 5-8-13 ribbon, EMA 9/21 pullback, EMA ribbon + ADX. 0 of 132 pass; every rule loses on all 12 (PF 0.03–0.97); gold 0.69–0.97, worst −$3,700 per 0.01 lot. Gold 3 Ducks detail (`research/ducks_detail.py`): 2,005 trades, win 38%, +$113 = +$0.06 a trade (spread $0.18), PF $ 1.01 (halves 0.97 / 1.04), stress 0.99, max DD −$393. Break-even, not added.
    - Quasimodo / QML (`research/quasimodo.py`, 2 Nov; owner asked for "Quasimodo cikgu Bahar", whose own rules are not public, so the standard pattern was tested): limit at the left shoulder, SL beyond the head, TP 2R / at the break / candle confirmation; M5, M15, H1; 12 instruments; fake-level control. 0 of 108 pass, worse than random entries. Gold: M5 PF 0.66 (−$1,405), M15 0.69 (−$819), H1 best 0.98 (QM_CONF). Test the teacher's exact rules if the owner sends them.
    - Round 18, gold daily breakouts (`research/goldday18.py`, 2 Nov; also checked on USDJPY / EURJPY / GBPJPY): NY breakout of the London range (gold PF 1.12, last 12 months negative), NR4, NR4 + inside day (132 trades), early Asian range, day after a big day: no pass. **Inside-day breakout (ID_D1: OCO at yesterday's high / low from 01:30, SL other side, close 22:30) passes on gold (205 trades, PF 1.42, halves 1.24 / 1.64) and USDJPY (PF 1.46)**, but about half of the gold inside days are NR7 days already traded live; without them 113 trades, PF 1.35 (halves 1.40 / 1.28), below the 150-trade minimum. On USDJPY it duplicates PDHL. Not added yet; offered to the owner.
    - Round 19 (`research/round19.py`, 2 Nov, M15 / H1, 12 instruments): Ichimoku TK cross, RSI / MACD divergence, engulfing and pin bar at the EMA 20, Gartley / Bat harmonics. Only gold H1 Kumo breakout (above) and EURJPY H1 TK cross (PF 1.41, not checked with swap) pass. The divergences first looked good on gold H1 (PF 1.23–1.37) but that came from evaluating the final swing list (look-ahead); checked online they fall to 0.98–1.11. Always detect swing patterns online.
    - Round 20, gold M15 S/R flip retest (`research/flip20.py`, 3 Nov, owner's rule: RBS / SBR, wait for a rejection candle, enter the next candle, TP at the next S/R or nearest SnD): last month 44 trades, PF 1.85, +$80 per 0.01 lot, but +$84 of it is one trade and fake levels did better in the same month (PF 1.96, +$94). 3 months PF 0.99; 2020-2026 3,462 trades, PF 0.79, −$1,216, every year 0.64–0.87, worse than fake levels (0.87). Median planned reward 0.72R: the next level is too close. All 8 variants (pin bar, any touch, TP 2R, RR ≥ 1, S/R-only TP, swing size 3 / 10) fail. Not added. Every last-month trade is drawn on M15 charts in the artifact "Gold M15 Flip Trades" (`research/flip20_month.py` dumps the data).
    - Round 21, gold **M1** scalping (`research/m1scalp21.py`, 3 Nov, owner asked for an M1 scalping EA): broker M1 history 2020-03-30 → 2026-11-03 (2.33 M bars, run 41663561048, export input `tf=M1`), median spread $0.19. EMA 9/21 cross, BB + RSI(7) fade, Stochastic 5-3-3, RSI(2), 20-bar breakout, EMA 50 pullback, London / NY open range breakout, M1 spike fade / follow: PF 0.65–0.93 after spread, every one below random entries except BB_RSI (0.91), OPEN_BO (0.93), SPK_FADE (0.88); 0 of 9 pass. Losses at 0.01 lot: −$505 to −$17,347 over 6.6 years. Raw (no spread) PF 0.88–1.23: only the spike fade has a raw edge (1.23) and the spread eats it. No M1 EA built.
    - RSI2 on forex.
    - The walk-forward ML model.
    - COT positioning.
    - Following news surprises.
    - Smart-money / "bank jerung" fades.
    - Every WTI, Brent or XNG setup.
    - Gold M15 S/R zone entries (bounce, rejection, break; PF 0.83–1.01, random 0.94) and reference levels (`research/srlevels.py`: previous day / week / month high-low-close, daily / weekly open, Asian range, floor pivots, $50 round numbers; 0 of 64 pass against fake levels). Real levels hold *less* often than random ones (37–50% vs about 50%). Closest: PDH break buy PF 1.28 but first half < 1.05. The owner wants only tested zones, so the S/R alerts are off.
    - Gold fixed-lot grid (`research/grid.py`, 48 variants: long / short / both / trend, $10 / $20 / $40 steps, 10 levels or no limit, $100 standard and cent accounts, swaps, 1:500, stop-out 50%). Standard: every variant blows the $100 account 16–677 times in 6.6 years, mostly within days. Cent: the best survivor made $0.33 a week with a 61% drawdown. 0 pass.
    - Gold martingale grid started only on reasoned signals (`research/martingale.py`: Williams breakout, London breakout, pullback to yesterday's low/high with the D1 trend; ×1.5 / ×2 lots, 6 levels, SL or hold, 0.5 / 1 D1 ATR steps; 5 random-start controls). Standard $100: every variant blows the account 8–65 times. Cent: one cell survives (WVB, 1 ATR, ×1.5, SL: +$47 in 6.6 years = $0.14 a week, max DD 37%, last 12 months +$1) and its neighbours fail. Not built: the edge is the Williams signal itself, already live without martingale.
    - Layers on the gold auction scalp (`research/gaulayer.py`, 2 Nov, owner's request: +0.01 lot every 10 pips = $1 against the entry, shared SL 2 ATR, exit 10:30): PF 1.84 but first half 1.03 (fail), max 38 layers, worst basket −$227 vs −$21 single, profit per $ of drawdown 8.2 vs 8.6 single. It is leverage on bad mornings, not extra edge; not built. A bigger plain lot gives the same profit with a smaller worst case.
  - The full write-ups are in the owner's claude.ai project "Trade", in the `claude/*.md` docs.
