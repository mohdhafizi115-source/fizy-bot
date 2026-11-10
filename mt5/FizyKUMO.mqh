//+------------------------------------------------------------------+
//| FizyKUMO.mqh - Ichimoku cloud (Kumo) breakout on gold H1, demo     |
//| only, included by FizyLB.mq5. Rules (research/round19.py and      |
//| goldh1_detail.py, JustMarkets 2020-2026, swap counted: 976 trades,|
//| PF 1.29, halves 1.14 / 1.48, every year positive):                |
//|   Ichimoku (9, 26, 52) on closed H1 bars. BUY when an H1 close    |
//|   breaks above the cloud from inside / below and Tenkan > Kijun   |
//|   (SELL mirrored). Signal bars 01:30-22:00 server. Entry at the   |
//|   next bar open. SL 0.2 ATR(H1) beyond the far cloud edge, at     |
//|   least 0.5 ATR away. Exit when an H1 close is back inside the    |
//|   cloud, or after 48 H1 bars. One trade at a time.                |
//|   v2.17 (10 Nov, owner): TP $20 (200 pips) from the entry price; |
//|   round 81 (research/kumo81.py): 6.6 y PF 1.04 / +$214 vs 1.23 /  |
//|   +$1,433 without, last 12 months +$132 vs +$1,071, worst trade   |
//|   -$90 vs -$206; the owner chose it after seeing these numbers.   |
//| Events go to MQL5\Files\kumo_events.txt (forwarded to Telegram).  |
//+------------------------------------------------------------------+
input bool   InpKumoOn      = true;
input string InpKumoSymbol  = "XAUUSD";
input double InpKumoLot     = 0.01;
input double InpKumoTpUsd   = 20.0;     // v2.17: TP this many $ of price from the entry (200 pips); 0 = no TP
input long   InpKumoMagic   = 260317;

string   km_sym = "";
bool     km_ready = false;
datetime km_bar = 0;
ulong    km_known[];

void KumoEvent(string msg)
{
   int h = FileOpen("kumo_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("kumo event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("KUMO EVENT ", msg);
}

bool KumoPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpKumoMagic && PositionGetString(POSITION_SYMBOL) == km_sym) { ticket = t; return true; }
   }
   return false;
}

// Ichimoku values at closed bar index j of r[] (r[0] oldest); false if not enough bars
double KumoMid(const MqlRates &r[], int j, int len)
{
   double hh = r[j].high, ll = r[j].low;
   for(int q = j - len + 1; q <= j; q++) { hh = MathMax(hh, r[q].high); ll = MathMin(ll, r[q].low); }
   return (hh + ll) / 2;
}

bool KumoAt(const MqlRates &r[], int j, double &ten, double &kij, double &top, double &bot)
{
   if(j - 26 - 51 < 0) return false;
   ten = KumoMid(r, j, 9); kij = KumoMid(r, j, 26);
   double sa = (KumoMid(r, j - 26, 9) + KumoMid(r, j - 26, 26)) / 2, sb = KumoMid(r, j - 26, 52);
   top = MathMax(sa, sb); bot = MathMin(sa, sb);
   return true;
}

void KumoInit()
{
   km_ready = true;
   km_sym = SymResolve(InpKumoSymbol);
   if(km_sym == "") { KumoEvent("ERROR | Kumo breakout: symbol " + InpKumoSymbol + " not found"); return; }
   SymbolSelect(km_sym, true);
   ulong t;
   if(KumoPosition(t)) { int m = ArraySize(km_known); ArrayResize(km_known, m + 1); km_known[m] = t; }
   KumoEvent(StringFormat("KUMO ONLINE | %s H1: buy / sell when an H1 close breaks out of the Ichimoku cloud with Tenkan on the same side, "
                          "SL beyond the cloud, TP $%.0f, exit on a close back inside the cloud or after 48 hours, lot %.2f | %d open position(s)",
                          km_sym, InpKumoTpUsd, InpKumoLot, ArraySize(km_known)));
}

void KumoReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "KUMO SL HIT" : (reason == DEAL_REASON_TP ? "KUMO TP HIT" : "KUMO CLOSED");
   string why = reason == DEAL_REASON_SL ? "stop loss beyond the cloud" : reason == DEAL_REASON_TP ? StringFormat("take profit, +$%.0f from the entry", InpKumoTpUsd) : (reason == DEAL_REASON_EXPERT ? "H1 close back inside the cloud or 48 hours" : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(km_sym, PERIOD_H1, "KMX", lv, lc, lb, 0, 0, 0, 0, false);
   KumoEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, km_sym, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL",
                          PriceStr(km_sym, inPx), PriceStr(km_sym, outPx), why, profit) + Img(fn));
}

void KumoOnTimer()
{
   if(!InpKumoOn) return;
   if(!km_ready) KumoInit();
   if(km_sym == "") return;
   for(int q = ArraySize(km_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(km_known[q])) { KumoReportClosed(km_known[q]); ArrayRemove(km_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(km_sym, tk) || now - tk.time > 600) return;              // market closed
   datetime b0 = iTime(km_sym, PERIOD_H1, 0);
   if(b0 == 0 || b0 == km_bar) return;                                         // act once per new H1 bar
   MqlRates r[];
   int n = CopyRates(km_sym, PERIOD_H1, 1, 200, r);                            // closed bars, r[n-1] = the bar that just closed
   if(n < 120) return;                                                         // history not loaded yet: retry next tick
   km_bar = b0;
   int j = n - 1;
   double ten, kij, top, bot, ten1, kij1, top1, bot1;
   if(!KumoAt(r, j, ten, kij, top, bot) || !KumoAt(r, j - 1, ten1, kij1, top1, bot1)) return;
   // ATR(14) Wilder up to the bar before the signal bar (as in the test)
   double atr = r[1].high - r[1].low;
   for(int i = 2; i < j; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   double c = r[j].close, c1 = r[j - 1].close;
   int dg = (int)SymbolInfoInteger(km_sym, SYMBOL_DIGITS);
   ulong pt;
   if(KumoPosition(pt))
   {
      bool known = false;
      for(int q = 0; q < ArraySize(km_known); q++) if(km_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(km_known); ArrayResize(km_known, m + 1); km_known[m] = pt; }
      PositionSelectByTicket(pt);
      bool buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      int held = iBarShift(km_sym, PERIOD_H1, (datetime)PositionGetInteger(POSITION_TIME), false);
      bool inside = buy ? (c < top) : (c > bot);
      double op = PositionGetDouble(POSITION_PRICE_OPEN), ctp = PositionGetDouble(POSITION_TP);
      if(InpKumoTpUsd > 0 && ctp == 0 && !inside && held < 48)                // v2.17: a position without the TP gets it
      {
         double ntp = NormalizeDouble(buy ? op + InpKumoTpUsd : op - InpKumoTpUsd, dg);
         trade.SetExpertMagicNumber(InpKumoMagic); trade.SetTypeFillingBySymbol(km_sym);
         if((buy && tk.bid >= ntp) || (!buy && tk.ask <= ntp)) trade.PositionClose(pt);   // already beyond it: take it
         else if(trade.PositionModify(pt, PositionGetDouble(POSITION_SL), ntp))
            KumoEvent(StringFormat("KUMO TP SET %s | TP %s ($%.0f from the entry %s)", km_sym, PriceStr(km_sym, ntp), InpKumoTpUsd, PriceStr(km_sym, op)));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      if(inside || held >= 48)
      {
         trade.SetExpertMagicNumber(InpKumoMagic); trade.SetTypeFillingBySymbol(km_sym);
         if(!trade.PositionClose(pt)) KumoEvent(StringFormat("ERROR | Kumo close %s failed: %d %s", km_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;                                                                  // one trade at a time (a new entry waits for the next bar)
   }
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(hm < 90 || hm >= 1320) return;                                           // signal bars 01:30-22:00 server
   int dr = 0;
   if(c > top && c1 <= top1 && ten > kij) dr = 1;
   else if(c < bot && c1 >= bot1 && ten < kij) dr = -1;
   if(dr == 0) return;
   double px = dr > 0 ? tk.ask : tk.bid;
   double sl = dr > 0 ? MathMin(bot - 0.2 * atr, c - 0.5 * atr) : MathMax(top + 0.2 * atr, c + 0.5 * atr);
   sl = NormalizeDouble(sl, dg);
   if((px - sl) * dr <= 0) return;
   double mn = SymbolInfoDouble(km_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(km_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpKumoLot / sv + 1e-9) * sv), 2);
   if(DayPaused()) return;                                              // daily target reached
   trade.SetExpertMagicNumber(InpKumoMagic); trade.SetTypeFillingBySymbol(km_sym);
   double tp = InpKumoTpUsd > 0 ? NormalizeDouble(px + dr * InpKumoTpUsd, dg) : 0;
   bool ok = dr > 0 ? trade.Buy(lot, km_sym, 0, sl, tp, "KUMO") : trade.Sell(lot, km_sym, 0, sl, tp, "KUMO");
   if(!ok) KumoEvent(StringFormat("ERROR | Kumo %s order failed: %d %s", km_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double lv[4]; color lc[4]; string lb[4];
   lv[0] = px; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = top; lc[2] = clrSeaGreen; lb[2] = "cloud top"; lv[3] = bot; lc[3] = clrIndianRed; lb[3] = "cloud bottom";
   string fn = Snap(km_sym, PERIOD_H1, "KMF", lv, lc, lb, 0, 0, 0, 0, false);
   KumoEvent(StringFormat("KUMO %s %s | H1 close %s broke %s the cloud (%s - %s), Tenkan %s Kijun | %s %.2f lot at %s, SL %s, %s; "
                          "else exit on an H1 close back inside the cloud or after 48 hours", dr > 0 ? "BUY" : "SELL", km_sym, PriceStr(km_sym, c),
                          dr > 0 ? "above" : "below", PriceStr(km_sym, bot), PriceStr(km_sym, top), dr > 0 ? "above" : "below",
                          dr > 0 ? "BUY" : "SELL", lot, PriceStr(km_sym, px), PriceStr(km_sym, sl),
                          tp > 0 ? StringFormat("TP %s (+$%.0f)", PriceStr(km_sym, tp), InpKumoTpUsd) : "no TP") + Img(fn));
   int m = ArraySize(km_known);
   if(KumoPosition(pt)) { ArrayResize(km_known, m + 1); km_known[m] = pt; }
}
//+------------------------------------------------------------------+
