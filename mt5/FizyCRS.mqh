//+------------------------------------------------------------------+
//| FizyCRS.mqh - gold M15 Connors RSI scalp, demo only, included by  |
//| FizyLB.mq5 (v2.28, 14 Nov 2026, rounds 110 / 110b, the owner:     |
//| "ya pasang je. nanti aku nilai").                                 |
//| Rule, on closed M15 bars of XAUUSD: Connors RSI(3, 2, 100) =      |
//| (RSI(3) of the close + RSI(2) of the up/down streak + percent     |
//| rank of the 1-bar change over 100 bars) / 3. BUY when it crosses  |
//| below 10 with the close above EMA 200; SELL when it crosses above |
//| 90 with the close below EMA 200. Market order at the open of the  |
//| next M15 bar, SL 1.5 x Wilder ATR(14, M15) of the signal bar from |
//| the entry, no TP, closed 120 minutes after the entry (or at 23:30 |
//| server), one position at a time, entries 01:30-23:30 server,      |
//| obeys the daily target.                                           |
//| Round 110b at 0.01 lot, last 2 years: 516 trades, PF 1.24, years  |
//| 1.30 / 1.20, +$575, max DD -$172, worst trade -$48; BUT 2025 Q4 + |
//| 2026 Q1 made $552 of it and the last three quarters lost, and M20 |
//| loses (PF 0.84): live on the owner's order to judge it himself.   |
//| Events go to MQL5\Files\crs_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpCrsOn       = true;
input string InpCrsSymbol   = "XAUUSD";
input double InpCrsLot      = 0.01;
input long   InpCrsMagic    = 260330;
input double InpCrsLo       = 10.0;     // buy when CRSI crosses below this
input double InpCrsHi       = 90.0;     // sell when CRSI crosses above this
input int    InpCrsEma      = 200;      // trend side filter on M15 closes
input double InpCrsSlAtr    = 1.5;      // SL distance in Wilder ATR(14, M15) of the signal bar
input int    InpCrsHoldMin  = 120;      // minutes in the trade

string   cr_sym = "";
datetime cr_bar = 0;                    // M15 bar already handled
ulong    cr_known[];
bool     cr_ready = false;

void CrsEvent(string msg)
{
   int h = FileOpen("crs_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("CRSI event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("CRSI EVENT ", msg);
}

bool CrsPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpCrsMagic && PositionGetString(POSITION_SYMBOL) == cr_sym) { ticket = t; return true; }
   }
   return false;
}

bool CrsTradedSince(datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d > 0 && HistoryDealGetInteger(d, DEAL_MAGIC) == InpCrsMagic && HistoryDealGetString(d, DEAL_SYMBOL) == cr_sym
         && HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) return true;
   }
   return false;
}

// Wilder smoothing as pandas ewm(alpha = 1/n, adjust = False), seeded with the first value
void CrsRsi(const double &x[], int n, int len, double &out[])
{
   ArrayResize(out, n);
   double au = 0, ad = 0;
   for(int i = 0; i < n; i++)
   {
      double d = i == 0 ? 0 : x[i] - x[i - 1];
      double u = d > 0 ? d : 0, w = d < 0 ? -d : 0;
      if(i == 0) { au = u; ad = w; }
      else { au += (u - au) / len; ad += (w - ad) / len; }
      out[i] = 100.0 - 100.0 / (1.0 + au / MathMax(ad, 1e-12));
   }
}

// Connors RSI of the last two closed M15 bars, EMA and ATR of the last one (research/scalp110.py)
bool CrsCalc(double &cr1, double &cr2, double &ema, double &atr, double &close1, datetime &t1)
{
   MqlRates r[];
   int n = CopyRates(cr_sym, PERIOD_M15, 1, 1500, r);                     // closed bars, oldest first
   if(n < 400) return false;
   double c[], st[], r3[], r2[];
   ArrayResize(c, n); ArrayResize(st, n);
   for(int i = 0; i < n; i++) c[i] = r[i].close;
   st[0] = 0;
   for(int i = 1; i < n; i++)
   {
      double d = c[i] - c[i - 1];
      if(d > 0) st[i] = st[i - 1] > 0 ? st[i - 1] + 1 : 1;
      else if(d < 0) st[i] = st[i - 1] < 0 ? st[i - 1] - 1 : -1;
      else st[i] = 0;
   }
   CrsRsi(c, n, 3, r3); CrsRsi(st, n, 2, r2);
   double cv[2];
   for(int q = 0; q < 2; q++)
   {
      int i = n - 1 - q;
      double roc = (c[i] - c[i - 1]) / c[i - 1];
      int cnt = 0;
      for(int j = i - 99; j < i; j++) if((c[j] - c[j - 1]) / c[j - 1] < roc) cnt++;
      cv[q] = (r3[i] + r2[i] + cnt / 99.0 * 100.0) / 3.0;
   }
   cr1 = cv[0]; cr2 = cv[1];
   double k = 2.0 / (InpCrsEma + 1.0); ema = c[0];
   for(int i = 1; i < n; i++) ema += k * (c[i] - ema);
   atr = 0;
   for(int i = 0; i < n; i++)
   {
      double tr = i == 0 ? r[i].high - r[i].low
                         : MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr = i == 0 ? tr : atr + (tr - atr) / 14.0;
   }
   close1 = c[n - 1]; t1 = r[n - 1].time;
   return true;
}

void CrsInit()
{
   cr_sym = SymResolve(InpCrsSymbol);
   cr_ready = true;
   if(cr_sym == "") { CrsEvent("ERROR | Connors RSI scalp: symbol " + InpCrsSymbol + " not found"); return; }
   SymbolSelect(cr_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpCrsMagic) { int m = ArraySize(cr_known); ArrayResize(cr_known, m + 1); cr_known[m] = t; }
   }
   cr_bar = iTime(cr_sym, PERIOD_M15, 0);                                   // never trade a bar that opened before this shift started
   CrsEvent(StringFormat("CRSI ONLINE | %s M15: Connors RSI(3,2,100) below %.0f with the close above EMA %d -> BUY, above %.0f below EMA %d -> SELL, "
                         "SL %.1f ATR(M15), no TP, out after %d min, one position, lot %.2f | %d open position(s)",
                         cr_sym, InpCrsLo, InpCrsEma, InpCrsHi, InpCrsEma, InpCrsSlAtr, InpCrsHoldMin, InpCrsLot, ArraySize(cr_known)));
}

void CrsReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "CRSI SL HIT" : "CRSI CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_EXPERT ? StringFormat("%d-minute / 23:30 exit", InpCrsHoldMin) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(cr_sym, PERIOD_M15, "CRS", lv, lc, lb, 0, 0, 0, 0, false);
   CrsEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, cr_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(cr_sym, inPx), PriceStr(cr_sym, outPx), why, profit) + Img(fn));
}

void CrsOnTimer()
{
   if(!InpCrsOn) return;
   if(!cr_ready) CrsInit();
   if(cr_sym == "") return;
   datetime now = TimeCurrent();
   for(int q = ArraySize(cr_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(cr_known[q])) { CrsReportClosed(cr_known[q]); ArrayRemove(cr_known, q, 1); }
   MqlDateTime s; TimeToStruct(now, s);
   int hm = s.hour * 60 + s.min;
   ulong pt;
   if(CrsPosition(pt))
   {
      PositionSelectByTicket(pt);
      datetime t0 = (datetime)PositionGetInteger(POSITION_TIME);
      t0 -= t0 % 60;                                                          // the entry bar's open
      datetime day0 = t0 - t0 % 86400;
      if(now >= t0 + InpCrsHoldMin * 60 || now >= day0 + 1410 * 60)
      {
         trade.SetExpertMagicNumber(InpCrsMagic); trade.SetTypeFillingBySymbol(cr_sym);
         if(!trade.PositionClose(pt)) CrsEvent(StringFormat("ERROR | CRSI close %s failed: %d %s", cr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;
   }
   datetime b0 = iTime(cr_sym, PERIOD_M15, 0);
   if(b0 == 0 || b0 == cr_bar) return;
   if(now - b0 > 120) { cr_bar = b0; return; }                             // only right after the bar opens
   if(s.day_of_week == 0 || s.day_of_week == 6 || hm < 90 || hm >= 1410) { cr_bar = b0; return; }
   double c1, c2, ema, A, close1; datetime t1;
   if(!CrsCalc(c1, c2, ema, A, close1, t1)) return;                         // history not ready: retry
   if(t1 != b0 - 15 * 60) return;                                           // the closed bar is not in yet: retry
   cr_bar = b0;
   bool buy = c1 < InpCrsLo && c2 >= InpCrsLo && close1 > ema;
   bool sell = c1 > InpCrsHi && c2 <= InpCrsHi && close1 < ema;
   if(!buy && !sell) return;
   if(DayPaused() || CrsTradedSince(b0) || A <= 0) return;
   MqlTick tk;
   if(!SymbolInfoTick(cr_sym, tk) || now - tk.time > 120) return;          // no live quotes
   int dg = (int)SymbolInfoInteger(cr_sym, SYMBOL_DIGITS);
   double e = buy ? tk.ask : tk.bid;
   double sl = NormalizeDouble(buy ? e - InpCrsSlAtr * A : e + InpCrsSlAtr * A, dg);
   double mn = SymbolInfoDouble(cr_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(cr_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpCrsLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpCrsMagic); trade.SetTypeFillingBySymbol(cr_sym);
   bool ok = buy ? trade.Buy(lot, cr_sym, 0, sl, 0, "CRSI") : trade.Sell(lot, cr_sym, 0, sl, 0, "CRSI");
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { CrsEvent(StringFormat("ERROR | CRSI %s %s failed: %d %s", buy ? "BUY" : "SELL", cr_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription())); return; }
   if(CrsPosition(pt)) { int m = ArraySize(cr_known); ArrayResize(cr_known, m + 1); cr_known[m] = pt; }
   double lv[3]; color lc[3]; string lb[3];
   lv[0] = e; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = ema; lc[2] = clrOrange; lb[2] = StringFormat("EMA %d", InpCrsEma);
   string fn = Snap(cr_sym, PERIOD_M15, "CRSE", lv, lc, lb, 0, 0, 0, 0, false);
   CrsEvent(StringFormat("CRSI %s %s | Connors RSI %.1f -> %.1f, close %s EMA %d | %s %.2f lot at %s, SL %s (%.1f ATR(M15) = %s), no TP, "
                         "closes after %d min", buy ? "BUY" : "SELL", cr_sym, c2, c1, buy ? "above" : "below", InpCrsEma,
                         buy ? "BUY" : "SELL", lot, PriceStr(cr_sym, e), PriceStr(cr_sym, sl), InpCrsSlAtr, PriceStr(cr_sym, A), InpCrsHoldMin) + Img(fn));
}
//+------------------------------------------------------------------+
