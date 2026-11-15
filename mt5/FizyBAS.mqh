//+------------------------------------------------------------------+
//| FizyBAS.mqh - gold H1 BASE ZONE with the D1 colour, day trade,    |
//| demo only, included by FizyLB.mq5 (v2.32, 15 Nov 2026, rounds     |
//| v2.33: bases thinner than 0.4 x ATR(H1) are skipped (round 115g). |
//| 115c-115e; the owner: "no 1", then "macam mana nak validkan dulu  |
//| pada area base semalam atau kelmarin").                           |
//| Rules (research/base115c.py, base115e.py "LIMIT + INV-CLOSE"):    |
//|   base = the high / low (wick to wick) of the 23:00 server H1 bar  |
//|   of a trading day. The day closed red (D1 close < open) -> BUY   |
//|   zone at the base high; green -> SELL zone at the base low; a    |
//|   doji day gives no base.                                         |
//|   The base is valid for the next 5 trading days. From 01:30       |
//|   server the EA waits for an M1 close on the right side (above    |
//|   the high for a buy, below the low for a sell); the FIRST return |
//|   to the level is the entry (limit order at the level, or market  |
//|   if price is already through it); one trade per base.           |
//|   VALIDATION: the base is cancelled if any later D1 close is      |
//|   beyond its far side (buy base: a close below its low).          |
//|   SL beyond the other side + spread + 0.1 x the base height, no   |
//|   TP, entries 01:30-23:00 server, closed at 23:30 server.         |
//|   Pending orders are deleted at 23:00 and placed again at 01:30   |
//|   while the base is still valid; obeys the daily target.          |
//| Stateless: the zones are rebuilt every minute from D1 / H1 / M1   |
//| history, a used base is recognised by the order comment           |
//| "BASE yyyy.mm.dd" (base day) in the history, so restarts are safe.|
//| Round 115e at 0.01 lot, last 2 years: 394 trades (3.8 a week),    |
//| PF 1.80, years 1.28 / 2.07, stress 1.75, +$2,129, last 12 months  |
//| +$1,875, max drawdown -$250, worst day -$56; 91% of the fills are |
//| on the day after the base. Round 115d: most of the edge is the D1 |
//| colour (a plain 01:30 market order against it scores PF 1.59).    |
//| Events go to MQL5\Files\bas_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpBasOn       = true;
input string InpBasSymbol   = "XAUUSD";
input double InpBasLot      = 0.01;
input long   InpBasMagic    = 260333;
input int    InpBasHour     = 23;       // base = this server H1 bar of the day
input int    InpBasValid    = 5;        // trading days a base stays valid
input double InpBasBufH     = 0.1;      // SL buffer = spread + this x the base height
input bool   InpBasInvClose = true;     // cancel a base after a D1 close beyond its far side
input double InpBasMinAtr   = 0.4;      // v2.33: skip a base thinner than this x ATR(H1) (mean H1 range of the 14 bars up to it), 0 = off
input int    InpBasStartMin = 90;       // 01:30 server: first minute for a side / touch / entry
input int    InpBasLastMin  = 1380;     // 23:00 server: no entries after, pending orders deleted
input int    InpBasEndMin   = 1410;     // 23:30 server: a trade is closed

struct BasZ
{
   datetime day;                        // the base day (D1 bar time)
   double   hi, lo;
   int      dir;                        // +1 buy zone (red day), -1 sell zone (green day), 0 none
   int      state;                      // -1 history not ready, 0 gone, 1 waiting for the side, 2 armed
   int      why;                        // state 0: 1 returned already, 2 cancelled by a D1 close, 3 no base, 4 too thin
};

string   bz_sym = "";
bool     bz_ready = false;
datetime bz_last = 0;
datetime bz_bar = 0;                    // M1 bar the zones were last built on
datetime bz_mapday = 0;                 // day the zone map was sent
BasZ     bz_z[];
ulong    bz_known[];
datetime bz_told[];                     // bases whose order placement was already reported in this run

void BasEvent(string msg)
{
   int h = FileOpen("bas_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("base event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("BASE EVENT ", msg);
}

string BasComment(datetime day) { return "BASE " + TimeToString(day, TIME_DATE); }

// rebuild one base (D1 shift s >= 1) and replay the M1 bars since the next day began
void BasEval(int s, BasZ &z)
{
   z.state = 0; z.why = 3; z.dir = 0; z.hi = 0; z.lo = 0;
   datetime dt = iTime(bz_sym, PERIOD_D1, s);
   z.day = dt;
   if(dt == 0) { z.state = -1; return; }
   MqlDateTime ds; TimeToStruct(dt, ds);
   if(ds.day_of_week == 0 || ds.day_of_week == 6) return;
   double o = iOpen(bz_sym, PERIOD_D1, s), c = iClose(bz_sym, PERIOD_D1, s);
   if(o <= 0 || c <= 0) { z.state = -1; return; }
   z.dir = c < o ? 1 : (c > o ? -1 : 0);
   if(z.dir == 0) return;
   datetime ht = dt + InpBasHour * 3600;
   int hs = iBarShift(bz_sym, PERIOD_H1, ht, true);
   if(hs < 0 || iTime(bz_sym, PERIOD_H1, hs) != ht) return;               // that H1 bar does not exist (short day)
   z.hi = iHigh(bz_sym, PERIOD_H1, hs); z.lo = iLow(bz_sym, PERIOD_H1, hs);
   if(z.hi <= 0 || z.lo <= 0 || z.hi <= z.lo) return;
   if(InpBasMinAtr > 0)                                                    // v2.33, round 115g: a thin base puts the SL inside the noise
   {
      double rs = 0;
      for(int k = 0; k < 14; k++)
      {
         double h = iHigh(bz_sym, PERIOD_H1, hs + k), l = iLow(bz_sym, PERIOD_H1, hs + k);
         if(h <= 0 || l <= 0) { z.state = -1; return; }
         rs += h - l;
      }
      if(z.hi - z.lo < InpBasMinAtr * rs / 14.0) { z.why = 4; return; }
   }
   datetime t0 = iTime(bz_sym, PERIOD_D1, s - 1);
   if(t0 == 0) { z.state = -1; return; }
   MqlRates r[];
   int n = CopyRates(bz_sym, PERIOD_M1, t0, TimeCurrent(), r);
   if(n <= 0 && s - 1 > 0) { z.state = -1; return; }
   if(n > 0 && s - 1 > 0 && r[0].time - t0 > 3 * 3600) { z.state = -1; return; }   // M1 history has a hole: retry
   datetime cur = iTime(bz_sym, PERIOD_M1, 0);
   double pt = SymbolInfoDouble(bz_sym, SYMBOL_POINT);
   int kk = s - 1;                                                         // next day to check for a D1 close beyond the base
   bool side = false;
   for(int i = 0; i < n; i++)
   {
      if(r[i].time >= cur) break;                                          // closed bars only
      while(kk >= 1)
      {
         datetime dend = iTime(bz_sym, PERIOD_D1, kk - 1);
         if(dend == 0 || r[i].time < dend) break;
         if(InpBasInvClose)
         {
            double cc = iClose(bz_sym, PERIOD_D1, kk);
            if((z.dir == 1 && cc < z.lo) || (z.dir == -1 && cc > z.hi)) { z.state = 0; z.why = 2; return; }
         }
         kk--;
      }
      MqlDateTime bt; TimeToStruct(r[i].time, bt);
      int m = bt.hour * 60 + bt.min;
      if(m < InpBasStartMin || m >= InpBasLastMin) continue;
      if(!side)
      {
         if((z.dir == 1 && r[i].close > z.hi) || (z.dir == -1 && r[i].close < z.lo)) side = true;
         continue;
      }
      bool touch = z.dir == 1 ? (r[i].low + r[i].spread * pt <= z.hi) : (r[i].high >= z.lo);
      if(touch) { z.state = 0; z.why = 1; return; }                       // the first return is gone (filled or missed)
   }
   while(kk >= 1)                                                          // days that ended with no bar after them yet
   {
      datetime dend = iTime(bz_sym, PERIOD_D1, kk - 1);
      if(dend == 0 || dend > TimeCurrent()) break;
      if(InpBasInvClose)
      {
         double cc = iClose(bz_sym, PERIOD_D1, kk);
         if((z.dir == 1 && cc < z.lo) || (z.dir == -1 && cc > z.hi)) { z.state = 0; z.why = 2; return; }
      }
      kk--;
   }
   z.state = side ? 2 : 1;
}

int BasFind(datetime day)
{
   for(int i = 0; i < ArraySize(bz_z); i++) if(bz_z[i].day == day) return i;
   return -1;
}

datetime BasDayOf(string cm)
{
   if(StringFind(cm, "BASE ") != 0) return 0;
   return StringToTime(StringSubstr(cm, 5, 10));
}

bool BasHasOrder(string cm)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpBasMagic && OrderGetString(ORDER_SYMBOL) == bz_sym && OrderGetString(ORDER_COMMENT) == cm) return true;
   }
   return false;
}

// the base was already traded: an open position or a filled order with its comment
bool BasUsed(string cm, datetime day)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpBasMagic && PositionGetString(POSITION_COMMENT) == cm) return true;
   }
   if(!HistorySelect(day, TimeCurrent() + 60)) return true;                 // cannot tell: do not risk a second trade
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t == 0 || HistoryOrderGetInteger(t, ORDER_MAGIC) != InpBasMagic) continue;
      if(HistoryOrderGetString(t, ORDER_COMMENT) != cm) continue;
      if(HistoryOrderGetInteger(t, ORDER_STATE) == ORDER_STATE_FILLED || HistoryOrderGetDouble(t, ORDER_VOLUME_CURRENT) < HistoryOrderGetDouble(t, ORDER_VOLUME_INITIAL)) return true;
   }
   return false;
}

bool BasTold(datetime day)
{
   for(int i = 0; i < ArraySize(bz_told); i++) if(bz_told[i] == day) return true;
   int m = ArraySize(bz_told); ArrayResize(bz_told, m + 1); bz_told[m] = day;
   return false;
}

void BasInit()
{
   bz_sym = SymResolve(InpBasSymbol);
   bz_ready = true;
   if(bz_sym == "") { BasEvent("ERROR | base zone: symbol " + InpBasSymbol + " not found"); return; }
   SymbolSelect(bz_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpBasMagic) { int m = ArraySize(bz_known); ArrayResize(bz_known, m + 1); bz_known[m] = t; }
   }
   BasEvent(StringFormat("BASE ONLINE | %s: the %02d:00 server H1 bar of a red day = BUY zone at its high, of a green day = SELL zone at its low; "
                         "base at least %.1f x ATR(H1) tall, valid %d trading days, first return only, cancelled by a D1 close beyond its far side; SL beyond the base + spread + %.1f x its height, "
                         "no TP, entries 01:30-23:00 server, closed at 23:30 server, lot %.2f | %d open position(s)",
                         bz_sym, InpBasHour, InpBasMinAtr, InpBasValid, InpBasBufH, InpBasLot, ArraySize(bz_known)));
}

void BasReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "BASE SL HIT" : "BASE CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss beyond the base" : (reason == DEAL_REASON_EXPERT ? "23:30 day-end close" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(bz_sym, PERIOD_M15, "BSX", lv, lc, lb, 0, 0, 0, 0, false);
   BasEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, bz_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(bz_sym, inPx), PriceStr(bz_sym, outPx), why, profit) + Img(fn));
}

void BasDelete(ulong t, string why, bool tell)
{
   if(!OrderSelect(t)) return;
   string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_LIMIT ? "BUY LIMIT" : "SELL LIMIT";
   double pr = OrderGetDouble(ORDER_PRICE_OPEN);
   string cm = OrderGetString(ORDER_COMMENT);
   trade.SetExpertMagicNumber(InpBasMagic);
   bool ok = trade.OrderDelete(t);
   trade.SetExpertMagicNumber(InpMagic);
   if(ok && tell) BasEvent(StringFormat("BASE ORDER DELETED %s | %s %s of %s deleted (%s)", bz_sym, side, PriceStr(bz_sym, pr), cm, why));
}

void BasOnTimer()
{
   if(!InpBasOn) return;
   if(!bz_ready) BasInit();
   if(bz_sym == "") return;
   datetime now = TimeCurrent();
   if(now - bz_last < 2) return;
   bz_last = now;
   MqlDateTime st; TimeToStruct(now, st);
   int minute = st.hour * 60 + st.min;
   bool wday = st.day_of_week >= 1 && st.day_of_week <= 5;
   for(int q = ArraySize(bz_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(bz_known[q])) { BasReportClosed(bz_known[q]); ArrayRemove(bz_known, q, 1); }
   MqlTick tk;
   if(!SymbolInfoTick(bz_sym, tk) || now - tk.time > 600) return;          // market closed
   datetime d0 = iTime(bz_sym, PERIOD_D1, 0);
   if(d0 == 0) return;
   // open positions: report a new fill, close at 23:30 or when left from an earlier day
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong pt = PositionGetTicket(i);
      if(pt == 0 || PositionGetInteger(POSITION_MAGIC) != InpBasMagic || PositionGetString(POSITION_SYMBOL) != bz_sym) continue;
      bool known = false;
      for(int q = 0; q < ArraySize(bz_known); q++) if(bz_known[q] == pt) known = true;
      if(!known)
      {
         int m = ArraySize(bz_known); ArrayResize(bz_known, m + 1); bz_known[m] = pt;
         double lvf[2]; color lcf[2]; string lbf[2];
         lvf[0] = PositionGetDouble(POSITION_PRICE_OPEN); lcf[0] = clrBlue; lbf[0] = "entry";
         lvf[1] = PositionGetDouble(POSITION_SL); lcf[1] = clrIndianRed; lbf[1] = "SL";
         string pcm = PositionGetString(POSITION_COMMENT);
         bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double vol = PositionGetDouble(POSITION_VOLUME), op = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL);
         string fnf = Snap(bz_sym, PERIOD_M15, "BSF", lvf, lcf, lbf, 0, 0, 0, 0, false);
         BasEvent(StringFormat("BASE FILLED %s | %s %.2f lot from %s, SL %s, %s, no TP: closes at 23:30 server",
                  bz_sym, buy ? "BUY" : "SELL", vol, PriceStr(bz_sym, op), PriceStr(bz_sym, sl), pcm) + Img(fnf));
         if(!PositionSelectByTicket(pt)) continue;
      }
      if(minute >= InpBasEndMin || (datetime)PositionGetInteger(POSITION_TIME) < d0)
      {
         trade.SetExpertMagicNumber(InpBasMagic); trade.SetTypeFillingBySymbol(bz_sym);
         if(!trade.PositionClose(pt)) BasEvent(StringFormat("ERROR | base zone close %s failed: %d %s", bz_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   // the zones, rebuilt once per M1 bar
   datetime cb = iTime(bz_sym, PERIOD_M1, 0);
   if(cb != 0 && cb != bz_bar)
   {
      BasZ prev[];
      ArrayResize(prev, ArraySize(bz_z));
      for(int i = 0; i < ArraySize(bz_z); i++) prev[i] = bz_z[i];
      ArrayResize(bz_z, InpBasValid);
      bool ready = true;
      for(int s = 1; s <= InpBasValid; s++) { BasEval(s, bz_z[s - 1]); if(bz_z[s - 1].state < 0) ready = false; }
      bz_bar = ready ? cb : 0;
      for(int i = 0; i < ArraySize(bz_z); i++)                               // a base cancelled by yesterday's D1 close
      {
         if(bz_z[i].state != 0 || bz_z[i].why != 2) continue;
         for(int p = 0; p < ArraySize(prev); p++)
            if(prev[p].day == bz_z[i].day && prev[p].state >= 1)
               BasEvent(StringFormat("BASE CANCELLED %s | %s base of %s (%s-%s): a D1 close went beyond its %s side, so it is no longer valid",
                        bz_sym, bz_z[i].dir == 1 ? "BUY" : "SELL", TimeToString(bz_z[i].day, TIME_DATE), PriceStr(bz_sym, bz_z[i].lo),
                        PriceStr(bz_sym, bz_z[i].hi), bz_z[i].dir == 1 ? "lower" : "upper"));
      }
      if(ready && wday && minute >= InpBasStartMin && minute < InpBasStartMin + 60 && bz_mapday != d0)   // one zone map a day, 01:30-02:30
      {
         bz_mapday = d0;
         string txt = ""; int nl = 0;
         double lv[]; color lc[]; string lb[];
         ArrayResize(lv, 6); ArrayResize(lc, 6); ArrayResize(lb, 6);
         for(int i = 0; i < ArraySize(bz_z); i++)
         {
            if(bz_z[i].state < 1) continue;
            double lvl = bz_z[i].dir == 1 ? bz_z[i].hi : bz_z[i].lo;
            txt += StringFormat(" | %s %s at %s (base %s-%s, %s)", TimeToString(bz_z[i].day, TIME_DATE), bz_z[i].dir == 1 ? "BUY" : "SELL",
                                PriceStr(bz_sym, lvl), PriceStr(bz_sym, bz_z[i].lo), PriceStr(bz_sym, bz_z[i].hi),
                                bz_z[i].state == 2 ? "armed: waiting for the return" : "waiting for price to move away");
            if(nl < 6) { lv[nl] = lvl; lc[nl] = bz_z[i].dir == 1 ? clrSeaGreen : clrIndianRed; lb[nl] = (bz_z[i].dir == 1 ? "BUY " : "SELL ") + TimeToString(bz_z[i].day, TIME_DATE); nl++; }
         }
         if(nl > 0)
         {
            ArrayResize(lv, nl); ArrayResize(lc, nl); ArrayResize(lb, nl);
            string fn = Snap(bz_sym, PERIOD_H1, "BSZ", lv, lc, lb, 0, 0, 0, 0, false);
            BasEvent(StringFormat("BASE ZONES %s | %d valid base(s)", bz_sym, nl) + txt + Img(fn));
         }
      }
   }
   bool open = wday && minute >= InpBasStartMin && minute < InpBasLastMin;
   bool paused = DayPaused();
   // pending orders: keep only for an armed base inside the entry window
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpBasMagic || OrderGetString(ORDER_SYMBOL) != bz_sym) continue;
      int k = BasFind(BasDayOf(OrderGetString(ORDER_COMMENT)));
      bool old = (datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0;
      if(!open || old) BasDelete(t, "23:00, placed again at 01:30 while the base is valid", false);
      else if(paused) BasDelete(t, "daily target reached", true);
      else if(k >= 0 && bz_z[k].state == 0 && bz_z[k].why == 2) BasDelete(t, "base cancelled by a D1 close", true);
      else if(k < 0 && bz_bar != 0) BasDelete(t, "base expired", true);
   }
   if(!open || paused || bz_bar == 0) return;
   // place: one order per armed base
   int dg = (int)SymbolInfoInteger(bz_sym, SYMBOL_DIGITS);
   double pnt = SymbolInfoDouble(bz_sym, SYMBOL_POINT);
   double stops = MathMax((double)SymbolInfoInteger(bz_sym, SYMBOL_TRADE_STOPS_LEVEL), (double)SymbolInfoInteger(bz_sym, SYMBOL_TRADE_FREEZE_LEVEL)) * pnt;
   for(int i = 0; i < ArraySize(bz_z); i++)
   {
      if(bz_z[i].state != 2) continue;
      string cm = BasComment(bz_z[i].day);
      if(BasHasOrder(cm) || BasUsed(cm, bz_z[i].day)) continue;
      double ht = bz_z[i].hi - bz_z[i].lo, spr = tk.ask - tk.bid;
      double mn = SymbolInfoDouble(bz_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(bz_sym, SYMBOL_VOLUME_STEP);
      double lot = NormalizeDouble(MathMax(mn, MathFloor(InpBasLot / sv + 1e-9) * sv), 2);
      int em = (int)SymbolInfoInteger(bz_sym, SYMBOL_EXPIRATION_MODE);
      ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
      datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + InpBasLastMin * 60 + 300 : 0;   // backup: the EA deletes at 23:00
      bool ok = false, mkt = false; string kind = ""; double lvl = 0, sl = 0;
      trade.SetExpertMagicNumber(InpBasMagic); trade.SetTypeFillingBySymbol(bz_sym);
      if(bz_z[i].dir == 1)
      {
         lvl = NormalizeDouble(bz_z[i].hi, dg); sl = NormalizeDouble(bz_z[i].lo - spr - InpBasBufH * ht, dg);
         if(tk.bid <= sl) { trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol); continue; }
         if(tk.ask <= lvl) { ok = trade.Buy(lot, bz_sym, 0, sl, 0, cm); mkt = true; kind = "BUY at market (price already back at the base)"; }
         else if(tk.ask - lvl > stops) { ok = trade.BuyLimit(lot, lvl, bz_sym, sl, 0, tt, exp, cm); kind = "BUY LIMIT " + PriceStr(bz_sym, lvl); }
      }
      else
      {
         lvl = NormalizeDouble(bz_z[i].lo, dg); sl = NormalizeDouble(bz_z[i].hi + spr + InpBasBufH * ht, dg);
         if(tk.ask >= sl) { trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol); continue; }
         if(tk.bid >= lvl) { ok = trade.Sell(lot, bz_sym, 0, sl, 0, cm); mkt = true; kind = "SELL at market (price already back at the base)"; }
         else if(lvl - tk.bid > stops) { ok = trade.SellLimit(lot, lvl, bz_sym, sl, 0, tt, exp, cm); kind = "SELL LIMIT " + PriceStr(bz_sym, lvl); }
      }
      uint rc = trade.ResultRetcode(); string rd = trade.ResultRetcodeDescription();
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(kind == "") continue;                                              // too close to the level for a limit: wait
      if(!ok) { BasEvent(StringFormat("ERROR | base zone %s %s for %s failed: %d %s", bz_sym, kind, cm, rc, rd)); continue; }
      if(mkt || !BasTold(bz_z[i].day))
      {
         double risk = MathAbs(lvl - sl) * SymbolInfoDouble(bz_sym, SYMBOL_TRADE_TICK_VALUE) / SymbolInfoDouble(bz_sym, SYMBOL_TRADE_TICK_SIZE) * lot;
         double lv[3]; color lc[3]; string lb[3];
         lv[0] = bz_z[i].hi; lc[0] = clrGray; lb[0] = "base high"; lv[1] = bz_z[i].lo; lc[1] = clrGray; lb[1] = "base low";
         lv[2] = sl; lc[2] = clrIndianRed; lb[2] = "SL";
         string fn = mkt ? "" : Snap(bz_sym, PERIOD_M15, "BS", lv, lc, lb, 0, 0, 0, 0, false);
         if(!mkt)
            BasEvent(StringFormat("BASE ORDER PLACED %s | %s (SL %s), base of %s (%s day, %s-%s), lot %.2f, risk about $%.2f, no TP | "
                                  "deleted at 23:00 server and placed again at 01:30 while the base is valid; a trade closes at 23:30 server",
                                  bz_sym, kind, PriceStr(bz_sym, sl), TimeToString(bz_z[i].day, TIME_DATE), bz_z[i].dir == 1 ? "red" : "green",
                                  PriceStr(bz_sym, bz_z[i].lo), PriceStr(bz_sym, bz_z[i].hi), lot, risk) + Img(fn));
      }
   }
}
//+------------------------------------------------------------------+
