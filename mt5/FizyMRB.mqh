//+------------------------------------------------------------------+
//| FizyMRB.mqh - BTCUSD MARTINGALE BASKET, WEEKENDS, no stop loss,  |
//| demo only, included by FizyLB (v2.58, 22 Nov 2026, round 161,    |
//| built on the owner's explicit order over the no-martingale rule: |
//| "aku nak btc run sama macam ea live sekarang ... setting sebab   |
//| spread btc berbeza", then "pasang yang kau kata akaun tak        |
//| meletup bulan lepas. run hanya pada hari sabtu dan ahad saja").  |
//| The live gold MART (FizyMRT v2.57) with BTC distances: when flat |
//| on SATURDAY or SUNDAY (server time) a BUY STOP at the ask + $400 |
//| AND a SELL STOP at the bid - $400; the first fill opens the      |
//| basket in its direction and the other order is deleted. Every    |
//| $400 against the LAST entry adds the next lot (k x 0.01,         |
//| unlimited layers), the TP of every position moves to the price   |
//| where the WHOLE basket nets +$3 (swap included) and the EA also  |
//| closes it at +$3. NO SL. A basket still open on Monday keeps     |
//| adding and keeps its TP; only NEW baskets wait for the weekend   |
//| (pending orders are deleted when Monday starts).                 |
//| Round 161 (7 days a week, $1000 starts every 2nd weekday): S $400 |
//| TP $3 → 9-10 / 62 $1000 starts blown, last 3 months 629 baskets  |
//| 0 blow-ups, worst floating -$532, max 9 layers / previous 1 blow- |
//| up (4 Jun) — but S $300 / $600 beside it 31-55 / 34 of 62: no    |
//| plateau, so the low count is luck as much as setting. It shares  |
//| the account margin with the gold MART basket.                     |
//| Events go to MQL5\Files\mrb_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpMrbOn       = false;   // v2.61 (23 Nov): off, gold only on the cent account
input string InpMrbSymbol   = "BTCUSD";
input long   InpMrbMagic    = 260341;
input double InpMrbEntry    = 400.0;    // each first stop this many $ of price beyond the ask / bid
input double InpMrbStep     = 400.0;    // add a position every $ of price against the last entry
input double InpMrbTarget   = 3.0;      // basket TP: whole basket +$ (swap included)
input int    InpMrbMax      = 0;        // positions per basket, 0 = unlimited (as the gold MART)

string   mb_sym = "";
bool     mb_ready = false;
ulong    mb_known[];
int      mb_dir = 0;
datetime mb_lastadd = 0;

void MrbEvent(string msg)
{
   int h = FileOpen("mrb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("BMART event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("BMART EVENT ", msg);
}

bool   MrbCanAdd(int n) { return InpMrbMax <= 0 || n < InpMrbMax; }
string MrbMaxTxt() { return InpMrbMax <= 0 ? "unlimited" : IntegerToString(InpMrbMax); }
bool   MrbInList(ulong t) { for(int i = 0; i < ArraySize(mb_known); i++) if(mb_known[i] == t) return true; return false; }
void   MrbAdd(ulong t) { if(MrbInList(t)) return; int m = ArraySize(mb_known); ArrayResize(mb_known, m + 1); mb_known[m] = t; }
bool   MrbWeekend(MqlDateTime &s) { return s.day_of_week == 6 || s.day_of_week == 0; }

double MrbLot(int k)
{
   double mn = SymbolInfoDouble(mb_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(mb_sym, SYMBOL_VOLUME_STEP);
   double mx = SymbolInfoDouble(mb_sym, SYMBOL_VOLUME_MAX);
   double want = (k + 1) * 0.01;                                            // linear 0.01, 0.02, 0.03 ...
   double v = MathMax(mn, MathFloor(want / sv + 1e-9) * sv);
   if(mx > 0) v = MathMin(v, mx);
   return NormalizeDouble(v, 2);
}

int MrbBasket(ulong &tk[], int &dir, double &last, double &vol, double &pnl)
{
   ArrayResize(tk, 0); dir = 0; last = 0; vol = 0; pnl = 0;
   datetime lt = 0; ulong lticket = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMrbMagic || PositionGetString(POSITION_SYMBOL) != mb_sym) continue;
      int m = ArraySize(tk); ArrayResize(tk, m + 1); tk[m] = t;
      dir = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      vol += PositionGetDouble(POSITION_VOLUME);
      pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      datetime pt = (datetime)PositionGetInteger(POSITION_TIME);
      if(pt > lt || (pt == lt && t > lticket)) { lt = pt; lticket = t; last = PositionGetDouble(POSITION_PRICE_OPEN); }
   }
   return ArraySize(tk);
}

double MrbTpPrice(ulong &tk[], int dir)
{
   double ts = SymbolInfoDouble(mb_sym, SYMBOL_TRADE_TICK_SIZE), tv = SymbolInfoDouble(mb_sym, SYMBOL_TRADE_TICK_VALUE);
   if(ts <= 0 || tv <= 0) return 0;
   double sv = 0, sve = 0, sw = 0;
   for(int i = 0; i < ArraySize(tk); i++)
   {
      if(!PositionSelectByTicket(tk[i])) continue;
      double v = PositionGetDouble(POSITION_VOLUME) * tv / ts;               // $ per 1.0 of price
      sv += v; sve += v * PositionGetDouble(POSITION_PRICE_OPEN); sw += PositionGetDouble(POSITION_SWAP);
   }
   if(sv <= 0) return 0;
   double need = InpMrbTarget - sw;
   return dir == 1 ? (need + sve) / sv : (sve - need) / sv;
}

int MrbDeleteOrders(string why)
{
   int k = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrbMagic) continue;
      trade.SetExpertMagicNumber(InpMrbMagic);
      if(trade.OrderDelete(t)) k++;
      trade.SetExpertMagicNumber(InpMagic);
   }
   if(k > 0 && why != "") MrbEvent(StringFormat("BMART ORDER DELETED %s | %d pending order(s) deleted (%s)", mb_sym, k, why));
   return k;
}

void MrbInit()
{
   mb_sym = SymResolve(InpMrbSymbol);
   mb_ready = true;
   if(mb_sym == "") { MrbEvent("ERROR | BTC MART basket: symbol " + InpMrbSymbol + " not found"); return; }
   SymbolSelect(mb_sym, true);
   ulong tk[]; int dir; double last, vol, pnl;
   int n = MrbBasket(tk, dir, last, vol, pnl);
   for(int i = 0; i < n; i++) MrbAdd(tk[i]);
   mb_dir = dir;
   MrbEvent(StringFormat("BMART ONLINE | %s, SATURDAY and SUNDAY only (server): when flat a BUY STOP $%.0f above and a SELL STOP $%.0f below, "
                         "the first fill deletes the other; every $%.0f against the last entry adds the next lot (0.01/0.02/0.03/... %s), "
                         "the TP of all positions moves to the whole basket +$%.2f; NO stop loss; an open basket keeps running on weekdays | "
                         "open basket: %d position(s), %.2f lot, floating $%.2f",
                         mb_sym, InpMrbEntry, InpMrbEntry, InpMrbStep, MrbMaxTxt(), InpMrbTarget, n, vol, pnl));
}

void MrbReportClosed()
{
   double profit = 0; int so = 0, n = ArraySize(mb_known); double vol = 0;
   for(int q = 0; q < n; q++)
   {
      if(!HistorySelectByPosition(mb_known[q])) continue;
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
   lv[0] = SymbolInfoDouble(mb_sym, SYMBOL_BID); lc[0] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[0] = "close";
   string fn = Snap(mb_sym, PERIOD_M15, "MRB", lv, lc, lb, 0, 0, 0, 0, false);
   if(so > 0)
      MrbEvent(StringFormat("BMART STOP OUT %s | the broker closed %d of %d position(s) on a margin stop-out, basket %.2f lot, loss $%.2f",
                            mb_sym, so, n, vol, profit) + Img(fn));
   else
      MrbEvent(StringFormat("BMART BASKET CLOSED %s | %s basket of %d position(s), %.2f lot, closed, profit $%.2f",
                            mb_sym, mb_dir == 1 ? "BUY" : "SELL", n, vol, profit) + Img(fn));
}

bool MrbCloseAll(ulong &tk[], string why)
{
   bool ok = true;
   trade.SetExpertMagicNumber(InpMrbMagic); trade.SetTypeFillingBySymbol(mb_sym);
   for(int i = 0; i < ArraySize(tk); i++)
      if(!trade.PositionClose(tk[i]))
      {
         ok = false;
         MrbEvent(StringFormat("ERROR | BMART close %s (%s) failed: %d %s", mb_sym, why, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   return ok;
}

// flat: BUY STOP ask + entry and SELL STOP bid - entry on Saturday / Sunday; pending orders are deleted outside the weekend
void MrbBothSides(MqlDateTime &s, datetime now, bool live, MqlTick &tk, int dg)
{
   bool window = MrbWeekend(s);
   datetime d0 = now - now % 86400;
   int hb = 0, hs = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrbMagic) continue;
      long ot = OrderGetInteger(ORDER_TYPE);
      bool stale = (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0 || (ot != ORDER_TYPE_BUY_STOP && ot != ORDER_TYPE_SELL_STOP);
      if(stale || !window) { trade.SetExpertMagicNumber(InpMrbMagic); trade.OrderDelete(t); trade.SetExpertMagicNumber(InpMagic); continue; }
      if(ot == ORDER_TYPE_BUY_STOP) hb++; else hs++;
   }
   if((hb > 0 || hs > 0) && DayPaused()) { MrbDeleteOrders("daily target reached"); return; }
   if((hb > 0 && hs > 0) || !window || !live || DayPaused()) return;
   double lot = MrbLot(0);
   datetime exp = d0 + 86400 + 300;                                         // re-placed each server day; broker expiry backup
   string txt = "";
   trade.SetExpertMagicNumber(InpMrbMagic); trade.SetTypeFillingBySymbol(mb_sym);
   if(hb == 0)
   {
      double px = NormalizeDouble(tk.ask + InpMrbEntry, dg);
      if(trade.BuyStop(lot, px, mb_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "BMART L1")) txt += "BUY STOP " + PriceStr(mb_sym, px);
      else MrbEvent(StringFormat("ERROR | BMART buy stop %s failed: %d %s", mb_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   if(hs == 0)
   {
      double px = NormalizeDouble(tk.bid - InpMrbEntry, dg);
      if(trade.SellStop(lot, px, mb_sym, 0, 0, ORDER_TIME_SPECIFIED, exp, "BMART L1")) txt += (txt != "" ? " + " : "") + "SELL STOP " + PriceStr(mb_sym, px);
      else MrbEvent(StringFormat("ERROR | BMART sell stop %s failed: %d %s", mb_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(txt == "") return;
   MrbEvent(StringFormat("BMART ORDER PLACED %s | weekend, both sides: %s ($%.0f away), lot %.2f, the first fill deletes the other, no SL",
                         mb_sym, txt, InpMrbEntry, lot));
}

void MrbOnTimer()
{
   if(!InpMrbOn) return;
   if(!mb_ready) MrbInit();
   if(mb_sym == "") return;
   datetime now = TimeCurrent();
   MqlTick tk;
   bool live = SymbolInfoTick(mb_sym, tk) && now - tk.time <= 60;
   int dg = (int)SymbolInfoInteger(mb_sym, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(mb_sym, SYMBOL_POINT);
   MqlDateTime s; TimeToStruct(now, s);

   ulong bk[]; int dir; double last, vol, pnl;
   int n = MrbBasket(bk, dir, last, vol, pnl);
   if(n == 0 && ArraySize(mb_known) > 0) { MrbReportClosed(); ArrayResize(mb_known, 0); mb_dir = 0; }

   if(n > 0)
   {
      bool fresh = ArraySize(mb_known) == 0;
      for(int i = 0; i < n; i++) MrbAdd(bk[i]);
      mb_dir = dir;
      if(fresh)
      {
         MrbDeleteOrders("");
         MrbEvent(StringFormat("BMART %s %s | basket opened: the %s stop filled at %s, lot %.2f, the other order deleted; next add at %s, no SL",
                               dir == 1 ? "BUY" : "SELL", mb_sym, dir == 1 ? "buy" : "sell", PriceStr(mb_sym, last), vol,
                               PriceStr(mb_sym, dir == 1 ? last - InpMrbStep : last + InpMrbStep)));
      }
      if(!live) return;
      if(pnl >= InpMrbTarget) { MrbCloseAll(bk, "basket target"); return; }
      double px = dir == 1 ? tk.ask : tk.bid;
      if(MrbCanAdd(n) && now - mb_lastadd >= 2 && (dir == 1 ? px <= last - InpMrbStep : px >= last + InpMrbStep))
      {
         double lot = MrbLot(n);
         trade.SetExpertMagicNumber(InpMrbMagic); trade.SetTypeFillingBySymbol(mb_sym);
         string cm = StringFormat("BMART L%d", n + 1);
         bool ok = dir == 1 ? trade.Buy(lot, mb_sym, 0, 0, 0, cm) : trade.Sell(lot, mb_sym, 0, 0, 0, cm);
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         mb_lastadd = now;
         if(!ok) { MrbEvent(StringFormat("ERROR | BMART add %s level %d failed: %d %s", mb_sym, n + 1, trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
         n = MrbBasket(bk, dir, last, vol, pnl);
         for(int i = 0; i < n; i++) MrbAdd(bk[i]);
         double tpx = MrbTpPrice(bk, dir);
         MrbEvent(StringFormat("BMART ADD %s | level %d/%s: %s %.2f at %s, basket %.2f lot, floating $%.2f; basket TP %s (+$%.2f); next add at %s",
                               mb_sym, n, MrbMaxTxt(), dir == 1 ? "BUY" : "SELL", lot, PriceStr(mb_sym, last), vol, pnl,
                               PriceStr(mb_sym, tpx), InpMrbTarget, PriceStr(mb_sym, dir == 1 ? last - InpMrbStep : last + InpMrbStep)));
      }
      double tp = NormalizeDouble(MrbTpPrice(bk, dir), dg);
      if(tp > 0)
      {
         double lim = SymbolInfoInteger(mb_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
         bool valid = dir == 1 ? tp > tk.bid + lim : tp < tk.ask - lim;
         if(!valid) { MrbCloseAll(bk, "TP already reached"); return; }
         trade.SetExpertMagicNumber(InpMrbMagic);
         for(int i = 0; i < n; i++)
         {
            if(!PositionSelectByTicket(bk[i])) continue;
            if(MathAbs(PositionGetDouble(POSITION_TP) - tp) <= pt / 2 && PositionGetDouble(POSITION_SL) == 0) continue;
            if(!trade.PositionModify(bk[i], 0, tp))
               MrbEvent(StringFormat("ERROR | BMART TP move %s failed: %d %s", mb_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         }
         trade.SetExpertMagicNumber(InpMagic);
      }
      return;
   }
   MrbBothSides(s, now, live, tk, dg);
}
//+------------------------------------------------------------------+
