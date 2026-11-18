//+------------------------------------------------------------------+
//| FizyCB1.mqh - BBMA CB1 + CSAK on M15, 28 forex pairs + XAUUSD +  |
//| BTCUSD, demo only, included by FizyLB.mq5.  v2.50 (18 Nov 2026),  |
//| the owner's order after round 143d: "aku nak kau buat modul cb1   |
//| bukan di level last bear, tp 2r ... pastikan semua pair masuk".   |
//|                                                                  |
//| RULES on closed M15 bars (BUY shown, SELL is the mirror):         |
//|  swing   fractal 2: a high that is the highest of the 2 bars on   |
//|          each side; the newest one is the level, cleared when     |
//|          broken                                                    |
//|  CB1     an M15 close above that swing high (previous close at or |
//|          below it), "soft": body < 1 ATR(14, M15) and not a       |
//|          bullish engulfing, AND the level is NOT within 0.3 ATR   |
//|          of the high of the last bear candle before the break     |
//|  CSAK    within 8 candles after the CB1, one candle opens below   |
//|          min(mid BB 20, EMA 50, LWMA 5 / 10 of the highs) and     |
//|          closes above max(mid BB, EMA 50, LWMA 5 / 10 high)       |
//|  entry   market right after the CSAK closes, one position per     |
//|          symbol; SL below the lowest low of the 12 candles before |
//|          the CB1 up to the CSAK - 0.1 ATR; TP 2R; closed after    |
//|          24 hours                                                  |
//| TEST (research/ticks/bbma143.py + round 143d, round 133 M5 export,|
//| 30 symbols pooled, 0.01 lot): last 3 months 158 trades, win 36%,  |
//| PF 1.30, stress 1.22, +$64, DD -$47, worst day -$26, worst trade  |
//| -$23 / the 3 months before 134 trades PF 2.10, +$158, DD -$31.    |
//| FAILS the pass rule: the random-direction twin at the same fills  |
//| scores 1.02 / 1.87, neighbours (tolerance 0.1, CSAK window 16)    |
//| lose, and XAUUSD makes +$81 / +$184 of it (forex about -$20 a     |
//| window). Built on the owner's explicit order.                     |
//| Events go to MQL5\Files\cb1_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpCb1On      = true;
input double InpCb1Lot     = 0.01;
input long   InpCb1Magic   = 260339;
input string InpCb1Symbols = "XAUUSD,BTCUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,EURNZD,"
                             "GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY";
input int    InpCb1Window  = 8;       // the CSAK must come within this many M15 candles after the CB1
input double InpCb1LbTol   = 0.3;     // CB1 level not within this many ATR of the last opposite candle's high (low)
input int    InpCb1Swing   = 12;      // SL beyond the extreme of this many candles before the CB1 up to the CSAK
input double InpCb1SlBuf   = 0.1;     // ... plus this many ATR(14, M15)
input double InpCb1TpR     = 2.0;     // TP in R
input int    InpCb1HoldH   = 24;      // close at market after this many hours
input bool   InpCb1GoldOnly = true;   // v2.51 (18 Nov, owner "hadkan pada gold sahaja"): NEW entries on XAUUSD only; open positions on other symbols keep their SL / TP / 24 h exit

string   cb_sym[];
datetime cb_bar[];
ulong    cb_known[];
bool     cb_ready = false;

void Cb1Event(string msg)
{
   int h = FileOpen("cb1_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("cb1 event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("CB1 EVENT ", msg);
}

bool Cb1Position(string sym, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpCb1Magic && PositionGetString(POSITION_SYMBOL) == sym) { ticket = t; return true; }
   }
   return false;
}

void Cb1Remember(ulong t)
{
   for(int q = 0; q < ArraySize(cb_known); q++) if(cb_known[q] == t) return;
   int m = ArraySize(cb_known); ArrayResize(cb_known, m + 1); cb_known[m] = t;
}

void Cb1Init()
{
   cb_ready = true;
   string parts[];
   int k = StringSplit(InpCb1Symbols, ',', parts);
   string missing = "";
   ArrayResize(cb_sym, 0);
   for(int i = 0; i < k; i++)
   {
      string b = parts[i]; StringTrimLeft(b); StringTrimRight(b);
      if(b == "") continue;
      string s = SymResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ",") + b; continue; }
      SymbolSelect(s, true);
      MqlRates tmp[];
      CopyRates(s, PERIOD_M15, 0, 700, tmp);                  // start the history download
      int m = ArraySize(cb_sym); ArrayResize(cb_sym, m + 1); cb_sym[m] = s;
   }
   ArrayResize(cb_bar, ArraySize(cb_sym));
   for(int i = 0; i < ArraySize(cb_bar); i++) cb_bar[i] = 0;
   int open = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpCb1Magic) { Cb1Remember(t); open++; }
   }
   Cb1Event(StringFormat("CB1 ONLINE | BBMA CB1 + CSAK on M15, %d symbols (%s): a soft break of the nearest swing (not at the last "
                         "opposite candle's level, %.1f ATR), then a CSAK within %d candles; market entry, SL beyond the swing "
                         "- %.1f ATR, TP %.0fR, out after %d h, lot %.2f%s | %d open position(s)",
                         ArraySize(cb_sym), InpCb1GoldOnly ? "new entries on XAUUSD only, the rest only close open trades" : "all", InpCb1LbTol, InpCb1Window, InpCb1SlBuf, InpCb1TpR, InpCb1HoldH, InpCb1Lot,
                         missing == "" ? "" : " | not at this broker: " + missing, open));
}

void Cb1ReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "CB1 SL HIT" : (reason == DEAL_REASON_TP ? "CB1 TP HIT" : "CB1 CLOSED");
   string why = reason == DEAL_REASON_SL ? "stop loss beyond the swing" : reason == DEAL_REASON_TP ? StringFormat("take profit %.0fR", InpCb1TpR)
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d hours up", InpCb1HoldH) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sym, PERIOD_M15, "CBX", lv, lc, lb, 0, 0, 0, 0, false);
   Cb1Event(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, sym, side, PriceStr(sym, inPx),
                         PriceStr(sym, outPx), why, profit) + Img(fn));
}

double Cb1Lwma(const MqlRates &r[], int i, int len, bool high)
{
   double s = 0, w = 0;
   for(int q = 0; q < len; q++) { double v = len - q; s += v * (high ? r[i - q].high : r[i - q].low); w += v; }
   return s / w;
}

// one symbol: manage its open position, then look at a freshly closed M15 bar
void Cb1Symbol(int si, datetime now)
{
   string sym = cb_sym[si];
   MqlTick tk;
   if(!SymbolInfoTick(sym, tk) || now - tk.time > 600) return;                 // market closed / no quotes
   ulong pt;
   bool inPos = Cb1Position(sym, pt);
   if(inPos)
   {
      Cb1Remember(pt);
      PositionSelectByTicket(pt);
      long held = (long)(now - (datetime)PositionGetInteger(POSITION_TIME));
      if(held >= (long)InpCb1HoldH * 3600)                                       // the time exit
      {
         trade.SetExpertMagicNumber(InpCb1Magic); trade.SetTypeFillingBySymbol(sym);
         if(!trade.PositionClose(pt)) Cb1Event(StringFormat("ERROR | CB1 close %s failed: %d %s", sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   datetime b0 = iTime(sym, PERIOD_M15, 0);
   if(b0 == 0 || b0 == cb_bar[si]) return;                                      // once per new M15 bar
   if(now - b0 > 300) { cb_bar[si] = b0; return; }                              // too late for this bar: skip it
   MqlRates r[];
   int n = CopyRates(sym, PERIOD_M15, 1, 700, r);                               // closed bars, r[n-1] = the CSAK candidate
   if(n < 400) return;                                                          // history still loading: try again next second
   int j = n - 1;
   if(r[j].time + 900 != b0) { cb_bar[si] = b0; return; }                       // a gap: not the bar that just closed
   cb_bar[si] = b0;
   if(inPos) return;
   if(InpCb1GoldOnly && StringFind(sym, "XAU") != 0) return;                    // v2.51: other symbols only manage open positions

   // M15 indicators: BB 20 mid, EMA 50, Wilder ATR 14
   double c[], mid[], e50[], atr[];
   ArrayResize(c, n); ArrayResize(mid, n); ArrayResize(e50, n); ArrayResize(atr, n);
   for(int i = 0; i < n; i++) { c[i] = r[i].close; mid[i] = 0; }
   double ka = 2.0 / 51.0;
   e50[0] = c[0]; atr[0] = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
   {
      e50[i] = e50[i - 1] + ka * (c[i] - e50[i - 1]);
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr[i] = atr[i - 1] + (tr - atr[i - 1]) / 14.0;
   }
   for(int i = 19; i < n; i++) { double s = 0; for(int q = i - 19; q <= i; q++) s += c[q]; mid[i] = s / 20.0; }

   // replay the fractal swings and the CB1 breaks up to the candidate bar
   double sh = 0, sl_ = 0; bool hasH = false, hasL = false;
   int lastUp = -1000000, lastDn = -1000000;
   for(int i = 60; i <= j; i++)
   {
      int p = i - 2;
      double mx = r[p - 2].high, mn = r[p - 2].low;
      for(int q = p - 1; q <= i; q++) { mx = MathMax(mx, r[q].high); mn = MathMin(mn, r[q].low); }
      if(r[p].high == mx) { sh = r[p].high; hasH = true; }
      if(r[p].low == mn) { sl_ = r[p].low; hasL = true; }
      double body = MathAbs(r[i].close - r[i].open);
      bool big = body >= atr[i];
      if(hasH && r[i].close > sh && r[i - 1].close <= sh)
      {
         bool eng = r[i].close > r[i].open && r[i - 1].close < r[i - 1].open && r[i].close >= r[i - 1].open && r[i].open <= r[i - 1].close;
         bool ok = !(big || eng);
         if(ok)
            for(int q = i - 1; q > MathMax(i - 40, 0); q--)
               if(r[q].close < r[q].open) { if(MathAbs(r[q].high - sh) <= InpCb1LbTol * atr[i]) ok = false; break; }
         if(ok) lastUp = i;
         hasH = false;
      }
      if(hasL && r[i].close < sl_ && r[i - 1].close >= sl_)
      {
         bool eng = r[i].close < r[i].open && r[i - 1].close > r[i - 1].open && r[i].close <= r[i - 1].open && r[i].open >= r[i - 1].close;
         bool ok = !(big || eng);
         if(ok)
            for(int q = i - 1; q > MathMax(i - 40, 0); q--)
               if(r[q].close > r[q].open) { if(MathAbs(r[q].low - sl_) <= InpCb1LbTol * atr[i]) ok = false; break; }
         if(ok) lastDn = i;
         hasL = false;
      }
   }

   // the CSAK on the candidate bar
   double h5 = Cb1Lwma(r, j, 5, true), h10 = Cb1Lwma(r, j, 10, true), l5 = Cb1Lwma(r, j, 5, false), l10 = Cb1Lwma(r, j, 10, false);
   double hiB = MathMax(MathMax(mid[j], e50[j]), MathMax(h5, h10)), loB = MathMin(MathMin(mid[j], e50[j]), MathMin(h5, h10));
   double hiS = MathMax(MathMax(mid[j], e50[j]), MathMax(l5, l10)), loS = MathMin(MathMin(mid[j], e50[j]), MathMin(l5, l10));
   int dir = 0, cb = -1;
   if(r[j].open < loB && r[j].close > hiB && j - lastUp > 0 && j - lastUp <= InpCb1Window) { dir = 1; cb = lastUp; }
   else if(r[j].open > hiS && r[j].close < loS && j - lastDn > 0 && j - lastDn <= InpCb1Window) { dir = -1; cb = lastDn; }
   if(dir == 0) return;
   if(DayPaused()) return;                                                      // daily target reached

   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double pnt = SymbolInfoDouble(sym, SYMBOL_POINT);
   int lo0 = MathMax(cb - InpCb1Swing, 0);
   double ext = dir == 1 ? r[lo0].low : r[lo0].high;
   for(int i = lo0; i <= j; i++) ext = dir == 1 ? MathMin(ext, r[i].low) : MathMax(ext, r[i].high);
   double sl = NormalizeDouble(ext - dir * InpCb1SlBuf * atr[j], dg);
   double entry = dir == 1 ? tk.ask : tk.bid;
   double now_spr = tk.ask - tk.bid;
   double risk = (entry - sl) * dir;
   if(risk <= now_spr) return;
   double tp = NormalizeDouble(entry + dir * InpCb1TpR * risk, dg);
   double stopLv = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * pnt;
   if((dir == 1 ? tk.bid - sl : sl - tk.ask) <= stopLv) return;
   double mn = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), vs = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpCb1Lot / vs + 1e-9) * vs), 2);
   trade.SetExpertMagicNumber(InpCb1Magic); trade.SetTypeFillingBySymbol(sym);
   bool ok = dir == 1 ? trade.Buy(lot, sym, 0, sl, tp, "CB1") : trade.Sell(lot, sym, 0, sl, tp, "CB1");
   if(!ok) Cb1Event(StringFormat("ERROR | CB1 %s order failed: %d %s", sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double riskUsd = ts > 0 ? risk / ts * tv * lot : 0;
   string side = dir == 1 ? "BUY" : "SELL";
   double lv[4]; color lc[4]; string lb[4];
   lv[0] = entry; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = tp; lc[2] = clrSeaGreen; lb[2] = "TP"; lv[3] = r[cb].close; lc[3] = clrGoldenrod; lb[3] = "CB1";
   string fn = Snap(sym, PERIOD_M15, "CBE", lv, lc, lb, 0, 0, 0, 0, false);
   Cb1Event(StringFormat("CB1 %s %s | CB1 %s at %s (%d candles ago), then a CSAK %s through EMA 50, mid BB and MA5/10 | %s %.2f lot at %s, "
                         "SL %s, TP %s (%.0fR, risk $%.2f), out after %d h",
                         side, sym, dir == 1 ? "break up" : "break down", TimeToString(r[cb].time, TIME_MINUTES), j - cb,
                         dir == 1 ? "up" : "down", side, lot, PriceStr(sym, entry), PriceStr(sym, sl), PriceStr(sym, tp),
                         InpCb1TpR, riskUsd, InpCb1HoldH) + Img(fn));
   if(Cb1Position(sym, pt)) Cb1Remember(pt);
}

void Cb1OnTimer()
{
   if(!InpCb1On) return;
   if(!cb_ready) Cb1Init();
   for(int q = ArraySize(cb_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(cb_known[q])) { Cb1ReportClosed(cb_known[q]); ArrayRemove(cb_known, q, 1); }
   datetime now = TimeCurrent();
   for(int i = 0; i < ArraySize(cb_sym); i++) Cb1Symbol(i, now);
}
//+------------------------------------------------------------------+
