//+------------------------------------------------------------------+
//| FizyATB.mqh - gold ATR open-band breakout, day trade, demo only,  |
//| included by FizyLB.mq5 (v2.26, 13 Nov 2026, round 107 / 107b,     |
//| the owner: "pasang no 1").                                        |
//| Rules (research/atr107b.py, the small-risk cell):                 |
//|   at 01:30 server take the open of that M1 bar; ATR = the mean    |
//|   true range of the last 14 completed D1 bars; place OCO stops at |
//|   open +- 0.25 x ATR (BUY STOP above, SELL STOP below), SL half   |
//|   way back to the open (0.5 x the band), no TP, one trade a day.  |
//|   Unfilled orders are deleted and a filled trade is closed at     |
//|   23:30 server. Skip the day if a level was already touched       |
//|   before the orders could be placed (the first touch is gone).    |
//|   Obeys the daily target: no orders, and pending ones deleted.    |
//| Round 107b at 0.01 lot, last 2 years: 506 trades (4.9 a week),    |
//| PF 1.34, years 1.41 / 1.31, +$1,347, risk about $10 a trade, max  |
//| drawdown -$268, worst day -$36, 18 of 25 months positive; k 0.15- |
//| 0.6 all PF 1.27-1.41 (a plateau).                                 |
//| Events go to MQL5\Files\atb_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpAtbOn       = true;
input string InpAtbSymbol   = "XAUUSD";
input double InpAtbLot      = 0.01;
input long   InpAtbMagic    = 260328;
input double InpAtbK        = 0.25;     // band = k x ATR(D1) from the 01:30 open
input double InpAtbSlFrac   = 0.5;      // SL distance = this share of the band (1.0 = back at the open)
input int    InpAtbAtrN     = 14;       // D1 bars in the ATR
input int    InpAtbStartMin = 90;       // 01:30 server: anchor and order time
input int    InpAtbEndMin   = 1410;     // 23:30 server: unfilled orders deleted, a trade closed

string   ab_sym = "";
datetime ab_day = 0;                    // day the orders were handled
ulong    ab_known[];
bool     ab_ready = false;
datetime ab_last = 0;

void AtbEvent(string msg)
{
   int h = FileOpen("atb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("ATR band event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("ATRBO EVENT ", msg);
}

int AtbOrders()
{
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpAtbMagic && OrderGetString(ORDER_SYMBOL) == ab_sym) c++;
   }
   return c;
}

bool AtbPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpAtbMagic && PositionGetString(POSITION_SYMBOL) == ab_sym) { ticket = t; return true; }
   }
   return false;
}

bool AtbTradedSince(datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == InpAtbMagic && HistoryOrderGetString(t, ORDER_SYMBOL) == ab_sym) return true;
   }
   return false;
}

void AtbDeletePending(string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpAtbMagic || OrderGetString(ORDER_SYMBOL) != ab_sym) continue;
      string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      trade.SetExpertMagicNumber(InpAtbMagic);
      if(trade.OrderDelete(t)) AtbEvent(StringFormat("ATRBO ORDER DELETED %s | %s %s deleted (%s)", ab_sym, side, PriceStr(ab_sym, pr), why));
      trade.SetExpertMagicNumber(InpMagic);
   }
}

// mean true range of the last n completed D1 bars (as research/atr107b.py), 0 if the history is not loaded
double AtbAtr(int n)
{
   double s = 0;
   for(int i = 1; i <= n; i++)
   {
      double h = iHigh(ab_sym, PERIOD_D1, i), l = iLow(ab_sym, PERIOD_D1, i), pc = iClose(ab_sym, PERIOD_D1, i + 1);
      if(h <= 0 || l <= 0 || pc <= 0) return 0;
      s += MathMax(h, pc) - MathMin(l, pc);
   }
   return s / n;
}

void AtbInit()
{
   ab_sym = SymResolve(InpAtbSymbol);
   ab_ready = true;
   if(ab_sym == "") { AtbEvent("ERROR | ATR band breakout: symbol " + InpAtbSymbol + " not found"); return; }
   SymbolSelect(ab_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpAtbMagic) { int m = ArraySize(ab_known); ArrayResize(ab_known, m + 1); ab_known[m] = t; }
   }
   AtbEvent(StringFormat("ATRBO ONLINE | %s: day trade, at 01:30 server OCO stops at the 01:30 open +- %.2f x ATR%d(D1), SL %.0f%% of the band "
                         "back toward the open, no TP, one trade a day, orders deleted and the trade closed at 23:30 server, lot %.2f | %d open position(s)",
                         ab_sym, InpAtbK, InpAtbAtrN, 100 * InpAtbSlFrac, InpAtbLot, ArraySize(ab_known)));
}

void AtbReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, dtype = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); dtype = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = reason == DEAL_REASON_SL ? "ATRBO SL HIT" : "ATRBO CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss half way to the open" : (reason == DEAL_REASON_EXPERT ? "23:30 day-end close" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(ab_sym, PERIOD_M15, "ABX", lv, lc, lb, 0, 0, 0, 0, false);
   AtbEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, ab_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(ab_sym, inPx), PriceStr(ab_sym, outPx), why, profit) + Img(fn));
}

void AtbOnTimer()
{
   if(!InpAtbOn) return;
   if(!ab_ready) AtbInit();
   if(ab_sym == "") return;
   datetime now = TimeCurrent();
   if(now - ab_last < 2) return;
   ab_last = now;
   MqlDateTime st; TimeToStruct(now, st);
   int minute = st.hour * 60 + st.min;
   for(int q = ArraySize(ab_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(ab_known[q])) { AtbReportClosed(ab_known[q]); ArrayRemove(ab_known, q, 1); }
   MqlTick tk;
   if(!SymbolInfoTick(ab_sym, tk) || now - tk.time > 600) return;          // market closed
   datetime d0 = iTime(ab_sym, PERIOD_D1, 0);
   if(d0 == 0) return;
   ulong pt;
   if(AtbPosition(pt))
   {
      bool known = false;
      for(int q = 0; q < ArraySize(ab_known); q++) if(ab_known[q] == pt) known = true;
      if(!known)
      {
         int m = ArraySize(ab_known); ArrayResize(ab_known, m + 1); ab_known[m] = pt;
         PositionSelectByTicket(pt);
         double lvf[2]; color lcf[2]; string lbf[2];
         lvf[0] = PositionGetDouble(POSITION_PRICE_OPEN); lcf[0] = clrBlue; lbf[0] = "entry";
         lvf[1] = PositionGetDouble(POSITION_SL); lcf[1] = clrIndianRed; lbf[1] = "SL";
         string fnf = Snap(ab_sym, PERIOD_M15, "ABF", lvf, lcf, lbf, 0, 0, 0, 0, false);
         PositionSelectByTicket(pt);
         AtbEvent(StringFormat("ATRBO FILLED %s | %s %.2f lot from %s, SL %s (half way to the open), no TP: closes at 23:30 server",
                  ab_sym, PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME),
                  PriceStr(ab_sym, PositionGetDouble(POSITION_PRICE_OPEN)), PriceStr(ab_sym, PositionGetDouble(POSITION_SL))) + Img(fnf));
      }
      if(AtbOrders() > 0) AtbDeletePending("the other side filled");
      PositionSelectByTicket(pt);
      if(minute >= InpAtbEndMin || (datetime)PositionGetInteger(POSITION_TIME) < d0)
      {
         trade.SetExpertMagicNumber(InpAtbMagic); trade.SetTypeFillingBySymbol(ab_sym);
         if(!trade.PositionClose(pt)) AtbEvent(StringFormat("ERROR | ATR band close %s failed: %d %s", ab_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;
   }
   // pending orders: delete at 23:30, when left from an earlier day, or once the daily target is reached
   if(AtbOrders() > 0)
   {
      bool old = false;
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong t = OrderGetTicket(i);
         if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpAtbMagic && OrderGetString(ORDER_SYMBOL) == ab_sym &&
            (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0) old = true;
      }
      if(minute >= InpAtbEndMin || old) AtbDeletePending("23:30, no breakout");
      else if(DayPaused()) AtbDeletePending("daily target reached");
      return;
   }
   if(st.day_of_week == 0 || st.day_of_week == 6 || minute < InpAtbStartMin || minute >= InpAtbEndMin - 30) return;
   if(ab_day == d0) return;
   if(AtbTradedSince(d0)) { ab_day = d0; return; }                          // already done today (restart)
   if(DayPaused()) return;                                                   // checked again later today
   // the anchor: the first M1 bar at or after 01:30 server
   MqlRates r[];
   datetime a0 = d0 + InpAtbStartMin * 60;
   int nb = CopyRates(ab_sym, PERIOD_M1, a0, now, r);
   if(nb <= 0 || r[0].time - a0 > 1800) return;                              // M1 history not there yet: retry
   double A = AtbAtr(InpAtbAtrN);
   if(A <= 0) return;                                                        // D1 history not loaded yet: retry
   ab_day = d0;
   int dg = (int)SymbolInfoInteger(ab_sym, SYMBOL_DIGITS);
   double O = r[0].open, band = InpAtbK * A;
   double up = NormalizeDouble(O + band, dg), dn = NormalizeDouble(O - band, dg);
   double slu = NormalizeDouble(up - InpAtbSlFrac * band, dg), sld = NormalizeDouble(dn + InpAtbSlFrac * band, dg);
   double hi = 0, lo = 0;
   for(int i = 0; i < nb; i++) { if(i == 0 || r[i].high > hi) hi = r[i].high; if(i == 0 || r[i].low < lo) lo = r[i].low; }
   if(hi + SymbolInfoDouble(ab_sym, SYMBOL_POINT) * r[nb - 1].spread >= up || lo <= dn || tk.ask >= up || tk.bid <= dn)
   {
      AtbEvent(StringFormat("ATRBO SKIPPED %s | a level (%s / %s) was already touched before the orders could be placed", ab_sym, PriceStr(ab_sym, up), PriceStr(ab_sym, dn)));
      return;
   }
   double mn = SymbolInfoDouble(ab_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(ab_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpAtbLot / sv + 1e-9) * sv), 2);
   int em = (int)SymbolInfoInteger(ab_sym, SYMBOL_EXPIRATION_MODE);
   ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + InpAtbEndMin * 60 + 300 : 0;   // backup: the EA deletes (and reports) at 23:30
   string cm = "ATRBO " + TimeToString(d0, TIME_DATE), res = "";
   trade.SetExpertMagicNumber(InpAtbMagic); trade.SetTypeFillingBySymbol(ab_sym);
   if(!trade.BuyStop(lot, up, ab_sym, slu, 0, tt, exp, cm)) res += StringFormat(" | buy stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   if(!trade.SellStop(lot, dn, ab_sym, sld, 0, tt, exp, cm)) res += StringFormat(" | sell stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   double lv[5]; color lc[5]; string lb[5];
   lv[0] = up; lc[0] = clrSeaGreen; lb[0] = "BUY STOP"; lv[1] = slu; lc[1] = clrIndianRed; lb[1] = "buy SL";
   lv[2] = O; lc[2] = clrGray; lb[2] = "01:30 open"; lv[3] = sld; lc[3] = clrIndianRed; lb[3] = "sell SL";
   lv[4] = dn; lc[4] = clrSeaGreen; lb[4] = "SELL STOP";
   string fn = Snap(ab_sym, PERIOD_M15, "AB", lv, lc, lb, 0, 0, 0, 0, false);
   AtbEvent(StringFormat("ATRBO ORDERS PLACED %s | 01:30 open %s, ATR%d(D1) %s, band %.2f x ATR = %s | BUY STOP %s (SL %s) / SELL STOP %s (SL %s), "
                         "no TP, lot %.2f, risk about $%.2f | OCO; unfilled at 23:30 server = deleted; a trade closes at 23:30 server%s",
                         ab_sym, PriceStr(ab_sym, O), InpAtbAtrN, PriceStr(ab_sym, A), InpAtbK, PriceStr(ab_sym, band),
                         PriceStr(ab_sym, up), PriceStr(ab_sym, slu), PriceStr(ab_sym, dn), PriceStr(ab_sym, sld), lot,
                         InpAtbSlFrac * band * SymbolInfoDouble(ab_sym, SYMBOL_TRADE_TICK_VALUE) / SymbolInfoDouble(ab_sym, SYMBOL_TRADE_TICK_SIZE) * lot, res) + Img(fn));
}
//+------------------------------------------------------------------+
