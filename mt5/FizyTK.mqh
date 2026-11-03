//+------------------------------------------------------------------+
//| FizyTK.mqh - Ichimoku Tenkan / Kijun cross on gold H1, day trade, |
//| demo only, included by FizyLB.mq5. Rules (research/ind23.py and   |
//| goldh1_ind24.py, JustMarkets 2020-2026, spread counted, no swap:  |
//| 640 trades, PF 1.50, halves 1.10 / 1.74, buys 1.55, sells 1.43,   |
//| neighbours 7/22/44 and 12/30/60 PF 1.33 / 1.27):                  |
//|   On closed H1 bars, Tenkan (9) crosses above Kijun (26) with the |
//|   close above the cloud (spans 26 / 52): BUY at the next bar open |
//|   (SELL mirrored). Signal bars 02:00-20:00 server, weekdays.      |
//|   SL 2 ATR(14, H1) from the signal close, no TP. Exit on the      |
//|   opposite cross, at 23:00 server, or at 22:00 on Fridays (never  |
//|   overnight, so no swap). One trade at a time.                    |
//| Events go to MQL5\Files\tk_events.txt (forwarded to Telegram).    |
//+------------------------------------------------------------------+
input bool   InpTkOn      = true;
input string InpTkSymbol  = "XAUUSD";
input double InpTkLot     = 0.01;
input long   InpTkMagic   = 260318;

string   tkx_sym = "";
bool     tkx_ready = false;
datetime tkx_bar = 0;
ulong    tkx_known[];

void TkEvent(string msg)
{
   int h = FileOpen("tk_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("tk event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("TK EVENT ", msg);
}

bool TkPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpTkMagic && PositionGetString(POSITION_SYMBOL) == tkx_sym) { ticket = t; return true; }
   }
   return false;
}

double TkMid(const MqlRates &r[], int j, int len)
{
   double hh = r[j].high, ll = r[j].low;
   for(int q = j - len + 1; q <= j; q++) { hh = MathMax(hh, r[q].high); ll = MathMin(ll, r[q].low); }
   return (hh + ll) / 2;
}

// Tenkan, Kijun and the cloud at closed bar j of r[] (r[0] oldest); false if not enough bars
bool TkAt(const MqlRates &r[], int j, double &ten, double &kij, double &top, double &bot)
{
   if(j - 26 - 51 < 0) return false;
   ten = TkMid(r, j, 9); kij = TkMid(r, j, 26);
   double sa = (TkMid(r, j - 26, 9) + TkMid(r, j - 26, 26)) / 2, sb = TkMid(r, j - 26, 52);
   top = MathMax(sa, sb); bot = MathMin(sa, sb);
   return true;
}

void TkInit()
{
   tkx_ready = true;
   tkx_sym = SymResolve(InpTkSymbol);
   if(tkx_sym == "") { TkEvent("ERROR | TK cross: symbol " + InpTkSymbol + " not found"); return; }
   SymbolSelect(tkx_sym, true);
   ulong t;
   if(TkPosition(t)) { int m = ArraySize(tkx_known); ArrayResize(tkx_known, m + 1); tkx_known[m] = t; }
   TkEvent(StringFormat("TK ONLINE | %s H1: buy / sell when Tenkan crosses Kijun with the H1 close beyond the Ichimoku cloud, "
                        "SL 2 ATR, exit on the opposite cross or at 23:00 server (day trade, no swap), lot %.2f | %d open position(s)",
                        tkx_sym, InpTkLot, ArraySize(tkx_known)));
}

void TkReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "TK SL HIT" : "TK CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss 2 ATR" : (reason == DEAL_REASON_EXPERT ? "opposite Tenkan / Kijun cross or day end" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(tkx_sym, PERIOD_H1, "TKX", lv, lc, lb, 0, 0, 0, 0, false);
   TkEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, tkx_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                        PriceStr(tkx_sym, inPx), PriceStr(tkx_sym, outPx), why, profit) + Img(fn));
}

void TkClose(ulong pt)
{
   trade.SetExpertMagicNumber(InpTkMagic); trade.SetTypeFillingBySymbol(tkx_sym);
   if(!trade.PositionClose(pt)) TkEvent(StringFormat("ERROR | TK close %s failed: %d %s", tkx_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
}

void TkOnTimer()
{
   if(!InpTkOn) return;
   if(!tkx_ready) TkInit();
   if(tkx_sym == "") return;
   for(int q = ArraySize(tkx_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(tkx_known[q])) { TkReportClosed(tkx_known[q]); ArrayRemove(tkx_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(tkx_sym, tk) || now - tk.time > 600) return;            // market closed
   MqlDateTime ns; TimeToStruct(now, ns);
   int nowMin = ns.hour * 60 + ns.min;
   ulong pt;
   bool have = TkPosition(pt);
   if(have)
   {
      bool known = false;
      for(int q = 0; q < ArraySize(tkx_known); q++) if(tkx_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(tkx_known); ArrayResize(tkx_known, m + 1); tkx_known[m] = pt; }
      if(nowMin >= 1380 || (ns.day_of_week == 5 && nowMin >= 1320)) { TkClose(pt); return; }   // day trade: never overnight
   }
   datetime b0 = iTime(tkx_sym, PERIOD_H1, 0);
   if(b0 == 0 || b0 == tkx_bar) return;                                       // act once per new H1 bar
   MqlRates r[];
   int n = CopyRates(tkx_sym, PERIOD_H1, 1, 200, r);                          // closed bars, r[n-1] = the bar that just closed
   if(n < 120) return;                                                        // history not loaded yet: retry next tick
   tkx_bar = b0;
   int j = n - 1;
   double ten, kij, top, bot, ten1, kij1, top1, bot1;
   if(!TkAt(r, j, ten, kij, top, bot) || !TkAt(r, j - 1, ten1, kij1, top1, bot1)) return;
   bool crossUp = ten > kij && ten1 <= kij1, crossDn = kij > ten && kij1 <= ten1;
   if(have)
   {
      PositionSelectByTicket(pt);
      bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      if((buy && crossDn) || (!buy && crossUp)) TkClose(pt);                  // opposite cross: out (no reverse on the same bar)
      return;
   }
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1260) return;   // signal bars 02:00-20:00 server
   double c = r[j].close;
   int dr = 0;
   if(crossUp && c > top) dr = 1;
   else if(crossDn && c < bot) dr = -1;
   if(dr == 0) return;
   // ATR(14) Wilder up to the bar before the signal bar (as in the test)
   double atr = r[1].high - r[1].low;
   for(int i = 2; i < j; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   int dg = (int)SymbolInfoInteger(tkx_sym, SYMBOL_DIGITS);
   double px = dr > 0 ? tk.ask : tk.bid;
   double sl = NormalizeDouble(c - dr * 2.0 * atr, dg);
   if((px - sl) * dr <= 0) return;
   double mn = SymbolInfoDouble(tkx_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(tkx_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpTkLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpTkMagic); trade.SetTypeFillingBySymbol(tkx_sym);
   bool ok = dr > 0 ? trade.Buy(lot, tkx_sym, 0, sl, 0, "TK") : trade.Sell(lot, tkx_sym, 0, sl, 0, "TK");
   if(!ok) TkEvent(StringFormat("ERROR | TK %s order failed: %d %s", tkx_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double lv[4]; color lc[4]; string lb[4];
   lv[0] = px; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = ten; lc[2] = clrDarkOrange; lb[2] = "Tenkan"; lv[3] = kij; lc[3] = clrPurple; lb[3] = "Kijun";
   string fn = Snap(tkx_sym, PERIOD_H1, "TKF", lv, lc, lb, 0, 0, 0, 0, false);
   TkEvent(StringFormat("TK %s %s | Tenkan %s crossed %s Kijun %s with the H1 close %s %s the cloud (%s - %s) | %s %.2f lot at %s, SL %s, no TP: "
                        "exit on the opposite cross or at 23:00 server", dr > 0 ? "BUY" : "SELL", tkx_sym, PriceStr(tkx_sym, ten),
                        dr > 0 ? "above" : "below", PriceStr(tkx_sym, kij), PriceStr(tkx_sym, c), dr > 0 ? "above" : "below",
                        PriceStr(tkx_sym, bot), PriceStr(tkx_sym, top), dr > 0 ? "BUY" : "SELL", lot, PriceStr(tkx_sym, px), PriceStr(tkx_sym, sl)) + Img(fn));
   int m = ArraySize(tkx_known);
   if(TkPosition(pt)) { ArrayResize(tkx_known, m + 1); tkx_known[m] = pt; }
}
//+------------------------------------------------------------------+
