//+------------------------------------------------------------------+
//| FizySMC.mqh - gold M15 Smart Money Concepts entry, demo only,     |
//| included by FizyLB.mq5.  v2.23 (13 Nov 2026), the owner's order   |
//| ("ya bina je") after rounds 102-102c.                             |
//|                                                                  |
//| RULES on closed M15 bars of XAUUSD (BUY shown, SELL mirrored):    |
//|  swings    fractal highs / lows, InpSmcSwing (5) bars each side,  |
//|            known only 5 bars later (no look-ahead)                |
//|  BOS       an M15 close above the last unused swing high while    |
//|            the structure was already bullish (a break after a     |
//|            bearish structure is a CHoCH and is NOT traded)        |
//|  protected the lowest low between that swing high and the break   |
//|  low                                                              |
//|  order     the last bearish candle at the protected low or up to  |
//|  block     5 candles before it (the low's own candle if none)     |
//|  entry     BUY when the ask comes back to the OB high, inside the |
//|            killzone 09:00-12:00 or 14:00-17:00 server (London /   |
//|            NY); a setup that is touched outside the killzone or   |
//|            while a position is open is used up                    |
//|  cancelled by an M15 close below the SL, a break the other way,   |
//|            or after InpSmcWait (30) M15 bars                      |
//|  SL        protected low - 0.1 ATR(14, M15) - spread              |
//|  TP        InpSmcTpR (3) x the risk; out after InpSmcHoldH (12) h |
//|  one position at a time, obeys the daily target                   |
//| TEST (research/smc102b.py, smc102c.py, gold, last 2 years):       |
//| 189 trades (1.8 a week), PF 1.67, years 1.64 / 1.72, stress 1.64, |
//| +$558 per 0.01 lot, last 12 months +$289, 9 of 9 quarters up,     |
//| buys 1.25 / sells 2.40, always-buy twin 0.69, random 0.98, max DD |
//| -$92, worst trade -$59, average risk $8.9.  Entry TF M10-M20 hold |
//| (1.17-1.48), fake killzone hours fail (0.85).  On the 28 forex    |
//| pairs the same rule loses (PF 0.81 pooled), so gold only.         |
//| Events go to MQL5\Files\smc_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpSmcOn     = true;
input double InpSmcLot    = 0.01;
input long   InpSmcMagic  = 260325;
input int    InpSmcSwing  = 5;       // fractal swing: bars on each side
input int    InpSmcWait   = 30;      // a setup lives this many M15 bars after the break
input double InpSmcTpR    = 3.0;     // TP in multiples of the risk
input double InpSmcBufAtr = 0.1;     // SL buffer beyond the protected low / high, in ATR(14, M15), plus the spread
input int    InpSmcHoldH  = 12;      // close at market after this many hours

struct SmcSetup { datetime bt; int dir; double e, sl, obh, obl, prot; };
SmcSetup sm_live[];
long     sm_used[];
ulong    sm_known[];
string   sm_sym = "";
datetime sm_bar = 0;
bool     sm_ready = false;

void SmcEvent(string msg)
{
   int h = FileOpen("smc_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("smc event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("SMC EVENT ", msg);
}

bool SmcPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpSmcMagic) { ticket = t; return true; }
   }
   return false;
}

void SmcRemember(ulong t)
{
   for(int q = 0; q < ArraySize(sm_known); q++) if(sm_known[q] == t) return;
   int m = ArraySize(sm_known); ArrayResize(sm_known, m + 1); sm_known[m] = t;
}

long SmcKey(datetime bt, int dir) { return (long)bt * 2 + (dir == 1 ? 1 : 0); }

bool SmcIsUsed(long k)
{
   for(int q = 0; q < ArraySize(sm_used); q++) if(sm_used[q] == k) return true;
   return false;
}

void SmcUse(long k)
{
   if(SmcIsUsed(k)) return;
   int m = ArraySize(sm_used);
   if(m > 200) { ArrayRemove(sm_used, 0, 100); m = ArraySize(sm_used); }
   ArrayResize(sm_used, m + 1); sm_used[m] = k;
}

bool SmcKillzone(datetime t)
{
   MqlDateTime s; TimeToStruct(t, s);
   if(s.day_of_week == 0 || s.day_of_week == 6) return false;
   return (s.hour >= 9 && s.hour < 12) || (s.hour >= 14 && s.hour < 17);
}

string SmcSession(datetime t)
{
   MqlDateTime s; TimeToStruct(t, s);
   return s.hour < 12 ? "London" : "New York";
}

void SmcInit()
{
   sm_ready = true;
   sm_sym = SymResolve("XAUUSD");
   if(sm_sym == "") { SmcEvent("ERROR | SMC: XAUUSD not found at this broker"); return; }
   SymbolSelect(sm_sym, true);
   MqlRates tmp[];
   CopyRates(sm_sym, PERIOD_M15, 0, 2500, tmp);                 // start the history download
   CopyRates(sm_sym, PERIOD_M5, 0, 150, tmp);
   int open = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpSmcMagic) { SmcRemember(t); open++; }
   }
   SmcEvent(StringFormat("SMC ONLINE | %s M15 smart money: BOS (swing %d) then a limit at the order block, filled only in the killzone "
                         "09:00-12:00 / 14:00-17:00 server; SL beyond the protected low / high, TP %.0fR, out after %d h, lot %.2f | "
                         "%d open position(s)", sm_sym, InpSmcSwing, InpSmcTpR, InpSmcHoldH, InpSmcLot, open));
}

void SmcReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, typ = -1; string sym = "";
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN)
      {
         inPx = HistoryDealGetDouble(d, DEAL_PRICE); typ = HistoryDealGetInteger(d, DEAL_TYPE); sym = HistoryDealGetString(d, DEAL_SYMBOL);
      }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0 || sym == "") return;
   string side = typ == DEAL_TYPE_BUY ? "BUY" : "SELL";
   string what = reason == DEAL_REASON_TP ? "SMC TP HIT" : (reason == DEAL_REASON_SL ? "SMC SL HIT" : "SMC CLOSED");
   string why = reason == DEAL_REASON_TP ? StringFormat("take profit %.0fR", InpSmcTpR)
              : (reason == DEAL_REASON_SL ? "stop loss beyond the protected level"
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d hours up", InpSmcHoldH) : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sym, PERIOD_M15, "SMX", lv, lc, lb, 0, 0, 0, 0, false);
   SmcEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, sym, side, PriceStr(sym, inPx),
                         PriceStr(sym, outPx), why, profit) + Img(fn));
}

// median M5 spread (price) of the M15 bar that opens at t; 0 if no M5 bars
double SmcSpread(MqlRates &m5[], int n5, datetime t, double pnt)
{
   double sv[]; int k = 0;
   for(int i = 0; i < n5; i++)
      if(m5[i].time >= t && m5[i].time < t + 900) { ArrayResize(sv, k + 1); sv[k++] = m5[i].spread * pnt; }
   if(k == 0) return 0;
   ArraySort(sv);
   return k % 2 == 1 ? sv[k / 2] : (sv[k / 2 - 1] + sv[k / 2]) / 2;
}

// rebuild the structure from closed M15 bars and keep the setups that are still alive; false = history not ready
bool SmcRebuild()
{
   MqlRates r[];
   int n = CopyRates(sm_sym, PERIOD_M15, 1, 2500, r);           // closed bars, oldest first
   if(n < 1000) return false;
   MqlRates m5[];
   int n5 = CopyRates(sm_sym, PERIOD_M5, 0, 3 * (InpSmcWait + 6), m5);
   double pnt = SymbolInfoDouble(sm_sym, SYMBOL_POINT);
   int sw = InpSmcSwing;
   double atr[]; ArrayResize(atr, n);
   atr[0] = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr[i] = atr[i - 1] + (tr - atr[i - 1]) / 14.0;
   }
   // strict fractal pivots
   bool ph[], pl[]; ArrayResize(ph, n); ArrayResize(pl, n);
   for(int j = 0; j < n; j++)
   {
      ph[j] = false; pl[j] = false;
      if(j < sw || j + sw > n - 1) continue;
      bool hi = true, lo = true;
      for(int q = j - sw; q <= j + sw; q++)
      {
         if(q == j) continue;
         if(r[q].high >= r[j].high) hi = false;
         if(r[q].low <= r[j].low) lo = false;
      }
      ph[j] = hi; pl[j] = lo;
   }
   // online structure: breaks (bar, dir, BOS?, protected extreme)
   int bt[], bd[], bex[]; bool bbos[];
   int nb = 0;
   double sh = 0, slv = 0; int shi = -1, sli = -1; bool shu = true, slu = true; int trend = 0;
   for(int t = 0; t < n; t++)
   {
      int j = t - sw;
      if(j >= 0)
      {
         if(ph[j]) { sh = r[j].high; shi = j; shu = false; }
         if(pl[j]) { slv = r[j].low; sli = j; slu = false; }
      }
      int dir = 0, ex = -1;
      if(!shu && r[t].close > sh)
      {
         dir = 1; ex = shi;
         for(int q = shi; q <= t; q++) if(r[q].low < r[ex].low) ex = q;
         shu = true;
      }
      else if(!slu && r[t].close < slv)
      {
         dir = -1; ex = sli;
         for(int q = sli; q <= t; q++) if(r[q].high > r[ex].high) ex = q;
         slu = true;
      }
      if(dir == 0) continue;
      ArrayResize(bt, nb + 1); ArrayResize(bd, nb + 1); ArrayResize(bex, nb + 1); ArrayResize(bbos, nb + 1);
      bt[nb] = t; bd[nb] = dir; bex[nb] = ex; bbos[nb] = (trend == dir); nb++;
      trend = dir;
   }
   // setups from the recent BOS breaks, walked through the closed bars since
   ArrayResize(sm_live, 0);
   MqlRates f0[];
   bool hasf = CopyRates(sm_sym, PERIOD_M15, 0, 1, f0) == 1;
   for(int b = 0; b < nb; b++)
   {
      int t = bt[b], dir = bd[b], ex = bex[b];
      if(!bbos[b] || t < n - 1 - InpSmcWait) continue;
      int cancel = n + 1000;
      for(int q = b + 1; q < nb; q++) if(bd[q] == -dir) { cancel = bt[q]; break; }
      double legx = dir == 1 ? r[ex].high : r[ex].low;
      for(int q = ex; q <= t; q++) legx = dir == 1 ? MathMax(legx, r[q].high) : MathMin(legx, r[q].low);
      int ob = ex;
      for(int k = ex; k > MathMax(ex - 6, 0); k--)
         if((dir == 1 && r[k].close < r[k].open) || (dir == -1 && r[k].close > r[k].open)) { ob = k; break; }
      double e = dir == 1 ? r[ob].high : r[ob].low;
      double sp = SmcSpread(m5, n5, r[t].time, pnt);
      if(sp <= 0) sp = r[t].spread * pnt;
      double prot = dir == 1 ? r[ex].low : r[ex].high;
      double sl = prot - dir * (InpSmcBufAtr * atr[t] + sp);
      if((e - sl) * dir <= 0 || (legx - e) * dir <= 0) continue;
      bool dead = false;
      for(int z = t + 1; z < n && !dead; z++)
      {
         if(z > t + InpSmcWait || z >= cancel) { dead = true; break; }
         double s5 = SmcSpread(m5, n5, r[z].time, pnt);
         if(s5 <= 0) s5 = r[z].spread * pnt;
         if(dir == 1 && r[z].low + s5 <= e) dead = true;                   // touched: used up (traded or not)
         if(dir == -1 && r[z].high >= e) dead = true;
         if(dir == 1 && r[z].close < sl) dead = true;
         if(dir == -1 && r[z].close > sl) dead = true;
      }
      if(dead || n > t + InpSmcWait || cancel <= n - 1) continue;
      long key = SmcKey(r[t].time, dir);
      if(SmcIsUsed(key)) continue;
      if(hasf)                                                               // touched earlier in the forming bar
      {
         double sf = SymbolInfoInteger(sm_sym, SYMBOL_SPREAD) * pnt;
         if((dir == 1 && f0[0].low + sf <= e) || (dir == -1 && f0[0].high >= e)) { SmcUse(key); continue; }
      }
      int m = ArraySize(sm_live); ArrayResize(sm_live, m + 1);
      sm_live[m].bt = r[t].time; sm_live[m].dir = dir; sm_live[m].e = e; sm_live[m].sl = sl;
      sm_live[m].obh = r[ob].high; sm_live[m].obl = r[ob].low; sm_live[m].prot = prot;
   }
   return true;
}

void SmcOnTimer()
{
   if(!InpSmcOn) return;
   if(!sm_ready) SmcInit();
   if(sm_sym == "") return;
   for(int q = ArraySize(sm_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(sm_known[q])) { SmcReportClosed(sm_known[q]); ArrayRemove(sm_known, q, 1); }
   datetime now = TimeCurrent();
   MqlTick tk;
   if(!SymbolInfoTick(sm_sym, tk) || now - tk.time > 600) return;            // market closed / no quotes
   ulong pt;
   bool inPos = SmcPosition(pt);
   if(inPos)
   {
      SmcRemember(pt);
      PositionSelectByTicket(pt);
      if((long)(now - (datetime)PositionGetInteger(POSITION_TIME)) >= (long)InpSmcHoldH * 3600)
      {
         trade.SetExpertMagicNumber(InpSmcMagic); trade.SetTypeFillingBySymbol(sm_sym);
         if(!trade.PositionClose(pt)) SmcEvent(StringFormat("ERROR | SMC close failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   datetime b0 = iTime(sm_sym, PERIOD_M15, 0);
   if(b0 != 0 && b0 != sm_bar) { if(SmcRebuild()) sm_bar = b0; else return; }
   // watch the live setups every second
   for(int i = ArraySize(sm_live) - 1; i >= 0; i--)
   {
      SmcSetup st = sm_live[i];
      int dir = st.dir; double e = st.e, sl = st.sl;
      long key = SmcKey(st.bt, dir);
      if(SmcIsUsed(key)) { ArrayRemove(sm_live, i, 1); continue; }
      bool touched = dir == 1 ? tk.ask <= e : tk.bid >= e;
      if(!touched) continue;
      SmcUse(key);                                                           // first touch uses the setup up
      ArrayRemove(sm_live, i, 1);
      if(!SmcKillzone(now) || SmcPosition(pt) || DayPaused()) continue;
      double spr = tk.ask - tk.bid, entry = dir == 1 ? tk.ask : tk.bid;
      double risk = (entry - sl) * dir;
      if(risk <= 2 * spr) continue;
      int dg = (int)SymbolInfoInteger(sm_sym, SYMBOL_DIGITS);
      double pnt = SymbolInfoDouble(sm_sym, SYMBOL_POINT);
      double tp = NormalizeDouble(entry + dir * InpSmcTpR * risk, dg);
      double sln = NormalizeDouble(sl, dg);
      double stopLv = SymbolInfoInteger(sm_sym, SYMBOL_TRADE_STOPS_LEVEL) * pnt;
      if((dir == 1 ? tk.bid - sln : sln - tk.ask) <= stopLv) continue;
      double mn = SymbolInfoDouble(sm_sym, SYMBOL_VOLUME_MIN), vs = SymbolInfoDouble(sm_sym, SYMBOL_VOLUME_STEP);
      double lot = NormalizeDouble(MathMax(mn, MathFloor(InpSmcLot / vs + 1e-9) * vs), 2);
      trade.SetExpertMagicNumber(InpSmcMagic); trade.SetTypeFillingBySymbol(sm_sym);
      bool ok = dir == 1 ? trade.Buy(lot, sm_sym, 0, sln, tp, "SMC") : trade.Sell(lot, sm_sym, 0, sln, tp, "SMC");
      if(!ok) SmcEvent(StringFormat("ERROR | SMC order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(!ok) continue;
      double tv = SymbolInfoDouble(sm_sym, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(sm_sym, SYMBOL_TRADE_TICK_SIZE);
      double riskUsd = ts > 0 ? risk / ts * tv * lot : 0;
      string side = dir == 1 ? "BUY" : "SELL";
      double lv[4]; color lc[4]; string lb[4];
      lv[0] = entry; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sln; lc[1] = clrIndianRed; lb[1] = "SL";
      lv[2] = tp; lc[2] = clrSeaGreen; lb[2] = "TP"; lv[3] = dir == 1 ? st.obl : st.obh; lc[3] = clrGoldenrod; lb[3] = "OB far side";
      string fn = Snap(sm_sym, PERIOD_M15, "SME", lv, lc, lb, 0, 0, 0, 0, false);
      SmcEvent(StringFormat("SMC %s %s | M15 BOS %s closed %s, price back to the order block %s inside the %s killzone | %s %.2f lot at %s, "
                            "SL %s (risk $%.2f), TP %s (%.0fR), out after %d h",
                            side, sm_sym, dir == 1 ? "up" : "down", TimeToString(st.bt + 900, TIME_MINUTES), PriceStr(sm_sym, e),
                            SmcSession(now), side, lot, PriceStr(sm_sym, entry), PriceStr(sm_sym, sln), riskUsd, PriceStr(sm_sym, tp),
                            InpSmcTpR, InpSmcHoldH) + Img(fn));
      if(SmcPosition(pt)) SmcRemember(pt);
      break;                                                                 // one position at a time
   }
}
//+------------------------------------------------------------------+
