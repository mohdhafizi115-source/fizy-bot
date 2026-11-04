//+------------------------------------------------------------------+
//| FizySPK.mqh - gold M1 spike fade, demo only, included by          |
//| FizyLB.mq5. The first M1 rule that ever passed on this broker's   |
//| own data (research/scalpcost37.py, spike38.py, spike39.py;        |
//| JustMarkets M1 2020-03 .. 2026-11, 1,064 trades, 0.62 a day:      |
//| PF 1.37 after spread, halves 1.33 / 1.38, stress 1.30, +$675 per  |
//| 0.01 lot, last 12 months +$519, max drawdown $87, every year      |
//| 0.99 or better and 2022 the best at 1.45, so it is not just the   |
//| gold uptrend).                                                    |
//| Rules, all on closed M1 bars:                                     |
//|   1. COST GATE: ATR(14, M1) >= InpSpkAtrSpread x the current      |
//|      spread. This gate is what makes the rule work: without it    |
//|      the same trade is PF 0.80, with it 1.37. On M1 the move has  |
//|      to dwarf the cost.                                           |
//|   2. SIGNAL: the bar that just closed fell (close < open) and its |
//|      range >= InpSpkAtr x ATR(14, M1 up to the bar before it).    |
//|   3. BUY at the next bar's open. SL = that bar's low - 0.2 ATR.   |
//|      TP = its close + 0.75 x its range. Out after 20 minutes.     |
//|   Signal bars 01:30-22:00 server, one position at a time.         |
//| Only the BUY side is traded: fading UP spikes scored PF 0.92 and  |
//| lost money, so it is left out.                                    |
//| Events go to MQL5\Files\spk_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpSpkOn        = true;
input string InpSpkSymbol    = "XAUUSD";
input double InpSpkLot       = 0.01;
input long   InpSpkMagic     = 260320;
input double InpSpkAtr       = 3.0;      // the spike's range, in ATR(14, M1)
input double InpSpkAtrSpread = 8.0;      // the cost gate: ATR(M1) must be at least this x the spread
input double InpSpkSlAtr     = 0.2;      // SL this far below the spike's low, in ATR(M1)
input double InpSpkTpRange   = 0.75;     // TP this much of the spike's range above its close
input int    InpSpkHoldMin   = 20;       // close at market after this many minutes

string   sp_sym = "";
bool     sp_ready = false;
datetime sp_bar = 0;
ulong    sp_known[];

void SpkEvent(string msg)
{
   int h = FileOpen("spk_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("spike event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("SPIKE EVENT ", msg);
}

bool SpkPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpSpkMagic && PositionGetString(POSITION_SYMBOL) == sp_sym) { ticket = t; return true; }
   }
   return false;
}

void SpkInit()
{
   sp_ready = true;
   sp_sym = SymResolve(InpSpkSymbol);
   if(sp_sym == "") { SpkEvent("ERROR | M1 spike fade: symbol " + InpSpkSymbol + " not found"); return; }
   SymbolSelect(sp_sym, true);
   ulong t;
   if(SpkPosition(t)) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = t; }
   SpkEvent(StringFormat("SPIKE ONLINE | %s M1: BUY when a down bar of %.0f x ATR(M1) closes AND ATR(M1) >= %.0f x the spread "
                         "(the cost gate), SL %.1f ATR below its low, TP %.2f of its range, out after %d min, lot %.2f | %d open position(s)",
                         sp_sym, InpSpkAtr, InpSpkAtrSpread, InpSpkSlAtr, InpSpkTpRange, InpSpkHoldMin, InpSpkLot, ArraySize(sp_known)));
}

void SpkReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) inPx = HistoryDealGetDouble(d, DEAL_PRICE);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = reason == DEAL_REASON_SL ? "SPIKE SL HIT" : (reason == DEAL_REASON_TP ? "SPIKE TP HIT" : "SPIKE CLOSED");
   string why = reason == DEAL_REASON_SL ? "stop loss below the spike low"
              : (reason == DEAL_REASON_TP ? "take profit, 0.75 of the spike range"
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d minutes up", InpSpkHoldMin) : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sp_sym, PERIOD_M1, "SPX", lv, lc, lb, 0, 0, 0, 0, false);
   SpkEvent(StringFormat("%s %s | BUY from %s closed at %s (%s), profit $%.2f", what, sp_sym, PriceStr(sp_sym, inPx),
                         PriceStr(sp_sym, outPx), why, profit) + Img(fn));
}

void SpkOnTimer()
{
   if(!InpSpkOn) return;
   if(!sp_ready) SpkInit();
   if(sp_sym == "") return;
   for(int q = ArraySize(sp_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(sp_known[q])) { SpkReportClosed(sp_known[q]); ArrayRemove(sp_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(sp_sym, tk) || now - tk.time > 600) return;              // market closed
   ulong pt;
   if(SpkPosition(pt))
   {
      bool known = false;
      for(int q = 0; q < ArraySize(sp_known); q++) if(sp_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = pt; }
      PositionSelectByTicket(pt);
      MqlDateTime ns; TimeToStruct(now, ns);
      long held = (long)(now - (datetime)PositionGetInteger(POSITION_TIME));
      if(held >= (long)InpSpkHoldMin * 60 || ns.hour * 60 + ns.min >= 1350)    // time exit, and never past 22:30
      {
         trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
         if(!trade.PositionClose(pt)) SpkEvent(StringFormat("ERROR | spike close %s failed: %d %s", sp_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;                                                                  // one position at a time
   }
   datetime b0 = iTime(sp_sym, PERIOD_M1, 0);
   if(b0 == 0 || b0 == sp_bar) return;                                         // act once per new M1 bar
   MqlRates r[];
   int n = CopyRates(sp_sym, PERIOD_M1, 1, 40, r);                             // closed bars, r[n-1] = the bar that just closed
   if(n < 30) return;                                                          // history not loaded yet: retry next tick
   sp_bar = b0;
   int j = n - 1;
   // ATR(14) Wilder over the bars BEFORE the signal bar, as in the test
   double atr = r[1].high - r[1].low;
   for(int i = 2; i < j; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   if(atr <= 0) return;
   double spread = tk.ask - tk.bid;
   if(spread <= 0 || atr < InpSpkAtrSpread * spread) return;                   // the cost gate
   double rng = r[j].high - r[j].low;
   if(r[j].close >= r[j].open || rng < InpSpkAtr * atr) return;                // only a DOWN spike of the right size
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1320) return;
   int dg = (int)SymbolInfoInteger(sp_sym, SYMBOL_DIGITS);
   double sl = NormalizeDouble(r[j].low - InpSpkSlAtr * atr, dg);
   double tp = NormalizeDouble(r[j].close + InpSpkTpRange * rng, dg);
   if(tk.ask <= sl || tk.ask >= tp) return;                                    // the price already left the setup
   double mn = SymbolInfoDouble(sp_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(sp_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpSpkLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
   bool ok = trade.Buy(lot, sp_sym, 0, sl, tp, "SPIKE");
   if(!ok) SpkEvent(StringFormat("ERROR | spike %s order failed: %d %s", sp_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double lv[3]; color lc[3]; string lb[3];
   lv[0] = tk.ask; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = tp; lc[2] = clrSeaGreen; lb[2] = "TP";
   string fn = Snap(sp_sym, PERIOD_M1, "SPF", lv, lc, lb, 0, 0, 0, 0, false);
   SpkEvent(StringFormat("SPIKE BUY %s | an M1 bar dropped %s (%.1f x ATR) and ATR %s is %.0f x the spread %.2f | BUY %.2f lot at %s, "
                         "SL %s, TP %s, out after %d min", sp_sym, PriceStr(sp_sym, rng), rng / atr, PriceStr(sp_sym, atr),
                         atr / spread, spread, lot, PriceStr(sp_sym, tk.ask), PriceStr(sp_sym, sl), PriceStr(sp_sym, tp), InpSpkHoldMin) + Img(fn));
   int m = ArraySize(sp_known);
   if(SpkPosition(pt)) { ArrayResize(sp_known, m + 1); sp_known[m] = pt; }
}
//+------------------------------------------------------------------+
