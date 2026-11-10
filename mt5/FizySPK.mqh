//+------------------------------------------------------------------+
//| FizySPK.mqh - gold M1 spike fade WITH CONFIRMATION, demo only,   |
//| included by FizyLB.mq5.  v2.00 (6 Nov 2026).                      |
//|                                                                  |
//| WHY v2.00. On the night of 5 Nov the old rule (enter on the spike |
//| bar itself) bought four times in six minutes, 16:38-16:44 server, |
//| while gold fell 4124 -> 4099; every trade hit its stop, -$14 in   |
//| one evening. Entering on the spike bar buys every leg of a        |
//| sustained drop. The owner then sent the classic spike-fade method |
//| (wait for a rejection candle, SL beyond the wick, TP back at the  |
//| pre-spike level, RSI extreme) and chose this version after seeing |
//| the test (research/spkconf52.py, spkconf53.py).                   |
//|                                                                  |
//| RULES, all on closed M1 bars, BUY side only:                      |
//|  1. SPIKE: a down bar with range >= InpSpkAtr x ATR(14, M1, up to |
//|     the bar before), ATR >= InpSpkAtrSpread x the spread (the     |
//|     cost gate), and RSI(14) of that bar < InpSpkRsi. Bars from     |
//|     01:30 to 22:00 server. The spike is ARMED, nothing is bought. |
//|  2. CONFIRMATION within the next InpSpkWait bars: a bar whose      |
//|     lower wick is >= InpSpkWick of its range and that closes in    |
//|     the upper half (sellers rejected). The lowest low since the   |
//|     spike is tracked as the wick tip.                             |
//|  3. BUY at the next bar's open. SL = the wick tip - InpSpkSlAtr x |
//|     the spike's ATR. TP = the OPEN of the spike bar (back to where |
//|     it started). Out after InpSpkHoldMin minutes, never past      |
//|     22:30 server. One position at a time.                         |
//|                                                                  |
//| TEST, JustMarkets M1 2020-03 .. 2026-11, k 2.0 / gate 8 / RSI 30 / |
//| wait 3 / wick 0.5: 760 trades (0.45 a day), PF 1.28, halves 1.34 / |
//| 1.27, stress 1.22, last 12 months +$369, net +$412 per 0.01 lot,  |
//| max drawdown -$111, worst single day -$45, win 47.5%.             |
//| The old v1.99 in the same simulator: 3.07 a day, PF 1.07, max DD  |
//| -$226, worst day -$78.                                            |
//| Plateau: RSI < 20 / 25 / 30 pass (1.33 / 1.30 / 1.28), 35 and 40  |
//| fail (1.09 / 1.07); 11 of 12 wait x wick cells pass (1.14-1.42);  |
//| spike size 2.0 / 2.5 / 3.0 pass (1.28 / 1.37 / 1.39), 1.5 fails.  |
//| Attribution: RSI without the wick wait 1.07, the wick without RSI |
//| 0.95, both together 1.28 - the two conditions are needed jointly. |
//| Random entries on RSI<30 bars: 0.80. The sell side fails (0.85-  |
//| 0.89) and is not traded.                                          |
//| Weakness to know: 2021 / 2023 / 2024 are below 1 (0.79 / 0.83 /   |
//| 0.76), so profit comes in bursts. Expect quiet losing months.    |
//|                                                                  |
//| Earlier versions, kept for the record: v1.95 entered on the spike |
//| bar with TP 0.75 x range (PF 1.37); v1.97 dropped the TP (1.53 at |
//| k 3.0); v1.98 k 2.5 no TP (1.34, 1.31 a day); v1.99 k 2.0 TP 0.5  |
//| (1.08, the owner's frequency override). See CLAUDE.md.            |
//| Events go to MQL5\Files\spk_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpSpkOn        = true;    // v2.12 (9 Nov): back ON in raw mode, round 74 (owner: frequent scalper judged on 3 months)
input bool   InpSpkConfirm   = false;   // v2.12: false = RAW mode, buy right after the spike bar (no RSI, no rejection candle)
input double InpSpkRawSl     = 0.2;     // RAW mode: SL this many ATR under the spike bar's low; no TP
input double InpSpkBeAtr     = 1.0;     // v2.16 (round 79b): RAW mode, SL to entry once price is this many ATR (of the entry) in profit; 0 = off
input string InpSpkSymbol    = "XAUUSD";
input double InpSpkLot       = 0.01;
input long   InpSpkMagic     = 260320;
input double InpSpkAtr       = 2.0;      // the spike's range, in ATR(14, M1)
input double InpSpkAtrSpread = 8.0;      // the cost gate: ATR(M1) must be at least this x the spread
input double InpSpkRsi       = 30.0;     // RSI(14, M1) of the spike bar must be below this
input int    InpSpkWait      = 3;        // bars after the spike in which the rejection candle must come
input double InpSpkWick      = 0.5;      // lower wick of the confirmation bar, as a share of its range
input double InpSpkSlAtr     = 0.1;      // SL this far below the wick tip, in the spike's ATR
input int    InpSpkHoldMin   = 45;       // close at market after this many minutes

string   sp_sym = "";
bool     sp_ready = false;
datetime sp_bar = 0;
ulong    sp_known[];
int      sp_rsi = INVALID_HANDLE;
// armed spikes waiting for a confirmation candle (oldest first, as in the test)
datetime sa_time[];
double   sa_open[], sa_ext[], sa_atr[];
int      sa_left[];

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

void SpkDisarmAll() { ArrayResize(sa_time, 0); ArrayResize(sa_open, 0); ArrayResize(sa_ext, 0); ArrayResize(sa_atr, 0); ArrayResize(sa_left, 0); }

void SpkDisarm(int q)
{
   ArrayRemove(sa_time, q, 1); ArrayRemove(sa_open, q, 1); ArrayRemove(sa_ext, q, 1);
   ArrayRemove(sa_atr, q, 1); ArrayRemove(sa_left, q, 1);
}

void SpkInit()
{
   sp_ready = true;
   sp_sym = SymResolve(InpSpkSymbol);
   if(sp_sym == "") { SpkEvent("ERROR | M1 spike fade: symbol " + InpSpkSymbol + " not found"); return; }
   SymbolSelect(sp_sym, true);
   sp_rsi = iRSI(sp_sym, PERIOD_M1, 14, PRICE_CLOSE);
   if(sp_rsi == INVALID_HANDLE) SpkEvent(StringFormat("ERROR | M1 spike fade: RSI handle failed (%d)", GetLastError()));
   ulong t;
   if(SpkPosition(t)) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = t; }
   if(!InpSpkConfirm)
      SpkEvent(StringFormat("SPIKE ONLINE | %s M1, raw: BUY right after a down bar of %.1f x ATR(M1) when ATR >= %.0f x the "
                            "spread; SL %.1f ATR under the spike's low, no TP, out after %d min, lot %.2f | %d open position(s)",
                            sp_sym, InpSpkAtr, InpSpkAtrSpread, InpSpkRawSl, InpSpkHoldMin, InpSpkLot, ArraySize(sp_known)));
   else
   SpkEvent(StringFormat("SPIKE ONLINE | %s M1, with confirmation: a down bar of %.1f x ATR(M1), ATR >= %.0f x the spread "
                         "and RSI < %.0f arms the setup; BUY only after a rejection candle (lower wick >= %.0f%% of its "
                         "range, close in the upper half) within %d bars. SL %.1f ATR under the wick, TP back at the "
                         "spike's open, out after %d min, lot %.2f | %d open position(s)",
                         sp_sym, InpSpkAtr, InpSpkAtrSpread, InpSpkRsi, InpSpkWick * 100, InpSpkWait, InpSpkSlAtr,
                         InpSpkHoldMin, InpSpkLot, ArraySize(sp_known)));
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
   string why = reason == DEAL_REASON_SL ? (outPx >= inPx - 0.10 ? "stopped at the entry price (breakeven)" : "stop loss under the spike")
              : (reason == DEAL_REASON_TP ? "take profit, back at the spike's open"
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
   MqlDateTime ns; TimeToStruct(now, ns);
   ulong pt;
   bool inPos = SpkPosition(pt);
   if(inPos)
   {
      bool known = false;
      for(int q = 0; q < ArraySize(sp_known); q++) if(sp_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = pt; }
      PositionSelectByTicket(pt);
      long held = (long)(now - (datetime)PositionGetInteger(POSITION_TIME));
      double op = PositionGetDouble(POSITION_PRICE_OPEN), cs = PositionGetDouble(POSITION_SL), ea = 0;
      string cp[];                                                              // comment "SPIKE <ATR at entry>"
      if(StringSplit(PositionGetString(POSITION_COMMENT), ' ', cp) >= 2) ea = StringToDouble(cp[1]);
      if(held >= (long)InpSpkHoldMin * 60 || ns.hour * 60 + ns.min >= 1350)    // time exit, and never past 22:30
      {
         trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
         if(!trade.PositionClose(pt)) SpkEvent(StringFormat("ERROR | spike close %s failed: %d %s", sp_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      else if(!InpSpkConfirm && InpSpkBeAtr > 0 && ea > 0 && cs < op - 0.5 * _Point && tk.bid >= op + InpSpkBeAtr * ea)
      {
         trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
         if(trade.PositionModify(pt, NormalizeDouble(op, (int)SymbolInfoInteger(sp_sym, SYMBOL_DIGITS)), 0))
            SpkEvent(StringFormat("SPIKE SL MOVED %s | price is $%.2f in profit (%.1f ATR): SL moved to the entry %s (no loss from here)",
                                  sp_sym, tk.bid - op, InpSpkBeAtr, PriceStr(sp_sym, op)));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   datetime b0 = iTime(sp_sym, PERIOD_M1, 0);
   if(b0 == 0 || b0 == sp_bar) return;                                         // act once per new M1 bar
   MqlRates r[];
   int n = CopyRates(sp_sym, PERIOD_M1, 1, 40, r);                             // closed bars, r[n-1] = the bar that just closed
   if(n < 30) { Print("spike: only ", n, " M1 bars available, waiting for history"); return; }
   double rv[];
   if(sp_rsi == INVALID_HANDLE || CopyBuffer(sp_rsi, 0, 1, 1, rv) != 1) { Print("spike: RSI not ready"); return; }
   sp_bar = b0;
   int j = n - 1;
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   // a new trading day or the rollover ends every pending setup, as in the test
   if(ArraySize(sa_time) > 0)
   {
      MqlDateTime s0; TimeToStruct(sa_time[0], s0);
      if(s0.day != st.day || hm >= 1350 || hm < 90) SpkDisarmAll();
   }

   // ---- 1. update the armed spikes with the bar that just closed, and look for the rejection candle
   bool confirmed = false;
   double c_open = 0, c_ext = 0, c_atr = 0;
   for(int q = 0; q < ArraySize(sa_time); q++)
   {
      if(r[j].time <= sa_time[q]) continue;
      sa_ext[q] = MathMin(sa_ext[q], r[j].low);
      double rr = r[j].high - r[j].low;
      double wick = MathMin(r[j].open, r[j].close) - r[j].low;
      bool good = rr > 0 && wick >= InpSpkWick * rr && r[j].close >= (r[j].high + r[j].low) / 2.0;
      if(good && !confirmed) { confirmed = true; c_open = sa_open[q]; c_ext = sa_ext[q]; c_atr = sa_atr[q]; }
      sa_left[q]--;
   }
   if(confirmed) SpkDisarmAll();
   else for(int q = ArraySize(sa_time) - 1; q >= 0; q--) if(sa_left[q] <= 0) SpkDisarm(q);

   // ---- 2. is the bar that just closed a new spike? arm it (nothing is bought yet)
   double atr = r[1].high - r[1].low;                                          // Wilder ATR(14) of the bars BEFORE it
   for(int i = 2; i < j; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   double spread = tk.ask - tk.bid;
   double rng = r[j].high - r[j].low;
   // ---- RAW mode (v2.12, round 74): buy right away after the spike bar, SL under its low, no TP
   if(!InpSpkConfirm)
   {
      if(inPos || atr <= 0 || spread <= 0 || atr < InpSpkAtrSpread * spread || r[j].close >= r[j].open || rng < InpSpkAtr * atr
         || st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1320) return;
      if(DayPaused()) return;                                                   // daily target reached
      int dg0 = (int)SymbolInfoInteger(sp_sym, SYMBOL_DIGITS);
      double sl0 = NormalizeDouble(r[j].low - InpSpkRawSl * atr, dg0);
      if(tk.bid <= sl0) return;
      double mn0 = SymbolInfoDouble(sp_sym, SYMBOL_VOLUME_MIN), sv0 = SymbolInfoDouble(sp_sym, SYMBOL_VOLUME_STEP);
      double lot0 = NormalizeDouble(MathMax(mn0, MathFloor(InpSpkLot / sv0 + 1e-9) * sv0), 2);
      trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
      bool ok0 = trade.Buy(lot0, sp_sym, 0, sl0, 0, "SPIKE " + DoubleToString(atr, 2));
      if(!ok0) SpkEvent(StringFormat("ERROR | spike %s order failed: %d %s", sp_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(!ok0) return;
      double lv0[2]; color lc0[2]; string lb0[2];
      lv0[0] = tk.ask; lc0[0] = clrBlue; lb0[0] = "entry"; lv0[1] = sl0; lc0[1] = clrIndianRed; lb0[1] = "SL";
      string fn0 = Snap(sp_sym, PERIOD_M1, "SPF", lv0, lc0, lb0, 0, 0, 0, 0, false);
      SpkEvent(StringFormat("SPIKE BUY %s | a down M1 bar of %.2f (%.1f x ATR, gate %.0f x spread) | BUY %.2f lot at %s, "
                            "SL %s under the spike, no TP, SL to entry after +$%.2f (%.1f ATR), out after %d min", sp_sym, rng, rng / atr, atr / spread, lot0,
                            PriceStr(sp_sym, tk.ask), PriceStr(sp_sym, sl0), InpSpkBeAtr * atr, InpSpkBeAtr, InpSpkHoldMin) + Img(fn0));
      if(SpkPosition(pt)) { int m0 = ArraySize(sp_known); ArrayResize(sp_known, m0 + 1); sp_known[m0] = pt; }
      return;
   }
   if(!confirmed && atr > 0 && spread > 0 && atr >= InpSpkAtrSpread * spread && r[j].close < r[j].open
      && rng >= InpSpkAtr * atr && rv[0] < InpSpkRsi
      && st.day_of_week != 0 && st.day_of_week != 6 && hm >= 90 && hm < 1320)
   {
      int m = ArraySize(sa_time);
      ArrayResize(sa_time, m + 1); ArrayResize(sa_open, m + 1); ArrayResize(sa_ext, m + 1);
      ArrayResize(sa_atr, m + 1); ArrayResize(sa_left, m + 1);
      sa_time[m] = r[j].time; sa_open[m] = r[j].open; sa_ext[m] = r[j].low; sa_atr[m] = atr; sa_left[m] = InpSpkWait;
      Print(StringFormat("spike: armed at %s, drop %.2f (%.1f ATR), RSI %.1f, gate %.1f", TimeToString(r[j].time),
                         rng, rng / atr, rv[0], atr / spread));
   }

   // ---- 3. confirmed: buy now, if flat
   if(!confirmed || inPos) return;
   int dg = (int)SymbolInfoInteger(sp_sym, SYMBOL_DIGITS);
   double sl = NormalizeDouble(c_ext - InpSpkSlAtr * c_atr, dg);
   double tp = NormalizeDouble(c_open, dg);
   if(tk.bid <= sl || tk.ask >= tp) return;                                    // the setup is already gone
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
   SpkEvent(StringFormat("SPIKE BUY %s | a down spike with RSI < %.0f was followed by a rejection candle (sellers "
                         "exhausted) | BUY %.2f lot at %s, SL %s under the wick, TP %s back at the spike's open, out "
                         "after %d min", sp_sym, InpSpkRsi, lot, PriceStr(sp_sym, tk.ask), PriceStr(sp_sym, sl),
                         PriceStr(sp_sym, tp), InpSpkHoldMin) + Img(fn));
   if(SpkPosition(pt)) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = pt; }
}
//+------------------------------------------------------------------+
