//+------------------------------------------------------------------+
//| FizyMRT.mqh - gold MARTINGALE BASKET with NO stop loss, demo     |
//| only, included by FizyLB (v2.52, 18 Nov 2026, round 146b, built  |
//| on the owner's explicit order over the no-martingale rule: "buat |
//| aku ea ni. modul lain semua off sekejap. aku nak test dengan     |
//| akaun 1000$. stop trade bila dah profit 30$ sehari").             |
//| Rule: direction AGAINST yesterday's D1 colour (red day: buys,    |
//| green day: sells, doji: no new basket). From 01:30 server, when  |
//| flat, ONE stop order $3 away on the allowed side (BUY STOP at    |
//| the ask + $3 / SELL STOP at the bid - $3) opens a basket; it     |
//| stays until filled or 23:00 server. Every further $3 against the |
//| LAST entry adds the next lot of the x1.5 schedule 1, 2, 3, 5, 8, |
//| 12 x 0.01 (max 6 positions, 0.31 lot in all). After every add    |
//| the TP of all positions moves to the price where the WHOLE       |
//| basket nets +$3 (swap included); the EA also closes the basket   |
//| itself once it is +$3. NO SL, held overnight. After a TP a new   |
//| stop order re-arms (entries 01:30-23:00). New baskets obey the   |
//| EA daily target (InpDayTarget, $30 for this test); a basket that |
//| is open keeps adding and keeps its TP.                            |
//| Round 146b on the owner's real ticks, $1000 account, $30 target: |
//| last 3 months 346 baskets, all closed in profit, +$1,038, 0 blow- |
//| ups, worst day +$3; previous 3 months +$1,359; 0 of 63 $1000     |
//| starts blown. The SAME rule on $100 blew up on the 2nd day of    |
//| the window (round 146): after the 6th position there is no stop, |
//| 0.31 lot = $31 per $1, so a ~$30 run beyond the last level takes |
//| the $1000 account. A backtest of 6.5 months, not a guarantee.    |
//| Events go to MQL5\Files\mrt_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpMrtOn       = true;
input string InpMrtSymbol   = "XAUUSD";
input long   InpMrtMagic    = 260340;
input double InpMrtEntry    = 3.0;      // first stop order this many $ beyond the ask / bid
input double InpMrtStep     = 3.0;      // add a position every $ against the last entry
input double InpMrtTarget   = 3.0;      // basket TP: whole basket +$ (swap included)
input int    InpMrtMax      = 6;        // positions per basket
input int    InpMrtFrom     = 90;       // first entry minute, server (01:30)
input int    InpMrtTo       = 1380;     // no new basket from this minute (23:00)
input bool   InpMrtClose2330 = false;   // false = hold overnight (the tested cell)

int      MR_LOTS[12] = {1, 2, 3, 5, 8, 12, 18, 27, 41, 62, 93, 140};   // x 0.01, the x1.5 schedule
string   mr_sym = "";
bool     mr_ready = false;
ulong    mr_known[];             // tickets of the basket currently open
datetime mr_start = 0;           // time the current basket opened
int      mr_dir = 0;             // +1 buy basket, -1 sell basket
datetime mr_lastadd = 0;

void MrtEvent(string msg)
{
   int h = FileOpen("mrt_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("MART event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("MART EVENT ", msg);
}

bool MrtInList(ulong t) { for(int i = 0; i < ArraySize(mr_known); i++) if(mr_known[i] == t) return true; return false; }
void MrtAdd(ulong t) { if(MrtInList(t)) return; int m = ArraySize(mr_known); ArrayResize(mr_known, m + 1); mr_known[m] = t; }

double MrtLot(int k)
{
   double mn = SymbolInfoDouble(mr_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(mr_sym, SYMBOL_VOLUME_STEP);
   double want = MR_LOTS[MathMin(k, 11)] * 0.01;
   return NormalizeDouble(MathMax(mn, MathFloor(want / sv + 1e-9) * sv), 2);
}

// the open basket: tickets, direction, last entry price, totals
int MrtBasket(ulong &tk[], int &dir, double &last, double &vol, double &pnl)
{
   ArrayResize(tk, 0); dir = 0; last = 0; vol = 0; pnl = 0;
   datetime lt = 0; ulong lticket = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMrtMagic || PositionGetString(POSITION_SYMBOL) != mr_sym) continue;
      int m = ArraySize(tk); ArrayResize(tk, m + 1); tk[m] = t;
      dir = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      vol += PositionGetDouble(POSITION_VOLUME);
      pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      datetime pt = (datetime)PositionGetInteger(POSITION_TIME);
      if(pt > lt || (pt == lt && t > lticket)) { lt = pt; lticket = t; last = PositionGetDouble(POSITION_PRICE_OPEN); }
   }
   return ArraySize(tk);
}

// the price where the whole basket nets +InpMrtTarget, swap included
double MrtTpPrice(ulong &tk[], int dir)
{
   double ts = SymbolInfoDouble(mr_sym, SYMBOL_TRADE_TICK_SIZE), tv = SymbolInfoDouble(mr_sym, SYMBOL_TRADE_TICK_VALUE);
   if(ts <= 0 || tv <= 0) return 0;
   double sv = 0, sve = 0, sw = 0;
   for(int i = 0; i < ArraySize(tk); i++)
   {
      if(!PositionSelectByTicket(tk[i])) continue;
      double v = PositionGetDouble(POSITION_VOLUME) * tv / ts;               // $ per $1 of price
      sv += v; sve += v * PositionGetDouble(POSITION_PRICE_OPEN); sw += PositionGetDouble(POSITION_SWAP);
   }
   if(sv <= 0) return 0;
   double need = InpMrtTarget - sw;
   return dir == 1 ? (need + sve) / sv : (sve - need) / sv;
}

int MrtDeleteOrders(string why)
{
   int k = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrtMagic) continue;
      trade.SetExpertMagicNumber(InpMrtMagic);
      if(trade.OrderDelete(t)) k++;
      trade.SetExpertMagicNumber(InpMagic);
   }
   if(k > 0 && why != "") MrtEvent(StringFormat("MART ORDER DELETED %s | %d stop order(s) deleted (%s)", mr_sym, k, why));
   return k;
}

// allowed side from yesterday's D1 candle: +1 buys (red day), -1 sells (green day), 0 doji
int MrtSide()
{
   double o = iOpen(mr_sym, PERIOD_D1, 1), c = iClose(mr_sym, PERIOD_D1, 1);
   if(o <= 0 || c <= 0) return 0;
   if(c < o) return 1;
   if(c > o) return -1;
   return 0;
}

void MrtInit()
{
   mr_sym = SymResolve(InpMrtSymbol);
   mr_ready = true;
   if(mr_sym == "") { MrtEvent("ERROR | MART basket: symbol " + InpMrtSymbol + " not found"); return; }
   SymbolSelect(mr_sym, true);
   ulong tk[]; int dir; double last, vol, pnl;
   int n = MrtBasket(tk, dir, last, vol, pnl);
   for(int i = 0; i < n; i++) MrtAdd(tk[i]);
   mr_dir = dir; mr_start = n > 0 ? TimeCurrent() : 0;
   string lots = "";
   for(int k = 0; k < InpMrtMax; k++) lots += (k > 0 ? "/" : "") + DoubleToString(MrtLot(k), 2);
   MrtEvent(StringFormat("MART ONLINE | %s: against yesterday's D1 colour, a stop $%.2f away from %02d:%02d server opens a basket; "
                         "every $%.2f against the last entry adds the next lot (%s, max %d), the TP of all positions moves to the "
                         "whole basket +$%.2f; NO stop loss, %s; new baskets stop once the day's closed profit reaches $%.0f | "
                         "open basket: %d position(s), %.2f lot, floating $%.2f",
                         mr_sym, InpMrtEntry, InpMrtFrom / 60, InpMrtFrom % 60, InpMrtStep, lots, InpMrtMax, InpMrtTarget,
                         InpMrtClose2330 ? "closed at 23:30 server" : "held overnight", InpDayTarget, n, vol, pnl));
}

void MrtReportClosed()
{
   double profit = 0; int so = 0, n = ArraySize(mr_known); double vol = 0;
   for(int q = 0; q < n; q++)
   {
      if(!HistorySelectByPosition(mr_known[q])) continue;
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong d = HistoryDealGetTicket(i);
         if(d == 0) continue;
         profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) vol += HistoryDealGetDouble(d, DEAL_VOLUME);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT && HistoryDealGetInteger(d, DEAL_REASON) == DEAL_REASON_SO) so++;
      }
   }
   double lv[1]; color lc[1]; string lb[1];
   lv[0] = SymbolInfoDouble(mr_sym, SYMBOL_BID); lc[0] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[0] = "close";
   string fn = Snap(mr_sym, PERIOD_M5, "MRT", lv, lc, lb, 0, 0, 0, 0, false);
   if(so > 0)
      MrtEvent(StringFormat("MART STOP OUT %s | the broker closed %d of %d position(s) on a margin stop-out, basket %.2f lot, loss $%.2f",
                            mr_sym, so, n, vol, profit) + Img(fn));
   else
      MrtEvent(StringFormat("MART BASKET CLOSED %s | %s basket of %d position(s), %.2f lot, closed, profit $%.2f",
                            mr_sym, mr_dir == 1 ? "BUY" : "SELL", n, vol, profit) + Img(fn));
}

bool MrtCloseAll(ulong &tk[], string why)
{
   bool ok = true;
   trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
   for(int i = 0; i < ArraySize(tk); i++)
      if(!trade.PositionClose(tk[i]))
      {
         ok = false;
         MrtEvent(StringFormat("ERROR | MART close %s (%s) failed: %d %s", mr_sym, why, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   return ok;
}

void MrtOnTimer()
{
   if(!InpMrtOn) return;
   if(!mr_ready) MrtInit();
   if(mr_sym == "") return;
   datetime now = TimeCurrent();
   MqlTick tk;
   bool live = SymbolInfoTick(mr_sym, tk) && now - tk.time <= 60;
   int dg = (int)SymbolInfoInteger(mr_sym, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(mr_sym, SYMBOL_POINT);
   MqlDateTime s; TimeToStruct(now, s);
   int minute = s.hour * 60 + s.min;

   ulong bk[]; int dir; double last, vol, pnl;
   int n = MrtBasket(bk, dir, last, vol, pnl);
   if(n == 0 && ArraySize(mr_known) > 0) { MrtReportClosed(); ArrayResize(mr_known, 0); mr_dir = 0; }

   if(n > 0)
   {
      bool fresh = ArraySize(mr_known) == 0;
      for(int i = 0; i < n; i++) MrtAdd(bk[i]);
      mr_dir = dir;
      if(fresh)
      {
         mr_start = now;
         MrtDeleteOrders("");
         MrtEvent(StringFormat("MART %s %s | basket opened: the %s stop filled at %s, lot %.2f; next add at %s, no SL",
                               dir == 1 ? "BUY" : "SELL", mr_sym, dir == 1 ? "buy" : "sell", PriceStr(mr_sym, last), vol,
                               PriceStr(mr_sym, dir == 1 ? last - InpMrtStep : last + InpMrtStep)));
      }
      if(!live) return;
      // the basket is +$target: close it (backup to the broker TP)
      if(pnl >= InpMrtTarget) { MrtCloseAll(bk, "basket target"); return; }
      // optional 23:30 close
      if(InpMrtClose2330 && minute >= 1410 && s.day_of_week >= 1 && s.day_of_week <= 5) { MrtCloseAll(bk, "23:30"); return; }
      // add the next level
      double px = dir == 1 ? tk.ask : tk.bid;
      if(n < InpMrtMax && now - mr_lastadd >= 2 && (dir == 1 ? px <= last - InpMrtStep : px >= last + InpMrtStep))
      {
         double lot = MrtLot(n);
         trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
         string cm = StringFormat("MART L%d", n + 1);
         bool ok = dir == 1 ? trade.Buy(lot, mr_sym, 0, 0, 0, cm) : trade.Sell(lot, mr_sym, 0, 0, 0, cm);
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         mr_lastadd = now;
         if(!ok) { MrtEvent(StringFormat("ERROR | MART add %s level %d failed: %d %s", mr_sym, n + 1, trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
         n = MrtBasket(bk, dir, last, vol, pnl);
         for(int i = 0; i < n; i++) MrtAdd(bk[i]);
         double tpx = MrtTpPrice(bk, dir);
         MrtEvent(StringFormat("MART ADD %s | level %d/%d: %s %.2f at %s, basket %.2f lot, floating $%.2f; basket TP %s (+$%.2f)%s",
                               mr_sym, n, InpMrtMax, dir == 1 ? "BUY" : "SELL", lot, PriceStr(mr_sym, last), vol, pnl,
                               PriceStr(mr_sym, tpx), InpMrtTarget,
                               n < InpMrtMax ? "; next add at " + PriceStr(mr_sym, dir == 1 ? last - InpMrtStep : last + InpMrtStep)
                                             : "; LAST LEVEL, no more adds and no stop loss"));
      }
      // every position's TP = the basket +$target price
      double tp = NormalizeDouble(MrtTpPrice(bk, dir), dg);
      if(tp > 0)
      {
         double lim = SymbolInfoInteger(mr_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
         bool valid = dir == 1 ? tp > tk.bid + lim : tp < tk.ask - lim;
         if(!valid) { MrtCloseAll(bk, "TP already reached"); return; }
         trade.SetExpertMagicNumber(InpMrtMagic);
         for(int i = 0; i < n; i++)
         {
            if(!PositionSelectByTicket(bk[i])) continue;
            if(MathAbs(PositionGetDouble(POSITION_TP) - tp) <= pt / 2 && PositionGetDouble(POSITION_SL) == 0) continue;
            if(!trade.PositionModify(bk[i], 0, tp))
               MrtEvent(StringFormat("ERROR | MART TP move %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         }
         trade.SetExpertMagicNumber(InpMagic);
      }
      return;
   }

   // flat: one stop order on the allowed side, 01:30-23:00 server on weekdays
   int side = MrtSide();
   bool window = s.day_of_week >= 1 && s.day_of_week <= 5 && minute >= InpMrtFrom && minute < InpMrtTo;
   datetime d0 = now - now % 86400;
   int have = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrtMagic) continue;
      long ot = OrderGetInteger(ORDER_TYPE);
      bool stale = (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0 || (side == 1 && ot != ORDER_TYPE_BUY_STOP) || (side == -1 && ot != ORDER_TYPE_SELL_STOP) || side == 0;
      if(stale || !window) { trade.SetExpertMagicNumber(InpMrtMagic); trade.OrderDelete(t); trade.SetExpertMagicNumber(InpMagic); continue; }
      have++;
   }
   if(have > 0 && DayPaused()) { MrtDeleteOrders("daily target reached"); return; }
   if(have > 0 || !window || side == 0 || !live || DayPaused()) return;
   double lot = MrtLot(0);
   double px = NormalizeDouble(side == 1 ? tk.ask + InpMrtEntry : tk.bid - InpMrtEntry, dg);
   datetime exp = d0 + InpMrtTo * 60 + 300;                                  // the EA deletes it at 23:00; broker expiry backup
   trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
   bool ok = side == 1 ? trade.BuyStop(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1")
                       : trade.SellStop(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1");
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { MrtEvent(StringFormat("ERROR | MART stop order %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
   MrtEvent(StringFormat("MART ORDER PLACED %s | yesterday's D1 was %s, so %s only: %s %s ($%.2f away), lot %.2f, no SL",
                         mr_sym, side == 1 ? "red" : "green", side == 1 ? "buys" : "sells", side == 1 ? "BUY STOP" : "SELL STOP",
                         PriceStr(mr_sym, px), InpMrtEntry, lot));
}
//+------------------------------------------------------------------+
