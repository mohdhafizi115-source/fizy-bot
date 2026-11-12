//+------------------------------------------------------------------+
//| FizyKLT.mqh - gold M1 KELTNER RE-ENTRY scalp, demo only, included |
//| by FizyLB.mq5.  v2.16 (10 Nov 2026), the owner's order after      |
//| rounds 79-79d ("ya pasang dua-dua", with his breakeven at 30 pips)|
//|                                                                  |
//| RULES, closed M1 bars, BUY side only:                             |
//|  band    EMA 20 - InpKltBand (3.0) x ATR(14)                      |
//|  signal  the previous bar closed BELOW the band and the bar that  |
//|          just closed is back AT / ABOVE it; ATR (up to the bar    |
//|          before) >= InpKltGate (8) x the spread; 01:30-22:00      |
//|          server, weekdays                                         |
//|  skip    if the M1 spike fade had a signal on this bar or in the  |
//|          InpKltSkip (5) bars before (that trade belongs to it)    |
//|  entry   BUY at market, SL InpKltSl (0.2) ATR under the bar's low,|
//|          no TP, out after InpKltHoldMin (45) minutes              |
//|  BE      once the bid is InpKltBeUsd ($3 = 30 pips) above the     |
//|          entry, the SL moves to the entry price                   |
//| TEST (research/scalp79d.py, this causal rule, 6.6 years, 0.01 lot):|
//| 1,665 trades, win 17%, PF 1.25, stress 1.18, +$641, max DD -$208, |
//| worst day -$24; last 3 months +$136, the 3 before +$40, last 12   |
//| months +$558.  WEAKNESS: first half PF 0.84 (2020, 2021, 2022 and |
//| 2024 below 1) - it earns only in the fast 2025-26 market and fails|
//| the project's pass rule; live on the owner's 3-month frame.       |
//| Events go to MQL5\Files\klt_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpKltOn      = false;   // OFF since 12 Nov (owner, after a stop-out: only the gold auction stays)
input string InpKltSymbol  = "XAUUSD";
input double InpKltLot     = 0.01;
input long   InpKltMagic   = 260323;
input int    InpKltEma     = 20;
input double InpKltBand    = 3.0;      // band = EMA - this x ATR(14, M1)
input double InpKltGate    = 8.0;      // cost gate: ATR must be at least this x the spread
input double InpKltSl      = 0.2;      // SL this many ATR under the signal bar's low
input int    InpKltHoldMin = 45;       // close at market after this many minutes
input double InpKltBeUsd   = 3.0;      // SL to entry once price is this many $ in profit (30 pips); 0 = off
input int    InpKltSkip    = 5;        // skip when the spike fade signalled on this bar or this many bars before

string   kl_sym = "";
bool     kl_ready = false;
datetime kl_bar = 0;
ulong    kl_known[];
int      kl_ema = INVALID_HANDLE;

void KltEvent(string msg)
{
   int h = FileOpen("klt_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("keltner event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("KELT EVENT ", msg);
}

bool KltPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpKltMagic && PositionGetString(POSITION_SYMBOL) == kl_sym) { ticket = t; return true; }
   }
   return false;
}

void KltInit()
{
   kl_ready = true;
   kl_sym = SymResolve(InpKltSymbol);
   if(kl_sym == "") { KltEvent("ERROR | M1 Keltner: symbol " + InpKltSymbol + " not found"); return; }
   SymbolSelect(kl_sym, true);
   kl_ema = iMA(kl_sym, PERIOD_M1, InpKltEma, 0, MODE_EMA, PRICE_CLOSE);
   if(kl_ema == INVALID_HANDLE) KltEvent(StringFormat("ERROR | M1 Keltner: EMA handle failed (%d)", GetLastError()));
   ulong t;
   if(KltPosition(t)) { int m = ArraySize(kl_known); ArrayResize(kl_known, m + 1); kl_known[m] = t; }
   KltEvent(StringFormat("KELT ONLINE | %s M1: BUY when a bar closes back above EMA %d - %.1f x ATR after a close below it, "
                         "ATR >= %.0f x the spread, no spike-fade signal in the last %d bars; SL %.1f ATR under the bar, "
                         "no TP, SL to entry after +$%.0f, out after %d min, lot %.2f | %d open position(s)",
                         kl_sym, InpKltEma, InpKltBand, InpKltGate, InpKltSkip, InpKltSl, InpKltBeUsd, InpKltHoldMin,
                         InpKltLot, ArraySize(kl_known)));
}

void KltReportClosed(ulong pos)
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
   bool be = reason == DEAL_REASON_SL && outPx >= inPx - 0.10;
   string what = reason == DEAL_REASON_SL ? (be ? "KELT BREAKEVEN" : "KELT SL HIT") : "KELT CLOSED";
   string why = reason == DEAL_REASON_SL ? (be ? "stopped at the entry price" : "stop loss under the bar")
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d minutes up", InpKltHoldMin) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(kl_sym, PERIOD_M1, "KLX", lv, lc, lb, 0, 0, 0, 0, false);
   KltEvent(StringFormat("%s %s | BUY from %s closed at %s (%s), profit $%.2f", what, kl_sym, PriceStr(kl_sym, inPx),
                         PriceStr(kl_sym, outPx), why, profit) + Img(fn));
}

void KltOnTimer()
{
   if(!InpKltOn) return;
   if(!kl_ready) KltInit();
   if(kl_sym == "") return;
   for(int q = ArraySize(kl_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(kl_known[q])) { KltReportClosed(kl_known[q]); ArrayRemove(kl_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(kl_sym, tk) || now - tk.time > 600) return;              // market closed
   MqlDateTime ns; TimeToStruct(now, ns);
   int dg = (int)SymbolInfoInteger(kl_sym, SYMBOL_DIGITS);
   ulong pt;
   bool inPos = KltPosition(pt);
   if(inPos)
   {
      bool known = false;
      for(int q = 0; q < ArraySize(kl_known); q++) if(kl_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(kl_known); ArrayResize(kl_known, m + 1); kl_known[m] = pt; }
      PositionSelectByTicket(pt);
      long held = (long)(now - (datetime)PositionGetInteger(POSITION_TIME));
      double op = PositionGetDouble(POSITION_PRICE_OPEN), cs = PositionGetDouble(POSITION_SL);
      trade.SetExpertMagicNumber(InpKltMagic); trade.SetTypeFillingBySymbol(kl_sym);
      if(held >= (long)InpKltHoldMin * 60 || ns.hour * 60 + ns.min >= 1425)    // time exit, flat before the rollover
      {
         if(!trade.PositionClose(pt)) KltEvent(StringFormat("ERROR | Keltner close %s failed: %d %s", kl_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
      else if(InpKltBeUsd > 0 && cs < op - 0.5 * _Point && tk.bid >= op + InpKltBeUsd)
      {
         if(trade.PositionModify(pt, NormalizeDouble(op, dg), 0))
            KltEvent(StringFormat("KELT SL MOVED %s | price is $%.2f in profit: SL moved to the entry %s (no loss from here)", kl_sym, tk.bid - op, PriceStr(kl_sym, op)));
      }
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   }
   datetime b0 = iTime(kl_sym, PERIOD_M1, 0);
   if(b0 == 0 || b0 == kl_bar) return;                                         // act once per new M1 bar
   MqlRates r[];
   int n = CopyRates(kl_sym, PERIOD_M1, 1, 300, r);                            // closed bars, r[n-1] = the bar that just closed
   if(n < 100) { Print("keltner: only ", n, " M1 bars available, waiting for history"); return; }
   double ev[];
   if(kl_ema == INVALID_HANDLE || CopyBuffer(kl_ema, 0, 1, 2, ev) != 2) { Print("keltner: EMA not ready"); return; }
   kl_bar = b0;
   int j = n - 1;
   double av[];                                                                 // Wilder ATR(14) including each bar
   ArrayResize(av, n);
   av[0] = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      av[i] = av[i - 1] + (tr - av[i - 1]) / 14.0;
   }
   double emaNow = ev[1], emaPrev = ev[0];                                      // CopyBuffer: oldest first
   double bandNow = emaNow - InpKltBand * av[j], bandPrev = emaPrev - InpKltBand * av[j - 1];
   double spread = tk.ask - tk.bid, a1 = av[j - 1];
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(inPos || spread <= 0 || a1 <= 0 || a1 < InpKltGate * spread) return;
   if(!(r[j - 1].close < bandPrev && r[j].close >= bandNow)) return;
   if(st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1320) return;
   double pnt = SymbolInfoDouble(kl_sym, SYMBOL_POINT);
   for(int i = j; i >= j - InpKltSkip && i >= 1; i--)                           // the spike fade's own signal on these bars?
   {
      double sp_i = r[i].spread * pnt;
      if(r[i].close < r[i].open && r[i].high - r[i].low >= InpSpkAtr * av[i - 1] && sp_i > 0 && av[i - 1] >= InpSpkAtrSpread * sp_i) return;
   }
   if(DayPaused()) return;                                                      // daily target reached
   double sl = NormalizeDouble(r[j].low - InpKltSl * av[j], dg);
   if(tk.bid <= sl) return;
   double mn = SymbolInfoDouble(kl_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(kl_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpKltLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpKltMagic); trade.SetTypeFillingBySymbol(kl_sym);
   bool ok = trade.Buy(lot, kl_sym, 0, sl, 0, "KELT");
   if(!ok) KltEvent(StringFormat("ERROR | Keltner %s order failed: %d %s", kl_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double lv[3]; color lc[3]; string lb[3];
   lv[0] = tk.ask; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = bandNow; lc[2] = clrGoldenrod; lb[2] = "band";
   string fn = Snap(kl_sym, PERIOD_M1, "KLE", lv, lc, lb, 0, 0, 0, 0, false);
   KltEvent(StringFormat("KELT BUY %s | closed back above the band (EMA %d - %.1f ATR = %s) after a close below it, gate %.0f x "
                         "spread | BUY %.2f lot at %s, SL %s under the bar, no TP, SL to entry after +$%.0f, out after %d min",
                         kl_sym, InpKltEma, InpKltBand, PriceStr(kl_sym, bandNow), a1 / spread, lot, PriceStr(kl_sym, tk.ask),
                         PriceStr(kl_sym, sl), InpKltBeUsd, InpKltHoldMin) + Img(fn));
   if(KltPosition(pt)) { int m = ArraySize(kl_known); ArrayResize(kl_known, m + 1); kl_known[m] = pt; }
}
//+------------------------------------------------------------------+
