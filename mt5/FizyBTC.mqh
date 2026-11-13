//+------------------------------------------------------------------+
//| FizyBTC.mqh - BTCUSD 24/7, demo only, included by FizyLB.mq5.     |
//| v2.25 (13 Nov 2026), the owner's order ("aku nak 24/7 tanpa henti |
//| untuk btc. kau buatkan mana yang sesuai") after rounds 103-103c.  |
//| Two legs, each with its own magic and one position at a time:     |
//|  FOL (260326) M5 BIG-CANDLE FOLLOW, every hour, every day: when a  |
//|      closed M5 bar's body is >= 2.5 ATR(14, M5) and ATR >= 8 x its |
//|      spread, enter its way at the next bar's open; SL 0.3 ATR       |
//|      beyond the bar's far end, no TP, out after 60 min; no entries  |
//|      23:45-01:30 server.                                           |
//|  SMC (260327) the gold SMC rules on M20, swing 3, BOS only, entry   |
//|      at the OTE 0.705 of the impulse, first touch only, filled in   |
//|      the killzone 09-12 / 14-17 server on WEEKDAYS (its weekend     |
//|      fills lost: 56 trades PF 0.88), SL protected extreme + 0.1 ATR |
//|      + spread, TP 3R, out after 16 h.                              |
//| TEST (research/btc103c.py, last 2 years, 0.01 lot each, spread and |
//| swap): FOL 351 trades PF 1.29, years 1.28 / 1.29, +$227, DD -$77    |
//| (weekdays 1.20, weekend 2.14); SMC weekdays 201 trades PF 1.51,    |
//| years 1.37 / 1.71, +$197, DD -$39, worst trade -$8. Both 24/7:     |
//| 608 trades (5.8 a week) PF 1.33, +$415, last 12 months +$235, max  |
//| DD -$67, worst day -$21, 17 of 25 months positive.                 |
//| BTC swap is -$0.85 (buy) / -$0.56 (sell) per 0.01 lot a night, so  |
//| neither leg holds long. Events in MQL5\Files\btc_events.txt.       |
//+------------------------------------------------------------------+
input bool   InpBflOn      = true;
input double InpBflLot     = 0.01;
input long   InpBflMagic   = 260326;
input double InpBflK       = 2.5;     // body >= this x ATR(14, M5)
input double InpBflGate    = 8.0;     // ATR(14, M5) >= this x the bar's spread
input double InpBflSlAtr   = 0.3;     // SL this many ATR beyond the big bar's far end
input int    InpBflHoldMin = 60;      // close at market after this many minutes
input bool   InpBsmOn      = true;
input double InpBsmLot     = 0.01;
input long   InpBsmMagic   = 260327;
input int    InpBsmSwing   = 3;       // fractal swing: bars on each side (M20)
input int    InpBsmWait    = 30;      // a setup lives this many M20 bars after the break
input double InpBsmOte     = 0.705;   // entry at this retracement of the impulse
input double InpBsmTpR     = 3.0;
input double InpBsmBufAtr  = 0.1;
input int    InpBsmHoldH   = 16;      // 48 M20 bars

int bs_open = 0;
struct BsmSetup { datetime bt; int dir; double e, sl, obh, obl, prot; };
BsmSetup bs_live[];
long     bs_used[];
ulong    bs_known[];
string   bs_sym = "";
datetime bs_bar = 0;
bool     bs_ready = false;

void BsmEvent(string msg)
{
   int h = FileOpen("btc_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("btc event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("BTC EVENT ", msg);
}

bool BsmPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpBsmMagic) { ticket = t; return true; }
   }
   return false;
}

void BsmRemember(ulong t)
{
   for(int q = 0; q < ArraySize(bs_known); q++) if(bs_known[q] == t) return;
   int m = ArraySize(bs_known); ArrayResize(bs_known, m + 1); bs_known[m] = t;
}

long BsmKey(datetime bt, int dir) { return (long)bt * 2 + (dir == 1 ? 1 : 0); }

bool BsmIsUsed(long k)
{
   for(int q = 0; q < ArraySize(bs_used); q++) if(bs_used[q] == k) return true;
   return false;
}

void BsmUse(long k)
{
   if(BsmIsUsed(k)) return;
   int m = ArraySize(bs_used);
   if(m > 200) { ArrayRemove(bs_used, 0, 100); m = ArraySize(bs_used); }
   ArrayResize(bs_used, m + 1); bs_used[m] = k;
}

bool BsmKillzone(datetime t)
{
   MqlDateTime s; TimeToStruct(t, s);
   if(s.day_of_week == 0 || s.day_of_week == 6) return false;
   return (s.hour >= 9 && s.hour < 12) || (s.hour >= 14 && s.hour < 17);
}

string BsmSession(datetime t)
{
   MqlDateTime s; TimeToStruct(t, s);
   return s.hour < 12 ? "London" : "New York";
}

void BsmInit()
{
   bs_ready = true;
   bs_sym = SymResolve("BTCUSD");
   if(bs_sym == "") { BsmEvent("ERROR | BTC SMC: BTCUSD not found at this broker"); return; }
   SymbolSelect(bs_sym, true);
   MqlRates tmp[];
   CopyRates(bs_sym, PERIOD_M20, 0, 2500, tmp);                 // start the history download
   CopyRates(bs_sym, PERIOD_M5, 0, 150, tmp);
   int open = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpBsmMagic) { BsmRemember(t); open++; }
   }
   bs_open = open;
}

void BsmReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_TP ? "BTC SMC TP HIT" : (reason == DEAL_REASON_SL ? "BTC SMC SL HIT" : "BTC SMC CLOSED");
   string why = reason == DEAL_REASON_TP ? StringFormat("take profit %.0fR", InpBsmTpR)
              : (reason == DEAL_REASON_SL ? "stop loss beyond the protected level"
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d hours up", InpBsmHoldH) : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sym, PERIOD_M20, "BSX", lv, lc, lb, 0, 0, 0, 0, false);
   BsmEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, sym, side, PriceStr(sym, inPx),
                         PriceStr(sym, outPx), why, profit) + Img(fn));
}

// median M5 spread (price) of the M20 bar that opens at t; 0 if no M5 bars
double BsmSpread(MqlRates &m5[], int n5, datetime t, double pnt)
{
   double sv[]; int k = 0;
   for(int i = 0; i < n5; i++)
      if(m5[i].time >= t && m5[i].time < t + 1200) { ArrayResize(sv, k + 1); sv[k++] = m5[i].spread * pnt; }
   if(k == 0) return 0;
   ArraySort(sv);
   return k % 2 == 1 ? sv[k / 2] : (sv[k / 2 - 1] + sv[k / 2]) / 2;
}

// rebuild the structure from closed M20 bars and keep the setups that are still alive; false = history not ready
bool BsmRebuild()
{
   MqlRates r[];
   int n = CopyRates(bs_sym, PERIOD_M20, 1, 2500, r);           // closed bars, oldest first
   if(n < 1000) return false;
   MqlRates m5[];
   int n5 = CopyRates(bs_sym, PERIOD_M5, 0, 3 * (InpBsmWait + 6), m5);
   double pnt = SymbolInfoDouble(bs_sym, SYMBOL_POINT);
   int sw = InpBsmSwing;
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
   ArrayResize(bs_live, 0);
   MqlRates f0[];
   bool hasf = CopyRates(bs_sym, PERIOD_M20, 0, 1, f0) == 1;
   for(int b = 0; b < nb; b++)
   {
      int t = bt[b], dir = bd[b], ex = bex[b];
      if(!bbos[b] || t < n - 1 - InpBsmWait) continue;
      int cancel = n + 1000;
      for(int q = b + 1; q < nb; q++) if(bd[q] == -dir) { cancel = bt[q]; break; }
      double legx = dir == 1 ? r[ex].high : r[ex].low;
      for(int q = ex; q <= t; q++) legx = dir == 1 ? MathMax(legx, r[q].high) : MathMin(legx, r[q].low);
      int ob = ex;
      for(int k = ex; k > MathMax(ex - 6, 0); k--)
         if((dir == 1 && r[k].close < r[k].open) || (dir == -1 && r[k].close > r[k].open)) { ob = k; break; }
      double prot0 = dir == 1 ? r[ex].low : r[ex].high;
      double e = legx - dir * InpBsmOte * MathAbs(legx - prot0);           // OTE 0.705 of the impulse (round 103b: OB top 1.00 on BTC)
      double sp = BsmSpread(m5, n5, r[t].time, pnt);
      if(sp <= 0) sp = r[t].spread * pnt;
      double prot = dir == 1 ? r[ex].low : r[ex].high;
      double sl = prot - dir * (InpBsmBufAtr * atr[t] + sp);
      if((e - sl) * dir <= 0 || (legx - e) * dir <= 0) continue;
      bool dead = false;
      for(int z = t + 1; z < n && !dead; z++)
      {
         if(z > t + InpBsmWait || z >= cancel) { dead = true; break; }
         double s5 = BsmSpread(m5, n5, r[z].time, pnt);
         if(s5 <= 0) s5 = r[z].spread * pnt;
         if(dir == 1 && r[z].low + s5 <= e) dead = true;                   // touched: used up (traded or not)
         if(dir == -1 && r[z].high >= e) dead = true;
         if(dir == 1 && r[z].close < sl) dead = true;
         if(dir == -1 && r[z].close > sl) dead = true;
      }
      if(dead || n > t + InpBsmWait || cancel <= n - 1) continue;
      long key = BsmKey(r[t].time, dir);
      if(BsmIsUsed(key)) continue;
      if(hasf)                                                               // touched earlier in the forming bar
      {
         double sf = SymbolInfoInteger(bs_sym, SYMBOL_SPREAD) * pnt;
         if((dir == 1 && f0[0].low + sf <= e) || (dir == -1 && f0[0].high >= e)) { BsmUse(key); continue; }
      }
      int m = ArraySize(bs_live); ArrayResize(bs_live, m + 1);
      bs_live[m].bt = r[t].time; bs_live[m].dir = dir; bs_live[m].e = e; bs_live[m].sl = sl;
      bs_live[m].obh = r[ob].high; bs_live[m].obl = r[ob].low; bs_live[m].prot = prot;
   }
   return true;
}

void BsmOnTimer()
{
   for(int q = ArraySize(bs_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(bs_known[q])) { BsmReportClosed(bs_known[q]); ArrayRemove(bs_known, q, 1); }
   datetime now = TimeCurrent();
   MqlTick tk;
   if(!SymbolInfoTick(bs_sym, tk) || now - tk.time > 600) return;            // market closed / no quotes
   ulong pt;
   bool inPos = BsmPosition(pt);
   if(inPos)
   {
      BsmRemember(pt);
      PositionSelectByTicket(pt);
      if((long)(now - (datetime)PositionGetInteger(POSITION_TIME)) >= (long)InpBsmHoldH * 3600)
      {
         trade.SetExpertMagicNumber(InpBsmMagic); trade.SetTypeFillingBySymbol(bs_sym);
         if(!trade.PositionClose(pt)) BsmEvent(StringFormat("ERROR | BTC SMC close failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   datetime b0 = iTime(bs_sym, PERIOD_M20, 0);
   if(b0 != 0 && b0 != bs_bar) { if(BsmRebuild()) bs_bar = b0; else return; }
   // watch the live setups every second
   for(int i = ArraySize(bs_live) - 1; i >= 0; i--)
   {
      BsmSetup st = bs_live[i];
      int dir = st.dir; double e = st.e, sl = st.sl;
      long key = BsmKey(st.bt, dir);
      if(BsmIsUsed(key)) { ArrayRemove(bs_live, i, 1); continue; }
      bool touched = dir == 1 ? tk.ask <= e : tk.bid >= e;
      if(!touched) continue;
      BsmUse(key);                                                           // first touch uses the setup up
      ArrayRemove(bs_live, i, 1);
      if(!BsmKillzone(now) || BsmPosition(pt) || DayPaused()) continue;
      double spr = tk.ask - tk.bid, entry = dir == 1 ? tk.ask : tk.bid;
      double risk = (entry - sl) * dir;
      if(risk <= 2 * spr) continue;
      int dg = (int)SymbolInfoInteger(bs_sym, SYMBOL_DIGITS);
      double pnt = SymbolInfoDouble(bs_sym, SYMBOL_POINT);
      double tp = NormalizeDouble(entry + dir * InpBsmTpR * risk, dg);
      double sln = NormalizeDouble(sl, dg);
      double stopLv = SymbolInfoInteger(bs_sym, SYMBOL_TRADE_STOPS_LEVEL) * pnt;
      if((dir == 1 ? tk.bid - sln : sln - tk.ask) <= stopLv) continue;
      double mn = SymbolInfoDouble(bs_sym, SYMBOL_VOLUME_MIN), vs = SymbolInfoDouble(bs_sym, SYMBOL_VOLUME_STEP);
      double lot = NormalizeDouble(MathMax(mn, MathFloor(InpBsmLot / vs + 1e-9) * vs), 2);
      trade.SetExpertMagicNumber(InpBsmMagic); trade.SetTypeFillingBySymbol(bs_sym);
      bool ok = dir == 1 ? trade.Buy(lot, bs_sym, 0, sln, tp, "BTC SMC") : trade.Sell(lot, bs_sym, 0, sln, tp, "BTC SMC");
      if(!ok) BsmEvent(StringFormat("ERROR | BTC SMC order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      if(!ok) continue;
      double tv = SymbolInfoDouble(bs_sym, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(bs_sym, SYMBOL_TRADE_TICK_SIZE);
      double riskUsd = ts > 0 ? risk / ts * tv * lot : 0;
      string side = dir == 1 ? "BUY" : "SELL";
      double lv[4]; color lc[4]; string lb[4];
      lv[0] = entry; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sln; lc[1] = clrIndianRed; lb[1] = "SL";
      lv[2] = tp; lc[2] = clrSeaGreen; lb[2] = "TP"; lv[3] = st.prot; lc[3] = clrGoldenrod; lb[3] = "protected";
      string fn = Snap(bs_sym, PERIOD_M20, "BSE", lv, lc, lb, 0, 0, 0, 0, false);
      BsmEvent(StringFormat("BTC SMC %s %s | M20 BOS %s closed %s, price back to the OTE 0.705 at %s inside the %s killzone | %s %.2f lot at %s, "
                            "SL %s (risk $%.2f), TP %s (%.0fR), out after %d h",
                            side, bs_sym, dir == 1 ? "up" : "down", TimeToString(st.bt + 1200, TIME_MINUTES), PriceStr(bs_sym, e),
                            BsmSession(now), side, lot, PriceStr(bs_sym, entry), PriceStr(bs_sym, sln), riskUsd, PriceStr(bs_sym, tp),
                            InpBsmTpR, InpBsmHoldH) + Img(fn));
      if(BsmPosition(pt)) BsmRemember(pt);
      break;                                                                 // one position at a time
   }
}

//==================== FOL leg ====================
datetime bf_bar = 0;
ulong    bf_known[];

bool BflPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpBflMagic) { ticket = t; return true; }
   }
   return false;
}

void BflRemember(ulong t)
{
   for(int q = 0; q < ArraySize(bf_known); q++) if(bf_known[q] == t) return;
   int m = ArraySize(bf_known); ArrayResize(bf_known, m + 1); bf_known[m] = t;
}

void BflReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "BTC FOL SL HIT" : "BTC FOL CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss beyond the big candle"
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d minutes up", InpBflHoldMin) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sym, PERIOD_M5, "BFX", lv, lc, lb, 0, 0, 0, 0, false);
   BsmEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, sym, side, PriceStr(sym, inPx),
                         PriceStr(sym, outPx), why, profit) + Img(fn));
}

void BflOnTimer(datetime now, MqlTick &tk)
{
   string sym = bs_sym;
   for(int q = ArraySize(bf_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(bf_known[q])) { BflReportClosed(bf_known[q]); ArrayRemove(bf_known, q, 1); }
   ulong pt;
   bool inPos = BflPosition(pt);
   if(inPos)
   {
      BflRemember(pt);
      PositionSelectByTicket(pt);
      if((long)(now - (datetime)PositionGetInteger(POSITION_TIME)) >= (long)InpBflHoldMin * 60)
      {
         trade.SetExpertMagicNumber(InpBflMagic); trade.SetTypeFillingBySymbol(sym);
         if(!trade.PositionClose(pt)) BsmEvent(StringFormat("ERROR | BTC FOL close failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   datetime b0 = iTime(sym, PERIOD_M5, 0);
   if(b0 == 0 || b0 == bf_bar) return;                                       // once per new M5 bar
   if(now - b0 > 60) { bf_bar = b0; return; }                                // only right at the bar's open
   MqlRates r[];
   int n = CopyRates(sym, PERIOD_M5, 1, 400, r);
   if(n < 100) return;                                                       // history loading: try again next second
   int j = n - 1;
   bf_bar = b0;
   if(r[j].time + 300 != b0) return;                                         // a gap: not the bar that just closed
   double atr = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   double pnt = SymbolInfoDouble(sym, SYMBOL_POINT);
   double sp = r[j].spread * pnt;
   if(sp <= 0) sp = tk.ask - tk.bid;
   double body = r[j].close - r[j].open;
   if(MathAbs(body) < InpBflK * atr || atr < InpBflGate * sp) return;
   MqlDateTime st; TimeToStruct(b0, st);
   int hm = st.hour * 60 + st.min;
   if(hm < 90 || hm >= 1425) return;                                         // rollover: the bid is distorted
   if(inPos || DayPaused()) return;
   int dir = body > 0 ? 1 : -1;
   double entry = dir == 1 ? tk.ask : tk.bid;
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double sl = NormalizeDouble((dir == 1 ? r[j].low : r[j].high) - dir * InpBflSlAtr * atr, dg);
   double risk = (entry - sl) * dir, spr = tk.ask - tk.bid;
   if(risk <= spr) return;
   double stopLv = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * pnt;
   if((dir == 1 ? tk.bid - sl : sl - tk.ask) <= stopLv) return;
   double mn = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), vs = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpBflLot / vs + 1e-9) * vs), 2);
   trade.SetExpertMagicNumber(InpBflMagic); trade.SetTypeFillingBySymbol(sym);
   bool ok = dir == 1 ? trade.Buy(lot, sym, 0, sl, 0, "BTC FOL") : trade.Sell(lot, sym, 0, sl, 0, "BTC FOL");
   if(!ok) BsmEvent(StringFormat("ERROR | BTC FOL order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double riskUsd = ts > 0 ? risk / ts * tv * lot : 0;
   string side = dir == 1 ? "BUY" : "SELL";
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = entry; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   string fn = Snap(sym, PERIOD_M5, "BFE", lv, lc, lb, 0, 0, 0, 0, false);
   BsmEvent(StringFormat("BTC FOL %s %s | M5 candle %s of %s = %.1f ATR (spread %.2f ATR) | %s %.2f lot at %s, SL %s (risk $%.2f), "
                         "no TP, out after %d min", side, sym, dir == 1 ? "up" : "down", PriceStr(sym, MathAbs(body)), MathAbs(body) / atr,
                         sp / atr, side, lot, PriceStr(sym, entry), PriceStr(sym, sl), riskUsd, InpBflHoldMin) + Img(fn));
   if(BflPosition(pt)) BflRemember(pt);
}

//==================== both legs ====================
bool bt_announced = false;

void BtcOnTimer()
{
   if(!InpBflOn && !InpBsmOn) return;
   if(!bs_ready) BsmInit();
   if(bs_sym == "") return;
   if(!bt_announced)
   {
      bt_announced = true;
      int fo = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong t = PositionGetTicket(i);
         if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpBflMagic) { BflRemember(t); fo++; }
      }
      BsmEvent(StringFormat("BTC ONLINE | %s 24/7: FOL %s (M5 candle >= %.1f ATR with ATR >= %.0fx spread, follow it, SL %.1f ATR beyond, "
                            "out after %d min, any hour, any day); SMC %s (M20 BOS, limit at OTE %.3f, killzone 09-12 / 14-17 server on "
                            "weekdays, TP %.0fR, out after %d h); lot %.2f | %d open position(s)",
                            bs_sym, InpBflOn ? "on" : "off", InpBflK, InpBflGate, InpBflSlAtr, InpBflHoldMin, InpBsmOn ? "on" : "off",
                            InpBsmOte, InpBsmTpR, InpBsmHoldH, InpBflLot, fo + bs_open));
   }
   if(InpBsmOn) BsmOnTimer();
   if(InpBflOn)
   {
      MqlTick tk;
      datetime now = TimeCurrent();
      if(SymbolInfoTick(bs_sym, tk) && now - tk.time <= 600) BflOnTimer(now, tk);
   }
}
//+------------------------------------------------------------------+
