//+------------------------------------------------------------------+
//| FizyFLP.mqh - gold M1 stop-and-reverse with a FROZEN stop         |
//| (GOLD FLIP), demo only, included by FizyLB.mq5 (v2.30, 14 Nov     |
//| 2026, rounds 113-113d; the owner's TikTok "buy stop / sell stop"  |
//| idea: "buat ea ikut pf yang paling tinggi. dapat 25$ terus stop") |
//| Rules (research/flip113d.py, centre cell gap $5, lock +$1):       |
//|   always in the market 01:30-23:30 server on weekdays, one        |
//|   position; the day starts with a BUY at market; the stop sits    |
//|   $5 behind the price and trails it on every closed M1 bar until  |
//|   the trade has been +$1 (10 pips) in profit, then it FREEZES and |
//|   waits; when it is hit the EA opens the other way at once with   |
//|   a fresh $5 stop. No TP. Closed at 23:30 server.                 |
//|   Lock state is read back from the SL itself (stateless): a long  |
//|   is frozen once SL >= entry + lock - gap (mirror for a short).   |
//|   Stops for the day once this module's own closed profit today    |
//|   reaches $25 (the open position is closed); obeys DayPaused()    |
//|   for new entries / reversals like the other modules.             |
//| Round 113d at 0.01 lot, last 2 years: 6,637 trades (13 a day),    |
//| win 18%, PF 1.22, years 1.31 / 1.19, stress 1.16, buys 1.23 /     |
//| sells 1.21, start long / short / random 1.22 / 1.22 / 1.23,       |
//| +$4,550, every quarter positive, max DD -$855, worst day -$154;   |
//| with the $25 target PF 1.19, +$3,336, max DD -$865. Plateau: gap  |
//| $3-10 x lock $0.5-3 all PF 1.11-1.24. The plain trailing version  |
//| (round 113, no freeze) loses.                                     |
//| v2.35 (16 Nov, round 121, owner: "aku nak on the spot real time"): |
//| the stop now trails every second instead of once per closed M1    |
//| bar (InpFlpRealTime); last 3 months PF 1.38 +$836 vs 1.50 +$1,079, |
//| the 3 before 1.35 +$817 vs 1.12 +$343 (6 months +$1,653 / +$1,422).|
//| v2.36 (16 Nov, round 121f, the owner's order "pasang. aku nak     |
//| test"): InpFlpFixTrail - the stop stays FIXED $4 from the entry   |
//| until the trade is +$1, then it follows the price in real time    |
//| $4 behind it and is never frozen. Round 121f: last 3 months PF    |
//| 1.09 +$686 (coin order 0.66) vs the freeze 1.38 +$836: it FAILED   |
//| the test and runs on the owner's word. False = the v2.35 freeze.  |
//| Events go to MQL5\Files\flp_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpFlpOn       = true;
input string InpFlpSymbol   = "XAUUSD";
input double InpFlpLot      = 0.01;
input long   InpFlpMagic    = 260332;
input double InpFlpGap      = 5.0;      // stop distance in price ($5 = 50 pips)
input double InpFlpLock     = 1.0;      // freeze the stop once the trade has been this far in profit ($1 = 10 pips)
input double InpFlpTarget   = 25.0;     // this module stops for the day at this closed profit ($)
input int    InpFlpFromMin  = 90;       // 01:30 server
input int    InpFlpEndMin   = 1410;     // 23:30 server
input bool   InpFlpOco      = true;     // v2.31: start the day with a BUY STOP / SELL STOP pair instead of a market BUY
input double InpFlpOcoDist  = 3.0;      // the pair sits at the 01:30 open +- this ($3 = 30 pips; round 113g plateau $2-5)
input bool   InpFlpRealTime = true;     // v2.35: trail the stop every second (true) instead of once per closed M1 bar (round 121)
input double InpFlpStep     = 0.10;     // real-time trailing: move the stop only when it gains at least this much ($0.10 = 1 pip)
input bool   InpFlpFixTrail = true;     // v2.36 (owner): fixed stop until +lock, then a real-time trail that never freezes (round 121f)
input double InpFlpSl       = 4.0;      // v2.36: the fixed stop distance from the entry ($4 = 40 pips)
input double InpFlpTrail    = 4.0;      // v2.36: the trail distance behind the price once the trade has been +lock

double FlpGap() { return InpFlpFixTrail ? InpFlpSl : InpFlpGap; }

string   fp_sym = "";
bool     fp_ready = false;
datetime fp_bar = 0;                    // last closed M1 bar used for the trail
datetime fp_try = 0;                    // last open attempt
ulong    fp_known = 0;                  // open position ticket being watched
datetime fp_doneday = 0;                // day the $25 target was reported

void FlpEvent(string msg)
{
   int h = FileOpen("flp_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("FLP event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("FLIP EVENT ", msg);
}

// today's closed P&L of this module; last closing deal's reason and the closed position's direction (+1 buy, -1 sell, 0 none)
double FlpDay(datetime d0, long &reason, int &dir, double &lastp)
{
   reason = -1; dir = 0; lastp = 0;
   double s = 0; datetime lt = 0;
   if(!HistorySelect(d0, TimeCurrent() + 60)) return 0;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0 || HistoryDealGetInteger(d, DEAL_MAGIC) != InpFlpMagic || HistoryDealGetString(d, DEAL_SYMBOL) != fp_sym) continue;
      double p = HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      s += p;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      datetime t = (datetime)HistoryDealGetInteger(d, DEAL_TIME);
      if(t >= lt)
      {
         lt = t; reason = HistoryDealGetInteger(d, DEAL_REASON); lastp = p;
         dir = HistoryDealGetInteger(d, DEAL_TYPE) == DEAL_TYPE_SELL ? 1 : -1;   // the out deal of a buy is a sell
      }
   }
   return s;
}

// pending FLIP orders of this module; old = one placed before today
int FlpPending(datetime d0, bool &old)
{
   int c = 0; old = false;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpFlpMagic || OrderGetString(ORDER_SYMBOL) != fp_sym) continue;
      c++;
      if((datetime)OrderGetInteger(ORDER_TIME_SETUP) < d0) old = true;
   }
   return c;
}

void FlpDeletePending(string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpFlpMagic || OrderGetString(ORDER_SYMBOL) != fp_sym) continue;
      string side = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      trade.SetExpertMagicNumber(InpFlpMagic);
      if(trade.OrderDelete(t)) FlpEvent(StringFormat("FLIP ORDER DELETED %s | %s %s deleted (%s)", fp_sym, side, PriceStr(fp_sym, pr), why));
      trade.SetExpertMagicNumber(InpMagic);
   }
}

// first trade of the day by an OCO pair at the 01:30 open +- InpFlpOcoDist. Returns +1 / -1 when a level was already
// passed (late start: enter that way at market now), 0 when the pair is placed / waiting / not ready yet.
int FlpOco(datetime d0, MqlTick &tk, datetime now)
{
   bool old; if(FlpPending(d0, old) > 0) return 0;
   MqlRates r[];
   int n = CopyRates(fp_sym, PERIOD_M1, d0 + InpFlpFromMin * 60, now, r);
   if(n < 1) return 0;                                                      // no M1 bar since 01:30 yet
   double pt = SymbolInfoDouble(fp_sym, SYMBOL_POINT);
   int dg = (int)SymbolInfoInteger(fp_sym, SYMBOL_DIGITS);
   double op = r[0].open, up = NormalizeDouble(op + InpFlpOcoDist, dg), dn = NormalizeDouble(op - InpFlpOcoDist, dg);
   for(int i = 0; i < n; i++)                                                // a level taken before the pair could be placed
   {
      if(r[i].time >= now - now % 60) break;
      bool hb = r[i].high + r[i].spread * pt >= up, hs = r[i].low <= dn;
      if(hb && hs) return (up - (r[i].open + r[i].spread * pt) <= r[i].open - dn) ? 1 : -1;
      if(hb) return 1;
      if(hs) return -1;
   }
   if(tk.ask >= up) return 1;
   if(tk.bid <= dn) return -1;
   if(now - fp_try < 5) return 0;
   fp_try = now;
   double mn = SymbolInfoDouble(fp_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(fp_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpFlpLot / sv + 1e-9) * sv), 2);
   double spr = tk.ask - tk.bid;
   int em = (int)SymbolInfoInteger(fp_sym, SYMBOL_EXPIRATION_MODE);
   ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_GTC) != 0) ? ORDER_TIME_GTC : ORDER_TIME_SPECIFIED;
   datetime exp = (tt == ORDER_TIME_SPECIFIED) ? d0 + InpFlpEndMin * 60 + 300 : 0;   // backup: the EA deletes at 23:30
   trade.SetExpertMagicNumber(InpFlpMagic); trade.SetTypeFillingBySymbol(fp_sym);
   bool b = trade.BuyStop(lot, up, fp_sym, NormalizeDouble(up - spr - FlpGap(), dg), 0, tt, exp, "FLIP BS");
   string eb = b ? "" : StringFormat(" | buy stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   bool s_ = trade.SellStop(lot, dn, fp_sym, NormalizeDouble(dn + spr + FlpGap(), dg), 0, tt, exp, "FLIP SS");
   string es = s_ ? "" : StringFormat(" | sell stop error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!b && !s_) { FlpEvent("ERROR | gold FLIP OCO not placed" + eb + es); FlpDeletePending("half pair"); return 0; }
   if(!b || !s_) { FlpDeletePending("only one side placed, retrying"); FlpEvent("ERROR | gold FLIP OCO half placed" + eb + es); return 0; }
   FlpEvent(StringFormat("FLIP OCO PLACED %s | 01:30 open %s: BUY STOP %s, SELL STOP %s (+-$%.0f), lot %.2f; the first to fill starts the day, the other is deleted",
                         fp_sym, PriceStr(fp_sym, op), PriceStr(fp_sym, up), PriceStr(fp_sym, dn), InpFlpOcoDist, lot));
   return 0;
}

ulong FlpPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpFlpMagic && PositionGetString(POSITION_SYMBOL) == fp_sym) return t;
   }
   return 0;
}

void FlpInit()
{
   fp_sym = SymResolve(InpFlpSymbol);
   fp_ready = true;
   if(fp_sym == "") { FlpEvent("ERROR | gold FLIP: symbol " + InpFlpSymbol + " not found"); return; }
   SymbolSelect(fp_sym, true);
   fp_known = FlpPosition();
   string how = InpFlpFixTrail
      ? StringFormat("stop fixed $%.2f from the entry until the trade is +$%.2f, then it follows the price in real time $%.2f behind (never frozen)", InpFlpSl, InpFlpLock, InpFlpTrail)
      : StringFormat("stop $%.2f behind the price, trailing until the trade is +$%.2f, then frozen", InpFlpGap, InpFlpLock);
   FlpEvent(StringFormat("FLIP ONLINE | %s: always in %02d:%02d-%02d:%02d server, starts the day with %s; %s; when hit it reverses at once; "
                         "no TP; closed at 23:30 server; stops for the day at $%.0f closed profit, lot %.2f | %d open position(s)",
                         fp_sym, InpFlpFromMin / 60, InpFlpFromMin % 60, InpFlpEndMin / 60, InpFlpEndMin % 60,
                         InpFlpOco ? StringFormat("a BUY STOP / SELL STOP at the 01:30 open +-$%.0f (first fill wins)", InpFlpOcoDist) : "a market BUY",
                         how, InpFlpTarget, InpFlpLot, fp_known > 0 ? 1 : 0));
}

void FlpClose(ulong t, string why, double day)
{
   if(!PositionSelectByTicket(t)) return;
   bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   double pr = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   trade.SetExpertMagicNumber(InpFlpMagic); trade.SetTypeFillingBySymbol(fp_sym);
   bool ok = trade.PositionClose(t);
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { FlpEvent(StringFormat("ERROR | gold FLIP close failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
   FlpEvent(StringFormat("FLIP CLOSED %s | %s closed (%s), profit $%.2f, today $%.2f", fp_sym, buy ? "BUY" : "SELL", why, pr, day + pr));
   fp_known = 0;
}

void FlpOnTimer()
{
   if(!InpFlpOn) return;
   if(!fp_ready) FlpInit();
   if(fp_sym == "") return;
   datetime now = TimeCurrent();
   MqlTick tk;
   if(!SymbolInfoTick(fp_sym, tk) || now - tk.time > 600) return;          // market closed
   MqlDateTime st; TimeToStruct(now, st);
   int minute = st.hour * 60 + st.min;
   datetime d0 = iTime(fp_sym, PERIOD_D1, 0);
   if(d0 == 0) return;
   bool wday = st.day_of_week >= 1 && st.day_of_week <= 5;
   bool live = wday && minute >= InpFlpFromMin && minute < InpFlpEndMin;
   long reason; int ldir; double lastp;
   double day = FlpDay(d0, reason, ldir, lastp);
   bool done = day >= InpFlpTarget;
   ulong t = FlpPosition();
   double pt = SymbolInfoDouble(fp_sym, SYMBOL_POINT);
   int dg = (int)SymbolInfoInteger(fp_sym, SYMBOL_DIGITS);

   bool oldp; int npend = FlpPending(d0, oldp);
   if(t > 0)
   {
      if(fp_known != t)
      {
         string cm = PositionGetString(POSITION_COMMENT);
         if(StringFind(cm, "FLIP BS") == 0 || StringFind(cm, "FLIP SS") == 0)
            FlpEvent(StringFormat("FLIP %s %s | the %s filled at %s, stop %s ($%.0f), " + (InpFlpFixTrail ? "trails from +$%.0f, never frozen" : "trails until +$%.0f then frozen") + " | first trade of the day",
                     PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL", fp_sym,
                     PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY STOP" : "SELL STOP",
                     PriceStr(fp_sym, PositionGetDouble(POSITION_PRICE_OPEN)), PriceStr(fp_sym, PositionGetDouble(POSITION_SL)), FlpGap(), InpFlpLock));
      }
      fp_known = t;
      if(npend > 0) { FlpDeletePending("the other side filled"); if(!PositionSelectByTicket(t)) return; }
      if(!live || (datetime)PositionGetInteger(POSITION_TIME) < d0) { FlpClose(t, minute >= InpFlpEndMin ? "23:30 day end" : "outside the window", day); return; }
      if(done) { FlpClose(t, StringFormat("$%.0f target reached", InpFlpTarget), day); return; }
      if(InpFlpFixTrail)
      {
         // v2.36: the stop stays where it was placed (entry -+ InpFlpSl) until the trade has been +lock, then it follows
         // the price every second InpFlpTrail behind it and never freezes. Active = +lock now, or the stop already moved.
         bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double ent = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL);
         double lvl = SymbolInfoInteger(fp_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
         double ns;
         if(buy)
         {
            bool act = tk.bid - ent >= InpFlpLock || sl > ent - InpFlpSl + 0.05;
            if(!act) return;
            ns = MathMin(MathMax(sl, tk.bid - InpFlpTrail), tk.bid - lvl - pt);
            if(ns < sl + InpFlpStep) return;
         }
         else
         {
            bool act = ent - tk.ask >= InpFlpLock || (sl > 0 && sl < ent + InpFlpSl - 0.05);
            if(!act) return;
            ns = tk.ask + InpFlpTrail;
            if(sl > 0) ns = MathMin(sl, ns);
            ns = MathMax(ns, tk.ask + lvl + pt);
            if(sl > 0 && ns > sl - InpFlpStep) return;
         }
         ns = NormalizeDouble(ns, dg);
         trade.SetExpertMagicNumber(InpFlpMagic);
         if(!trade.PositionModify(t, ns, 0))
            FlpEvent(StringFormat("ERROR | gold FLIP stop move failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic);
         return;
      }
      if(InpFlpRealTime)
      {
         // v2.35: trail in real time (checked every second) until the trade has been +lock, then freeze at entry +- (lock - gap)
         bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double ent = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL);
         double lvl = SymbolInfoInteger(fp_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
         double ns = sl;
         bool freeze = false;
         if(buy)
         {
            if(sl >= ent + InpFlpLock - InpFlpGap - pt / 2) return;          // frozen
            if(tk.bid - ent >= InpFlpLock) { ns = MathMax(sl, ent + InpFlpLock - InpFlpGap); freeze = true; }
            else ns = MathMax(sl, tk.bid - InpFlpGap);
            ns = MathMin(ns, tk.bid - lvl - pt);
            if(ns < sl + (freeze ? pt / 2 : InpFlpStep)) return;
         }
         else
         {
            if(sl > 0 && sl <= ent - InpFlpLock + InpFlpGap + pt / 2) return; // frozen
            if(ent - tk.ask >= InpFlpLock) { ns = ent - InpFlpLock + InpFlpGap; freeze = true; }
            else ns = tk.ask + InpFlpGap;
            if(sl > 0) ns = MathMin(sl, ns);
            ns = MathMax(ns, tk.ask + lvl + pt);
            if(sl > 0 && ns > sl - (freeze ? pt / 2 : InpFlpStep)) return;
         }
         ns = NormalizeDouble(ns, dg);
         trade.SetExpertMagicNumber(InpFlpMagic);
         if(!trade.PositionModify(t, ns, 0))
            FlpEvent(StringFormat("ERROR | gold FLIP stop move failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         else if(freeze)
            Print(StringFormat("FLIP stop frozen at %s (entry %s)", PriceStr(fp_sym, ns), PriceStr(fp_sym, ent)));
         trade.SetExpertMagicNumber(InpMagic);
         return;
      }
      // trail on each new closed M1 bar until frozen (v2.30-v2.34)
      datetime b1 = iTime(fp_sym, PERIOD_M1, 1);
      if(b1 == 0 || b1 == fp_bar) return;
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      if(b1 < ot - ot % 60) { fp_bar = b1; return; }
      MqlRates r[];
      if(CopyRates(fp_sym, PERIOD_M1, 1, 1, r) != 1) return;
      fp_bar = b1;
      bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      double ent = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL);
      double lvl = SymbolInfoInteger(fp_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
      double ns = sl;
      if(buy)
      {
         if(sl >= ent + InpFlpLock - InpFlpGap - pt / 2) return;            // frozen
         ns = MathMax(sl, r[0].high - InpFlpGap);
         ns = MathMin(ns, tk.bid - lvl - pt);
         if(ns <= sl + pt / 2) return;
      }
      else
      {
         if(sl > 0 && sl <= ent - InpFlpLock + InpFlpGap + pt / 2) return;  // frozen
         ns = r[0].low + r[0].spread * pt + InpFlpGap;
         if(sl > 0) ns = MathMin(sl, ns);
         ns = MathMax(ns, tk.ask + lvl + pt);
         if(sl > 0 && ns >= sl - pt / 2) return;
      }
      ns = NormalizeDouble(ns, dg);
      trade.SetExpertMagicNumber(InpFlpMagic);
      if(!trade.PositionModify(t, ns, 0))
         FlpEvent(StringFormat("ERROR | gold FLIP stop move failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      else if(buy ? ns >= ent + InpFlpLock - InpFlpGap - pt / 2 : ns <= ent - InpFlpLock + InpFlpGap + pt / 2)
         Print(StringFormat("FLIP stop frozen at %s (entry %s)", PriceStr(fp_sym, ns), PriceStr(fp_sym, ent)));
      trade.SetExpertMagicNumber(InpMagic);
      return;
   }

   // no position
   if(fp_known > 0) fp_known = 0;
   if(npend > 0 && (!live || done || oldp || DayPaused()))
   { FlpDeletePending(!live ? "23:30, not triggered" : (done ? "daily target reached" : (oldp ? "left from an earlier day" : "EA daily target reached"))); npend = 0; }
   if(done)
   {
      if(fp_doneday != d0 && live)
      {
         fp_doneday = d0;
         FlpEvent(StringFormat("FLIP TARGET REACHED %s | today's closed profit $%.2f >= $%.0f: no more flips until tomorrow", fp_sym, day, InpFlpTarget));
      }
      return;
   }
   if(!live || DayPaused()) return;
   int dir = 0;
   bool any = reason >= 0;                                                 // a position of this module was closed today
   if(!any)                                                                 // first trade of the day
   {
      if(!InpFlpOco) dir = 1;
      else { dir = FlpOco(d0, tk, now); if(dir == 0) return; }
   }
   else if(reason == DEAL_REASON_SL) dir = -ldir;                           // the stop was hit: reverse
   else return;                                                             // closed some other way: wait for tomorrow
   if(now - fp_try < 5) return;
   fp_try = now;
   double mn = SymbolInfoDouble(fp_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(fp_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpFlpLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpFlpMagic); trade.SetTypeFillingBySymbol(fp_sym);
   bool ok = dir == 1 ? trade.Buy(lot, fp_sym, 0, NormalizeDouble(tk.bid - FlpGap(), dg), 0, "FLIP B")
                      : trade.Sell(lot, fp_sym, 0, NormalizeDouble(tk.ask + FlpGap(), dg), 0, "FLIP S");
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { FlpEvent(StringFormat("ERROR | gold FLIP %s failed: %d %s", dir == 1 ? "buy" : "sell", trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
   double e = dir == 1 ? tk.ask : tk.bid;
   string prev = any ? StringFormat(" | previous %s stopped, $%.2f", ldir == 1 ? "BUY" : "SELL", lastp) : " | first trade of the day";
   FlpEvent(StringFormat("FLIP %s %s | %.2f lot at about %s, stop %s ($%.0f), " + (InpFlpFixTrail ? "trails from +$%.0f, never frozen" : "trails until +$%.0f then frozen") + "%s, today $%.2f",
                         dir == 1 ? "BUY" : "SELL", fp_sym, lot, PriceStr(fp_sym, e),
                         PriceStr(fp_sym, dir == 1 ? tk.bid - FlpGap() : tk.ask + FlpGap()), FlpGap(), InpFlpLock, prev, day));
   fp_bar = iTime(fp_sym, PERIOD_M1, 1);
}
//+------------------------------------------------------------------+
