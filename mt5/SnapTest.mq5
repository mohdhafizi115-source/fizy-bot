//+------------------------------------------------------------------+
//| SnapTest: no trading. Takes the two kinds of event screenshots   |
//| (London M15 with box + levels, RSI2 H1 with indicators) so they  |
//| can be checked, plus the S/R zone map and a zone alert picture,  |
//| then closes the terminal.                                         |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>
CTrade trade;                                   // FizyCommon needs these two (no trading here)
input string InpSymbol = "XAUUSD.m";
#include "FizySnap.mqh"
#include "FizyCommon.mqh"
#include "FizySR.mqh"
int OnInit() { EventSetTimer(3); return(INIT_SUCCEEDED); }
void OnDeinit(const int r) { EventKillTimer(); }
int n = 0;
void OnTimer()
{
   n++;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) && n < 40) return;
   EventKillTimer();
   string g = "XAUUSD.m", b = "BTCUSD.m";
   bool c; if(!SymbolExist(b, c)) b = "BTCUSD";
   SymbolSelect(g, true); SymbolSelect(b, true);
   MqlRates r[]; int k = CopyRates(g, PERIOD_M15, 0, 40, r);
   double hi = 0, lo = 1e9; for(int i = 0; i < k - 10; i++) { hi = MathMax(hi, r[i].high); lo = MathMin(lo, r[i].low); }
   double lv[4]; color lc[4]; string lb[4];
   lv[0] = hi + 0.1; lc[0] = clrSeaGreen; lb[0] = "BUY STOP"; lv[1] = lo - 0.1; lc[1] = clrIndianRed; lb[1] = "SELL STOP";
   lv[2] = hi + 2 * (hi - lo); lc[2] = clrBlue; lb[2] = "TP"; lv[3] = lo - 2 * (hi - lo); lc[3] = clrBlue; lb[3] = "TP";
   string f1 = (k > 12) ? Snap(g, PERIOD_M15, "TEST", lv, lc, lb, r[0].time, r[k - 11].time, hi, lo, false) : "";
   double lv2[2]; color lc2[2]; string lb2[2];
   double bid = SymbolInfoDouble(b, SYMBOL_BID);
   lv2[0] = bid; lc2[0] = clrBlue; lb2[0] = "entry"; lv2[1] = bid * 0.98; lc2[1] = clrIndianRed; lb2[1] = "SL";
   string f2 = Snap(b, PERIOD_H1, "TEST", lv2, lc2, lb2, 0, 0, 0, 0, true);
   // S/R zones: the map and an alert picture on the nearest support (pictures only, no events sent)
   for(int w = 0; w < 20 && Bars(g, PERIOD_M15) < 600; w++) Sleep(1000);
   sr_sym = g; sr_ready = true;
   SrCompute();
   double none[]; color nc[]; string nl[];
   string f3 = SrSnap("TEST_SRM", -1, none, nc, nl), f4 = "";
   double px = SymbolInfoDouble(g, SYMBOL_BID);
   int zi = -1;
   for(int i = 0; i < ArraySize(sr_lo); i++) if(sr_hi[i] < px) zi = i;
   if(zi >= 0)
   {
      double a = sr_atr, sl = sr_lo[zi] - 0.3 * a;
      double zl[3]; color zc[3]; string zb[3];
      zl[0] = sr_hi[zi]; zc[0] = clrRoyalBlue; zb[0] = "BUY idea";
      zl[1] = sl;        zc[1] = clrRed;       zb[1] = "SL";
      zl[2] = sr_hi[zi] + 2 * (sr_hi[zi] - sl); zc[2] = clrGreen; zb[2] = "TP 2R";
      f4 = SrSnap("TEST_SRZ", zi, zl, zc, zb);
   }
   string zs = StringFormat("SR: %d M15 bars, %d zones, ATR %s, price %s, resistance %s, support %s", Bars(g, PERIOD_M15), ArraySize(sr_lo),
                            SrP(sr_atr), SrP(px), SrList(px, true, 2), SrList(px, false, 2));
   int h = FileOpen("snap_test.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE) { FileWriteString(h, f1 + "\r\n" + f2 + "\r\n" + f3 + "\r\n" + f4 + "\r\n" + zs + "\r\n"); FileClose(h); }
   TerminalClose(0);
}
