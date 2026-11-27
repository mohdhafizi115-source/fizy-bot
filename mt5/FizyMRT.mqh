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
//| LAST entry adds the next lot, linear 1, 2, 3, 4, 5, 6 x 0.01   |
//| (max 6 positions, 0.21 lot in all). After every add    |
//| the TP of all positions moves to the price where the WHOLE       |
//| basket nets +$3 (swap included); the EA also closes the basket   |
//| itself once it is +$3. NO SL, held overnight. After a TP a new   |
//| stop order re-arms (entries 01:30-23:00). New baskets obey the   |
//| EA daily target (InpDayTarget, $30 for this test); a basket that |
//| is open keeps adding and keeps its TP.                            |
//| Round 146b on the owner's real ticks, $1000 account, $30 target: |
//| last 3 months 345 baskets, all closed in profit, +$1,035, 0 blow- |
//| ups, worst day +$3; previous 3 months +$1,368; 0 of 63 $1000     |
//| starts blown. The SAME rule on $100 blew up on the 2nd day of    |
//| the window (round 146): after the 6th position there is no stop, |
//| 0.21 lot = $21 per $1, so a ~$45 run beyond the last level takes |
//| the $1000 account. A backtest of 6.5 months, not a guarantee.    |
//| v2.55 (20 Nov, owner: "stop kau kekalkan. tambah limit ... bila  |
//| salah satu trigger, delete yang tak kena"): when flat the EA     |
//| places the stop AND a LIMIT $1 the other way (BUY LIMIT ask - $1 |
//| / SELL LIMIT bid + $1) on the same allowed side; the first fill  |
//| opens the basket and the other order is deleted (OCO). Round 146d|
//| tested stop $3 alone (38 / 63 $1000 starts blown at max 10) and  |
//| limit $1 alone (23 / 63); the OCO pair itself is not tested.     |
//| Events go to MQL5\Files\mrt_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpMrtOn       = true;
input string InpMrtSymbol   = "XAUUSD";
input long   InpMrtMagic    = 260340;
input double InpMrtEntry    = 3.0;      // first stop order this many $ beyond the ask / bid
input bool   InpMrtBoth     = true;     // v2.57: no D1 side, BUY STOP ask + entry AND SELL STOP bid - entry, the first fill deletes the other (round 146g)
input double InpMrtLimit    = 1.0;      // v2.55: also a limit this many $ the other way, OCO with the stop (0 = off)
input double InpMrtStep     = 3.0;      // add a position every $ against the last entry
input double InpMrtTarget   = 3.0;      // basket TP: whole basket +$ (swap included)
input int    InpMrtMax      = 0;        // positions per basket, 0 = UNLIMITED (v2.56 on the owner's order; v2.53-v2.55: 10)
input int    InpMrtFrom     = 0;        // first entry minute, server (v2.56: 00:00, 24 h on the owner's order; was 01:30)
input int    InpMrtTo       = 1440;     // no new basket from this minute (v2.56: 24:00 = all day; was 23:00)
input bool   InpMrtClose2330 = false;   // false = hold overnight (the tested cell)
// v2.62 (23 Nov, owner: "aku nak macam dalam video tu + mart dan flexible ... target harian 500 cent ... deploy sekarang"):
// FLEX mode = round 163 / 164 cell "M5 step = OCO = 1 ATR, trail arm 1 ATR / 0.5 ATR, flip 0.2 ATR" (57 / 63 $1000 starts
// blown on real ticks; deployed on the owner's order). All distances = k x Wilder ATR(14) of closed M5 bars, live.
input bool   InpMrtFlex     = true;     // true = the v2.62 rule below; false = the v2.57 fixed rule above
input double InpMrtFlexK    = 1.0;      // OCO distance and layer step, x ATR(M5)
input double InpMrtArmK     = 1.0;      // unused since v2.67 (the trail arms at basket +InpMrtLock); v2.65: x ATR beyond the basket breakeven
input double InpMrtTrailK   = 0.5;      // basket stop line trails this x ATR behind the price
input double InpMrtFlipK    = 0.2;      // opposite stop sits this x ATR inside the line (0 = no flip)
input double InpMrtLock     = 3.0;      // the line never sits below the price where the whole basket nets + this (account money; v2.65: 3, as the old basket TP)
input bool   InpMrtStopLine = true;     // v2.70 (owner): NO SL on the positions; the opposite STOP sits ON the trailing line and its fill closes the basket

double MrfAtr();
int      MR_LOTS[12] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};       // x 0.01, linear +0.01 (round 146b: same profit as x1.5, 0.21 lot max instead of 0.31)
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

bool   MrtCanAdd(int n) { return InpMrtMax <= 0 || n < InpMrtMax; }
string MrtMaxTxt() { return InpMrtMax <= 0 ? "unlimited" : IntegerToString(InpMrtMax); }

bool MrtInList(ulong t) { for(int i = 0; i < ArraySize(mr_known); i++) if(mr_known[i] == t) return true; return false; }
void MrtAdd(ulong t) { if(MrtInList(t)) return; int m = ArraySize(mr_known); ArrayResize(mr_known, m + 1); mr_known[m] = t; }

double MrtLot(int k)
{
   double mn = SymbolInfoDouble(mr_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(mr_sym, SYMBOL_VOLUME_STEP);
   double mx = SymbolInfoDouble(mr_sym, SYMBOL_VOLUME_MAX);
   double want = (k + 1) * 0.01;                                            // linear 0.01, 0.02, 0.03 ... (no cap since v2.56)
   double v = MathMax(mn, MathFloor(want / sv + 1e-9) * sv);
   if(mx > 0) v = MathMin(v, mx);
   return NormalizeDouble(v, 2);
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
double MrtTpPrice(ulong &tk[], int dir, double target = -1)
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
   double need = (target < 0 ? InpMrtTarget : target) - sw;
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
   if(k > 0 && why != "") MrtEvent(StringFormat("MART ORDER DELETED %s | %d pending order(s) deleted (%s)", mr_sym, k, why));
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
   int show = InpMrtMax <= 0 ? 5 : InpMrtMax;
   for(int k = 0; k < show; k++) lots += (k > 0 ? "/" : "") + DoubleToString(MrtLot(k), 2);
   if(InpMrtMax <= 0) lots += "/... +0.01 each";
   if(InpMrtFlex)
   {
      MrtEvent(StringFormat("MART ONLINE | %s FLEX (v2.62, video trail + martingale): ATR(14, M5) now $%.2f. Flat: BUY STOP / SELL STOP "
                            "%.1f ATR away, the first fill opens the basket; every %.1f ATR against the last entry adds the next lot (0.01, 0.02, 0.03 ... "
                            "unlimited); once the basket is +%.1f ATR the stop line of every position trails %.1f ATR behind the price and never below "
                            "the whole basket +%.2f, with an opposite stop %.1f ATR inside it that starts the next basket (v2.70: NO SL on the positions, the stop sits ON the line and its fill closes the basket); NO stop loss before that; "
                            "new baskets stop once the day's closed profit reaches %.0f | open: %d position(s), %.2f lot, floating %.2f",
                            mr_sym, MrfAtr(), InpMrtFlexK, InpMrtFlexK, InpMrtArmK, InpMrtTrailK, InpMrtLock, InpMrtFlipK, InpDayTarget, n, vol, pnl));
      return;
   }
   MrtEvent(StringFormat("MART ONLINE | %s: %s, a stop $%.2f away%s from %02d:%02d server opens a basket; "
                         "every $%.2f against the last entry adds the next lot (%s, max %s), the TP of all positions moves to the "
                         "whole basket +$%.2f; NO stop loss, %s; new baskets stop once the day's closed profit reaches $%.0f | "
                         "open basket: %d position(s), %.2f lot, floating $%.2f",
                         mr_sym, InpMrtBoth ? "both sides (BUY STOP above + SELL STOP below, no D1 filter)" : "against yesterday's D1 colour",
                         InpMrtEntry, InpMrtBoth ? " each way" : InpMrtLimit > 0 ? StringFormat(" + a limit $%.2f the other way (OCO)", InpMrtLimit) : "", InpMrtFrom / 60, InpMrtFrom % 60, InpMrtStep, lots, MrtMaxTxt(), InpMrtTarget,
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

// v2.57 (round 146g): flat -> BUY STOP at the ask + InpMrtEntry and SELL STOP at the bid - InpMrtEntry; the first fill opens
// the basket (MrtOnTimer deletes the other order when the basket appears) and decides its direction
void MrtBothSides(MqlDateTime &s, int minute, datetime now, bool live, MqlTick &tk, int dg, double dist = -1)
{
   if(dist <= 0) dist = InpMrtEntry;
   bool window = s.day_of_week >= 1 && s.day_of_week <= 5 && minute >= InpMrtFrom && minute < InpMrtTo;
   datetime d0 = now - now % 86400;
   int hb = 0, hs = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrtMagic) continue;
      long ot = OrderGetInteger(ORDER_TYPE);
      bool stale = (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0 || (ot != ORDER_TYPE_BUY_STOP && ot != ORDER_TYPE_SELL_STOP);
      if(stale || !window) { trade.SetExpertMagicNumber(InpMrtMagic); trade.OrderDelete(t); trade.SetExpertMagicNumber(InpMagic); continue; }
      if(ot == ORDER_TYPE_BUY_STOP) hb++; else hs++;
   }
   if((hb > 0 || hs > 0) && DayPaused()) { MrtDeleteOrders("daily target reached"); return; }
   if((hb > 0 && hs > 0) || !window || !live || DayPaused()) return;
   double lot = MrtLot(0);
   datetime exp = d0 + InpMrtTo * 60 + 300;
   string txt = "";
   trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
   if(hb == 0)
   {
      double px = NormalizeDouble(tk.ask + dist, dg);
      if(trade.BuyStop(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1")) txt += "BUY STOP " + PriceStr(mr_sym, px);
      else MrtEvent(StringFormat("ERROR | MART buy stop %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   if(hs == 0)
   {
      double px = NormalizeDouble(tk.bid - dist, dg);
      if(trade.SellStop(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1")) txt += (txt != "" ? " + " : "") + "SELL STOP " + PriceStr(mr_sym, px);
      else MrtEvent(StringFormat("ERROR | MART sell stop %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(txt == "") return;
   MrtEvent(StringFormat("MART ORDER PLACED %s | both sides, no D1 filter: %s ($%.2f away), lot %.2f, the first fill deletes the other, no SL",
                         mr_sym, txt, dist, lot));
}

#include "FizyMRF.mqh"

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
   if(InpMrtFlex) { MrfTimer(s, minute, now, live, tk, dg, pt); return; }

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
         string how = "stop";
         if(PositionSelectByTicket(bk[0]) && StringFind(PositionGetString(POSITION_COMMENT), "MART L1L") == 0) how = "limit";
         MrtEvent(StringFormat("MART %s %s | basket opened: the %s %s filled at %s, lot %.2f, the other order deleted; next add at %s, no SL",
                               dir == 1 ? "BUY" : "SELL", mr_sym, dir == 1 ? "buy" : "sell", how, PriceStr(mr_sym, last), vol,
                               PriceStr(mr_sym, dir == 1 ? last - InpMrtStep : last + InpMrtStep)));
      }
      if(!live) return;
      // the basket is +$target: close it (backup to the broker TP)
      if(pnl >= InpMrtTarget) { MrtCloseAll(bk, "basket target"); return; }
      // optional 23:30 close
      if(InpMrtClose2330 && minute >= 1410 && s.day_of_week >= 1 && s.day_of_week <= 5) { MrtCloseAll(bk, "23:30"); return; }
      // add the next level
      double px = dir == 1 ? tk.ask : tk.bid;
      if(MrtCanAdd(n) && now - mr_lastadd >= 2 && (dir == 1 ? px <= last - InpMrtStep : px >= last + InpMrtStep))
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
         MrtEvent(StringFormat("MART ADD %s | level %d/%s: %s %.2f at %s, basket %.2f lot, floating $%.2f; basket TP %s (+$%.2f)%s",
                               mr_sym, n, MrtMaxTxt(), dir == 1 ? "BUY" : "SELL", lot, PriceStr(mr_sym, last), vol, pnl,
                               PriceStr(mr_sym, tpx), InpMrtTarget,
                               MrtCanAdd(n) ? "; next add at " + PriceStr(mr_sym, dir == 1 ? last - InpMrtStep : last + InpMrtStep)
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

   // v2.57: two-sided OCO, no D1 filter
   if(InpMrtBoth) { MrtBothSides(s, minute, now, live, tk, dg); return; }
   // flat: one stop order on the allowed side, 01:30-23:00 server on weekdays
   int side = MrtSide();
   bool window = s.day_of_week >= 1 && s.day_of_week <= 5 && minute >= InpMrtFrom && minute < InpMrtTo;
   datetime d0 = now - now % 86400;
   int have = 0, hstop = 0, hlim = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrtMagic) continue;
      long ot = OrderGetInteger(ORDER_TYPE);
      bool isstop = ot == ORDER_TYPE_BUY_STOP || ot == ORDER_TYPE_SELL_STOP;
      bool okside = side == 1 ? (ot == ORDER_TYPE_BUY_STOP || (ot == ORDER_TYPE_BUY_LIMIT && InpMrtLimit > 0))
                              : (ot == ORDER_TYPE_SELL_STOP || (ot == ORDER_TYPE_SELL_LIMIT && InpMrtLimit > 0));
      bool stale = (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0 || !okside || side == 0;
      if(stale || !window) { trade.SetExpertMagicNumber(InpMrtMagic); trade.OrderDelete(t); trade.SetExpertMagicNumber(InpMagic); continue; }
      have++; if(isstop) hstop++; else hlim++;
   }
   if(have > 0 && DayPaused()) { MrtDeleteOrders("daily target reached"); return; }
   bool needlim = InpMrtLimit > 0 && hlim == 0;
   if((hstop > 0 && !needlim) || !window || side == 0 || !live || DayPaused()) return;
   double lot = MrtLot(0);
   datetime exp = d0 + InpMrtTo * 60 + 300;                                  // the EA deletes it at 23:00; broker expiry backup
   string txt = "";
   trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
   if(hstop == 0)
   {
      double px = NormalizeDouble(side == 1 ? tk.ask + InpMrtEntry : tk.bid - InpMrtEntry, dg);
      bool ok = side == 1 ? trade.BuyStop(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1")
                          : trade.SellStop(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1");
      if(!ok) MrtEvent(StringFormat("ERROR | MART stop order %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      else txt += StringFormat("%s %s ($%.2f away)", side == 1 ? "BUY STOP" : "SELL STOP", PriceStr(mr_sym, px), InpMrtEntry);
   }
   if(needlim)
   {
      double px = NormalizeDouble(side == 1 ? tk.ask - InpMrtLimit : tk.bid + InpMrtLimit, dg);
      bool ok = side == 1 ? trade.BuyLimit(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1L")
                          : trade.SellLimit(lot, px, mr_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "MART L1L");
      if(!ok) MrtEvent(StringFormat("ERROR | MART limit order %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      else txt += (txt != "" ? " + " : "") + StringFormat("%s %s ($%.2f away)", side == 1 ? "BUY LIMIT" : "SELL LIMIT", PriceStr(mr_sym, px), InpMrtLimit);
   }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(txt == "") return;
   MrtEvent(StringFormat("MART ORDER PLACED %s | yesterday's D1 was %s, so %s only: %s, lot %.2f, the first fill deletes the other, no SL",
                         mr_sym, side == 1 ? "red" : "green", side == 1 ? "buys" : "sells", txt, lot));
}
//+------------------------------------------------------------------+
