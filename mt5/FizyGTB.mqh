//+------------------------------------------------------------------+
//| FizyGTB.mqh - Gotobi Tokyo-fix reversal, demo only, included by   |
//| FizyLB.mq5. Rules (research/gotobi.py, JustMarkets M5 2020-2026): |
//|   on Gotobi days (the 5th, 10th, 15th, 20th, 25th and 30th in     |
//|   Tokyo; the month end in February; a weekend date moves to the   |
//|   Friday before) SELL at the Tokyo fix, 09:55:00 JST, and close   |
//|   at 10:15 JST. Protective SL 1.0 x ATR(H1, 120). No TP.          |
//|   No entry when more than InpGtbLateSec late (the move is in the  |
//|   first minutes) or when the spread is above InpGtbMaxSpread.     |
//| Tokyo time comes from TimeGMT() + 9 h (no DST in Japan).          |
//| Events go to MQL5\Files\gtb_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input string InpGtbSymbols   = "USDJPY,EURJPY";
input bool   InpGtbOn        = true;
input double InpGtbLot       = 0.01;
input long   InpGtbMagic     = 260311;
input double InpGtbSlAtr     = 1.0;
input double InpGtbMaxSpread = 3.0;      // pips
input int    InpGtbEntryMin  = 595;      // 09:55 JST
input int    InpGtbExitMin   = 615;      // 10:15 JST
input int    InpGtbLateSec   = 30;

string   gt_sym[];
int      gt_day[];          // Tokyo date (yyyymmdd) already handled per symbol
ulong    gt_known[];
bool     gt_ready = false;

void GtbEvent(string msg)
{
   int h = FileOpen("gtb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("gotobi event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("GOTOBI EVENT ", msg);
}

int GtbDim(int y, int m)
{
   if(m == 2) return ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0) ? 29 : 28;
   if(m == 4 || m == 6 || m == 9 || m == 11) return 30;
   return 31;
}

// jst: any time on the Tokyo date to check
bool GtbIsGotobi(datetime jst)
{
   MqlDateTime d; TimeToStruct(jst, d);
   if(d.day_of_week == 0 || d.day_of_week == 6) return false;
   int span = (d.day_of_week == 5) ? 2 : 0;                       // a Friday also takes Saturday's and Sunday's date
   for(int k = 0; k <= span; k++)
   {
      MqlDateTime x; TimeToStruct(jst + k * 86400, x);
      int dim = GtbDim(x.year, x.mon);
      if(x.day == 5 || x.day == 10 || x.day == 15 || x.day == 20 || x.day == 25 || x.day == 30 || (x.day == dim && dim < 30)) return true;
   }
   return false;
}

string GtbNext()
{
   datetime jst = TimeGMT() + 9 * 3600;
   MqlDateTime j; TimeToStruct(jst, j);
   int start = (j.hour * 60 + j.min >= InpGtbEntryMin) ? 1 : 0;
   for(int k = start; k < 20; k++)
      if(GtbIsGotobi(jst + k * 86400)) return TimeToString(jst + k * 86400, TIME_DATE);
   return "-";
}

double GtbAtr(string s)
{
   MqlRates r[];
   if(CopyRates(s, PERIOD_H1, 1, 121, r) < 121) return 0;
   double sum = 0;
   for(int i = 1; i < 121; i++)
      sum += MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
   return sum / 120.0;
}

double GtbLot(string s)
{
   double mn = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   return NormalizeDouble(MathMax(mn, MathFloor(InpGtbLot / st + 1e-9) * st), 2);
}

double GtbPip(string s)
{
   int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   double pt = SymbolInfoDouble(s, SYMBOL_POINT);
   return (dg == 3 || dg == 5) ? 10 * pt : pt;
}

bool GtbPosition(string s, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpGtbMagic && PositionGetString(POSITION_SYMBOL) == s) { ticket = t; return true; }
   }
   return false;
}

bool GtbTradedSince(string s, datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d > 0 && HistoryDealGetInteger(d, DEAL_MAGIC) == InpGtbMagic && HistoryDealGetString(d, DEAL_SYMBOL) == s) return true;
   }
   return false;
}

void GtbInit()
{
   string parts[];
   int n = StringSplit(InpGtbSymbols, ',', parts);
   string missing = "", names = "";
   for(int i = 0; i < n; i++)
   {
      string b = parts[i]; StringTrimLeft(b); StringTrimRight(b);
      if(b == "") continue;
      string s = RsiResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ", ") + b; continue; }
      SymbolSelect(s, true);
      int k = ArraySize(gt_sym); ArrayResize(gt_sym, k + 1); ArrayResize(gt_day, k + 1);
      gt_sym[k] = s; gt_day[k] = 0; names += (names == "" ? "" : ", ") + s;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpGtbMagic) { int m = ArraySize(gt_known); ArrayResize(gt_known, m + 1); gt_known[m] = t; }
   }
   gt_ready = true;
   GtbEvent(StringFormat("GOTOBI ONLINE | %s: SELL at the Tokyo fix 09:55 JST on Gotobi days, close 10:15 JST, SL %.1f ATR(H1), lot %.2f | "
                         "next Gotobi day %s | %d open position(s)%s", names, InpGtbSlAtr, InpGtbLot, GtbNext(), ArraySize(gt_known),
                         missing == "" ? "" : " | not found: " + missing));
}

void GtbReportClosed(ulong pos)
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
   double pip = GtbPip(s);
   string what = reason == DEAL_REASON_SL ? "GOTOBI SL HIT" : "GOTOBI CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_EXPERT ? "10:15 JST time exit" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(s, PERIOD_M5, "GTX", lv, lc, lb, 0, 0, 0, 0, false);
   GtbEvent(StringFormat("%s %s | SELL from %s closed at %s (%s), %+.1f pips, profit $%.2f", what, s, RsiP(s, inPx), RsiP(s, outPx), why,
                         (inPx - outPx) / pip, profit) + Img(fn));
}

void GtbOnTimer()
{
   if(!InpGtbOn) return;
   if(!gt_ready) GtbInit();
   datetime jst = TimeGMT() + 9 * 3600;
   MqlDateTime j; TimeToStruct(jst, j);
   int jmin = j.hour * 60 + j.min, jday = j.year * 10000 + j.mon * 100 + j.day;
   for(int q = ArraySize(gt_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(gt_known[q])) { GtbReportClosed(gt_known[q]); ArrayRemove(gt_known, q, 1); }
   for(int k = 0; k < ArraySize(gt_sym); k++)
   {
      string s = gt_sym[k];
      ulong pt;
      if(GtbPosition(s, pt))
      {
         bool known = false;
         for(int q = 0; q < ArraySize(gt_known); q++) if(gt_known[q] == pt) known = true;
         if(!known) { int m = ArraySize(gt_known); ArrayResize(gt_known, m + 1); gt_known[m] = pt; }
         PositionSelectByTicket(pt);
         long held = (long)(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME));
         if(jmin >= InpGtbExitMin || held >= (InpGtbExitMin - InpGtbEntryMin) * 60)
         {
            trade.SetExpertMagicNumber(InpGtbMagic); trade.SetTypeFillingBySymbol(s);
            if(!trade.PositionClose(pt)) GtbEvent(StringFormat("ERROR | Gotobi close %s failed: %d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
            trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         }
         continue;
      }
      if(j.day_of_week == 0 || j.day_of_week == 6 || jmin != InpGtbEntryMin || gt_day[k] == jday) continue;
      gt_day[k] = jday;
      if(!GtbIsGotobi(jst)) continue;
      if(j.sec > InpGtbLateSec) { GtbEvent(StringFormat("GOTOBI SKIPPED %s | the EA was %d s late for the 09:55 JST fix (the move is in the first minutes)", s, j.sec)); continue; }
      if(GtbTradedSince(s, TimeCurrent() - 3600)) continue;
      MqlTick tk;
      if(!SymbolInfoTick(s, tk) || TimeCurrent() - tk.time > 120) { GtbEvent("GOTOBI SKIPPED " + s + " | no fresh price"); continue; }
      double pip = GtbPip(s), spr = (tk.ask - tk.bid) / pip;
      if(spr > InpGtbMaxSpread) { GtbEvent(StringFormat("GOTOBI SKIPPED %s | spread %.1f pips is above %.1f", s, spr, InpGtbMaxSpread)); continue; }
      double atr = GtbAtr(s);
      if(atr <= 0) { GtbEvent("GOTOBI SKIPPED " + s + " | H1 history not loaded"); continue; }
      int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
      double sl = NormalizeDouble(tk.bid + InpGtbSlAtr * atr, dg);
      double lot = GtbLot(s);
      trade.SetExpertMagicNumber(InpGtbMagic); trade.SetTypeFillingBySymbol(s);
      bool ok = trade.Sell(lot, s, 0, sl, 0, "GOTOBI " + TimeToString(jst, TIME_DATE));
      double px = trade.ResultPrice();
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(ok)
         GtbEvent(StringFormat("GOTOBI SELL %s | Tokyo fix on a Gotobi day (%s JST): SELL %.2f lot at %s, SL %s (%.1f pips), no TP, "
                               "closes at 10:15 JST | spread %.1f pips", s, TimeToString(jst, TIME_DATE), lot, RsiP(s, px > 0 ? px : tk.bid),
                               RsiP(s, sl), (sl - tk.bid) / pip, spr));
      else
         GtbEvent(StringFormat("ERROR | Gotobi sell %s failed: %d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
}
//+------------------------------------------------------------------+
