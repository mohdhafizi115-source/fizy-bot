//+------------------------------------------------------------------+
//| FizyNR7.mqh - NR7 breakout (Toby Crabel) on D1, demo only,        |
//| included by FizyLB.mq5. Rules (research/nr7.py, Yahoo 2004-2026): |
//|   yesterday's daily range is the narrowest of the last 7 days ->  |
//|   today: BUY STOP at yesterday's high, SELL STOP at yesterday's   |
//|   low (OCO). SL at the other side of yesterday's range, no TP.    |
//|   Close the position at the start of the next day (hold 1 day).   |
//|   One setup = one entry, fixed lot.                               |
//| If today already traded through a level before the orders could  |
//| be placed (e.g. after a restart), the day is skipped.             |
//| Events go to MQL5\Files\nr7_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input string InpNr7Symbols = "BTCUSD,USDJPY,EURJPY,GBPJPY,XAUUSD,AUDJPY,GBPUSD";
input bool   InpNr7On      = true;
input double InpNr7Lot     = 0.01;
input long   InpNr7Magic   = 260310;

string   n_sym[];
datetime n_day[];          // D1 bar handled per symbol (orders placed or skipped)
ulong    n_known[];
bool     n_ready = false;
datetime n_lastRun = 0;

void Nr7Event(string msg)
{
   int h = FileOpen("nr7_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("nr7 event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("NR7 EVENT ", msg);
}

void Nr7Init()
{
   string parts[];
   int n = StringSplit(InpNr7Symbols, ',', parts);
   string missing = "";
   for(int i = 0; i < n; i++)
   {
      string b = parts[i]; StringTrimLeft(b); StringTrimRight(b);
      if(b == "") continue;
      string s = RsiResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ", ") + b; continue; }
      SymbolSelect(s, true);
      int k = ArraySize(n_sym); ArrayResize(n_sym, k + 1); ArrayResize(n_day, k + 1);
      n_sym[k] = s; n_day[k] = 0;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpNr7Magic) { int m = ArraySize(n_known); ArrayResize(n_known, m + 1); n_known[m] = t; }
   }
   n_ready = true;
   Nr7Event(StringFormat("NR7 ONLINE | %d symbols on D1 (%s), lot %.2f, %d open NR7 position(s)%s", ArraySize(n_sym), InpNr7Symbols, InpNr7Lot,
                         ArraySize(n_known), missing == "" ? "" : " | not found: " + missing));
}

double Nr7Lot(string s)
{
   double mn = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   return NormalizeDouble(MathMax(mn, MathFloor(InpNr7Lot / st + 1e-9) * st), 2);
}

void Nr7Trade(bool on) { trade.SetExpertMagicNumber(on ? InpNr7Magic : InpMagic); }

int Nr7Orders(string s)
{
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpNr7Magic && OrderGetString(ORDER_SYMBOL) == s) c++;
   }
   return c;
}

bool Nr7Position(string s, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpNr7Magic && PositionGetString(POSITION_SYMBOL) == s) { ticket = t; return true; }
   }
   return false;
}

// any NR7 order or deal for this symbol since the start of the given D1 bar
bool Nr7TradedSince(string s, datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == InpNr7Magic && HistoryOrderGetString(t, ORDER_SYMBOL) == s) return true;
   }
   return false;
}

void Nr7DeletePending(string s, string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpNr7Magic || OrderGetString(ORDER_SYMBOL) != s) continue;
      string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      if(trade.OrderDelete(t)) Nr7Event(StringFormat("NR7 ORDER DELETED %s | %s %s deleted (%s)", s, side, RsiP(s, pr), why));
   }
}

void Nr7ReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "NR7 SL HIT" : (reason == DEAL_REASON_EXPERT ? "NR7 CLOSED" : "NR7 CLOSED");
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_EXPERT ? "1 day held, closed at the new day" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(s, PERIOD_H4, "N7X", lv, lc, lb, 0, 0, 0, 0, false);
   Nr7Event(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, s, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         RsiP(s, inPx), RsiP(s, outPx), why, profit) + Img(fn));
}

void Nr7OnTimer()
{
   if(!InpNr7On) return;
   if(!n_ready) Nr7Init();
   datetime now = TimeCurrent();
   if(now - n_lastRun < 10) return;
   n_lastRun = now;
   // closes since the last check (SL hits, day-end closes)
   for(int j = ArraySize(n_known) - 1; j >= 0; j--)
      if(!PositionSelectByTicket(n_known[j])) { Nr7ReportClosed(n_known[j]); ArrayRemove(n_known, j, 1); }
   Nr7Trade(true);
   for(int k = 0; k < ArraySize(n_sym); k++)
   {
      string s = n_sym[k];
      MqlTick tk;
      if(!SymbolInfoTick(s, tk) || now - tk.time > 600) continue;          // market closed
      datetime d0 = iTime(s, PERIOD_D1, 0);
      if(d0 == 0) continue;
      // 1. positions: OCO and the 1-day exit
      ulong pt;
      if(Nr7Position(s, pt))
      {
         bool known = false;
         for(int q = 0; q < ArraySize(n_known); q++) if(n_known[q] == pt) known = true;
         if(!known)
         {
            int m = ArraySize(n_known); ArrayResize(n_known, m + 1); n_known[m] = pt;
            PositionSelectByTicket(pt);
            Nr7Event(StringFormat("NR7 FILLED %s | %s %.2f lot from %s, SL %s, no TP: closes at the start of the next day",
                     s, PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME),
                     RsiP(s, PositionGetDouble(POSITION_PRICE_OPEN)), RsiP(s, PositionGetDouble(POSITION_SL))));
         }
         if(Nr7Orders(s) > 0) Nr7DeletePending(s, "the other side filled");
         PositionSelectByTicket(pt);
         if((datetime)PositionGetInteger(POSITION_TIME) < d0)                  // opened on an earlier day: hold is over
            if(!trade.PositionClose(pt)) Nr7Event(StringFormat("ERROR | NR7 day-end close %s failed: %d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         continue;
      }
      // 2. old pending orders from an earlier day expire
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong t = OrderGetTicket(i);
         if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpNr7Magic && OrderGetString(ORDER_SYMBOL) == s && (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0)
            Nr7DeletePending(s, "day over, no breakout");
      }
      // 3. new day: is yesterday an NR7 day?
      if(n_day[k] == d0) continue;
      n_day[k] = d0;
      if(Nr7Orders(s) > 0 || Nr7TradedSince(s, d0)) continue;               // already done today (restart)
      MqlRates r[];
      if(CopyRates(s, PERIOD_D1, 1, 7, r) < 7) { n_day[k] = 0; continue; }   // history not loaded yet: retry
      double rg = r[6].high - r[6].low, mn = rg;
      for(int i = 0; i < 6; i++) mn = MathMin(mn, r[i].high - r[i].low);
      if(rg <= 0 || rg > mn) continue;                                       // not an NR7 day
      double hi = r[6].high, lo = r[6].low;
      double th = iHigh(s, PERIOD_D1, 0), tl = iLow(s, PERIOD_D1, 0);
      if(th >= hi || tl <= lo)
      {
         if(now - d0 > 300) { Nr7Event(StringFormat("NR7 SKIPPED %s | yesterday was NR7 (%s - %s) but today already traded through a level before the orders were placed", s, RsiP(s, hi), RsiP(s, lo))); continue; }
      }
      double lot = Nr7Lot(s);
      string cm = "NR7 " + TimeToString(d0, TIME_DATE);
      int em = (int)SymbolInfoInteger(s, SYMBOL_EXPIRATION_MODE);
      ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
      datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + 86400 - 60 : 0;
      trade.SetTypeFillingBySymbol(s);
      string res = "";
      bool okB = (tk.ask >= hi) ? trade.Buy(lot, s, 0, lo, 0, cm) : trade.BuyStop(lot, hi, s, lo, 0, tt, exp, cm);
      if(!okB) res += StringFormat(" | buy error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      bool marketBuy = okB && tk.ask >= hi;
      bool okS = true;
      if(!marketBuy)
      {
         okS = (tk.bid <= lo) ? trade.Sell(lot, s, 0, hi, 0, cm) : trade.SellStop(lot, lo, s, hi, 0, tt, exp, cm);
         if(!okS) res += StringFormat(" | sell error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      }
      double lv[2]; color lc[2]; string lb[2];
      lv[0] = hi; lc[0] = clrSeaGreen; lb[0] = "BUY STOP / sell SL"; lv[1] = lo; lc[1] = clrIndianRed; lb[1] = "SELL STOP / buy SL";
      string fn = Snap(s, PERIOD_D1, "N7", lv, lc, lb, 0, 0, 0, 0, false);
      Nr7Event(StringFormat("NR7 ORDERS PLACED %s | yesterday's range %s - %s was the narrowest of 7 days | BUY STOP %s (SL %s) / SELL STOP %s (SL %s), no TP, lot %.2f | "
                            "OCO; a filled trade closes at the start of the next day%s",
                            s, RsiP(s, lo), RsiP(s, hi), RsiP(s, hi), RsiP(s, lo), RsiP(s, lo), RsiP(s, hi), lot, res) + Img(fn));
   }
   Nr7Trade(false);
   trade.SetTypeFillingBySymbol(InpSymbol);
}
//+------------------------------------------------------------------+
