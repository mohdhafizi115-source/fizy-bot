//+------------------------------------------------------------------+
//| FizyMRF.mqh - FLEX mode of the gold MART basket (v2.62, 23 Nov   |
//| 2026), included by FizyMRT.mqh. The owner's video trail + the    |
//| martingale basket with ATR-scaled distances (round 163 / 164     |
//| cell "M5 1 ATR, trail arm 1 / 0.5 ATR, flip 0.2 ATR": 57 of 63   |
//| $1000 starts blown on his real ticks; deployed on his explicit   |
//| order, demo only).                                               |
//| A = Wilder ATR(14) of closed M5 bars, read live.                 |
//| Flat: BUY STOP ask + FlexK*A / SELL STOP bid - FlexK*A, the first|
//| fill opens a basket, the other is deleted.                       |
//| Basket (one per direction, all positions of that side): every    |
//| FlexK*A against the last entry adds the next lot k x 0.01, no    |
//| cap, no SL. Once the basket floats + ArmK*A (money of 0.01 lot   |
//| per ATR) the SL of EVERY position = the stop line                |
//|   buy:  max(bid - TrailK*A, price where the basket nets +Lock)   |
//|   sell: min(ask + TrailK*A, price where the basket nets +Lock)   |
//| moved only in the profit direction; no more adds once trailing.  |
//| While exactly one basket is open and trailing, an opposite STOP  |
//| sits FlipK*A inside the line (buy basket: SELL STOP line + G),   |
//| moved with it; its fill opens the next basket the other way      |
//| while the old one exits on its line (the video's trick).         |
//| New baskets (OCO and flip orders) obey DayPaused().              |
//+------------------------------------------------------------------+
ulong    mrf_kb[];
ulong    mrf_ks[];
datetime mrf_lastadd = 0;
double   mrf_line[2] = {0, 0};      // v2.64: the EA's own basket line per side (0 buy, 1 sell); 0 = not trailing
int      mrf_tn[2]   = {0, 0};      // positions in the basket when its line was armed
datetime mrf_tryclose[2] = {0, 0};

double MrfAtr()
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(mr_sym, PERIOD_M5, 1, 300, r);                        // closed bars only, oldest first
   if(n < 20) return 0;
   double atr = 0;
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr = i == 1 ? tr : atr + (tr - atr) / 14.0;
   }
   // v2.68: live ATR - the forming M5 bar counts as soon as its range so far would raise the ATR
   MqlRates c[];
   if(CopyRates(mr_sym, PERIOD_M5, 0, 1, c) == 1)
   {
      double trn = MathMax(c[0].high - c[0].low, MathMax(MathAbs(c[0].high - r[n - 1].close), MathAbs(c[0].low - r[n - 1].close)));
      if(trn > atr) atr += (trn - atr) / 14.0;
   }
   return atr;
}

// v2.68: the waiting OCO pair keeps its centre (placement mid) and moves its distance with the live ATR
void MrfOcoAdjust(double A, MqlTick &tk, int dg, double pt)
{
   ulong tb = 0, ts = 0; double pb = 0, ps = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrtMagic) continue;
      if(OrderGetString(ORDER_SYMBOL) != mr_sym || StringFind(OrderGetString(ORDER_COMMENT), "MART L1F") == 0) continue;
      long ot = OrderGetInteger(ORDER_TYPE);
      if(ot == ORDER_TYPE_BUY_STOP)  { tb = t; pb = OrderGetDouble(ORDER_PRICE_OPEN); }
      if(ot == ORDER_TYPE_SELL_STOP) { ts = t; ps = OrderGetDouble(ORDER_PRICE_OPEN); }
   }
   if(tb == 0 || ts == 0) return;
   double mid = (pb + ps) / 2, half = (tk.ask - tk.bid) / 2, dist = InpMrtFlexK * A;
   double lim = (SymbolInfoInteger(mr_sym, SYMBOL_TRADE_STOPS_LEVEL) + 1) * pt;
   double nb = NormalizeDouble(mid + half + dist, dg), ns = NormalizeDouble(mid - half - dist, dg);
   trade.SetExpertMagicNumber(InpMrtMagic);
   if(MathAbs(nb - pb) >= 0.10 && nb >= tk.ask + lim && OrderSelect(tb))
      trade.OrderModify(tb, nb, 0, 0, ORDER_TIME_SPECIFIED, (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION));
   if(MathAbs(ns - ps) >= 0.10 && ns <= tk.bid - lim && OrderSelect(ts))
      trade.OrderModify(ts, ns, 0, 0, ORDER_TIME_SPECIFIED, (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION));
   trade.SetExpertMagicNumber(InpMagic);
}

// account money per $1 of price for 0.01 lot
double MrfMoneyPerUsd()
{
   double ts = SymbolInfoDouble(mr_sym, SYMBOL_TRADE_TICK_SIZE), tv = SymbolInfoDouble(mr_sym, SYMBOL_TRADE_TICK_VALUE);
   return ts > 0 ? 0.01 * tv / ts : 0;
}

bool MrfKnown(int d, ulong t)
{
   if(d == 1) { for(int i = 0; i < ArraySize(mrf_kb); i++) if(mrf_kb[i] == t) return true; }
   else       { for(int i = 0; i < ArraySize(mrf_ks); i++) if(mrf_ks[i] == t) return true; }
   return false;
}
void MrfRemember(int d, ulong t)
{
   if(MrfKnown(d, t)) return;
   if(d == 1) { int m = ArraySize(mrf_kb); ArrayResize(mrf_kb, m + 1); mrf_kb[m] = t; }
   else       { int m = ArraySize(mrf_ks); ArrayResize(mrf_ks, m + 1); mrf_ks[m] = t; }
}

// one side's basket
int MrfSide(int d, ulong &tk[], double &last, double &vol, double &pnl, double &sl)
{
   ArrayResize(tk, 0); last = 0; vol = 0; pnl = 0; sl = 0;
   datetime lt = 0; ulong lticket = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMrtMagic || PositionGetString(POSITION_SYMBOL) != mr_sym) continue;
      int pd = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      if(pd != d) continue;
      int m = ArraySize(tk); ArrayResize(tk, m + 1); tk[m] = t;
      vol += PositionGetDouble(POSITION_VOLUME);
      pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      double psl = PositionGetDouble(POSITION_SL);
      if(psl > 0) sl = sl == 0 ? psl : (d == 1 ? MathMax(sl, psl) : MathMin(sl, psl));   // v2.64: the most advanced SL = the line
      datetime pt = (datetime)PositionGetInteger(POSITION_TIME);
      if(pt > lt || (pt == lt && t > lticket)) { lt = pt; lticket = t; last = PositionGetDouble(POSITION_PRICE_OPEN); }
   }
   return ArraySize(tk);
}

void MrfReport(int d)
{
   double profit = 0, vol = 0; int so = 0, n = d == 1 ? ArraySize(mrf_kb) : ArraySize(mrf_ks);
   for(int q = 0; q < n; q++)
   {
      ulong pid = d == 1 ? mrf_kb[q] : mrf_ks[q];
      if(!HistorySelectByPosition(pid)) continue;
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong x = HistoryDealGetTicket(i);
         if(x == 0) continue;
         profit += HistoryDealGetDouble(x, DEAL_PROFIT) + HistoryDealGetDouble(x, DEAL_SWAP) + HistoryDealGetDouble(x, DEAL_COMMISSION);
         if(HistoryDealGetInteger(x, DEAL_ENTRY) == DEAL_ENTRY_IN) vol += HistoryDealGetDouble(x, DEAL_VOLUME);
         if(HistoryDealGetInteger(x, DEAL_ENTRY) == DEAL_ENTRY_OUT && HistoryDealGetInteger(x, DEAL_REASON) == DEAL_REASON_SO) so++;
      }
   }
   double lv[1]; color lc[1]; string lb[1];
   lv[0] = SymbolInfoDouble(mr_sym, SYMBOL_BID); lc[0] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[0] = "close";
   string fn = Snap(mr_sym, PERIOD_M5, "MRT", lv, lc, lb, 0, 0, 0, 0, false);
   if(so > 0)
      MrtEvent(StringFormat("MART STOP OUT %s | the broker closed %d of %d position(s) on a margin stop-out, %s basket %.2f lot, loss %.2f",
                            mr_sym, so, n, d == 1 ? "BUY" : "SELL", vol, profit) + Img(fn));
   else
      MrtEvent(StringFormat("MART BASKET CLOSED %s | %s basket of %d position(s), %.2f lot, closed on its trailing line, profit %.2f",
                            mr_sym, d == 1 ? "BUY" : "SELL", n, vol, profit) + Img(fn));
}

// pending MART orders: flip (comment MART L1F) or OCO (MART L1)
int MrfOrders(bool flip, ulong &ot[], int &otype[], double &opx[])
{
   ArrayResize(ot, 0); ArrayResize(otype, 0); ArrayResize(opx, 0);
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMrtMagic) continue;
      bool isflip = StringFind(OrderGetString(ORDER_COMMENT), "MART L1F") == 0;
      if(isflip != flip) continue;
      int m = ArraySize(ot); ArrayResize(ot, m + 1); ArrayResize(otype, m + 1); ArrayResize(opx, m + 1);
      ot[m] = t; otype[m] = (int)OrderGetInteger(ORDER_TYPE); opx[m] = OrderGetDouble(ORDER_PRICE_OPEN);
   }
   return ArraySize(ot);
}

void MrfDelete(bool flip)
{
   ulong ot[]; int ty[]; double px[];
   int k = MrfOrders(flip, ot, ty, px);
   trade.SetExpertMagicNumber(InpMrtMagic);
   for(int i = 0; i < k; i++) trade.OrderDelete(ot[i]);
   trade.SetExpertMagicNumber(InpMagic);
}

// one basket: adds before the trail, then the trailing line; returns true while trailing
// v2.64: put every position of the basket on the line (results checked; a failure is retried on the next tick)
void MrfSync(int d, ulong &bk[], int n, double line, MqlTick &tk, double pt, double lim)
{
   if(!(d == 1 ? line < tk.bid - lim : line > tk.ask + lim)) return;        // too close for the broker: the EA's own line covers it
   trade.SetExpertMagicNumber(InpMrtMagic);
   for(int i = 0; i < n; i++)
      if(PositionSelectByTicket(bk[i]) && MathAbs(PositionGetDouble(POSITION_SL) - line) > pt / 2)
         trade.PositionModify(bk[i], line, 0);
   trade.SetExpertMagicNumber(InpMagic);
}

// one basket: adds before the trail, then the trailing line; returns true while trailing
bool MrfManage(int d, ulong &bk[], int n, double last, double vol, double pnl, double sl, double A, MqlTick &tk, int dg, double pt, datetime now)
{
   int ix = d == 1 ? 0 : 1;
   double mp = MrfMoneyPerUsd();
   double lim = SymbolInfoInteger(mr_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt + 2 * pt;
   if(mrf_line[ix] <= 0 && sl > 0) { mrf_line[ix] = sl; mrf_tn[ix] = n; }    // after a restart: the line is the most advanced SL
   bool trailing = mrf_line[ix] > 0;
   double lockpx = MrtTpPrice(bk, d, InpMrtLock);
   if(!trailing)
   {
      // v2.67: arm as soon as the whole basket nets more than +InpMrtLock (3, the old basket TP); the line then
      // locks at least +InpMrtLock and trails InpMrtTrailK x ATR behind the price
      if(lockpx > 0 && (d == 1 ? tk.bid > lockpx : tk.ask < lockpx))
      {
         double line = d == 1 ? MathMax(tk.bid - InpMrtTrailK * A, lockpx) : MathMin(tk.ask + InpMrtTrailK * A, lockpx);
         line = NormalizeDouble(line, dg);
         bool ok = d == 1 ? line < tk.bid : line > tk.ask;
         if(!ok) { MrtCloseAll(bk, "trail line already reached"); return false; }
         mrf_line[ix] = line; mrf_tn[ix] = n;
         MrfSync(d, bk, n, line, tk, pt, lim);
         MrtEvent(StringFormat("MART TRAIL %s | %s basket of %d position(s), %.2f lot, floating %.2f: profit locked, stop line of every "
                               "position at %s (trails %.2f behind, basket +%.2f at worst; the EA closes ALL of them when it is touched)%s",
                               mr_sym, d == 1 ? "BUY" : "SELL", n, vol, pnl, PriceStr(mr_sym, line), InpMrtTrailK * A, InpMrtLock,
                               InpMrtFlipK > 0 ? StringFormat("; a %s STOP %.2f inside it starts the next basket", d == 1 ? "SELL" : "BUY", InpMrtFlipK * A) : ""));
         return true;
      }
      // add the next level
      double px = d == 1 ? tk.ask : tk.bid, S = InpMrtFlexK * A;
      if(S > 0 && now - mrf_lastadd >= 2 && (d == 1 ? px <= last - S : px >= last + S))
      {
         double lot = MrtLot(n);
         trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
         string cm = StringFormat("MART L%d", n + 1);
         bool ok = d == 1 ? trade.Buy(lot, mr_sym, 0, 0, 0, cm) : trade.Sell(lot, mr_sym, 0, 0, 0, cm);
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         mrf_lastadd = now;
         if(!ok) MrtEvent(StringFormat("ERROR | MART add %s level %d failed: %d %s", mr_sym, n + 1, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         else MrtEvent(StringFormat("MART ADD %s | %s level %d: %.2f at %s (%.2f = %.1f ATR below/above the last entry), basket %.2f lot, floating %.2f; "
                                    "next add %.2f further, trail arms %.2f beyond the basket breakeven",
                                    mr_sym, d == 1 ? "BUY" : "SELL", n + 1, lot, PriceStr(mr_sym, px), S, InpMrtFlexK, vol + lot, pnl, S, InpMrtArmK * A));
      }
      return false;
   }
   // v2.64: the line touched, or the broker already closed part of the basket on it -> the EA closes ALL the rest at once
   double line = mrf_line[ix];
   bool hit = d == 1 ? tk.bid <= line : tk.ask >= line;
   if(hit || n < mrf_tn[ix])
   {
      if(now - mrf_tryclose[ix] >= 3)
      {
         mrf_tryclose[ix] = now;
         MrtCloseAll(bk, hit ? "basket line reached" : "rest of the basket after the line");
      }
      return true;
   }
   // trailing: move the line in the profit direction only
   double want = d == 1 ? MathMax(tk.bid - InpMrtTrailK * A, lockpx) : MathMin(tk.ask + InpMrtTrailK * A, lockpx);
   want = NormalizeDouble(want, dg);
   bool better = d == 1 ? want >= line + 0.10 : want <= line - 0.10;
   if(better) { line = want; mrf_line[ix] = line; }
   MrfSync(d, bk, n, line, tk, pt, lim);
   return true;
}

// the opposite stop that rides inside the line of the one trailing basket
void MrfFlip(int d, double line, double A, MqlTick &tk, int dg, double pt, datetime now)
{
   if(InpMrtFlipK <= 0 || DayPaused()) { MrfDelete(true); return; }
   double G = InpMrtFlipK * A;
   double lim = SymbolInfoInteger(mr_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt + 2 * pt;
   double px = NormalizeDouble(d == 1 ? line + G : line - G, dg);
   bool valid = d == 1 ? px < tk.bid - lim : px > tk.ask + lim;               // sell stop below the bid / buy stop above the ask
   ulong ot[]; int ty[]; double opx[];
   int k = MrfOrders(true, ot, ty, opx);
   int want = d == 1 ? ORDER_TYPE_SELL_STOP : ORDER_TYPE_BUY_STOP;
   trade.SetExpertMagicNumber(InpMrtMagic); trade.SetTypeFillingBySymbol(mr_sym);
   bool have = false;
   for(int i = 0; i < k; i++)
   {
      if(ty[i] != want || have) { trade.OrderDelete(ot[i]); continue; }
      have = true;
      if(valid && MathAbs(opx[i] - px) >= 0.10) trade.OrderModify(ot[i], px, 0, 0, ORDER_TIME_GTC, 0);
   }
   if(!have && valid)
   {
      double lot = MrtLot(0);
      bool ok = d == 1 ? trade.SellStop(lot, px, mr_sym, 0, 0, ORDER_TIME_GTC, 0, "MART L1F")
                       : trade.BuyStop(lot, px, mr_sym, 0, 0, ORDER_TIME_GTC, 0, "MART L1F");
      if(!ok) MrtEvent(StringFormat("ERROR | MART flip order %s failed: %d %s", mr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
}

void MrfTimer(MqlDateTime &s, int minute, datetime now, bool live, MqlTick &tk, int dg, double pt)
{
   ulong bb[], bs[]; double lb, vb, pb, slb, ls, vs, ps, sls;
   int nb = MrfSide(1, bb, lb, vb, pb, slb);
   int ns = MrfSide(-1, bs, ls, vs, ps, sls);
   // closed baskets
   if(nb == 0 && ArraySize(mrf_kb) > 0) { MrfReport(1); ArrayResize(mrf_kb, 0); }
   if(ns == 0 && ArraySize(mrf_ks) > 0) { MrfReport(-1); ArrayResize(mrf_ks, 0); }
   if(nb == 0) { mrf_line[0] = 0; mrf_tn[0] = 0; }
   if(ns == 0) { mrf_line[1] = 0; mrf_tn[1] = 0; }
   // new baskets
   for(int side = 1; side >= -1; side -= 2)
   {
      int n = side == 1 ? nb : ns;
      if(n == 0) continue;
      bool fresh = side == 1 ? ArraySize(mrf_kb) == 0 : ArraySize(mrf_ks) == 0;
      for(int i = 0; i < n; i++) MrfRemember(side, side == 1 ? bb[i] : bs[i]);
      if(fresh)
      {
         MrfDelete(false);                                                     // the other OCO leg
         string how = "OCO stop";
         ulong t0 = side == 1 ? bb[0] : bs[0];
         if(PositionSelectByTicket(t0) && StringFind(PositionGetString(POSITION_COMMENT), "MART L1F") == 0) how = "flip stop (video trail)";
         MrtEvent(StringFormat("MART %s %s | basket opened: the %s filled at %s, lot %.2f; no SL until price is %.1f ATR beyond the basket breakeven",
                               side == 1 ? "BUY" : "SELL", mr_sym, how, PriceStr(mr_sym, side == 1 ? lb : ls), side == 1 ? vb : vs, InpMrtArmK));
      }
   }
   if(!live) return;
   double A = MrfAtr();
   if(A <= 0) return;
   bool trb = false, trs = false;
   if(nb > 0) trb = MrfManage(1, bb, nb, lb, vb, pb, slb, A, tk, dg, pt, now);
   if(ns > 0) trs = MrfManage(-1, bs, ns, ls, vs, ps, sls, A, tk, dg, pt, now);
   int open = (nb > 0 ? 1 : 0) + (ns > 0 ? 1 : 0);
   if(open == 1 && (trb || trs))
   {
      int d = trb ? 1 : -1;
      double ln = mrf_line[d == 1 ? 0 : 1];                                   // the EA's own line
      if(ln > 0) MrfFlip(d, ln, A, tk, dg, pt, now);
      return;
   }
   if(open > 0) { MrfDelete(true); return; }
   // flat: no flip orders, an OCO pair FlexK * ATR away
   MrfDelete(true);
   MrfOcoAdjust(A, tk, dg, pt);
   MrtBothSides(s, minute, now, live, tk, dg, InpMrtFlexK * A);
}
//+------------------------------------------------------------------+
