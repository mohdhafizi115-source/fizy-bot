//+------------------------------------------------------------------+
//| FizyDTJ.mqh - two USDJPY day trades, demo only, included by       |
//| FizyLB.mq5. Both passed research/daytrade.py on the broker's data |
//| twice (export to 30 Oct and to 2 Nov 2026):                       |
//|  PDHL   previous-day breakout: from 02:00 server OCO stops at      |
//|         yesterday's high and low, SL at yesterday's middle, TP 2R, |
//|         orders until 20:00, close 22:30 (PF 1.21, halves 1.23 /    |
//|         1.19, 0.72 trades a day). Skipped if the price is already  |
//|         outside yesterday's range when the orders would be placed. |
//|  NYCONT New York continuation: at 15:30 server trade the direction |
//|         of the 09:00-15:30 move, SL 1.5 x ATR(H1) (2 x M15 ATR),   |
//|         no TP, close 22:00 (PF 1.18, halves 1.16 / 1.20, 0.97 a    |
//|         day).                                                     |
//| Events go to MQL5\Files\dtj_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpDtjOn       = true;
input string InpDtjSymbol   = "USDJPY";
input double InpDtjLot      = 0.01;
input long   InpPdhlMagic   = 260315;
input long   InpNycMagic    = 260316;

string   dj_sym = "";
bool     dj_ready = false;
datetime dj_pdDay = 0, dj_nyDay = 0, dj_last = 0;
ulong    dj_known[];

void DtjEvent(string msg)
{
   int h = FileOpen("dtj_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("dtj event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("DTJ EVENT ", msg);
}

string DtjName(long magic) { return magic == InpPdhlMagic ? "PDHL" : "NYCONT"; }

int DtjOrders(long magic)
{
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == magic && OrderGetString(ORDER_SYMBOL) == dj_sym) c++;
   }
   return c;
}

bool DtjPosition(long magic, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == magic && PositionGetString(POSITION_SYMBOL) == dj_sym) { ticket = t; return true; }
   }
   return false;
}

bool DtjTradedSince(long magic, datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == magic && HistoryOrderGetString(t, ORDER_SYMBOL) == dj_sym) return true;
   }
   return false;
}

void DtjDeletePending(long magic, string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != magic || OrderGetString(ORDER_SYMBOL) != dj_sym) continue;
      string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      trade.SetExpertMagicNumber(magic);
      if(trade.OrderDelete(t)) DtjEvent(StringFormat("%s ORDER DELETED %s | %s %s deleted (%s)", DtjName(magic), dj_sym, side, PriceStr(dj_sym, pr), why));
      trade.SetExpertMagicNumber(InpMagic);
   }
}

double DtjLot()
{
   double mn = SymbolInfoDouble(dj_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(dj_sym, SYMBOL_VOLUME_STEP);
   return NormalizeDouble(MathMax(mn, MathFloor(InpDtjLot / sv + 1e-9) * sv), 2);
}

void DtjInit()
{
   dj_ready = true;
   dj_sym = SymResolve(InpDtjSymbol);
   if(dj_sym == "") { DtjEvent("ERROR | USDJPY day trades: symbol " + InpDtjSymbol + " not found"); return; }
   SymbolSelect(dj_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      long mg = PositionGetInteger(POSITION_MAGIC);
      if(t > 0 && (mg == InpPdhlMagic || mg == InpNycMagic)) { int m = ArraySize(dj_known); ArrayResize(dj_known, m + 1); dj_known[m] = t; }
   }
   DtjEvent(StringFormat("PDHL ONLINE | %s: from 02:00 server OCO stops at yesterday's high / low, SL at yesterday's middle, TP 2R, "
                         "orders until 20:00, close 22:30, lot %.2f", dj_sym, InpDtjLot));
   DtjEvent(StringFormat("NYCONT ONLINE | %s: at 15:30 server follow the 09:00-15:30 move, SL 1.5 x ATR(H1), no TP, close 22:00, "
                         "lot %.2f | %d open position(s)", dj_sym, InpDtjLot, ArraySize(dj_known)));
}

void DtjReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, dtype = -1, magic = 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      magic = HistoryDealGetInteger(d, DEAL_MAGIC);
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); dtype = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string nm = DtjName(magic);
   string what = reason == DEAL_REASON_TP ? nm + " TP HIT" : (reason == DEAL_REASON_SL ? nm + " SL HIT" : nm + " CLOSED");
   string why = reason == DEAL_REASON_TP ? "take profit 2R" : (reason == DEAL_REASON_SL ? "stop loss" :
                (reason == DEAL_REASON_EXPERT ? (nm == "PDHL" ? "22:30 day-end close" : "22:00 day-end close") : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(dj_sym, PERIOD_M15, nm == "PDHL" ? "PDX" : "NYX", lv, lc, lb, 0, 0, 0, 0, false);
   DtjEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, dj_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(dj_sym, inPx), PriceStr(dj_sym, outPx), why, profit) + Img(fn));
}

// a position of this magic: report the fill once, cancel the other OCO leg, close at the day-end minute
bool DtjManage(long magic, int closeMin, int minute, datetime d0)
{
   ulong pt;
   if(!DtjPosition(magic, pt)) return false;
   bool known = false;
   for(int q = 0; q < ArraySize(dj_known); q++) if(dj_known[q] == pt) known = true;
   if(!known)
   {
      int m = ArraySize(dj_known); ArrayResize(dj_known, m + 1); dj_known[m] = pt;
      PositionSelectByTicket(pt);
      double lv[3]; color lc[3]; string lb[3];
      lv[0] = PositionGetDouble(POSITION_PRICE_OPEN); lc[0] = clrBlue; lb[0] = "entry";
      lv[1] = PositionGetDouble(POSITION_SL); lc[1] = clrIndianRed; lb[1] = "SL";
      lv[2] = PositionGetDouble(POSITION_TP); lc[2] = clrSeaGreen; lb[2] = "TP";
      string fn = Snap(dj_sym, PERIOD_M15, magic == InpPdhlMagic ? "PDF" : "NYF", lv, lc, lb, 0, 0, 0, 0, false);
      PositionSelectByTicket(pt);
      double tp = PositionGetDouble(POSITION_TP);
      DtjEvent(StringFormat("%s FILLED %s | %s %.2f lot from %s, SL %s, %s: closes at %s server", DtjName(magic), dj_sym,
               PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME),
               PriceStr(dj_sym, PositionGetDouble(POSITION_PRICE_OPEN)), PriceStr(dj_sym, PositionGetDouble(POSITION_SL)),
               tp > 0 ? "TP " + PriceStr(dj_sym, tp) + " (2R)" : "no TP", magic == InpPdhlMagic ? "22:30" : "22:00") + Img(fn));
   }
   if(DtjOrders(magic) > 0) DtjDeletePending(magic, "the other side filled");
   PositionSelectByTicket(pt);
   if(minute >= closeMin || (datetime)PositionGetInteger(POSITION_TIME) < d0)
   {
      trade.SetExpertMagicNumber(magic); trade.SetTypeFillingBySymbol(dj_sym);
      if(!trade.PositionClose(pt)) DtjEvent(StringFormat("ERROR | %s close %s failed: %d %s", DtjName(magic), dj_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   }
   return true;
}

// ATR(14) of M15 with Wilder smoothing up to the last closed bar (the research uses 2 x this as ATR(H1))
double DtjAtr15()
{
   MqlRates r[];
   int n = CopyRates(dj_sym, PERIOD_M15, 1, 300, r);
   if(n < 50) return 0;
   double a = r[1].high - r[1].low;
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      a += (tr - a) / 14.0;
   }
   return a;
}

void DtjOnTimer()
{
   if(!InpDtjOn) return;
   if(!dj_ready) DtjInit();
   if(dj_sym == "") return;
   datetime now = TimeCurrent();
   if(now - dj_last < 2) return;
   dj_last = now;
   MqlDateTime st; TimeToStruct(now, st);
   int minute = st.hour * 60 + st.min;
   for(int q = ArraySize(dj_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(dj_known[q])) { DtjReportClosed(dj_known[q]); ArrayRemove(dj_known, q, 1); }
   MqlTick tk;
   if(!SymbolInfoTick(dj_sym, tk) || now - tk.time > 600) return;            // market closed
   datetime d0 = iTime(dj_sym, PERIOD_D1, 0);
   if(d0 == 0) return;
   bool weekday = st.day_of_week >= 1 && st.day_of_week <= 5;
   int dg = (int)SymbolInfoInteger(dj_sym, SYMBOL_DIGITS);

   // ---- PDHL
   if(!DtjManage(InpPdhlMagic, 1350, minute, d0))
   {
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong t = OrderGetTicket(i);
         if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpPdhlMagic && OrderGetString(ORDER_SYMBOL) == dj_sym &&
            (minute >= 1200 || (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0))
         { DtjDeletePending(InpPdhlMagic, "20:00, no breakout"); break; }
      }
      if(weekday && minute >= 120 && minute < 1200 && dj_pdDay != d0)
      {
         dj_pdDay = d0;
         double ph = iHigh(dj_sym, PERIOD_D1, 1), pl = iLow(dj_sym, PERIOD_D1, 1);
         if(ph <= pl) dj_pdDay = 0;                                         // history not loaded yet: retry
         else if(DtjOrders(InpPdhlMagic) == 0 && !DtjTradedSince(InpPdhlMagic, d0))
         {
            double mid = NormalizeDouble((ph + pl) / 2, dg);
            ph = NormalizeDouble(ph, dg); pl = NormalizeDouble(pl, dg);
            if(tk.ask >= ph || tk.bid <= pl)
               DtjEvent(StringFormat("PDHL SKIPPED %s | price already outside yesterday's range (%s - %s) at %s", dj_sym, PriceStr(dj_sym, pl),
                                     PriceStr(dj_sym, ph), TimeToString(now, TIME_MINUTES)));
            else
            {
               double tpb = NormalizeDouble(ph + 2 * (ph - mid), dg), tps = NormalizeDouble(pl - 2 * (mid - pl), dg);
               int em = (int)SymbolInfoInteger(dj_sym, SYMBOL_EXPIRATION_MODE);
               ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
               datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + 1200 * 60 : 0;
               string cm = "PDHL " + TimeToString(d0, TIME_DATE), res = "";
               double lot = DtjLot();
               trade.SetExpertMagicNumber(InpPdhlMagic); trade.SetTypeFillingBySymbol(dj_sym);
               if(!trade.BuyStop(lot, ph, dj_sym, mid, tpb, tt, exp, cm)) res += StringFormat(" | buy stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
               if(!trade.SellStop(lot, pl, dj_sym, mid, tps, tt, exp, cm)) res += StringFormat(" | sell stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
               trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
               double lv[5]; color lc[5]; string lb[5];
               lv[0] = tpb; lc[0] = clrBlue; lb[0] = "TP buy"; lv[1] = ph; lc[1] = clrSeaGreen; lb[1] = "BUY STOP (yesterday's high)";
               lv[2] = mid; lc[2] = clrGray; lb[2] = "SL (middle)"; lv[3] = pl; lc[3] = clrIndianRed; lb[3] = "SELL STOP (yesterday's low)";
               lv[4] = tps; lc[4] = clrBlue; lb[4] = "TP sell";
               string fn = Snap(dj_sym, PERIOD_M15, "PD", lv, lc, lb, 0, 0, 0, 0, false);
               DtjEvent(StringFormat("PDHL ORDERS PLACED %s | yesterday's high %s / low %s | BUY STOP %s (TP %s) / SELL STOP %s (TP %s), SL at the middle %s, "
                                     "lot %.2f | OCO; unfilled at 20:00 server = deleted; a trade closes at 22:30 server%s",
                                     dj_sym, PriceStr(dj_sym, ph), PriceStr(dj_sym, pl), PriceStr(dj_sym, ph), PriceStr(dj_sym, tpb),
                                     PriceStr(dj_sym, pl), PriceStr(dj_sym, tps), PriceStr(dj_sym, mid), lot, res) + Img(fn));
            }
         }
      }
   }

   // ---- NY continuation
   if(!DtjManage(InpNycMagic, 1320, minute, d0) && weekday && minute >= 930 && minute < 945 && dj_nyDay != d0)
   {
      dj_nyDay = d0;
      if(!DtjTradedSince(InpNycMagic, d0))
      {
         int s9 = iBarShift(dj_sym, PERIOD_M15, d0 + 9 * 3600, true), s15 = iBarShift(dj_sym, PERIOD_M15, d0 + 15 * 3600 + 15 * 60, true);
         double atr = DtjAtr15();
         if(s9 < 0 || s15 < 0 || atr <= 0) { dj_nyDay = 0; return; }                // bars not loaded yet: retry
         double o9 = iOpen(dj_sym, PERIOD_M15, s9), c15 = iClose(dj_sym, PERIOD_M15, s15), mv = c15 - o9;
         if(mv != 0)
         {
            int dr = mv > 0 ? 1 : -1;
            double px = dr > 0 ? tk.ask : tk.bid, sl = NormalizeDouble(px - dr * 1.5 * 2 * atr, dg);
            trade.SetExpertMagicNumber(InpNycMagic); trade.SetTypeFillingBySymbol(dj_sym);
            bool ok = dr > 0 ? trade.Buy(DtjLot(), dj_sym, 0, sl, 0, "NYCONT") : trade.Sell(DtjLot(), dj_sym, 0, sl, 0, "NYCONT");
            if(!ok) DtjEvent(StringFormat("ERROR | NYCONT %s order failed: %d %s", dj_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
            trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
            if(ok) DtjEvent(StringFormat("NYCONT SIGNAL %s | 09:00-15:30 move %s%s (from %s to %s): %s, SL %s (1.5 x ATR(H1))",
                                         dj_sym, mv > 0 ? "+" : "", DoubleToString(mv, dg), PriceStr(dj_sym, o9), PriceStr(dj_sym, c15),
                                         dr > 0 ? "BUY" : "SELL", PriceStr(dj_sym, sl)));
         }
      }
   }
}
//+------------------------------------------------------------------+
