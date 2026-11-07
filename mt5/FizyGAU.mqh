//+------------------------------------------------------------------+
//| FizyGAU.mqh - gold before the LBMA AM auction, demo only,         |
//| included by FizyLB.mq5. Rules (research/lbma.py, and the M1 exit  |
//| from gau_m1_34.py / gau_exit35.py / gau_trail36.py, JustMarkets   |
//| 2020-2026, 1,703 trades: PF 1.66 after spread, halves 1.26 /      |
//| 1.91, +$762 per 0.01 lot, max drawdown $83, 52 of 81 months up):  |
//|   every trading day SELL XAUUSD at 10:15:00 London.               |
//|   Protective SL 2.0 x ATR(M5, 14). No TP.                         |
//|   v1.94: hold PAST the 10:30 auction start with an M1 trailing    |
//|   stop. From 10:30 London, on every M1 bar the stop is pulled      |
//|   down to (lowest M1 low since entry + InpGauTrailAtr x ATR(M1)); |
//|   hard exit at 10:45. Exiting at 10:30 scored PF 1.48 with a      |
//|   failing first half (0.98); every exit minute 10:31-10:37 and    |
//|   every trail from 0.3 to 2.0 ATR passes, so this is a plateau,   |
//|   not one lucky setting.                                          |
//|   No entry when more than InpGauLateSec late or when the spread   |
//|   is above InpGauMaxSpread.                                       |
//| London time from TimeGMT() with UK summer time (FizyCommon.mqh).  |
//| Events go to MQL5\Files\gau_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input string InpGauSymbol    = "XAUUSD";
input bool   InpGauOn        = true;
input double InpGauLot       = 0.01;
input long   InpGauMagic     = 260312;
input double InpGauSlAtr     = 2.0;
input double InpGauMaxSpread = 0.50;     // in price ($ for gold)
input int    InpGauEntryMin  = 615;      // 10:15 London
input int    InpGauExitMin   = 645;      // 10:45 London: hard exit
input int    InpGauTrailMin  = 630;      // 10:30 London: the M1 trailing stop starts
input double InpGauTrailAtr  = 1.0;      // trail at the lowest M1 low + this x ATR(M1, 14)
input int    InpGauLateSec   = 60;

string   ga_sym = "";
int      ga_day = 0;
ulong    ga_known[];
bool     ga_ready = false;

void GauEvent(string msg)
{
   int h = FileOpen("gau_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("gold auction event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("AUCTION EVENT ", msg);
}

double GauAtr(string s)
{
   MqlRates r[];
   if(CopyRates(s, PERIOD_M5, 1, 15, r) < 15) return 0;
   double sum = 0;
   for(int i = 1; i < 15; i++)
      sum += MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
   return sum / 14.0;
}

// ATR(14) on closed M1 bars, and the lowest M1 low since the entry
double GauAtrM1(string s)
{
   MqlRates r[];
   if(CopyRates(s, PERIOD_M1, 1, 15, r) < 15) return 0;
   double sum = 0;
   for(int i = 1; i < 15; i++)
      sum += MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
   return sum / 14.0;
}

double GauLowSince(string s, datetime since)
{
   MqlRates r[];
   int n = CopyRates(s, PERIOD_M1, since, TimeCurrent(), r);
   double lo = 0;
   for(int i = 0; i < n; i++) if(lo == 0 || r[i].low < lo) lo = r[i].low;
   return lo;
}

bool GauPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpGauMagic && PositionGetString(POSITION_SYMBOL) == ga_sym) { ticket = t; return true; }
   }
   return false;
}

bool GauTradedSince(datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d > 0 && HistoryDealGetInteger(d, DEAL_MAGIC) == InpGauMagic && HistoryDealGetString(d, DEAL_SYMBOL) == ga_sym) return true;
   }
   return false;
}

void GauInit()
{
   ga_sym = SymResolve(InpGauSymbol);
   if(ga_sym != "") SymbolSelect(ga_sym, true);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpGauMagic) { int m = ArraySize(ga_known); ArrayResize(ga_known, m + 1); ga_known[m] = t; }
   }
   ga_ready = true;
   datetime ldn = LondonTime();
   int off = (int)MathRound((TimeCurrent() - TimeGMT()) / 3600.0) - (int)MathRound((ldn - TimeGMT()) / 3600.0);
   GauEvent(StringFormat("AUCTION ONLINE | %s: SELL at 10:15 London before the LBMA gold auction, every trading day "
                         "(%02d:15 server time now), SL %.1f ATR(M5); from 10:30 an M1 trailing stop at the lowest M1 low + %.1f ATR(M1), "
                         "hard exit 10:45 (%02d:45 server), lot %.2f | %d open position(s)%s",
                         ga_sym == "" ? InpGauSymbol : ga_sym, 10 + off, InpGauSlAtr, InpGauTrailAtr, 10 + off, InpGauLot,
                         ArraySize(ga_known), ga_sym == "" ? " | symbol not found" : ""));
}

void GauReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1; string s = "";
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      s = HistoryDealGetString(d, DEAL_SYMBOL);
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) inPx = HistoryDealGetDouble(d, DEAL_PRICE);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0 || s == "") return;
   string what = reason == DEAL_REASON_SL ? "AUCTION STOP HIT" : "AUCTION CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop: the M1 trailing stop after 10:30, or the 2 ATR stop loss"
                : (reason == DEAL_REASON_EXPERT ? "10:45 London, hard exit" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(s, PERIOD_M5, "GAX", lv, lc, lb, 0, 0, 0, 0, false);
   GauEvent(StringFormat("%s %s | SELL from %s closed at %s (%s), %+.2f, profit $%.2f", what, s, PriceStr(s, inPx), PriceStr(s, outPx), why,
                         inPx - outPx, profit) + Img(fn));
}

// Pull the stop down to (lowest M1 low since entry + InpGauTrailAtr x ATR(M1)), never above the current one,
// and never closer than the broker's stops level above the ask.
void GauTrail(ulong pt)
{
   if(!PositionSelectByTicket(pt)) return;
   double a1 = GauAtrM1(ga_sym);
   double lo = GauLowSince(ga_sym, (datetime)PositionGetInteger(POSITION_TIME));
   MqlTick tk;
   if(a1 <= 0 || lo <= 0 || !SymbolInfoTick(ga_sym, tk)) return;
   int dg = (int)SymbolInfoInteger(ga_sym, SYMBOL_DIGITS);
   double pt_ = SymbolInfoDouble(ga_sym, SYMBOL_POINT);
   double stops = (double)SymbolInfoInteger(ga_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt_;
   double floor_ = tk.ask + stops + pt_;
   double trail = NormalizeDouble(MathMax(lo + InpGauTrailAtr * a1, floor_), dg);
   double cur = PositionGetDouble(POSITION_SL);
   if(cur > 0 && trail >= cur - pt_) return;                                 // only ever tighten
   trade.SetExpertMagicNumber(InpGauMagic); trade.SetTypeFillingBySymbol(ga_sym);
   if(!trade.PositionModify(pt, trail, 0))
      Print("AUCTION trail modify failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
}

void GauOnTimer()
{
   if(!InpGauOn) return;
   if(!ga_ready) GauInit();
   if(ga_sym == "") return;
   datetime ldn = LondonTime();
   MqlDateTime L; TimeToStruct(ldn, L);
   int lmin = L.hour * 60 + L.min, lday = L.year * 10000 + L.mon * 100 + L.day;
   for(int q = ArraySize(ga_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(ga_known[q])) { GauReportClosed(ga_known[q]); ArrayRemove(ga_known, q, 1); }
   ulong pt;
   if(GauPosition(pt))
   {
      bool known = false;
      for(int q = 0; q < ArraySize(ga_known); q++) if(ga_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(ga_known); ArrayResize(ga_known, m + 1); ga_known[m] = pt; }
      PositionSelectByTicket(pt);
      long held = (long)(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME));
      if(lmin >= InpGauExitMin || held >= (InpGauExitMin - InpGauEntryMin) * 60)
      {
         trade.SetExpertMagicNumber(InpGauMagic); trade.SetTypeFillingBySymbol(ga_sym);
         if(!trade.PositionClose(pt)) GauEvent(StringFormat("ERROR | gold auction close failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         return;
      }
      if(lmin >= InpGauTrailMin) GauTrail(pt);                               // M1 trailing stop from 10:30 London
      return;
   }
   if(L.day_of_week == 0 || L.day_of_week == 6 || lmin != InpGauEntryMin || ga_day == lday) return;
   ga_day = lday;
   if(L.sec > InpGauLateSec) { GauEvent(StringFormat("AUCTION SKIPPED %s | the EA was %d s late for 10:15 London", ga_sym, L.sec)); return; }
   if(GauTradedSince(TimeCurrent() - 3600)) return;
   MqlTick tk;
   if(!SymbolInfoTick(ga_sym, tk) || TimeCurrent() - tk.time > 120) { GauEvent("AUCTION SKIPPED " + ga_sym + " | no fresh price (holiday?)"); return; }
   double spr = tk.ask - tk.bid;
   if(spr > InpGauMaxSpread) { GauEvent(StringFormat("AUCTION SKIPPED %s | spread %.2f is above %.2f", ga_sym, spr, InpGauMaxSpread)); return; }
   double atr = GauAtr(ga_sym);
   if(atr <= 0) { GauEvent("AUCTION SKIPPED " + ga_sym + " | M5 history not loaded"); return; }
   int dg = (int)SymbolInfoInteger(ga_sym, SYMBOL_DIGITS);
   double sl = NormalizeDouble(tk.bid + InpGauSlAtr * atr, dg);
   double mn = SymbolInfoDouble(ga_sym, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(ga_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpGauLot / st + 1e-9) * st), 2);
   if(DayPaused()) { GauEvent("AUCTION SKIPPED " + ga_sym + " | daily target reached"); return; }
   trade.SetExpertMagicNumber(InpGauMagic); trade.SetTypeFillingBySymbol(ga_sym);
   bool ok = trade.Sell(lot, ga_sym, 0, sl, 0, "AUCTION " + TimeToString(ldn, TIME_DATE));
   double px = trade.ResultPrice();
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(ok)
   {
      double lv[2]; color lc[2]; string lb[2];
      lv[0] = px > 0 ? px : tk.bid; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
      string fn = Snap(ga_sym, PERIOD_M5, "GA", lv, lc, lb, 0, 0, 0, 0, false);
      GauEvent(StringFormat("AUCTION SELL %s | 10:15 London, 15 minutes before the LBMA gold auction: SELL %.2f lot at %s, SL %s, no TP, "
                            "closes at 10:30 London | spread %.2f", ga_sym, lot, PriceStr(ga_sym, lv[0]), PriceStr(ga_sym, sl), spr) + Img(fn));
   }
   else
      GauEvent(StringFormat("ERROR | gold auction sell failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
}
//+------------------------------------------------------------------+
