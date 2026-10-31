//+------------------------------------------------------------------+
//| FizyLB.mq5 - London breakout auto-trader for XAUUSD (demo only)  |
//| Same rules as the FIZY BOT alerts / backtest (chart = server     |
//| time): Asian range 03:00-08:00, OCO stops +-0.10 at 08:00, SL at |
//| the other side capped at 0.6% of price, TP 2.5R, SL to entry at  |
//| 1.5R, close everything at 21:00. Squeeze filter: range < 0.6 x   |
//| daily ATR(14); range must be 0.30-1.60% of price.                |
//| Stateless: everything is read back from the broker (orders,      |
//| positions, history with the magic number), so the terminal can   |
//| be restarted at any time (it runs on GitHub Actions in shifts).  |
//| Events are appended to MQL5\Files\flb_events.txt (one per line); |
//| the workflow forwards them to Telegram.                           |
//+------------------------------------------------------------------+
#property strict
#property version "1.10"
#include <Trade/Trade.mqh>

input string InpSymbol     = "XAUUSD.m";
input double InpLot        = 0.01;
input long   InpMagic      = 260308;
input int    InpRangeStart = 3;       // Asian range start hour (server)
input int    InpRangeEnd   = 8;       // range end = order time (server)
input int    InpLateMin    = 30;      // no new orders after 08:30
input int    InpCloseHour  = 21;      // close everything (server)
input double InpMinPct     = 0.30;
input double InpMaxPct     = 1.60;
input double InpCapPct     = 0.60;
input double InpTpR        = 2.5;
input double InpBeR        = 1.5;
input double InpBuffer     = 0.10;
input double InpSqueeze    = 0.60;    // 0 = off
input bool   InpDemoOnly   = true;

CTrade trade;
string g_noTradeDay = "";             // day already reported as "no trade" in this run
ulong  g_known[];                     // position tickets seen open (to report TP / SL closes)

#include "FizyRSI2.mqh"                // H1 RSI(2) on gold, 28 forex pairs and BTCUSD (same EA, same chart)

//--- helpers -------------------------------------------------------
datetime DayStart(datetime t) { MqlDateTime s; TimeToStruct(t, s); s.hour = 0; s.min = 0; s.sec = 0; return StructToTime(s); }
string   P(double v)           { return DoubleToString(v, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)); }
double   N(double v)           { return NormalizeDouble(v, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)); }

void Event(string msg)
{
   int h = FileOpen("flb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("EVENT ", msg);
}

double VolumeOk(double lot)
{
   double mn = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double mx = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   double v = MathMax(mn, MathFloor(lot / st + 1e-9) * st);
   return NormalizeDouble(MathMin(v, mx), 2);
}

int CountOrders()
{
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpMagic && OrderGetString(ORDER_SYMBOL) == InpSymbol) n++;
   }
   return n;
}

int CountPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic && PositionGetString(POSITION_SYMBOL) == InpSymbol) n++;
   }
   return n;
}

// any order placed or deal done today by this EA (so it never places twice on the same day)
bool TradedToday(datetime day)
{
   if(!HistorySelect(day, TimeCurrent() + 60)) return false;
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == InpMagic) return true;
   }
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t > 0 && HistoryDealGetInteger(t, DEAL_MAGIC) == InpMagic) return true;
   }
   return false;
}

void DeletePending(string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMagic || OrderGetString(ORDER_SYMBOL) != InpSymbol) continue;
      string side = (OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP) ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      if(trade.OrderDelete(t)) Event(StringFormat("ORDER DELETED | %s %s deleted (%s)", side, P(pr), why));
      else Event(StringFormat("ERROR | could not delete %s %s: %d %s", side, P(pr), trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
}

//--- 08:00: place the two stop orders ------------------------------
void PlaceOrders(datetime day)
{
   datetime r0 = day + InpRangeStart * 3600, r1 = day + InpRangeEnd * 3600;
   MqlRates m15[];
   int n = CopyRates(InpSymbol, PERIOD_M15, r0, r1 - 1, m15);
   if(n < (InpRangeEnd - InpRangeStart) * 4 - 2)
   {
      if(g_noTradeDay != TimeToString(day, TIME_DATE)) { g_noTradeDay = TimeToString(day, TIME_DATE); Event(StringFormat("NO TRADE TODAY | only %d M15 candles in the Asian range", n)); }
      return;
   }
   double hi = m15[0].high, lo = m15[0].low;
   for(int i = 1; i < n; i++) { hi = MathMax(hi, m15[i].high); lo = MathMin(lo, m15[i].low); }
   double mid = (hi + lo) / 2, pct = (hi - lo) / mid * 100;
   // daily ATR(14) from the days before today
   MqlRates d1[];
   double atr = 0;
   int nd = CopyRates(InpSymbol, PERIOD_D1, 1, 15, d1);
   if(nd >= 15)
   {
      double s = 0;
      for(int i = 1; i < 15; i++)
         s += MathMax(d1[i].high - d1[i].low, MathMax(MathAbs(d1[i].high - d1[i - 1].close), MathAbs(d1[i].low - d1[i - 1].close)));
      atr = s / 14;
   }
   double ratio = (atr > 0) ? (hi - lo) / atr : -1;
   string rng = StringFormat("Asian range %02d:00-%02d:00 high %s / low %s (%.2f%%, %s daily ATR)", InpRangeStart, InpRangeEnd, P(hi), P(lo), pct,
                             ratio >= 0 ? StringFormat("%.2fx", ratio) : "n/a");
   string dkey = TimeToString(day, TIME_DATE);
   if(InpSqueeze > 0 && ratio >= InpSqueeze)
   {
      if(g_noTradeDay != dkey) { g_noTradeDay = dkey; Event("NO TRADE TODAY | " + rng + StringFormat(", needs < %.2fx ATR", InpSqueeze)); }
      return;
   }
   if(pct < InpMinPct || pct > InpMaxPct)
   {
      if(g_noTradeDay != dkey) { g_noTradeDay = dkey; Event("NO TRADE TODAY | " + rng + StringFormat(", needs %.2f-%.2f%%", InpMinPct, InpMaxPct)); }
      return;
   }
   double capd = mid * InpCapPct / 100;
   double bIn = N(hi + InpBuffer), bSl = N(MathMax(lo, bIn - capd)), bR = bIn - bSl, bTp = N(bIn + InpTpR * bR);
   double sIn = N(lo - InpBuffer), sSl = N(MathMin(hi, sIn + capd)), sR = sSl - sIn, sTp = N(sIn - InpTpR * sR);
   double lot = VolumeOk(InpLot);
   string cm = "FLB " + TimeToString(day, TIME_DATE);
   // expiration at the close hour when the symbol allows it
   int em = (int)SymbolInfoInteger(InpSymbol, SYMBOL_EXPIRATION_MODE);
   ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime exp = (tt == ORDER_TIME_SPECIFIED) ? day + InpCloseHour * 3600 : 0;
   MqlTick tk; SymbolInfoTick(InpSymbol, tk);
   string res = "";
   bool okB, okS;
   if(tk.ask >= bIn) okB = trade.Buy(lot, InpSymbol, 0, bSl, bTp, cm);            // already above: in at market
   else okB = trade.BuyStop(lot, bIn, InpSymbol, bSl, bTp, tt, exp, cm);
   res += okB ? "" : StringFormat(" | buy error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   if(tk.bid <= sIn) okS = trade.Sell(lot, InpSymbol, 0, sSl, sTp, cm);
   else okS = trade.SellStop(lot, sIn, InpSymbol, sSl, sTp, tt, exp, cm);
   res += okS ? "" : StringFormat(" | sell error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   Event(StringFormat("ORDERS PLACED | %s | BUY STOP %s SL %s TP %s (BE at %s) | SELL STOP %s SL %s TP %s (BE at %s) | lot %.2f, risk per side $%.2f / $%.2f%s",
                      rng, P(bIn), P(bSl), P(bTp), P(bIn + InpBeR * bR), P(sIn), P(sSl), P(sTp), P(sIn - InpBeR * sR),
                      lot, bR * lot * 100, sR * lot * 100, res));
}

//--- report positions that closed (TP / SL / BE) -------------------
void ReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1; long dtype = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); dtype = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = (reason == DEAL_REASON_TP) ? "TP HIT" : (reason == DEAL_REASON_SL) ? (MathAbs(outPx - inPx) <= 0.2 ? "BREAKEVEN" : "SL HIT") : "CLOSED";
   Event(StringFormat("%s | %s from %s closed at %s, profit $%.2f", what, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL", P(inPx), P(outPx), profit));
}

void Manage(datetime now, datetime day)
{
   // OCO, breakeven, list of open tickets
   ulong open[]; ArrayResize(open, 0);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic || PositionGetString(POSITION_SYMBOL) != InpSymbol) continue;
      int k = ArraySize(open); ArrayResize(open, k + 1); open[k] = t;
      bool isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      double op = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      bool known = false;
      for(int j = 0; j < ArraySize(g_known); j++) if(g_known[j] == t) known = true;
      if(!known)
      {
         int m = ArraySize(g_known); ArrayResize(g_known, m + 1); g_known[m] = t;
         Event(StringFormat("POSITION OPEN | %s %.2f lot from %s, SL %s, TP %s", isBuy ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME), P(op), P(sl), P(tp)));
      }
      if(CountOrders() > 0) DeletePending("the other side filled");
      double risk = MathAbs(op - sl);
      if(sl > 0 && risk > InpBuffer + 0.05)                 // breakeven not done yet
      {
         MqlTick tk; SymbolInfoTick(InpSymbol, tk);
         double be = isBuy ? op + InpBeR * risk : op - InpBeR * risk;
         if((isBuy && tk.bid >= be) || (!isBuy && tk.ask <= be))
         {
            double nsl = N(isBuy ? op + InpBuffer : op - InpBuffer);
            if(trade.PositionModify(t, nsl, tp)) Event(StringFormat("SL MOVED TO ENTRY | price reached %s (1.5R), SL now %s, TP %s", P(be), P(nsl), P(tp)));
            else Event(StringFormat("ERROR | SL move failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         }
      }
   }
   // closed since the last check
   for(int j = ArraySize(g_known) - 1; j >= 0; j--)
   {
      bool still = false;
      for(int k = 0; k < ArraySize(open); k++) if(open[k] == g_known[j]) still = true;
      if(!still) { ReportClosed(g_known[j]); ArrayRemove(g_known, j, 1); }
   }
   // close hour
   MqlDateTime s; TimeToStruct(now, s);
   if(s.hour >= InpCloseHour)
   {
      for(int k = 0; k < ArraySize(open); k++)
         if(trade.PositionClose(open[k])) { /* reported by ReportClosed on the next check */ }
         else Event(StringFormat("ERROR | close at %02d:00 failed: %d %s", InpCloseHour, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      if(CountOrders() > 0) DeletePending(StringFormat("%02d:00, no breakout", InpCloseHour));
   }
}

//--- main ----------------------------------------------------------
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(InpSymbol);
   trade.SetDeviationInPoints(50);
   SymbolSelect(InpSymbol, true);
   EventSetTimer(2);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

bool g_started = false;
void OnTimer()
{
   if(!TerminalInfoInteger(TERMINAL_CONNECTED)) return;
   if(InpDemoOnly && AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
   {
      if(!g_started) { g_started = true; Event("STOPPED | this is not a demo account; the EA only trades demo accounts"); }
      return;
   }
   datetime now = TimeCurrent(), day = DayStart(now);
   MqlDateTime s; TimeToStruct(now, s);
   if(!g_started)
   {
      g_started = true;
      // remember the positions already open so their closes are reported too
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong t = PositionGetTicket(i);
         if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic) { int m = ArraySize(g_known); ArrayResize(g_known, m + 1); g_known[m] = t; }
      }
      Event(StringFormat("STARTED | server time %s, %d open position(s), %d pending order(s), lot %.2f",
                         TimeToString(now, TIME_DATE | TIME_MINUTES), CountPositions(), CountOrders(), VolumeOk(InpLot)));
   }
   RsiOnTimer();                                                            // 24/7 (BTCUSD trades at weekends)
   if(s.day_of_week == 0 || s.day_of_week == 6) return;
   int minute = s.hour * 60 + s.min;
   if(minute >= InpRangeEnd * 60 && minute < InpRangeEnd * 60 + InpLateMin && CountOrders() == 0 && CountPositions() == 0 && !TradedToday(day))
      PlaceOrders(day);
   Manage(now, day);
   // heartbeat for the workflow: server time and whether the day is finished
   int h = FileOpen("flb_state.txt", FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(h != INVALID_HANDLE)
   {
      bool done = (s.hour >= InpCloseHour && CountOrders() == 0 && CountPositions() == 0);
      FileWriteString(h, StringFormat("%s|%d|%d|%d\r\n", TimeToString(now, TIME_DATE | TIME_SECONDS), CountPositions(), CountOrders(), done ? 1 : 0));
      FileClose(h);
   }
}
//+------------------------------------------------------------------+
