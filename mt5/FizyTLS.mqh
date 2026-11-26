//+------------------------------------------------------------------+
//| FizyTLS.mqh - gold M15 TRENDLINE + S/R break with a MARTINGALE   |
//| basket, demo only, included by FizyLB.mq5.  v2.69 (26 Nov 2026), |
//| the owner's order after rounds 170b / 171: "ni akaun sen bro,    |
//| proceed terus. lot 0.01. buat martiangle. layer unlimited".      |
//|                                                                  |
//| SIGNAL on closed M15 bars (BUY shown, SELL is the mirror), the    |
//| round 170b rule:                                                  |
//|  swings  online fractals n 10 (a swing high at bar i is known     |
//|          once bar i+10 has closed)                                |
//|  line    falling line through the 2 latest swing highs            |
//|  break   an M15 close above the line (previous close not)         |
//|  S/R     resistance = the nearest unbroken swing high above that  |
//|          close (last 50 swings); wait up to 120 M15 bars for a    |
//|          close above it, cancelled by a close back below the line |
//|          (no resistance at all = signal at once)                  |
//|  hours   signal bar 01:30-23:45 server                            |
//| BASKET: market BUY 0.01 at the next bar; every 1.5 ATR(14, M15)   |
//| (ATR of the signal bar, kept in the comment) against the LAST     |
//| entry adds the next lot 0.02, 0.03 ... UNLIMITED, NO SL; the TP of |
//| every position = the price where the whole basket nets 3 x the    |
//| first layer's 1.5-ATR risk (account money, swap included), the EA |
//| also closes the basket there; one basket at a time, new signals   |
//| are ignored while it is open; new baskets obey DayPaused().       |
//| TEST: round 170b (real ticks, fixed SL 1.5 ATR, TP 3R, 4 h, one   |
//| trade): n 10 last 3 months 55 trades +$198, DD -$65 / previous 48 |
//| +$119. The MARTINGALE version is NOT tested; with no SL a trend   |
//| against the basket is closed only by the broker's stop-out.       |
//| Events go to MQL5\Files\tls_events.txt (prefix TLSR).             |
//+------------------------------------------------------------------+
input bool   InpTlsOn     = true;
input string InpTlsSymbol = "XAUUSD";
input long   InpTlsMagic  = 260342;
input int    InpTlsSwing  = 10;       // fractal swing size
input int    InpTlsWait   = 120;      // M15 bars to wait for the S/R break after the line break
input double InpTlsStepK  = 1.5;      // layer step, x ATR(14, M15) of the signal bar
input double InpTlsTpR    = 3.0;      // basket target = this x the first layer's step risk
input int    InpTlsBars   = 1500;     // closed M15 bars replayed

string   tl_sym = "";
bool     tl_ready = false;
datetime tl_bar = 0;
ulong    tl_known[];
int      tl_dir = 0;
double   tl_atr = 0;                  // ATR of the basket's signal bar
datetime tl_tpset = 0;

void TlsEvent(string msg)
{
   int h = FileOpen("tls_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("tls event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("TLS EVENT ", msg);
}

bool TlsKnown(ulong t) { for(int i = 0; i < ArraySize(tl_known); i++) if(tl_known[i] == t) return true; return false; }
void TlsRemember(ulong t) { if(TlsKnown(t)) return; int m = ArraySize(tl_known); ArrayResize(tl_known, m + 1); tl_known[m] = t; }

double TlsLot(int k)
{
   double mn = SymbolInfoDouble(tl_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(tl_sym, SYMBOL_VOLUME_STEP);
   double mx = SymbolInfoDouble(tl_sym, SYMBOL_VOLUME_MAX);
   double v = MathMax(mn, MathFloor((k + 1) * 0.01 / sv + 1e-9) * sv);
   if(mx > 0) v = MathMin(v, mx);
   return NormalizeDouble(v, 2);
}

// the open basket: tickets, direction, last entry, totals; the ATR from the first position's comment "TLS <atr>"
int TlsBasket(ulong &tk[], int &dir, double &last, double &vol, double &pnl, double &atr)
{
   ArrayResize(tk, 0); dir = 0; last = 0; vol = 0; pnl = 0; atr = 0;
   datetime lt = 0, ft = 0; ulong lticket = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpTlsMagic || PositionGetString(POSITION_SYMBOL) != tl_sym) continue;
      int m = ArraySize(tk); ArrayResize(tk, m + 1); tk[m] = t;
      dir = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      vol += PositionGetDouble(POSITION_VOLUME);
      pnl += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      datetime pt = (datetime)PositionGetInteger(POSITION_TIME);
      if(pt > lt || (pt == lt && t > lticket)) { lt = pt; lticket = t; last = PositionGetDouble(POSITION_PRICE_OPEN); }
      string c = PositionGetString(POSITION_COMMENT);
      if(StringFind(c, "TLS ") == 0 && (ft == 0 || pt < ft)) { ft = pt; atr = StringToDouble(StringSubstr(c, 4)); }
   }
   return ArraySize(tk);
}

double TlsMoneyPerUsd(double lot)
{
   double ts = SymbolInfoDouble(tl_sym, SYMBOL_TRADE_TICK_SIZE), tv = SymbolInfoDouble(tl_sym, SYMBOL_TRADE_TICK_VALUE);
   return ts > 0 ? lot * tv / ts : 0;
}

double TlsTarget(double atr) { return InpTlsTpR * InpTlsStepK * atr * TlsMoneyPerUsd(TlsLot(0)); }

// the price where the whole basket nets +target, swap included
double TlsTpPrice(ulong &tk[], int dir, double target)
{
   double sv = 0, sve = 0, sw = 0;
   for(int i = 0; i < ArraySize(tk); i++)
   {
      if(!PositionSelectByTicket(tk[i])) continue;
      double v = TlsMoneyPerUsd(PositionGetDouble(POSITION_VOLUME));
      sv += v; sve += v * PositionGetDouble(POSITION_PRICE_OPEN); sw += PositionGetDouble(POSITION_SWAP);
   }
   if(sv <= 0) return 0;
   double need = target - sw;
   return dir == 1 ? (need + sve) / sv : (sve - need) / sv;
}

void TlsSetTp(ulong &tk[], int dir, double tp)
{
   int dg = (int)SymbolInfoInteger(tl_sym, SYMBOL_DIGITS);
   tp = NormalizeDouble(tp, dg);
   trade.SetExpertMagicNumber(InpTlsMagic);
   for(int i = 0; i < ArraySize(tk); i++)
   {
      if(!PositionSelectByTicket(tk[i])) continue;
      if(MathAbs(PositionGetDouble(POSITION_TP) - tp) < SymbolInfoDouble(tl_sym, SYMBOL_POINT) * 2) continue;
      trade.PositionModify(tk[i], 0, tp);
   }
   trade.SetExpertMagicNumber(InpMagic);
}

bool TlsCloseAll(ulong &tk[], string why)
{
   bool ok = true;
   trade.SetExpertMagicNumber(InpTlsMagic); trade.SetTypeFillingBySymbol(tl_sym);
   for(int i = 0; i < ArraySize(tk); i++)
      if(!trade.PositionClose(tk[i]))
      {
         ok = false;
         TlsEvent(StringFormat("ERROR | TLSR close %s (%s) failed: %d %s", tl_sym, why, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
      }
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   return ok;
}

void TlsReportClosed()
{
   double profit = 0, vol = 0; int so = 0, n = ArraySize(tl_known);
   for(int q = 0; q < n; q++)
   {
      if(!HistorySelectByPosition(tl_known[q])) continue;
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong d = HistoryDealGetTicket(i);
         if(d == 0) continue;
         profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) vol += HistoryDealGetDouble(d, DEAL_VOLUME);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT && HistoryDealGetInteger(d, DEAL_REASON) == DEAL_REASON_SO) so++;
      }
   }
   double lv[1]; color lc[1]; string lb[1];
   lv[0] = SymbolInfoDouble(tl_sym, SYMBOL_BID); lc[0] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[0] = "close";
   string fn = Snap(tl_sym, PERIOD_M15, "TLS", lv, lc, lb, 0, 0, 0, 0, false);
   if(so > 0)
      TlsEvent(StringFormat("TLSR STOP OUT %s | the broker closed %d of %d position(s) on a margin stop-out, basket %.2f lot, loss %.2f",
                            tl_sym, so, n, vol, profit) + Img(fn));
   else
      TlsEvent(StringFormat("TLSR BASKET CLOSED %s | %s basket of %d position(s), %.2f lot, closed, profit %.2f",
                            tl_sym, tl_dir == 1 ? "BUY" : "SELL", n, vol, profit) + Img(fn));
}

void TlsInit()
{
   tl_ready = true;
   tl_sym = SymResolve(InpTlsSymbol);
   if(tl_sym == "") { TlsEvent("ERROR | TLSR: symbol " + InpTlsSymbol + " not found"); return; }
   SymbolSelect(tl_sym, true);
   MqlRates tmp[]; CopyRates(tl_sym, PERIOD_M15, 0, InpTlsBars + 2, tmp);   // start the history download
   ulong tk[]; int dir; double last, vol, pnl, atr;
   int n = TlsBasket(tk, dir, last, vol, pnl, atr);
   for(int i = 0; i < n; i++) TlsRemember(tk[i]);
   tl_dir = dir; tl_atr = atr;
   TlsEvent(StringFormat("TLSR ONLINE | %s M15 trendline + S/R break (swing %d, wait %d bars) opens a basket at 0.01; every %.1f ATR(M15) "
                         "against the last entry adds the next lot (0.01, 0.02, 0.03 ... unlimited), NO stop loss; TP of all positions = the "
                         "whole basket +%.0fx the first layer's risk | open: %d position(s), %.2f lot, floating %.2f",
                         tl_sym, InpTlsSwing, InpTlsWait, InpTlsStepK, InpTlsTpR, n, vol, pnl));
}

double TlsLine(double &v[], int i1, int i2, int x) { return v[i2] + (v[i2] - v[i1]) / (i2 - i1) * (x - i2); }

// replays the closed M15 bars; returns +1 / -1 if the LAST closed bar gives a signal, 0 otherwise; atr of that bar
int TlsSignal(double &atrOut)
{
   MqlRates r[];
   int n = CopyRates(tl_sym, PERIOD_M15, 1, InpTlsBars, r);
   int sw = InpTlsSwing;
   if(n < 4 * sw + 60) return 0;
   double h[], l[], c[], atr[];
   ArrayResize(h, n); ArrayResize(l, n); ArrayResize(c, n); ArrayResize(atr, n);
   for(int i = 0; i < n; i++) { h[i] = r[i].high; l[i] = r[i].low; c[i] = r[i].close; }
   atr[0] = h[0] - l[0];
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(h[i] - l[i], MathMax(MathAbs(h[i] - c[i - 1]), MathAbs(l[i] - c[i - 1])));
      atr[i] = atr[i - 1] + (tr - atr[i - 1]) / 14.0;
   }
   int sh[], sl[]; int nh = 0, nl = 0;
   int uh = -1, ul = -1;
   // pending S/R waits: break bar, dir, i1, i2, level
   int pj[], pd[], p1[], p2[]; double pl[]; int np = 0;
   int last = n - 1, res = 0;
   for(int j = 2 * sw + 1; j < n; j++)
   {
      int i = j - sw;
      double mx = h[i - sw], mn = l[i - sw], mxl = h[i - sw], mnl = l[i - sw];
      for(int q = i - sw; q <= i + sw; q++) { mx = MathMax(mx, h[q]); mn = MathMin(mn, l[q]); }
      for(int q = i - sw; q < i; q++) { mxl = MathMax(mxl, h[q]); mnl = MathMin(mnl, l[q]); }
      if(h[i] == mx && h[i] > mxl) { ArrayResize(sh, nh + 1); sh[nh++] = i; }
      if(l[i] == mn && l[i] < mnl) { ArrayResize(sl, nl + 1); sl[nl++] = i; }
      MqlDateTime t; TimeToStruct(r[j].time, t);
      int mins = t.hour * 60 + t.min;
      bool ok = mins >= 90 && mins < 1425;
      int sig = 0;
      if(nh >= 2)
      {
         int i1 = sh[nh - 2], i2 = sh[nh - 1];
         if(h[i2] < h[i1] && uh != i2 && j - 1 > i2 && c[j] > TlsLine(h, i1, i2, j) && c[j - 1] <= TlsLine(h, i1, i2, j - 1))
         {
            uh = i2;
            double lev = 0; bool has = false;
            for(int k = MathMax(0, nh - 50); k < nh; k++)
            {
               int s = sh[k];
               if(h[s] <= c[j]) continue;
               bool unb = true;
               for(int q = s + 1; q <= j; q++) if(h[q] >= h[s]) { unb = false; break; }
               if(unb && (!has || h[s] < lev)) { lev = h[s]; has = true; }
            }
            if(!has) { if(ok) sig = 1; }
            else { ArrayResize(pj, np + 1); ArrayResize(pd, np + 1); ArrayResize(p1, np + 1); ArrayResize(p2, np + 1); ArrayResize(pl, np + 1);
                   pj[np] = j; pd[np] = 1; p1[np] = i1; p2[np] = i2; pl[np] = lev; np++; }
         }
      }
      if(nl >= 2)
      {
         int i1 = sl[nl - 2], i2 = sl[nl - 1];
         if(l[i2] > l[i1] && ul != i2 && j - 1 > i2 && c[j] < TlsLine(l, i1, i2, j) && c[j - 1] >= TlsLine(l, i1, i2, j - 1))
         {
            ul = i2;
            double lev = 0; bool has = false;
            for(int k = MathMax(0, nl - 50); k < nl; k++)
            {
               int s = sl[k];
               if(l[s] >= c[j]) continue;
               bool unb = true;
               for(int q = s + 1; q <= j; q++) if(l[q] <= l[s]) { unb = false; break; }
               if(unb && (!has || l[s] > lev)) { lev = l[s]; has = true; }
            }
            if(!has) { if(ok && sig == 0) sig = -1; }
            else { ArrayResize(pj, np + 1); ArrayResize(pd, np + 1); ArrayResize(p1, np + 1); ArrayResize(p2, np + 1); ArrayResize(pl, np + 1);
                   pj[np] = j; pd[np] = -1; p1[np] = i1; p2[np] = i2; pl[np] = lev; np++; }
         }
      }
      int keep = 0;
      for(int q = 0; q < np; q++)
      {
         bool stay = true;
         if(j > pj[q])
         {
            if(j - pj[q] > InpTlsWait) stay = false;
            else
            {
               double L0 = pd[q] == 1 ? TlsLine(h, p1[q], p2[q], j) : TlsLine(l, p1[q], p2[q], j);
               if((pd[q] == 1 && c[j] < L0) || (pd[q] == -1 && c[j] > L0)) stay = false;
               else if((pd[q] == 1 && c[j] > pl[q]) || (pd[q] == -1 && c[j] < pl[q])) { if(ok && sig == 0) sig = pd[q]; stay = false; }
            }
         }
         if(stay) { pj[keep] = pj[q]; pd[keep] = pd[q]; p1[keep] = p1[q]; p2[keep] = p2[q]; pl[keep] = pl[q]; keep++; }
      }
      np = keep;
      if(j == last) res = sig;
   }
   atrOut = atr[last];
   return res;
}

void TlsOnTimer()
{
   if(!InpTlsOn) return;
   if(!tl_ready) TlsInit();
   if(tl_sym == "") return;
   MqlTick tk;
   if(!SymbolInfoTick(tl_sym, tk) || tk.bid <= 0) return;
   datetime now = TimeCurrent();
   ulong bk[]; int dir; double last, vol, pnl, atr;
   int n = TlsBasket(bk, dir, last, vol, pnl, atr);
   for(int i = 0; i < n; i++) TlsRemember(bk[i]);
   if(n == 0 && ArraySize(tl_known) > 0) { TlsReportClosed(); ArrayResize(tl_known, 0); tl_dir = 0; tl_atr = 0; }
   if(n > 0)
   {
      tl_dir = dir;
      if(atr <= 0) atr = tl_atr;
      if(atr <= 0) { double tmp; TlsSignal(tmp); atr = tmp; }
      tl_atr = atr;
      double target = TlsTarget(atr);
      if(pnl >= target && target > 0) { TlsCloseAll(bk, "basket target"); return; }
      double step = InpTlsStepK * atr;
      double px = dir == 1 ? tk.ask : tk.bid;
      if(step > 0 && (last - px) * dir >= step)
      {
         double lot = TlsLot(n);
         trade.SetExpertMagicNumber(InpTlsMagic); trade.SetTypeFillingBySymbol(tl_sym);
         string cm = StringFormat("TLS%d", n + 1);
         bool ok = dir == 1 ? trade.Buy(lot, tl_sym, 0, 0, 0, cm) : trade.Sell(lot, tl_sym, 0, 0, 0, cm);
         uint rc = trade.ResultRetcode(); string rd = trade.ResultRetcodeDescription();
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         if(!ok) { if(now - tl_tpset > 60) { tl_tpset = now; TlsEvent(StringFormat("ERROR | TLSR add %s failed: %d %s", tl_sym, rc, rd)); } return; }
         n = TlsBasket(bk, dir, last, vol, pnl, atr); if(atr <= 0) atr = tl_atr;
         for(int i = 0; i < n; i++) TlsRemember(bk[i]);
         double tp = TlsTpPrice(bk, dir, TlsTarget(atr));
         TlsSetTp(bk, dir, tp);
         TlsEvent(StringFormat("TLSR ADD %s | layer %d, %s %.2f lot at %s; basket %.2f lot, floating %.2f, new TP %s for the whole basket +%.2f",
                               tl_sym, n, dir == 1 ? "BUY" : "SELL", lot, PriceStr(tl_sym, last), vol, pnl, PriceStr(tl_sym, tp), TlsTarget(atr)));
         return;
      }
      if(now - tl_tpset >= 30) { tl_tpset = now; TlsSetTp(bk, dir, TlsTpPrice(bk, dir, target)); }
      return;
   }
   // flat: look for a signal once per new M15 bar
   datetime b0 = iTime(tl_sym, PERIOD_M15, 0);
   if(b0 == 0 || b0 == tl_bar) return;
   if(now - b0 > 300) { tl_bar = b0; return; }
   tl_bar = b0;
   if(DayPaused()) return;
   double a;
   int d = TlsSignal(a);
   if(d == 0 || a <= 0) return;
   double lot = TlsLot(0);
   string cm = "TLS " + DoubleToString(a, 2);
   trade.SetExpertMagicNumber(InpTlsMagic); trade.SetTypeFillingBySymbol(tl_sym);
   bool ok = d == 1 ? trade.Buy(lot, tl_sym, 0, 0, 0, cm) : trade.Sell(lot, tl_sym, 0, 0, 0, cm);
   uint rc = trade.ResultRetcode(); string rd = trade.ResultRetcodeDescription();
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) { TlsEvent(StringFormat("ERROR | TLSR %s order failed: %d %s", tl_sym, rc, rd)); return; }
   n = TlsBasket(bk, dir, last, vol, pnl, atr);
   for(int i = 0; i < n; i++) TlsRemember(bk[i]);
   tl_dir = d; tl_atr = a;
   double tp = TlsTpPrice(bk, d, TlsTarget(a));
   TlsSetTp(bk, d, tp);
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = last; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = tp; lc[1] = clrSeaGreen; lb[1] = "TP";
   string fn = Snap(tl_sym, PERIOD_M15, "TLE", lv, lc, lb, 0, 0, 0, 0, false);
   TlsEvent(StringFormat("TLSR %s %s | M15 trendline broken and the nearest %s broken too | %s %.2f lot at %s, TP %s (basket +%.2f), "
                         "next layer %s, NO stop loss",
                         d == 1 ? "BUY" : "SELL", tl_sym, d == 1 ? "resistance" : "support", d == 1 ? "BUY" : "SELL", lot,
                         PriceStr(tl_sym, last), PriceStr(tl_sym, tp), TlsTarget(a), PriceStr(tl_sym, last - d * InpTlsStepK * a)) + Img(fn));
}
//+------------------------------------------------------------------+
