//+------------------------------------------------------------------+
//| FizyCMX.mqh - gold COMEX-open scalp, demo only, included by       |
//| FizyLB.mq5 (v2.27, 13 Nov 2026, round 108 / 108b, the owner:      |
//| "ya pasang").                                                     |
//| Rule: when the 08:20 New York M1 bar of XAUUSD closes (the COMEX  |
//| gold open), enter its direction at the 08:21 open, SL 1.0 x       |
//| Wilder ATR(14, M1) from the entry, no TP, closed 5 minutes later. |
//| One trade a trading day; no entry if the EA misses the first 50 s |
//| of 08:21; obeys the daily target. New York time comes from the    |
//| computer's UTC clock with the US DST rule (2nd Sunday of March to |
//| the 1st Sunday of November, 2:00 local).                          |
//| Round 108b at 0.01 lot, last 2 years: 515 trades, PF 1.45, years  |
//| 1.12 / 1.65, +$257, risk about $2 a trade, max DD -$59, worst day |
//| -$13; the same rule at 47 other NY minutes 07:00-11:00: median PF |
//| 0.83, only 08:20 >= 1.15 (an event, not NY-morning momentum).     |
//| Events go to MQL5\Files\cmx_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpCmxOn       = true;
input string InpCmxSymbol   = "XAUUSD";
input double InpCmxLot      = 0.01;
input long   InpCmxMagic    = 260329;
input double InpCmxSlAtr    = 1.0;      // SL distance in Wilder ATR(14, M1) of the 08:20 bar
input int    InpCmxHoldMin  = 5;        // minutes in the trade
input int    InpCmxNyMin    = 500;      // 08:20 New York = the signal bar

string   cx_sym = "";
datetime cx_done = 0;                   // server day handled
ulong    cx_known[];
bool     cx_ready = false;

void CmxEvent(string msg)
{
   int h = FileOpen("cmx_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("COMEX event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("COMEX EVENT ", msg);
}

// n-th Sunday (n >= 1) of a month, 00:00 UTC
datetime CmxNthSunday(int y, int m, int nth)
{
   MqlDateTime d; d.year = y; d.mon = m; d.day = 1; d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   MqlDateTime x; TimeToStruct(t, x);
   int first = (7 - x.day_of_week) % 7;                                  // days to the first Sunday
   return t + (first + 7 * (nth - 1)) * 86400;
}

// New York local time from the computer's UTC clock
datetime NyTime()
{
   datetime g = TimeGMT();
   MqlDateTime d; TimeToStruct(g, d);
   datetime a = CmxNthSunday(d.year, 3, 2) + 7 * 3600, b = CmxNthSunday(d.year, 11, 1) + 6 * 3600;   // 2:00 EST / 2:00 EDT in UTC
   return g - ((g >= a && g < b) ? 4 : 5) * 3600;
}

bool CmxPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpCmxMagic && PositionGetString(POSITION_SYMBOL) == cx_sym) { ticket = t; return true; }
   }
   return false;
}

bool CmxTradedSince(datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d > 0 && HistoryDealGetInteger(d, DEAL_MAGIC) == InpCmxMagic && HistoryDealGetString(d, DEAL_SYMBOL) == cx_sym) return true;
   }
   return false;
}

// Wilder ATR(14) of M1 at the bar with the given shift (as research/btc103.py atr(): ewm alpha 1/14 of the true range)
double CmxAtr(int shift)
{
   MqlRates r[];
   int n = CopyRates(cx_sym, PERIOD_M1, shift, 400, r);                  // oldest first
   if(n < 50) return 0;
   double a = 0;
   for(int i = 0; i < n; i++)
   {
      double tr = (i == 0) ? r[i].high - r[i].low
                           : MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      a = (i == 0) ? tr : a + (tr - a) / 14.0;
   }
   return a;
}

void CmxInit()
{
   cx_sym = SymResolve(InpCmxSymbol);
   cx_ready = true;
   if(cx_sym == "") { CmxEvent("ERROR | COMEX open scalp: symbol " + InpCmxSymbol + " not found"); return; }
   SymbolSelect(cx_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpCmxMagic) { int m = ArraySize(cx_known); ArrayResize(cx_known, m + 1); cx_known[m] = t; }
   }
   CmxEvent(StringFormat("COMEX ONLINE | %s: at the COMEX gold open (08:20 New York) follow the direction of the first 1-minute bar, "
                         "SL %.1f ATR(M1), no TP, out after %d min, one trade a day, lot %.2f | %d open position(s)",
                         cx_sym, InpCmxSlAtr, InpCmxHoldMin, InpCmxLot, ArraySize(cx_known)));
}

void CmxReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "COMEX SL HIT" : "COMEX CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_EXPERT ? StringFormat("%d-minute exit", InpCmxHoldMin) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(cx_sym, PERIOD_M1, "CMX", lv, lc, lb, 0, 0, 0, 0, false);
   CmxEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, cx_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(cx_sym, inPx), PriceStr(cx_sym, outPx), why, profit) + Img(fn));
}

void CmxOnTimer()
{
   if(!InpCmxOn) return;
   if(!cx_ready) CmxInit();
   if(cx_sym == "") return;
   datetime now = TimeCurrent();
   for(int q = ArraySize(cx_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(cx_known[q])) { CmxReportClosed(cx_known[q]); ArrayRemove(cx_known, q, 1); }
   ulong pt;
   if(CmxPosition(pt))
   {
      PositionSelectByTicket(pt);
      datetime t0 = (datetime)PositionGetInteger(POSITION_TIME);
      t0 -= t0 % 60;                                                          // the entry bar's open
      if(now >= t0 + InpCmxHoldMin * 60)
      {
         trade.SetExpertMagicNumber(InpCmxMagic); trade.SetTypeFillingBySymbol(cx_sym);
         if(!trade.PositionClose(pt)) CmxEvent(StringFormat("ERROR | COMEX close %s failed: %d %s", cx_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;
   }
   datetime ny = NyTime();
   MqlDateTime nd; TimeToStruct(ny, nd);
   if(nd.day_of_week == 0 || nd.day_of_week == 6) return;
   int nym = nd.hour * 60 + nd.min;
   if(nym != InpCmxNyMin + 1 || nd.sec >= 50) return;                      // only in the first 50 s of 08:21 New York
   datetime d0 = iTime(cx_sym, PERIOD_D1, 0);
   if(d0 == 0 || cx_done == d0) return;
   cx_done = d0;
   if(CmxTradedSince(d0) || DayPaused()) return;
   MqlTick tk;
   if(!SymbolInfoTick(cx_sym, tk) || now - tk.time > 120) return;          // no live quotes
   // the signal bar: the M1 bar that opened one minute before the current minute (server time)
   datetime cur = now - now % 60, sb = cur - 60;
   MqlRates r[];
   if(CopyRates(cx_sym, PERIOD_M1, sb, 1, r) != 1 || r[0].time != sb)
   { CmxEvent(StringFormat("COMEX SKIPPED %s | the 08:20 New York M1 bar (%s server) is not in the history", cx_sym, TimeToString(sb, TIME_DATE | TIME_MINUTES))); return; }
   double mv = r[0].close - r[0].open;
   if(mv == 0) { CmxEvent(StringFormat("COMEX SKIPPED %s | the 08:20 New York bar closed flat", cx_sym)); return; }
   int sh = iBarShift(cx_sym, PERIOD_M1, sb, true);
   double A = sh >= 0 ? CmxAtr(sh) : 0;
   if(A <= 0) { cx_done = 0; return; }                                      // history not ready: retry within the 50 s
   int dg = (int)SymbolInfoInteger(cx_sym, SYMBOL_DIGITS);
   bool buy = mv > 0;
   if(tk.ask - tk.bid > A)
   { CmxEvent(StringFormat("COMEX SKIPPED %s | spread %s wider than ATR(M1) %s", cx_sym, PriceStr(cx_sym, tk.ask - tk.bid), PriceStr(cx_sym, A))); return; }
   double e = buy ? tk.ask : tk.bid;
   double sl = NormalizeDouble(buy ? e - InpCmxSlAtr * A : e + InpCmxSlAtr * A, dg);
   double mn = SymbolInfoDouble(cx_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(cx_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpCmxLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpCmxMagic); trade.SetTypeFillingBySymbol(cx_sym);
   bool ok = buy ? trade.Buy(lot, cx_sym, 0, sl, 0, "COMEX") : trade.Sell(lot, cx_sym, 0, sl, 0, "COMEX");
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { CmxEvent(StringFormat("ERROR | COMEX %s %s failed: %d %s", buy ? "BUY" : "SELL", cx_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
   if(CmxPosition(pt)) { int m = ArraySize(cx_known); ArrayResize(cx_known, m + 1); cx_known[m] = pt; }
   double lv[3]; color lc[3]; string lb[3];
   lv[0] = e; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = r[0].open; lc[2] = clrGray; lb[2] = "08:20 open";
   string fn = Snap(cx_sym, PERIOD_M1, "CMXE", lv, lc, lb, 0, 0, 0, 0, false);
   CmxEvent(StringFormat("COMEX %s %s | the 08:20 New York bar (COMEX gold open) moved %s %s | %s %.2f lot at %s, SL %s (%.1f ATR(M1) = %s), no TP, "
                         "closes after %d min", buy ? "BUY" : "SELL", cx_sym, mv > 0 ? "up" : "down", PriceStr(cx_sym, MathAbs(mv)),
                         buy ? "BUY" : "SELL", lot, PriceStr(cx_sym, e), PriceStr(cx_sym, sl), InpCmxSlAtr, PriceStr(cx_sym, A), InpCmxHoldMin) + Img(fn));
}
//+------------------------------------------------------------------+
