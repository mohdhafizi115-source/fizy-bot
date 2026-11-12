//+------------------------------------------------------------------+
//| FizyLB.mq5 - the EA shell: it loads every module and, when       |
//| InpLbOn is true, trades the London breakout itself (demo only).  |
//| ON 5 NOV 2026 THE OWNER KEPT ONLY SIX MODULES: Gotobi, month-end |
//| fix, gold LBMA auction, Kumo, Tenkan/Kijun and the M1 spike      |
//| fade. The five breakout modules are switched off: the London     |
//| breakout here (InpLbOn), NR7, Williams, and both USDJPY day      |
//| trades. Their code stays in the repository so one input flips    |
//| them back on; SweepOff() below closes anything they left behind. |
//| London breakout rules, for when it is switched on again (chart = |
//| server time): Asian range 03:00-08:00, OCO stops +-0.10 at       |
//| 08:00, SL at the other side capped at 0.6% of price, TP 2.5R, SL |
//| to entry at 1.5R, close everything at 21:00. Squeeze filter:     |
//| range < 0.6 x daily ATR(14); range 0.30-1.60% of price.          |
//| Stateless: everything is read back from the broker (orders,      |
//| positions, history with the magic number), so the terminal can   |
//| be restarted at any time (it runs on GitHub Actions in shifts).  |
//| Events are appended to MQL5\Files\flb_events.txt (one per line); |
//| the workflow forwards them to Telegram.                           |
//+------------------------------------------------------------------+
#property strict
#property version "2.19"
#include <Trade/Trade.mqh>

input bool   InpLbOn       = false;   // the London breakout itself: OFF since 5 Nov at the owner's request
input string InpSymbol     = "XAUUSD.m";
input double InpLot        = 0.01;
input long   InpMagic      = 260308;
input int    InpRangeStart = 3;       // Asian range start hour (server)
input int    InpRangeEnd   = 8;       // range end = order time (server)
input int    InpLateMin    = 30;      // no new orders after 08:30
input int    InpCloseHour  = 21;      // close everything (server)
input double InpMinPct     = 0.30;
input double InpMaxPct     = 1.60;
input double InpCapPct     = 0.60;
input double InpTpR        = 2.5;
input double InpBeR        = 1.5;
input double InpBuffer     = 0.10;
input double InpSqueeze    = 0.60;    // 0 = off
input bool   InpDemoOnly   = true;
input bool   InpSnapTest   = false;   // test runs: send a screenshot with the start message

CTrade trade;
string g_noTradeDay = "";             // day already reported as "no trade" in this run
ulong  g_known[];                     // position tickets seen open (to report TP / SL closes)

#include "FizySnap.mqh"                // MT5 chart screenshots for the Telegram events
#include "FizyCommon.mqh"              // symbol names, prices, London time; closes anything the removed RSI2 module left
#include "FizyNR7.mqh"                 // D1 NR7 breakout on XAUUSD, USDJPY, AUDJPY
#include "FizyGTB.mqh"                 // Gotobi / month-end Tokyo-fix reversal on USDJPY, EURJPY, GBPJPY (09:55 -> 10:15 JST)
#include "FizyMEF.mqh"                 // month-end Tokyo fix on crosses (CADCHF, NZDCHF sell; USDCAD, GBPNZD buy; 09:40 -> 09:55 JST)
#include "FizyGAU.mqh"                 // gold before the LBMA AM auction (sell 10:15 -> 10:30 London)
#include "FizyWVB.mqh"                 // Williams volatility breakout day trade (USDJPY, EURJPY, GBPJPY, XAUUSD)
#include "FizySR.mqh"                  // gold M15 support / resistance zone alerts (no trading)
#include "FizyDTJ.mqh"                 // USDJPY day trades: previous-day breakout, New York continuation
#include "FizyKUMO.mqh"                // gold H1 Ichimoku cloud breakout
#include "FizyTK.mqh"                  // gold H1 Ichimoku Tenkan / Kijun cross, day trade
#include "FizySPK.mqh"                 // gold M1 spike fade (buy a sharp drop when ATR dwarfs the spread)
#include "FizyKLT.mqh"                 // gold M1 Keltner re-entry scalp with a 30-pip breakeven (v2.16, rounds 79-79d)
#include "FizyHA.mqh"                  // gold M1 Heikin Ashi + EMA 10/30 + Stochastic, the owner's rule, TP 1:1 (v2.08)
#include "FizyLEG.mqh"                 // gold M1 leg fade, the owner's rule: fade a 60-candle leg, up to 5 entries, no SL

//--- helpers -------------------------------------------------------
datetime DayStart(datetime t) { MqlDateTime s; TimeToStruct(t, s); s.hour = 0; s.min = 0; s.sec = 0; return StructToTime(s); }
string   P(double v)           { return DoubleToString(v, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)); }
double   N(double v)           { return NormalizeDouble(v, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)); }

void Event(string msg)
{
   int h = FileOpen("flb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("EVENT ", msg);
}

double VolumeOk(double lot)
{
   double mn = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN), st = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double mx = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   double v = MathMax(mn, MathFloor(lot / st + 1e-9) * st);
   return NormalizeDouble(MathMin(v, mx), 2);
}

int CountOrders()
{
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t > 0 && OrderGetInteger(ORDER_MAGIC) == InpMagic && OrderGetString(ORDER_SYMBOL) == InpSymbol) n++;
   }
   return n;
}

int CountPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic && PositionGetString(POSITION_SYMBOL) == InpSymbol) n++;
   }
   return n;
}

// any order placed or deal done today by this EA (so it never places twice on the same day)
bool TradedToday(datetime day)
{
   if(!HistorySelect(day, TimeCurrent() + 60)) return false;
   for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t > 0 && HistoryOrderGetInteger(t, ORDER_MAGIC) == InpMagic) return true;
   }
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t > 0 && HistoryDealGetInteger(t, DEAL_MAGIC) == InpMagic) return true;
   }
   return false;
}

void DeletePending(string why)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetInteger(ORDER_MAGIC) != InpMagic || OrderGetString(ORDER_SYMBOL) != InpSymbol) continue;
      string side = (OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP) ? "BUY STOP" : "SELL STOP";
      double pr = OrderGetDouble(ORDER_PRICE_OPEN);
      if(trade.OrderDelete(t)) Event(StringFormat("ORDER DELETED | %s %s deleted (%s)", side, P(pr), why));
      else Event(StringFormat("ERROR | could not delete %s %s: %d %s", side, P(pr), trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
}

//--- 08:00: place the two stop orders ------------------------------
void PlaceOrders(datetime day)
{
   datetime r0 = day + InpRangeStart * 3600, r1 = day + InpRangeEnd * 3600;
   MqlRates m15[];
   int n = CopyRates(InpSymbol, PERIOD_M15, r0, r1 - 1, m15);
   if(n < (InpRangeEnd - InpRangeStart) * 4 - 2)
   {
      if(g_noTradeDay != TimeToString(day, TIME_DATE)) { g_noTradeDay = TimeToString(day, TIME_DATE); Event(StringFormat("NO TRADE TODAY | only %d M15 candles in the Asian range", n)); }
      return;
   }
   double hi = m15[0].high, lo = m15[0].low;
   for(int i = 1; i < n; i++) { hi = MathMax(hi, m15[i].high); lo = MathMin(lo, m15[i].low); }
   double mid = (hi + lo) / 2, pct = (hi - lo) / mid * 100;
   // daily ATR(14) from the days before today
   MqlRates d1[];
   double atr = 0;
   int nd = CopyRates(InpSymbol, PERIOD_D1, 1, 15, d1);
   if(nd >= 15)
   {
      double s = 0;
      for(int i = 1; i < 15; i++)
         s += MathMax(d1[i].high - d1[i].low, MathMax(MathAbs(d1[i].high - d1[i - 1].close), MathAbs(d1[i].low - d1[i - 1].close)));
      atr = s / 14;
   }
   double ratio = (atr > 0) ? (hi - lo) / atr : -1;
   string rng = StringFormat("Asian range %02d:00-%02d:00 high %s / low %s (%.2f%%, %s daily ATR)", InpRangeStart, InpRangeEnd, P(hi), P(lo), pct,
                             ratio >= 0 ? StringFormat("%.2fx", ratio) : "n/a");
   string dkey = TimeToString(day, TIME_DATE);
   if(InpSqueeze > 0 && ratio >= InpSqueeze)
   {
      if(g_noTradeDay != dkey) { g_noTradeDay = dkey; Event("NO TRADE TODAY | " + rng + StringFormat(", needs < %.2fx ATR", InpSqueeze)); }
      return;
   }
   if(pct < InpMinPct || pct > InpMaxPct)
   {
      if(g_noTradeDay != dkey) { g_noTradeDay = dkey; Event("NO TRADE TODAY | " + rng + StringFormat(", needs %.2f-%.2f%%", InpMinPct, InpMaxPct)); }
      return;
   }
   double capd = mid * InpCapPct / 100;
   double bIn = N(hi + InpBuffer), bSl = N(MathMax(lo, bIn - capd)), bR = bIn - bSl, bTp = N(bIn + InpTpR * bR);
   double sIn = N(lo - InpBuffer), sSl = N(MathMin(hi, sIn + capd)), sR = sSl - sIn, sTp = N(sIn - InpTpR * sR);
   double lot = VolumeOk(InpLot);
   string cm = "FLB " + TimeToString(day, TIME_DATE);
   // the EA deletes unfilled orders at the close hour (and reports it); the broker expiry 5 minutes later is only a backup
   int em = (int)SymbolInfoInteger(InpSymbol, SYMBOL_EXPIRATION_MODE);
   ENUM_ORDER_TYPE_TIME tt = ((em & SYMBOL_EXPIRATION_SPECIFIED) != 0) ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC;
   datetime exp = (tt == ORDER_TIME_SPECIFIED) ? day + InpCloseHour * 3600 + 300 : 0;
   MqlTick tk; SymbolInfoTick(InpSymbol, tk);
   string res = "";
   bool okB, okS;
   if(tk.ask >= bIn) okB = trade.Buy(lot, InpSymbol, 0, bSl, bTp, cm);            // already above: in at market
   else okB = trade.BuyStop(lot, bIn, InpSymbol, bSl, bTp, tt, exp, cm);
   res += okB ? "" : StringFormat(" | buy error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   if(tk.bid <= sIn) okS = trade.Sell(lot, InpSymbol, 0, sSl, sTp, cm);
   else okS = trade.SellStop(lot, sIn, InpSymbol, sSl, sTp, tt, exp, cm);
   res += okS ? "" : StringFormat(" | sell error %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   double lv[6]; color lc[6]; string lb[6];
   lv[0] = bIn; lc[0] = clrSeaGreen; lb[0] = "BUY STOP";  lv[1] = bSl; lc[1] = clrIndianRed; lb[1] = "buy SL";
   lv[2] = bTp; lc[2] = clrBlue;     lb[2] = "buy TP";    lv[3] = sIn; lc[3] = clrIndianRed; lb[3] = "SELL STOP";
   lv[4] = sSl; lc[4] = clrSeaGreen; lb[4] = "sell SL";   lv[5] = sTp; lc[5] = clrBlue;      lb[5] = "sell TP";
   string fn = Snap(InpSymbol, PERIOD_M15, "LB", lv, lc, lb, r0, r1, hi, lo, false);
   Event(StringFormat("ORDERS PLACED | %s | BUY STOP %s SL %s TP %s (BE at %s) | SELL STOP %s SL %s TP %s (BE at %s) | lot %.2f, risk per side $%.2f / $%.2f%s",
                      rng, P(bIn), P(bSl), P(bTp), P(bIn + InpBeR * bR), P(sIn), P(sSl), P(sTp), P(sIn - InpBeR * sR),
                      lot, bR * lot * 100, sR * lot * 100, res) + Img(fn));
}

//--- report positions that closed (TP / SL / BE) -------------------
void ReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1; long dtype = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); dtype = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = (reason == DEAL_REASON_TP) ? "TP HIT" : (reason == DEAL_REASON_SL) ? (MathAbs(outPx - inPx) <= 0.2 ? "BREAKEVEN" : "SL HIT") : "CLOSED";
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(InpSymbol, PERIOD_M15, "LBX", lv, lc, lb, 0, 0, 0, 0, false);
   Event(StringFormat("%s | %s from %s closed at %s, profit $%.2f", what, dtype == DEAL_TYPE_BUY ? "BUY" : "SELL", P(inPx), P(outPx), profit) + Img(fn));
}

void Manage(datetime now, datetime day)
{
   // OCO, breakeven, list of open tickets
   ulong open[]; ArrayResize(open, 0);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic || PositionGetString(POSITION_SYMBOL) != InpSymbol) continue;
      int k = ArraySize(open); ArrayResize(open, k + 1); open[k] = t;
      bool isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      double op = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
      bool known = false;
      for(int j = 0; j < ArraySize(g_known); j++) if(g_known[j] == t) known = true;
      if(!known)
      {
         int m = ArraySize(g_known); ArrayResize(g_known, m + 1); g_known[m] = t;
         double lvf[3]; color lcf[3]; string lbf[3];
         lvf[0] = op; lcf[0] = clrBlue; lbf[0] = "entry"; lvf[1] = sl; lcf[1] = clrIndianRed; lbf[1] = "SL"; lvf[2] = tp; lcf[2] = clrSeaGreen; lbf[2] = "TP";
         string fnf = Snap(InpSymbol, PERIOD_M15, "LBF", lvf, lcf, lbf, 0, 0, 0, 0, false);
         Event(StringFormat("POSITION OPEN | %s %.2f lot from %s, SL %s, TP %s", isBuy ? "BUY" : "SELL", PositionGetDouble(POSITION_VOLUME), P(op), P(sl), P(tp)) + Img(fnf));
      }
      if(CountOrders() > 0) DeletePending("the other side filled");
      double risk = MathAbs(op - sl);
      if(sl > 0 && risk > InpBuffer + 0.05)                 // breakeven not done yet
      {
         MqlTick tk; SymbolInfoTick(InpSymbol, tk);
         double be = isBuy ? op + InpBeR * risk : op - InpBeR * risk;
         if((isBuy && tk.bid >= be) || (!isBuy && tk.ask <= be))
         {
            double nsl = N(isBuy ? op + InpBuffer : op - InpBuffer);
            if(trade.PositionModify(t, nsl, tp)) Event(StringFormat("SL MOVED TO ENTRY | price reached %s (1.5R), SL now %s, TP %s", P(be), P(nsl), P(tp)));
            else Event(StringFormat("ERROR | SL move failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         }
      }
   }
   // closed since the last check
   for(int j = ArraySize(g_known) - 1; j >= 0; j--)
   {
      bool still = false;
      for(int k = 0; k < ArraySize(open); k++) if(open[k] == g_known[j]) still = true;
      if(!still) { ReportClosed(g_known[j]); ArrayRemove(g_known, j, 1); }
   }
   // close hour
   MqlDateTime s; TimeToStruct(now, s);
   if(s.hour >= InpCloseHour)
   {
      for(int k = 0; k < ArraySize(open); k++)
         if(trade.PositionClose(open[k])) { /* reported by ReportClosed on the next check */ }
         else Event(StringFormat("ERROR | close at %02d:00 failed: %d %s", InpCloseHour, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      if(CountOrders() > 0) DeletePending(StringFormat("%02d:00, no breakout", InpCloseHour));
   }
}

//--- main ----------------------------------------------------------
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetTypeFillingBySymbol(InpSymbol);
   trade.SetDeviationInPoints(50);
   SymbolSelect(InpSymbol, true);
   EventSetTimer(1);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }

bool g_started = false;
//+------------------------------------------------------------------+
//| The five modules switched off on 5 Nov cannot clean up after     |
//| themselves: their OnTimer returns at the first line. So anything |
//| they still had open when the switch was flipped is closed here   |
//| and reported, once, instead of being left to the broker.         |
//+------------------------------------------------------------------+
datetime g_sweep = 0;

void SweepOff()
{
   if(TimeCurrent() - g_sweep < 60) return;                                 // at most once a minute
   g_sweep = TimeCurrent();
   long off[];
   ArrayResize(off, 0);
   if(!InpLbOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpMagic; }
   if(!InpNr7On) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpNr7Magic; }
   if(!InpWvbOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpWvbMagic; }
   if(!InpTkOn) { int m = ArraySize(off); ArrayResize(off, m + 2); off[m] = InpTkMagic; off[m + 1] = InpTkMagic15; }
   if(!InpSpkOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpSpkMagic; }
   if(!InpHaOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpHaMagic; }
   if(!InpKltOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpKltMagic; }
   if(!InpLegOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpLegMagic; }
   if(!InpKumoOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpKumoMagic; }
   if(!InpGtbOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpGtbMagic; }
   if(!InpMefOn) { int m = ArraySize(off); ArrayResize(off, m + 1); off[m] = InpMefMagic; }
   if(!InpDtjOn)
   {
      int m = ArraySize(off); ArrayResize(off, m + 2); off[m] = InpPdhlMagic; off[m + 1] = InpNycMagic;
   }
   int nOff = ArraySize(off);
   if(nOff == 0) return;
   for(int i = OrdersTotal() - 1; i >= 0; i--)                              // pending orders first
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      long mg = OrderGetInteger(ORDER_MAGIC);
      bool hit = false;
      for(int q = 0; q < nOff; q++) if(mg == off[q]) hit = true;
      if(!hit) continue;
      string sy = OrderGetString(ORDER_SYMBOL);
      if(trade.OrderDelete(t))
         Event(StringFormat("CLEANUP | %s pending order of a switched-off module deleted (magic %d)", sy, (int)mg));
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long mg = PositionGetInteger(POSITION_MAGIC);
      bool hit = false;
      for(int q = 0; q < nOff; q++) if(mg == off[q]) hit = true;
      if(!hit) continue;
      string sy = PositionGetString(POSITION_SYMBOL);
      MqlTick tk;
      if(!SymbolInfoTick(sy, tk) || TimeCurrent() - tk.time > 600) continue; // market closed: wait for the open
      double profit = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      trade.SetExpertMagicNumber(mg); trade.SetTypeFillingBySymbol(sy);
      bool ok = trade.PositionClose(t);
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(ok)
         Event(StringFormat("CLEANUP | %s position of a switched-off module closed at market, profit $%.2f (magic %d)",
                            sy, profit, (int)mg));
   }
}
//+------------------------------------------------------------------+

void OnTimer()
{
   if(!TerminalInfoInteger(TERMINAL_CONNECTED)) return;
   if(InpDemoOnly && AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
   {
      if(!g_started) { g_started = true; Event("STOPPED | this is not a demo account; the EA only trades demo accounts"); }
      return;
   }
   datetime now = TimeCurrent(), day = DayStart(now);
   MqlDateTime s; TimeToStruct(now, s);
   if(!g_started)
   {
      g_started = true;
      // remember the positions already open so their closes are reported too
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong t = PositionGetTicket(i);
         if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic) { int m = ArraySize(g_known); ArrayResize(g_known, m + 1); g_known[m] = t; }
      }
      string fn = "";
      if(InpSnapTest)
      {
         double lv[1]; color lc[1]; string lb[1];
         lv[0] = SymbolInfoDouble(InpSymbol, SYMBOL_BID); lc[0] = clrBlue; lb[0] = "bid";
         fn = Snap(InpSymbol, PERIOD_M15, "TEST", lv, lc, lb, 0, 0, 0, 0, false);
      }
      Event(StringFormat("STARTED | server time %s, %d open position(s), %d pending order(s), lot %.2f",
                         TimeToString(now, TIME_DATE | TIME_MINUTES), CountPositions(), CountOrders(), VolumeOk(InpLot)) + Img(fn));
   }
   GtbOnTimer();                                                            // first: the timed entries
   MefOnTimer();
   GauOnTimer();
   Nr7OnTimer();
   WvbOnTimer();
   DtjOnTimer();
   KumoOnTimer();
   TkOnTimer();
   SpkOnTimer();
   KltOnTimer();
   LegOnTimer();
   HaOnTimer();
   CloseLeftovers();
   SweepOff();                                                              // close what the switched-off modules left
   DayPaused();                                                             // daily $ target check (reports once when hit)
   if(s.day_of_week == 0 || s.day_of_week == 6) return;
   int minute = s.hour * 60 + s.min;
   if(InpLbOn && minute >= InpRangeEnd * 60 && minute < InpRangeEnd * 60 + InpLateMin && CountOrders() == 0 && CountPositions() == 0 && !TradedToday(day))
      PlaceOrders(day);
   if(InpLbOn) Manage(now, day);
   // heartbeat for the workflow: server time and whether the day is finished
   int h = FileOpen("flb_state.txt", FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(h != INVALID_HANDLE)
   {
      bool done = (s.hour >= InpCloseHour && CountOrders() == 0 && CountPositions() == 0);
      FileWriteString(h, StringFormat("%s|%d|%d|%d\r\n", TimeToString(now, TIME_DATE | TIME_SECONDS), CountPositions(), CountOrders(), done ? 1 : 0));
      FileClose(h);
   }
   SrOnTimer();                                                             // last: alerts only, its screenshots may take 2 s
}
//+------------------------------------------------------------------+
