//+------------------------------------------------------------------+
//| FizyMEF.mqh - month-end Tokyo-fix moves on crosses, demo only,    |
//| included by FizyLB.mq5 after FizyGTB.mqh (uses GtbAtr, GtbPip).   |
//| Rules (research/events.py + fx_flows.py, JustMarkets M5 2020-26): |
//|   on the last business day of the month (Tokyo date), at          |
//|   09:40:00 JST SELL CADCHF and NZDCHF, BUY USDCAD and GBPNZD, and |
//|   close them at the Tokyo fix, 09:55 JST. SL 1.0 x ATR(H1, 120).  |
//|   Tested 9:40 -> 9:55: PF 2.3-3.5 after spread, 5-7 of 7 years up. |
//| Events go to MQL5\Files\gtb_events.txt with the MONTHEND prefix.   |
//+------------------------------------------------------------------+
input string InpMefTrades   = "CADCHF:-1,NZDCHF:-1,USDCAD:1,GBPNZD:1";
input bool   InpMefOn       = true;
input double InpMefLot      = 0.01;
input long   InpMefMagic    = 260313;
input double InpMefSlAtr    = 1.0;
input double InpMefMaxSpread = 4.0;      // pips
input int    InpMefEntryMin = 580;       // 09:40 JST
input int    InpMefExitMin  = 595;       // 09:55 JST
input int    InpMefLateSec  = 60;

string   mf_sym[];
int      mf_dir[];
int      mf_day[];
ulong    mf_known[];
bool     mf_ready = false;

bool MefLastBusinessDay(datetime jst)
{
   MqlDateTime d; TimeToStruct(jst, d);
   if(d.day_of_week == 0 || d.day_of_week == 6) return false;
   MqlDateTime y; TimeToStruct(jst + (d.day_of_week == 5 ? 3 : 1) * 86400, y);
   return y.mon != d.mon;
}

bool MefPosition(string s, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMefMagic && PositionGetString(POSITION_SYMBOL) == s) { ticket = t; return true; }
   }
   return false;
}

bool MefTradedSince(string s, datetime since)
{
   if(!HistorySelect(since, TimeCurrent() + 60)) return false;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d > 0 && HistoryDealGetInteger(d, DEAL_MAGIC) == InpMefMagic && HistoryDealGetString(d, DEAL_SYMBOL) == s) return true;
   }
   return false;
}

void MefInit()
{
   string parts[];
   int n = StringSplit(InpMefTrades, ',', parts);
   string names = "", missing = "";
   for(int i = 0; i < n; i++)
   {
      string kv[];
      if(StringSplit(parts[i], ':', kv) != 2) continue;
      string b = kv[0]; StringTrimLeft(b); StringTrimRight(b);
      string s = SymResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ", ") + b; continue; }
      SymbolSelect(s, true);
      int k = ArraySize(mf_sym); ArrayResize(mf_sym, k + 1); ArrayResize(mf_dir, k + 1); ArrayResize(mf_day, k + 1);
      mf_sym[k] = s; mf_dir[k] = (int)StringToInteger(kv[1]) >= 0 ? 1 : -1; mf_day[k] = 0;
      names += (names == "" ? "" : ", ") + (mf_dir[k] > 0 ? "BUY " : "SELL ") + s;
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMefMagic) { int m = ArraySize(mf_known); ArrayResize(mf_known, m + 1); mf_known[m] = t; }
   }
   mf_ready = true;
   // next last business day
   datetime jst = TimeGMT() + 9 * 3600; string nxt = "-";
   MqlDateTime j; TimeToStruct(jst, j);
   int start = (j.hour * 60 + j.min >= InpMefEntryMin) ? 1 : 0;
   for(int k = start; k < 40; k++) if(MefLastBusinessDay(jst + k * 86400)) { nxt = TimeToString(jst + k * 86400, TIME_DATE); break; }
   GtbEvent(StringFormat("MONTHEND ONLINE | last business day of each month, 09:40 -> 09:55 JST (Tokyo fix): %s, SL %.1f ATR(H1), lot %.2f | next %s%s",
                         names, InpMefSlAtr, InpMefLot, nxt, missing == "" ? "" : " | not found: " + missing));
}

void MefReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, dtype = -1; string s = "";
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      s = HistoryDealGetString(d, DEAL_SYMBOL);
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); dtype = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0 || s == "") return;
   bool buy = dtype == DEAL_TYPE_BUY;
   double pips = (buy ? outPx - inPx : inPx - outPx) / GtbPip(s);
   string what = reason == DEAL_REASON_SL ? "MONTHEND SL HIT" : "MONTHEND CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss" : (reason == DEAL_REASON_EXPERT ? "09:55 JST fix" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(s, PERIOD_M5, "MEX", lv, lc, lb, 0, 0, 0, 0, false);
   GtbEvent(StringFormat("%s %s | %s from %s closed at %s (%s), %+.1f pips, profit $%.2f", what, s, buy ? "BUY" : "SELL", PriceStr(s, inPx),
                         PriceStr(s, outPx), why, pips, profit) + Img(fn));
}

void MefOnTimer()
{
   if(!InpMefOn) return;
   if(!mf_ready) MefInit();
   datetime jst = TimeGMT() + 9 * 3600;
   MqlDateTime j; TimeToStruct(jst, j);
   int jmin = j.hour * 60 + j.min, jday = j.year * 10000 + j.mon * 100 + j.day;
   for(int q = ArraySize(mf_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(mf_known[q])) { MefReportClosed(mf_known[q]); ArrayRemove(mf_known, q, 1); }
   string q_sym[], q_msg[]; double q_in[], q_sl[];
   for(int k = 0; k < ArraySize(mf_sym); k++)
   {
      string s = mf_sym[k];
      ulong pt;
      if(MefPosition(s, pt))
      {
         bool known = false;
         for(int q = 0; q < ArraySize(mf_known); q++) if(mf_known[q] == pt) known = true;
         if(!known) { int m = ArraySize(mf_known); ArrayResize(mf_known, m + 1); mf_known[m] = pt; }
         PositionSelectByTicket(pt);
         long held = (long)(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME));
         if(jmin >= InpMefExitMin || held >= (InpMefExitMin - InpMefEntryMin) * 60)
         {
            trade.SetExpertMagicNumber(InpMefMagic); trade.SetTypeFillingBySymbol(s);
            if(!trade.PositionClose(pt)) GtbEvent(StringFormat("ERROR | month-end close %s failed: %d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
            trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         }
         continue;
      }
      if(jmin != InpMefEntryMin || mf_day[k] == jday) continue;
      mf_day[k] = jday;
      if(!MefLastBusinessDay(jst)) continue;
      if(j.sec > InpMefLateSec) { GtbEvent(StringFormat("MONTHEND SKIPPED %s | the EA was %d s late for 09:40 JST", s, j.sec)); continue; }
      if(MefTradedSince(s, TimeCurrent() - 3600)) continue;
      MqlTick tk;
      if(!SymbolInfoTick(s, tk) || TimeCurrent() - tk.time > 120) { GtbEvent("MONTHEND SKIPPED " + s + " | no fresh price"); continue; }
      double pip = GtbPip(s), spr = (tk.ask - tk.bid) / pip;
      if(spr > InpMefMaxSpread) { GtbEvent(StringFormat("MONTHEND SKIPPED %s | spread %.1f pips is above %.1f", s, spr, InpMefMaxSpread)); continue; }
      double atr = GtbAtr(s);
      if(atr <= 0) { GtbEvent("MONTHEND SKIPPED " + s + " | H1 history not loaded"); continue; }
      int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
      bool buy = mf_dir[k] > 0;
      double sl = NormalizeDouble(buy ? tk.ask - InpMefSlAtr * atr : tk.bid + InpMefSlAtr * atr, dg);
      double mn = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
      double lot = NormalizeDouble(MathMax(mn, MathFloor(InpMefLot / st + 1e-9) * st), 2);
      trade.SetExpertMagicNumber(InpMefMagic); trade.SetTypeFillingBySymbol(s);
      string cm = "MONTHEND " + TimeToString(jst, TIME_DATE);
      bool ok = buy ? trade.Buy(lot, s, 0, sl, 0, cm) : trade.Sell(lot, s, 0, sl, 0, cm);
      double px = trade.ResultPrice();
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(ok)
      {
         int m = ArraySize(q_sym); ArrayResize(q_sym, m + 1); ArrayResize(q_msg, m + 1); ArrayResize(q_in, m + 1); ArrayResize(q_sl, m + 1);
         q_sym[m] = s; q_in[m] = px > 0 ? px : (buy ? tk.ask : tk.bid); q_sl[m] = sl;
         q_msg[m] = StringFormat("MONTHEND %s %s | last business day of the month, 09:40 JST: %s %.2f lot at %s, SL %s, no TP, closes at the 09:55 JST fix | spread %.1f pips",
                                 buy ? "BUY" : "SELL", s, buy ? "BUY" : "SELL", lot, PriceStr(s, q_in[m]), PriceStr(s, sl), spr);
      }
      else
         GtbEvent(StringFormat("ERROR | month-end %s %s failed: %d %s", buy ? "buy" : "sell", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   for(int m = 0; m < ArraySize(q_sym); m++)                               // charts after every order is in
   {
      double lv[2]; color lc[2]; string lb[2];
      lv[0] = q_in[m]; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = q_sl[m]; lc[1] = clrIndianRed; lb[1] = "SL";
      string fn = Snap(q_sym[m], PERIOD_M5, "ME", lv, lc, lb, 0, 0, 0, 0, false);
      GtbEvent(q_msg[m] + Img(fn));
   }
}
//+------------------------------------------------------------------+
