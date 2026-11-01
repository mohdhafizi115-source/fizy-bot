//+------------------------------------------------------------------+
//| FizyWVB.mqh - Larry Williams volatility breakout, day trade, demo  |
//| only, included by FizyLB.mq5. Rules (research/daytrade.py,        |
//| JustMarkets 2020-2026, k = 0.7: USDJPY PF 1.27, XAUUSD 1.19,      |
//| EURJPY 1.18, GBPJPY 1.17, both halves > 1.05):                    |
//|   at 01:30 server time place OCO stops at today's open +- 0.7 x   |
//|   yesterday's range (BUY STOP above, SELL STOP below), SL at       |
//|   today's open, no TP. Orders stay until 20:00 server; a filled    |
//|   trade closes at 22:30 server. Skip the day if the price is       |
//|   already beyond a level when the orders would be placed.          |
//| Events go to MQL5\Files\wvb_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input string InpWvbSymbols  = "USDJPY,EURJPY,GBPJPY,XAUUSD";
input bool   InpWvbOn       = true;
input double InpWvbLot      = 0.01;
input long   InpWvbMagic    = 260314;
input double InpWvbK        = 0.7;
input int    InpWvbStartMin = 90;      // 01:30 server
input int    InpWvbOrderEnd = 1200;    // 20:00 server: unfilled orders deleted
input int    InpWvbCloseMin = 1350;    // 22:30 server: positions closed

string   wv_sym[];
datetime wv_day[];
ulong    wv_known[];
bool     wv_ready = false;
datetime wv_last = 0;

void WvbEvent(string msg)
{
   int h = FileOpen("wvb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("volatility breakout event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("VOLBO EVENT ", msg);
}

int WvbOrders(string s)
{
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpWvbMagic && OrderGetString(ORDER_SYMBOL) == s) c++;
   }
   return c;
}

bool WvbPosition(string s, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpWvbMagic && PositionGetString(POSITION_SYMBOL) == s) { ticket = t; return true; }
   }
   return false;
}

bool WvbTradedSince(string s, datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == InpWvbMagic && HistoryOrderGetString(t, ORDER_SYMBOL) == s) return true;
   }
   return false;
}

void WvbDeletePending(string s, string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpWvbMagic || OrderGetString(ORDER_SYMBOL) != s) continue;
      string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      trade.SetExpertMagicNumber(InpWvbMagic);
      if(trade.OrderDelete(t)) WvbEvent(StringFormat("VOLBO ORDER DELETED %s | %s %s deleted (%s)", s, side, PriceStr(s, pr), why));
      trade.SetExpertMagicNumber(InpMagic);
   }
}

void WvbInit()
{
   string parts[];
   int n = StringSplit(InpWvbSymbols, ',', parts);
   string names = "", missing = "";
   for(int i = 0; i < n; i++)
   {
      string b = parts[i]; StringTrimLeft(b); StringTrimRight(b);
      if(b == "") continue;
      string s = SymResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ", ") + b; continue; }
      SymbolSelect(s, true);
      int k = ArraySize(wv_sym); ArrayResize(wv_sym, k + 1); ArrayResize(wv_day, k + 1);
      wv_sym[k] = s; wv_day[k] = 0; names += (names == "" ? "" : ", ") + s;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpWvbMagic) { int m = ArraySize(wv_known); ArrayResize(wv_known, m + 1); wv_known[m] = t; }
   }
   wv_ready = true;
   WvbEvent(StringFormat("VOLBO ONLINE | %s: day trade, at 01:30 server OCO stops at today's open +- %.1f x yesterday's range, SL at the open, "
                         "orders until 20:00, close 22:30 server, lot %.2f | %d open position(s)%s", names, InpWvbK, InpWvbLot,
                         ArraySize(wv_known), missing == "" ? "" : " | not found: " + missing));
}

void WvbReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "VOLBO SL HIT" : "VOLBO CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss at today's open" : (reason == DEAL_REASON_EXPERT ? "22:30 day-end close" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(s, PERIOD_M15, "WVX", lv, lc, lb, 0, 0, 0, 0, false);
   WvbEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, s, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(s, inPx), PriceStr(s, outPx), why, profit) + Img(fn));
}

void WvbOnTimer()
{
   if(!InpWvbOn) return;
   if(!wv_ready) WvbInit();
   datetime now = TimeCurrent();
   if(now - wv_last < 5) return;
   wv_last = now;
   MqlDateTime st; TimeToStruct(now, st);
   int minute = st.hour * 60 + st.min;
   for(int q = ArraySize(wv_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(wv_known[q])) { WvbReportClosed(wv_known[q]); ArrayRemove(wv_known, q, 1); }
   for(int k = 0; k < ArraySize(wv_sym); k++)
   {
      string s = wv_sym[k];
      MqlTick tk;
      if(!SymbolInfoTick(s, tk) || now - tk.time > 600) continue;            // market closed
      datetime d0 = iTime(s, PERIOD_D1, 0);
      if(d0 == 0) continue;
      ulong pt;
      if(WvbPosition(s, pt))
      {
         bool known = false;
         for(int q = 0; q < ArraySize(wv_known); q++) if(wv_known[q] == pt) known = true;
         if(!known)
         {
            int m = ArraySize(wv_known); ArrayResize(wv_known, m + 1); wv_known[m] = pt;
            PositionSelectByTicket(pt);
            double lvf[2]; color lcf[2]; string lbf[2];
            lvf[0] = PositionGetDouble(POSITION_PRICE_OPEN); lcf[0] = clrBlue; lbf[0] = "entry";
            lvf[1] = PositionGetDouble(POSITION_SL); lcf[1] = clrIndianRed; lbf[1] = "SL (open)";
            string fnf = Snap(s, PERIOD_M15, "WVF", lvf, lcf, lbf, 0, 0, 0, 0, false);
            PositionSelectByTicket(pt);
            WvbEvent(StringFormat("VOLBO FILLED %s | %s %.2f lot from %s, SL %s (today's open), no TP: closes at 22:30 server",
                     s, PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME),
                     PriceStr(s, PositionGetDouble(POSITION_PRICE_OPEN)), PriceStr(s, PositionGetDouble(POSITION_SL))) + Img(fnf));
         }
         if(WvbOrders(s) > 0) WvbDeletePending(s, "the other side filled");
         PositionSelectByTicket(pt);
         if(minute >= InpWvbCloseMin || (datetime)PositionGetInteger(POSITION_TIME) < d0)
         {
            trade.SetExpertMagicNumber(InpWvbMagic); trade.SetTypeFillingBySymbol(s);
            if(!trade.PositionClose(pt)) WvbEvent(StringFormat("ERROR | volatility breakout close %s failed: %d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
            trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         }
         continue;
      }
      // unfilled orders: delete at 20:00 or when left from an earlier day
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong t = OrderGetTicket(i);
         if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpWvbMagic && OrderGetString(ORDER_SYMBOL) == s &&
            (minute >= InpWvbOrderEnd || (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0))
         { WvbDeletePending(s, "20:00, no breakout"); break; }
      }
      if(st.day_of_week == 0 || st.day_of_week == 6 || minute < InpWvbStartMin || minute >= InpWvbOrderEnd) continue;
      if(wv_day[k] == d0) continue;
      wv_day[k] = d0;
      if(WvbOrders(s) > 0 || WvbTradedSince(s, d0)) continue;                  // already done today (restart)
      double O = iOpen(s, PERIOD_D1, 0), ph = iHigh(s, PERIOD_D1, 1), pl = iLow(s, PERIOD_D1, 1);
      double th = iHigh(s, PERIOD_D1, 0), tl = iLow(s, PERIOD_D1, 0);
      if(O <= 0 || ph <= pl) { wv_day[k] = 0; continue; }                     // history not loaded yet: retry
      double rg = ph - pl, up = O + InpWvbK * rg, dn = O - InpWvbK * rg;
      int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
      up = NormalizeDouble(up, dg); dn = NormalizeDouble(dn, dg); O = NormalizeDouble(O, dg);
      if(th >= up || tl <= dn || tk.ask >= up || tk.bid <= dn)
      { WvbEvent(StringFormat("VOLBO SKIPPED %s | price already beyond a level (%s / %s) before the orders were placed", s, PriceStr(s, up), PriceStr(s, dn))); continue; }
      double mn = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
      double lot = NormalizeDouble(MathMax(mn, MathFloor(InpWvbLot / sv + 1e-9) * sv), 2);
      int em = (int)SymbolInfoInteger(s, SYMBOL_EXPIRATION_MODE);
      ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
      datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + InpWvbOrderEnd * 60 : 0;
      string cm = "VOLBO " + TimeToString(d0, TIME_DATE), res = "";
      trade.SetExpertMagicNumber(InpWvbMagic); trade.SetTypeFillingBySymbol(s);
      if(!trade.BuyStop(lot, up, s, O, 0, tt, exp, cm)) res += StringFormat(" | buy stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      if(!trade.SellStop(lot, dn, s, O, 0, tt, exp, cm)) res += StringFormat(" | sell stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      double lv[3]; color lc[3]; string lb[3];
      lv[0] = up; lc[0] = clrSeaGreen; lb[0] = "BUY STOP"; lv[1] = O; lc[1] = clrGray; lb[1] = "open / SL"; lv[2] = dn; lc[2] = clrIndianRed; lb[2] = "SELL STOP";
      string fn = Snap(s, PERIOD_M15, "WV", lv, lc, lb, 0, 0, 0, 0, false);
      WvbEvent(StringFormat("VOLBO ORDERS PLACED %s | today's open %s, yesterday's range %s | BUY STOP %s / SELL STOP %s, SL at the open, no TP, "
                            "lot %.2f | OCO; unfilled at 20:00 server = deleted; a trade closes at 22:30 server%s",
                            s, PriceStr(s, O), PriceStr(s, rg), PriceStr(s, up), PriceStr(s, dn), lot, res) + Img(fn));
   }
}
//+------------------------------------------------------------------+
