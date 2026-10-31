//+------------------------------------------------------------------+
//| FizyRSI2.mqh - H1 RSI(2) pullback on many symbols (demo only),   |
//| included by FizyLB.mq5 (one EA, one chart).                       |
//| Rules (same as the FIZY BOT RSI2 alerts / backtest):              |
//|   buy  when the closed H1 candle is above SMA 200 and RSI(2) < 10 |
//|   sell when it is below SMA 200 and RSI(2) > 90                   |
//|   SL 2 x ATR(14) H1 from the entry, no TP                         |
//|   exit when an H1 close crosses back over the SMA 5               |
//|   one position per symbol (one setup = one entry), fixed lot      |
//| Events go to MQL5\Files\rsi2_events.txt (forwarded to Telegram).  |
//+------------------------------------------------------------------+
input string InpRsiSymbols = "XAUUSD,BTCUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,EURNZD,GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY";
input bool   InpRsiOn      = true;
input double InpRsiLot     = 0.01;
input long   InpRsiMagic   = 260309;
input double InpRsiLo      = 10;
input double InpRsiHi      = 90;
input double InpRsiSlAtr   = 2.0;
input double InpRsiMaxSpreadAtr = 0.30;   // skip an entry when the spread is above this part of ATR(H1)

string   r_sym[];          // broker symbol names that exist
datetime r_last[];         // last closed H1 bar handled per symbol
ulong    r_known[];        // RSI2 position tickets seen open
bool     r_ready = false;

void RsiEvent(string msg)
{
   int h = FileOpen("rsi2_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("rsi2 event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("RSI2 EVENT ", msg);
}

string RsiP(string s, double v) { return DoubleToString(v, (int)SymbolInfoInteger(s, SYMBOL_DIGITS)); }

// broker name for a plain symbol: try the plain name and common suffixes
string RsiResolve(string base)
{
   string cands[] = { "", ".m", "m", ".", "#", ".pro", ".std", ".ecn", ".r" };
   for(int i = 0; i < ArraySize(cands); i++)
   {
      string n = base + cands[i];
      bool custom;
      if(SymbolExist(n, custom)) return n;
   }
   return "";
}

void RsiInit()
{
   string parts[];
   int n = StringSplit(InpRsiSymbols, ',', parts);
   ArrayResize(r_sym, 0); ArrayResize(r_last, 0);
   string missing = "";
   for(int i = 0; i < n; i++)
   {
      string b = parts[i]; StringTrimLeft(b); StringTrimRight(b);
      if(b == "") continue;
      string s = RsiResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ", ") + b; continue; }
      SymbolSelect(s, true);
      int k = ArraySize(r_sym); ArrayResize(r_sym, k + 1); ArrayResize(r_last, k + 1);
      r_sym[k] = s; r_last[k] = 0;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpRsiMagic) { int m = ArraySize(r_known); ArrayResize(r_known, m + 1); r_known[m] = t; }
   }
   r_ready = true;
   RsiEvent(StringFormat("RSI2 ONLINE | %d symbols on H1, lot %.2f, %d open RSI2 position(s)%s", ArraySize(r_sym), InpRsiLot, ArraySize(r_known),
                         missing == "" ? "" : " | not found at this broker: " + missing));
}

bool RsiPosition(string s, ulong &ticket, bool &isBuy)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpRsiMagic && PositionGetString(POSITION_SYMBOL) == s)
      { ticket = t; isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY; return true; }
   }
   return false;
}

double RsiLot(string s)
{
   double mn = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   double v = MathMax(mn, MathFloor(InpRsiLot / st + 1e-9) * st);
   return NormalizeDouble(v, 2);
}

// indicators on closed H1 bars: rates[] oldest first, the last element is the bar just closed
bool RsiCalc(string s, double &close, double &sma200, double &sma5, double &rsi, double &atr, datetime &barTime)
{
   MqlRates r[];
   int n = CopyRates(s, PERIOD_H1, 1, 260, r);
   if(n < 215) return false;
   int last = n - 1;
   close = r[last].close; barTime = r[last].time;
   double s200 = 0; for(int i = last - 199; i <= last; i++) s200 += r[i].close; sma200 = s200 / 200;
   double s5 = 0; for(int i = last - 4; i <= last; i++) s5 += r[i].close; sma5 = s5 / 5;
   double up = 0, dn = 0;                                      // Wilder RSI(2) = ewm alpha 1/2 over the series
   for(int i = 1; i <= last; i++)
   {
      double d = r[i].close - r[i - 1].close;
      up = 0.5 * MathMax(d, 0) + 0.5 * up;
      dn = 0.5 * MathMax(-d, 0) + 0.5 * dn;
   }
   rsi = (dn == 0) ? 100 : 100 - 100 / (1 + up / dn);
   double tr = 0;
   for(int i = last - 13; i <= last; i++)
      tr += MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
   atr = tr / 14;
   return true;
}

void RsiReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, dtype = -1; string s = "";
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      s = HistoryDealGetString(d, DEAL_SYMBOL);
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); dtype = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0 || s == "") return;
   string what = (reason == DEAL_REASON_SL) ? "RSI2 SL HIT" : (reason == DEAL_REASON_EXPERT ? "RSI2 EXIT" : "RSI2 CLOSED");
   string why  = (reason == DEAL_REASON_SL) ? "stop loss" : (reason == DEAL_REASON_EXPERT ? "H1 close back over the SMA 5" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(s, PERIOD_H1, "RSX", lv, lc, lb, 0, 0, 0, 0, true);
   RsiEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, s, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         RsiP(s, inPx), RsiP(s, outPx), why, profit) + Img(fn));
}

datetime r_lastRun = 0;
void RsiOnTimer()
{
   if(!InpRsiOn) return;
   if(!r_ready) RsiInit();
   datetime now = TimeCurrent();
   if(now - r_lastRun < 10) return;                                         // every 10 s is enough for H1
   r_lastRun = now;
   // positions that closed since the last check (SL hits, our exits, manual closes)
   for(int j = ArraySize(r_known) - 1; j >= 0; j--)
   {
      bool still = PositionSelectByTicket(r_known[j]);
      if(!still) { RsiReportClosed(r_known[j]); ArrayRemove(r_known, j, 1); }
   }
   for(int k = 0; k < ArraySize(r_sym); k++)
   {
      string s = r_sym[k];
      double close, sma200, sma5, rsi, atr; datetime bt;
      if(!RsiCalc(s, close, sma200, sma5, rsi, atr, bt)) continue;
      if(r_last[k] == 0)
      {
         // first look after a (re)start: act on the last closed bar only if it closed in the last 10 minutes
         r_last[k] = (now - (bt + 3600) <= 600) ? bt - 1 : bt;
      }
      if(bt <= r_last[k]) continue;
      r_last[k] = bt;
      MqlTick tk;
      if(!SymbolInfoTick(s, tk) || now - tk.time > 600) continue;            // market closed / no fresh price
      ulong t; bool isBuy;
      if(RsiPosition(s, t, isBuy))
      {
         if((isBuy && close > sma5) || (!isBuy && close < sma5))
         {
            if(!trade.PositionClose(t)) RsiEvent(StringFormat("ERROR | RSI2 exit %s failed: %d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
            // the close (with profit and chart) is reported by RsiReportClosed on the next check
         }
         continue;                                                            // one setup = one entry
      }
      int dr = (close > sma200 && rsi < InpRsiLo) ? 1 : ((close < sma200 && rsi > InpRsiHi) ? -1 : 0);
      if(dr == 0) continue;
      double spread = tk.ask - tk.bid;
      if(atr <= 0 || spread > InpRsiMaxSpreadAtr * atr)
      {
         RsiEvent(StringFormat("RSI2 SKIPPED %s | %s signal but spread %s is too wide (ATR %s)", s, dr == 1 ? "BUY" : "SELL", RsiP(s, spread), RsiP(s, atr)));
         continue;
      }
      double lot = RsiLot(s);
      double entry = dr == 1 ? tk.ask : tk.bid;
      double sl = NormalizeDouble(entry - dr * InpRsiSlAtr * atr, (int)SymbolInfoInteger(s, SYMBOL_DIGITS));
      trade.SetExpertMagicNumber(InpRsiMagic);
      trade.SetTypeFillingBySymbol(s);
      bool ok = (dr == 1) ? trade.Buy(lot, s, 0, sl, 0, "RSI2 H1") : trade.Sell(lot, s, 0, sl, 0, "RSI2 H1");
      trade.SetExpertMagicNumber(InpMagic);
      trade.SetTypeFillingBySymbol(InpSymbol);
      if(!ok) { RsiEvent(StringFormat("ERROR | RSI2 %s %s failed: %d %s", dr == 1 ? "BUY" : "SELL", s, trade.ResultRetcode(), trade.ResultRetcodeDescription())); continue; }
      // remember the new position so its close is reported
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong pt = PositionGetTicket(i);
         if(pt > 0 && PositionGetInteger(POSITION_MAGIC) == InpRsiMagic && PositionGetString(POSITION_SYMBOL) == s)
         { int m = ArraySize(r_known); ArrayResize(r_known, m + 1); r_known[m] = pt; break; }
      }
      double fill = trade.ResultPrice() > 0 ? trade.ResultPrice() : entry;
      double lv[2]; color lc[2]; string lb[2];
      lv[0] = fill; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
      string fn = Snap(s, PERIOD_H1, "RS", lv, lc, lb, 0, 0, 0, 0, true);
      RsiEvent(StringFormat("RSI2 %s %s | H1 close %s %s SMA 200 (%s), RSI(2) %.1f | entry %s, SL %s (2 x ATR), lot %.2f | exit: H1 close back over SMA 5 (now %s)",
                            dr == 1 ? "BUY" : "SELL", s, RsiP(s, close), dr == 1 ? "above" : "below", RsiP(s, sma200), rsi,
                            RsiP(s, fill), RsiP(s, sl), lot, RsiP(s, sma5)) + Img(fn));
   }
}
//+------------------------------------------------------------------+
