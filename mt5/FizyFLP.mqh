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
   FlpEvent(StringFormat("FLIP ONLINE | %s: always in %02d:%02d-%02d:%02d server, starts the day with a BUY; stop $%.2f behind the price, trailing on every "
                         "closed M1 bar until the trade is +$%.2f, then frozen; when hit it reverses at once; no TP; closed at 23:30 server; stops for the day "
                         "at $%.0f closed profit, lot %.2f | %d open position(s)",
                         fp_sym, InpFlpFromMin / 60, InpFlpFromMin % 60, InpFlpEndMin / 60, InpFlpEndMin % 60, InpFlpGap, InpFlpLock, InpFlpTarget,
                         InpFlpLot, fp_known > 0 ? 1 : 0));
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

   if(t > 0)
   {
      fp_known = t;
      if(!live || (datetime)PositionGetInteger(POSITION_TIME) < d0) { FlpClose(t, minute >= InpFlpEndMin ? "23:30 day end" : "outside the window", day); return; }
      if(done) { FlpClose(t, StringFormat("$%.0f target reached", InpFlpTarget), day); return; }
      // trail on each new closed M1 bar until frozen
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
   if(!any) dir = 1;                                                        // first trade of the day: BUY
   else if(reason == DEAL_REASON_SL) dir = -ldir;                           // the stop was hit: reverse
   else return;                                                             // closed some other way: wait for tomorrow
   if(now - fp_try < 5) return;
   fp_try = now;
   double mn = SymbolInfoDouble(fp_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(fp_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpFlpLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpFlpMagic); trade.SetTypeFillingBySymbol(fp_sym);
   bool ok = dir == 1 ? trade.Buy(lot, fp_sym, 0, NormalizeDouble(tk.bid - InpFlpGap, dg), 0, "FLIP B")
                      : trade.Sell(lot, fp_sym, 0, NormalizeDouble(tk.ask + InpFlpGap, dg), 0, "FLIP S");
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { FlpEvent(StringFormat("ERROR | gold FLIP %s failed: %d %s", dir == 1 ? "buy" : "sell", trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
   double e = dir == 1 ? tk.ask : tk.bid;
   string prev = any ? StringFormat(" | previous %s stopped, $%.2f", ldir == 1 ? "BUY" : "SELL", lastp) : " | first trade of the day";
   FlpEvent(StringFormat("FLIP %s %s | %.2f lot at about %s, stop %s ($%.0f), trails until +$%.0f then frozen%s, today $%.2f",
                         dir == 1 ? "BUY" : "SELL", fp_sym, lot, PriceStr(fp_sym, e),
                         PriceStr(fp_sym, dir == 1 ? tk.bid - InpFlpGap : tk.ask + InpFlpGap), InpFlpGap, InpFlpLock, prev, day));
   fp_bar = iTime(fp_sym, PERIOD_M1, 1);
}
//+------------------------------------------------------------------+
