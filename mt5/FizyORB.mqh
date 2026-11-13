//+------------------------------------------------------------------+
//| FizyORB.mqh - gold early-session range breakout (GOLD_ORB, a free |
//| MQL5 / GitHub EA), day trade, demo only, included by FizyLB.mq5   |
//| (v2.29, 14 Nov 2026, rounds 112 / 112b, the owner: "pasang bro.   |
//| yang sedia ada kekalkan").                                        |
//| Rules (research/mql5ea112b.py, the chosen cell):                  |
//|   range = high / low of the M1 bars 01:00-03:59 server; at 04:00  |
//|   a BUY STOP at the range high and a SELL STOP at the range low,  |
//|   each once a day (both can fill, not OCO); SL 0.25 x ATR14(D1)   |
//|   (mean true range of the last 14 completed D1 bars), TP 2 x SL;  |
//|   unfilled orders deleted and open trades closed at 23:30 server. |
//|   A side whose level was already touched after 04:00 before the   |
//|   order could be placed is skipped (late start). Obeys the daily  |
//|   target: no orders, and pending ones deleted.                    |
//| Round 112b at 0.01 lot, last 2 years: 754 trades (7 a week), PF   |
//| 1.40, years 1.39 / 1.40, +$3,015, risk about $20 a trade, max     |
//| drawdown -$308, worst trade -$71; every cell of range 2-4 h x SL  |
//| 0.15-0.5 ATR x TP passes (PF 1.18-1.49). Daily P&L correlation    |
//| with FizyATB 0.52 (both trade most days).                         |
//| Events go to MQL5\Files\orb_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpOrbOn       = true;
input string InpOrbSymbol   = "XAUUSD";
input double InpOrbLot      = 0.01;
input long   InpOrbMagic    = 260331;
input int    InpOrbFromMin  = 60;       // 01:00 server: range start
input int    InpOrbToMin    = 240;      // 04:00 server: range end, orders placed
input double InpOrbSlAtr    = 0.25;     // SL = this x ATR14(D1)
input double InpOrbTpMult   = 2.0;      // TP = this x the SL distance
input int    InpOrbAtrN     = 14;
input int    InpOrbEndMin   = 1410;     // 23:30 server: orders deleted, trades closed

string   ob_sym = "";
datetime ob_day = 0;                    // day both sides were handled
ulong    ob_known[];
bool     ob_ready = false;
datetime ob_last = 0;

void OrbEvent(string msg)
{
   int h = FileOpen("orb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("ORB event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("GORB EVENT ", msg);
}

double OrbAtr(int n)
{
   double s = 0;
   for(int i = 1; i <= n; i++)
   {
      double h = iHigh(ob_sym, PERIOD_D1, i), l = iLow(ob_sym, PERIOD_D1, i), pc = iClose(ob_sym, PERIOD_D1, i + 1);
      if(h <= 0 || l <= 0 || pc <= 0) return 0;
      s += MathMax(h, pc) - MathMin(l, pc);
   }
   return s / n;
}

int OrbOrders(int side)                 // side 1 buy stop, -1 sell stop, 0 both
{
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpOrbMagic || OrderGetString(ORDER_SYMBOL) != ob_sym) continue;
      long ty = OrderGetInteger(ORDER_TYPE);
      if(side == 0 || (side == 1 && ty == ORDER_TYPE_BUY_STOP) || (side == -1 && ty == ORDER_TYPE_SELL_STOP)) c++;
   }
   return c;
}

// an order for this side was already sent today (survives restarts): any history order of the magic with "GORB B" / "GORB S"
bool OrbSentToday(datetime d0, int side)
{
   if(!HistorySelect(d0, TimeCurrent() + 60)) return false;
   string tag = side == 1 ? "GORB B" : "GORB S";
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == InpOrbMagic && HistoryOrderGetString(t, ORDER_SYMBOL) == ob_sym &&
         StringFind(HistoryOrderGetString(t, ORDER_COMMENT), tag) == 0) return true;
   }
   return false;
}

void OrbDeletePending(string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpOrbMagic || OrderGetString(ORDER_SYMBOL) != ob_sym) continue;
      string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      trade.SetExpertMagicNumber(InpOrbMagic);
      if(trade.OrderDelete(t)) OrbEvent(StringFormat("GORB ORDER DELETED %s | %s %s deleted (%s)", ob_sym, side, PriceStr(ob_sym, pr), why));
      trade.SetExpertMagicNumber(InpMagic);
   }
}

void OrbInit()
{
   ob_sym = SymResolve(InpOrbSymbol);
   ob_ready = true;
   if(ob_sym == "") { OrbEvent("ERROR | gold ORB: symbol " + InpOrbSymbol + " not found"); return; }
   SymbolSelect(ob_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpOrbMagic) { int m = ArraySize(ob_known); ArrayResize(ob_known, m + 1); ob_known[m] = t; }
   }
   OrbEvent(StringFormat("GORB ONLINE | %s: day trade, range of the M1 bars %02d:%02d-%02d:%02d server, at %02d:%02d a BUY STOP at its high and a SELL STOP "
                         "at its low (each once a day), SL %.2f x ATR%d(D1), TP %.0f x SL, orders deleted and trades closed at 23:30 server, lot %.2f | %d open position(s)",
                         ob_sym, InpOrbFromMin / 60, InpOrbFromMin % 60, InpOrbToMin / 60, InpOrbToMin % 60, InpOrbToMin / 60, InpOrbToMin % 60,
                         InpOrbSlAtr, InpOrbAtrN, InpOrbTpMult, InpOrbLot, ArraySize(ob_known)));
}

void OrbReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "GORB SL HIT" : (reason == DEAL_REASON_TP ? "GORB TP HIT" : "GORB CLOSED");
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_TP ? "take profit 2R" :
                (reason == DEAL_REASON_EXPERT ? "23:30 day-end close" : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(ob_sym, PERIOD_M15, "ORBX", lv, lc, lb, 0, 0, 0, 0, false);
   OrbEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, ob_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(ob_sym, inPx), PriceStr(ob_sym, outPx), why, profit) + Img(fn));
}

void OrbOnTimer()
{
   if(!InpOrbOn) return;
   if(!ob_ready) OrbInit();
   if(ob_sym == "") return;
   datetime now = TimeCurrent();
   if(now - ob_last < 2) return;
   ob_last = now;
   MqlDateTime st; TimeToStruct(now, st);
   int minute = st.hour * 60 + st.min;
   for(int q = ArraySize(ob_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(ob_known[q])) { OrbReportClosed(ob_known[q]); ArrayRemove(ob_known, q, 1); }
   MqlTick tk;
   if(!SymbolInfoTick(ob_sym, tk) || now - tk.time > 600) return;          // market closed
   datetime d0 = iTime(ob_sym, PERIOD_D1, 0);
   if(d0 == 0) return;
   // open positions: report new fills, close at 23:30 or when left from an earlier day
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong pt = PositionGetTicket(i);
      if(pt == 0 || PositionGetInteger(POSITION_MAGIC) != InpOrbMagic || PositionGetString(POSITION_SYMBOL) != ob_sym) continue;
      bool known = false;
      for(int q = 0; q < ArraySize(ob_known); q++) if(ob_known[q] == pt) known = true;
      if(!known)
      {
         int m = ArraySize(ob_known); ArrayResize(ob_known, m + 1); ob_known[m] = pt;
         double lvf[3]; color lcf[3]; string lbf[3];
         lvf[0] = PositionGetDouble(POSITION_PRICE_OPEN); lcf[0] = clrBlue; lbf[0] = "entry";
         lvf[1] = PositionGetDouble(POSITION_SL); lcf[1] = clrIndianRed; lbf[1] = "SL";
         lvf[2] = PositionGetDouble(POSITION_TP); lcf[2] = clrSeaGreen; lbf[2] = "TP";
         bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double vol = PositionGetDouble(POSITION_VOLUME);
         string fnf = Snap(ob_sym, PERIOD_M15, "ORBF", lvf, lcf, lbf, 0, 0, 0, 0, false);
         OrbEvent(StringFormat("GORB FILLED %s | %s %.2f lot from %s, SL %s, TP %s: closes at 23:30 server if neither is hit",
                  ob_sym, buy ? "BUY" : "SELL", vol, PriceStr(ob_sym, lvf[0]), PriceStr(ob_sym, lvf[1]), PriceStr(ob_sym, lvf[2])) + Img(fnf));
         PositionSelectByTicket(pt);
      }
      if(minute >= InpOrbEndMin || (datetime)PositionGetInteger(POSITION_TIME) < d0)
      {
         trade.SetExpertMagicNumber(InpOrbMagic); trade.SetTypeFillingBySymbol(ob_sym);
         if(!trade.PositionClose(pt)) OrbEvent(StringFormat("ERROR | gold ORB close %s failed: %d %s", ob_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   // pending orders: delete at 23:30, when left from an earlier day, or once the daily target is reached
   if(OrbOrders(0) > 0)
   {
      bool old = false;
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong t = OrderGetTicket(i);
         if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpOrbMagic && OrderGetString(ORDER_SYMBOL) == ob_sym &&
            (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0) old = true;
      }
      if(minute >= InpOrbEndMin || old) OrbDeletePending("23:30, no breakout");
      else if(DayPaused()) OrbDeletePending("daily target reached");
   }
   // placing the day's orders
   if(st.day_of_week == 0 || st.day_of_week == 6 || minute < InpOrbToMin || minute >= InpOrbEndMin - 30) return;
   if(ob_day == d0 || DayPaused()) return;
   MqlRates rr[];
   datetime a = d0 + InpOrbFromMin * 60, b = d0 + InpOrbToMin * 60;
   int nr = CopyRates(ob_sym, PERIOD_M1, a, b - 60, rr);
   if(nr < (InpOrbToMin - InpOrbFromMin) / 3) return;                       // M1 history not there yet: retry
   double A = OrbAtr(InpOrbAtrN);
   if(A <= 0) return;                                                        // D1 history not loaded yet: retry
   double hi = rr[0].high, lo = rr[0].low;
   for(int i = 1; i < nr; i++) { hi = MathMax(hi, rr[i].high); lo = MathMin(lo, rr[i].low); }
   // bars since 04:00, to see whether a level was already taken before this shift could place its order
   MqlRates ra[];
   int na = CopyRates(ob_sym, PERIOD_M1, b, now, ra);
   double pt_ = SymbolInfoDouble(ob_sym, SYMBOL_POINT);
   bool upTaken = false, dnTaken = false;
   for(int i = 0; i < na; i++)
   {
      if(ra[i].time >= now - now % 60) break;                               // the forming bar is checked by the live tick below
      if(ra[i].high + ra[i].spread * pt_ >= hi) upTaken = true;
      if(ra[i].low <= lo) dnTaken = true;
   }
   ob_day = d0;
   int dg = (int)SymbolInfoInteger(ob_sym, SYMBOL_DIGITS);
   double sl = InpOrbSlAtr * A, tp = InpOrbTpMult * sl;
   double mn = SymbolInfoDouble(ob_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(ob_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpOrbLot / sv + 1e-9) * sv), 2);
   int em = (int)SymbolInfoInteger(ob_sym, SYMBOL_EXPIRATION_MODE);
   ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + InpOrbEndMin * 60 + 300 : 0;   // backup: the EA deletes (and reports) at 23:30
   bool early = minute < InpOrbToMin + 5;
   string res = "", what = "";
   trade.SetExpertMagicNumber(InpOrbMagic); trade.SetTypeFillingBySymbol(ob_sym);
   for(int side = 1; side >= -1; side -= 2)
   {
      if(OrbOrders(side) > 0 || OrbSentToday(d0, side)) continue;            // already placed / filled today (restart)
      bool buy = side == 1;
      double lvl = NormalizeDouble(buy ? hi : lo, dg);
      bool taken = buy ? upTaken : dnTaken;
      bool beyond = buy ? tk.ask >= lvl : tk.bid <= lvl;
      string cm = (buy ? "GORB B " : "GORB S ") + TimeToString(d0, TIME_DATE);
      if(taken || (beyond && !early))
      { what += StringFormat(" | %s skipped: %s was already taken before the order could be placed", buy ? "BUY" : "SELL", PriceStr(ob_sym, lvl)); continue; }
      bool ok;
      if(beyond)                                                             // just past the level at 04:00: enter now, as the stop would have
      {
         double e = buy ? tk.ask : tk.bid;
         ok = buy ? trade.Buy(lot, ob_sym, 0, NormalizeDouble(e - sl, dg), NormalizeDouble(e + tp, dg), cm)
                  : trade.Sell(lot, ob_sym, 0, NormalizeDouble(e + sl, dg), NormalizeDouble(e - tp, dg), cm);
         what += StringFormat(" | %s at market %s (already past %s at 04:00)", buy ? "BUY" : "SELL", PriceStr(ob_sym, e), PriceStr(ob_sym, lvl));
      }
      else
      {
         ok = buy ? trade.BuyStop(lot, lvl, ob_sym, NormalizeDouble(lvl - sl, dg), NormalizeDouble(lvl + tp, dg), tt, exp, cm)
                  : trade.SellStop(lot, lvl, ob_sym, NormalizeDouble(lvl + sl, dg), NormalizeDouble(lvl - tp, dg), tt, exp, cm);
         what += StringFormat(" | %s STOP %s (SL %s, TP %s)", buy ? "BUY" : "SELL", PriceStr(ob_sym, lvl),
                              PriceStr(ob_sym, buy ? lvl - sl : lvl + sl), PriceStr(ob_sym, buy ? lvl + tp : lvl - tp));
      }
      if(!ok) res += StringFormat(" | %s error %d %s", buy ? "buy" : "sell", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(what == "") return;                                                   // both sides already handled earlier today
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = hi; lc[0] = clrSeaGreen; lb[0] = "range high"; lv[1] = lo; lc[1] = clrIndianRed; lb[1] = "range low";
   string fn = Snap(ob_sym, PERIOD_M15, "ORB", lv, lc, lb, 0, 0, 0, 0, false);
   OrbEvent(StringFormat("GORB ORDERS PLACED %s | range %02d:%02d-%02d:%02d server %s - %s, ATR%d(D1) %s, SL %.2f x ATR = %s, TP %s, lot %.2f, risk about $%.2f a side%s "
                         "| each side once a day; unfilled at 23:30 server = deleted; trades close at 23:30 server%s",
                         ob_sym, InpOrbFromMin / 60, InpOrbFromMin % 60, InpOrbToMin / 60, InpOrbToMin % 60, PriceStr(ob_sym, lo), PriceStr(ob_sym, hi),
                         InpOrbAtrN, PriceStr(ob_sym, A), InpOrbSlAtr, PriceStr(ob_sym, sl), PriceStr(ob_sym, tp), lot,
                         sl * SymbolInfoDouble(ob_sym, SYMBOL_TRADE_TICK_VALUE) / SymbolInfoDouble(ob_sym, SYMBOL_TRADE_TICK_SIZE) * lot, what, res) + Img(fn));
}
//+------------------------------------------------------------------+
