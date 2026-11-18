//+------------------------------------------------------------------+
//| FizyNWS.mqh - gold NEWS STRADDLE, demo only, included by FizyLB  |
//| (v2.49, 17 Nov 2026, rounds 138-141, the owner: "ok aku on yang  |
//| ni saja").                                                        |
//| Rule: on a weekday when the economic calendar has a moderate or  |
//| high importance release of USD or CAD at 08:30 New York, or of   |
//| EUR or GBP at 02:00 New York, place an OCO pair on XAUUSD a few  |
//| seconds before the release: BUY STOP at the ask + $2 and SELL    |
//| STOP at the bid - $2. The first fill deletes the other order;    |
//| SL $3 from the fill price, no TP, closed 15 minutes after the    |
//| orders were placed; unfilled orders are deleted after 6 minutes. |
//| One position at a time, obeys the daily target.                  |
//| Round 139b on real ticks (last 3 months / the 3 before): 08:30   |
//| USD/CAD release days 37 / 42 trades PF 1.38 / 2.97, 02:00 EUR /  |
//| GBP 24 / 26 trades PF 2.05 / 1.75; together 61 / 68 trades,      |
//| PF 1.52 / 2.56, +$73 / +$201, DD -$58 / -$16, worst day -$22.    |
//| Few trades (about 1-2 a day on 3-4 days a week) and the top days |
//| carry most of the money.                                          |
//| Events go to MQL5\Files\nws_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpNwsOn       = false;
input string InpNwsSymbol   = "XAUUSD";
input double InpNwsLot      = 0.01;
input long   InpNwsMagic    = 260338;
input double InpNwsK        = 2.0;      // stop orders this many $ beyond the ask / bid
input double InpNwsSl       = 3.0;      // SL $ from the fill
input int    InpNwsExpMin   = 6;        // unfilled orders deleted after this many minutes
input int    InpNwsHoldMin  = 15;       // position closed this many minutes after the orders were placed

string   nw_sym = "";
bool     nw_ready = false;
datetime nw_done[2];                    // NY day handled, per slot
ulong    nw_known[];
ulong    nw_filled[];                   // positions whose fill was already reported

void NwsEvent(string msg)
{
   int h = FileOpen("nws_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("NEWS event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("NEWS EVENT ", msg);
}

bool NwsInList(ulong &arr[], ulong t) { for(int i = 0; i < ArraySize(arr); i++) if(arr[i] == t) return true; return false; }
void NwsAdd(ulong &arr[], ulong t) { if(NwsInList(arr, t)) return; int m = ArraySize(arr); ArrayResize(arr, m + 1); arr[m] = t; }

bool NwsPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpNwsMagic && PositionGetString(POSITION_SYMBOL) == nw_sym) { ticket = t; return true; }
   }
   return false;
}

int NwsDeleteOrders(string why)
{
   int k = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpNwsMagic) continue;
      if(trade.OrderDelete(t)) k++;
   }
   if(k > 0 && why != "") NwsEvent(StringFormat("NEWS ORDER DELETED %s | %d stop order(s) deleted (%s)", nw_sym, k, why));
   return k;
}

// the placement time is written into the order comment ("NEWS <epoch>"), so exits survive a shift change
datetime NwsPlaced(string cm)
{
   if(StringFind(cm, "NEWS ") != 0) return 0;
   return (datetime)StringToInteger(StringSubstr(cm, 5));
}

// moderate / high importance releases of these currencies in the server minute that starts at t
string NwsReleases(datetime t, string c1, string c2)
{
   string out = "";
   string cs[2]; cs[0] = c1; cs[1] = c2;
   for(int q = 0; q < 2; q++)
   {
      MqlCalendarValue v[];
      int k = CalendarValueHistory(v, t, t + 59, NULL, cs[q]);
      for(int i = 0; i < k; i++)
      {
         MqlCalendarEvent e;
         if(!CalendarEventById(v[i].event_id, e)) continue;
         if(e.importance < CALENDAR_IMPORTANCE_MODERATE) continue;
         if(out != "") out += "; ";
         out += cs[q] + " " + e.name;
      }
   }
   return out;
}

void NwsInit()
{
   nw_sym = SymResolve(InpNwsSymbol);
   nw_ready = true;
   nw_done[0] = 0; nw_done[1] = 0;
   if(nw_sym == "") { NwsEvent("ERROR | NEWS straddle: symbol " + InpNwsSymbol + " not found"); return; }
   SymbolSelect(nw_sym, true);
   ulong pt;
   if(NwsPosition(pt)) { NwsAdd(nw_known, pt); NwsAdd(nw_filled, pt); }
   NwsEvent(StringFormat("NEWS ONLINE | %s: on release days (USD / CAD at 08:30 New York, EUR / GBP at 02:00 New York, moderate or high "
                         "importance) an OCO pair a few seconds before the release, BUY STOP ask + $%.2f / SELL STOP bid - $%.2f, SL $%.2f "
                         "from the fill, no TP, out after %d min, unfilled orders deleted after %d min, lot %.2f | %d open position(s)",
                         nw_sym, InpNwsK, InpNwsK, InpNwsSl, InpNwsHoldMin, InpNwsExpMin, InpNwsLot, ArraySize(nw_known)));
}

void NwsReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "NEWS SL HIT" : "NEWS CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_EXPERT ? StringFormat("%d-minute exit", InpNwsHoldMin) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(nw_sym, PERIOD_M1, "NWS", lv, lc, lb, 0, 0, 0, 0, false);
   NwsEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, nw_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(nw_sym, inPx), PriceStr(nw_sym, outPx), why, profit) + Img(fn));
}

void NwsOnTimer()
{
   if(!InpNwsOn) return;
   if(!nw_ready) NwsInit();
   if(nw_sym == "") return;
   datetime now = TimeCurrent();
   for(int q = ArraySize(nw_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(nw_known[q])) { NwsReportClosed(nw_known[q]); ArrayRemove(nw_known, q, 1); }
   int dg = (int)SymbolInfoInteger(nw_sym, SYMBOL_DIGITS);
   ulong pt;
   if(NwsPosition(pt))
   {
      PositionSelectByTicket(pt);
      NwsAdd(nw_known, pt);
      datetime placed = NwsPlaced(PositionGetString(POSITION_COMMENT));
      if(placed == 0) placed = (datetime)PositionGetInteger(POSITION_TIME);
      if(!NwsInList(nw_filled, pt))                                             // just filled: OCO + SL from the fill price
      {
         NwsAdd(nw_filled, pt);
         NwsDeleteOrders("");
         bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double e = PositionGetDouble(POSITION_PRICE_OPEN);
         double sl = NormalizeDouble(buy ? e - InpNwsSl : e + InpNwsSl, dg);
         trade.SetExpertMagicNumber(InpNwsMagic);
         if(MathAbs(PositionGetDouble(POSITION_SL) - sl) > SymbolInfoDouble(nw_sym, SYMBOL_POINT) / 2)
            if(!trade.PositionModify(pt, sl, 0)) NwsEvent(StringFormat("ERROR | NEWS SL move %s failed: %d %s", nw_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic);
         double lv[2]; color lc[2]; string lb[2];
         lv[0] = e; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
         string fn = Snap(nw_sym, PERIOD_M1, "NWSE", lv, lc, lb, 0, 0, 0, 0, false);
         NwsEvent(StringFormat("NEWS %s %s | the %s stop filled at %s, the other order deleted | SL %s ($%.2f), no TP, closes at %s server",
                               buy ? "BUY" : "SELL", nw_sym, buy ? "buy" : "sell", PriceStr(nw_sym, e), PriceStr(nw_sym, sl), InpNwsSl,
                               TimeToString(placed + InpNwsHoldMin * 60, TIME_MINUTES)) + Img(fn));
      }
      if(now >= placed + InpNwsHoldMin * 60)
      {
         trade.SetExpertMagicNumber(InpNwsMagic); trade.SetTypeFillingBySymbol(nw_sym);
         if(!trade.PositionClose(pt)) NwsEvent(StringFormat("ERROR | NEWS close %s failed: %d %s", nw_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;
   }
   // unfilled orders: deleted after InpNwsExpMin, or once the daily target is reached
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpNwsMagic) continue;
      datetime placed = NwsPlaced(OrderGetString(ORDER_COMMENT));
      if(placed == 0) placed = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
      if(now >= placed + InpNwsExpMin * 60) { NwsDeleteOrders(StringFormat("not filled within %d min of the release", InpNwsExpMin)); break; }
   }
   // the two release moments, New York time: slot 0 = 08:30 (USD, CAD), slot 1 = 02:00 (EUR, GBP)
   datetime ny = NyTime();
   MqlDateTime nd; TimeToStruct(ny, nd);
   if(nd.day_of_week == 0 || nd.day_of_week == 6) return;
   int nym = nd.hour * 60 + nd.min;
   int slot = nym == 8 * 60 + 29 ? 0 : (nym == 1 * 60 + 59 ? 1 : -1);
   if(slot < 0 || nd.sec < 55) return;                                         // place 1-5 s before the release
   datetime nyday = ny - (ny % 86400);
   if(nw_done[slot] == nyday) return;
   nw_done[slot] = nyday;
   if(DayPaused()) return;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpNwsMagic) return;          // orders already out
   }
   MqlTick tk;
   if(!SymbolInfoTick(nw_sym, tk) || now - tk.time > 120) return;              // no live quotes
   datetime srvNow = TimeTradeServer();
   datetime rel = srvNow - srvNow % 60 + 60;                                    // the server minute of the release
   string what = slot == 0 ? NwsReleases(rel, "USD", "CAD") : NwsReleases(rel, "EUR", "GBP");
   if(what == "") return;                                                       // no release today at this minute: no trade
   double bs = NormalizeDouble(tk.ask + InpNwsK, dg), ss = NormalizeDouble(tk.bid - InpNwsK, dg);
   double bsl = NormalizeDouble(bs - InpNwsSl, dg), ssl = NormalizeDouble(ss + InpNwsSl, dg);
   double mn = SymbolInfoDouble(nw_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(nw_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpNwsLot / sv + 1e-9) * sv), 2);
   datetime placed = now;
   datetime exp = placed + InpNwsExpMin * 60 + 300;                             // broker expiry only as a backup
   string cm = "NEWS " + IntegerToString((long)placed);
   trade.SetExpertMagicNumber(InpNwsMagic); trade.SetTypeFillingBySymbol(nw_sym);
   bool ok1 = trade.BuyStop(lot, bs, nw_sym, bsl, 0, ORDER_TIME_SPECIFIED, exp, cm);
   string e1 = ok1 ? "" : StringFormat("buy stop %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   bool ok2 = trade.SellStop(lot, ss, nw_sym, ssl, 0, ORDER_TIME_SPECIFIED, exp, cm);
   string e2 = ok2 ? "" : StringFormat("sell stop %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok1 || !ok2) NwsEvent(StringFormat("ERROR | NEWS orders %s: %s %s", nw_sym, e1, e2));
   if(!ok1 && !ok2) return;
   NwsEvent(StringFormat("NEWS ORDERS PLACED %s | %s New York release: %s | BUY STOP %s / SELL STOP %s, SL $%.2f from the fill, "
                         "deleted after %d min if not filled, trade closed after %d min",
                         nw_sym, slot == 0 ? "08:30" : "02:00", what, ok1 ? PriceStr(nw_sym, bs) : "-", ok2 ? PriceStr(nw_sym, ss) : "-",
                         InpNwsSl, InpNwsExpMin, InpNwsHoldMin));
}
//+------------------------------------------------------------------+
