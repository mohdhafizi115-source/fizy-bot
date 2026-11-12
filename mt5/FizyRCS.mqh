//+------------------------------------------------------------------+
//| FizyRCS.mqh - M15 REVERSAL CSAK on 28 forex pairs + gold, demo    |
//| only, included by FizyLB.mq5.  v2.20 (12 Nov 2026), the owner's   |
//| order ("bina no 1": forex + gold, no BTC) after rounds 96-98.      |
//|                                                                  |
//| RULES on closed M15 bars (BUY shown, SELL is the mirror):         |
//|  CSAK    the bar opens below min(mid BB 20, EMA 50) and closes    |
//|          above max(mid BB, EMA 50), not above the top BB 20,2     |
//|  H4      the last closed H4 candle sits in the LOWER half of its  |
//|          own BB 20,2: (close - mid) / (2 sd) <= -InpRcsH4Pos      |
//|  Extreme an M15 Extreme down (min of LWMA 5 / 10 of the lows      |
//|          below the bottom BB) in the InpRcsExtLb (8) candles      |
//|          before the CSAK                                          |
//|  cost    median spread of the CSAK's M5 bars <= InpRcsSprAtr      |
//|          (0.20) x Wilder ATR(14, M15)                             |
//|  time    CSAK bar opens 01:30-21:45 server, weekdays              |
//|  entry   market right after the CSAK closes, one position per     |
//|          symbol; SL beyond the InpRcsSwing (12)-candle swing ±    |
//|          the spread; NO TP; closed after InpRcsHoldH (8) hours    |
//| TEST (research/bbma97.py, bbma98.py, last 2 years, 30 symbols):   |
//| 940 trades, PF 1.15 (in R), years 1.13 / 1.20, stress 1.10, last  |
//| 12 months +26R, random direction 0.89 - PASS.  $ per 0.01 lot:    |
//| XAUUSD 59 trades PF 2.29 +$539 (avg risk $22.71, worst -$42),     |
//| forex 773 trades PF 1.22 +$179; BTCUSD lost (PF 0.83), left out.  |
//| Plateaus: Extreme lookback 4-16, swing 4-24, hold 2-12 h.         |
//| Events go to MQL5\Files\rcs_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpRcsOn      = true;
input double InpRcsLot     = 0.01;
input long   InpRcsMagic   = 260324;
input string InpRcsSymbols = "XAUUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,EURNZD,"
                             "GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY";
input double InpRcsH4Pos   = 0.5;     // H4 close at least this far into the opposite half of the H4 band (in band half-widths)
input int    InpRcsExtLb   = 8;       // M15 Extreme against the CSAK within this many candles before it
input double InpRcsSprAtr  = 0.20;    // cost gate: spread <= this x ATR(14, M15)
input int    InpRcsSwing   = 12;      // SL beyond the lowest low / highest high of this many M15 candles up to the CSAK
input int    InpRcsHoldH   = 8;       // close at market after this many hours

string   rc_sym[];
datetime rc_bar[];
ulong    rc_known[];
bool     rc_ready = false;

void RcsEvent(string msg)
{
   int h = FileOpen("rcs_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("rcs event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("RCS EVENT ", msg);
}

bool RcsPosition(string sym, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpRcsMagic && PositionGetString(POSITION_SYMBOL) == sym) { ticket = t; return true; }
   }
   return false;
}

void RcsRemember(ulong t)
{
   for(int q = 0; q < ArraySize(rc_known); q++) if(rc_known[q] == t) return;
   int m = ArraySize(rc_known); ArrayResize(rc_known, m + 1); rc_known[m] = t;
}

void RcsInit()
{
   rc_ready = true;
   string parts[];
   int k = StringSplit(InpRcsSymbols, ',', parts);
   string missing = "";
   ArrayResize(rc_sym, 0);
   for(int i = 0; i < k; i++)
   {
      string b = parts[i]; StringTrimLeft(b); StringTrimRight(b);
      if(b == "") continue;
      string s = SymResolve(b);
      if(s == "") { missing += (missing == "" ? "" : ",") + b; continue; }
      SymbolSelect(s, true);
      MqlRates tmp[];
      CopyRates(s, PERIOD_M15, 0, 700, tmp);                  // start the history download
      CopyRates(s, PERIOD_H4, 0, 60, tmp);
      CopyRates(s, PERIOD_M5, 0, 10, tmp);
      int m = ArraySize(rc_sym); ArrayResize(rc_sym, m + 1); rc_sym[m] = s;
   }
   ArrayResize(rc_bar, ArraySize(rc_sym));
   for(int i = 0; i < ArraySize(rc_bar); i++) rc_bar[i] = 0;
   int open = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpRcsMagic) { RcsRemember(t); open++; }
   }
   RcsEvent(StringFormat("RCS ONLINE | M15 reversal CSAK on %d symbols (forex + XAUUSD): a CSAK after an M15 Extreme the other way in "
                         "the last %d candles, with the last H4 close in the opposite half of its band (<= -%.1f), spread <= %.2f ATR; "
                         "SL beyond the %d-candle swing, no TP, out after %d h, lot %.2f%s | %d open position(s)",
                         ArraySize(rc_sym), InpRcsExtLb, InpRcsH4Pos, InpRcsSprAtr, InpRcsSwing, InpRcsHoldH, InpRcsLot,
                         missing == "" ? "" : " | not at this broker: " + missing, open));
}

void RcsReportClosed(ulong pos)
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
   string what = reason == DEAL_REASON_SL ? "RCS SL HIT" : "RCS CLOSED";
   string why = reason == DEAL_REASON_SL ? "stop loss beyond the swing"
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d hours up", InpRcsHoldH) : "closed outside the EA");
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sym, PERIOD_M15, "RCX", lv, lc, lb, 0, 0, 0, 0, false);
   RcsEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, sym, side, PriceStr(sym, inPx),
                         PriceStr(sym, outPx), why, profit) + Img(fn));
}

// one symbol: manage its open position, then look at a freshly closed M15 bar
void RcsSymbol(int si, datetime now)
{
   string sym = rc_sym[si];
   MqlTick tk;
   if(!SymbolInfoTick(sym, tk) || now - tk.time > 600) return;                 // market closed / no quotes
   ulong pt;
   bool inPos = RcsPosition(sym, pt);
   if(inPos)
   {
      RcsRemember(pt);
      PositionSelectByTicket(pt);
      long held = (long)(now - (datetime)PositionGetInteger(POSITION_TIME));
      if(held >= (long)InpRcsHoldH * 3600)                                       // the time exit
      {
         trade.SetExpertMagicNumber(InpRcsMagic); trade.SetTypeFillingBySymbol(sym);
         if(!trade.PositionClose(pt)) RcsEvent(StringFormat("ERROR | RCS close %s failed: %d %s", sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
   }
   datetime b0 = iTime(sym, PERIOD_M15, 0);
   if(b0 == 0 || b0 == rc_bar[si]) return;                                      // once per new M15 bar
   if(now - b0 > 300) { rc_bar[si] = b0; return; }                              // too late for this bar: skip it
   MqlRates r[];
   int n = CopyRates(sym, PERIOD_M15, 1, 700, r);                               // closed bars, r[n-1] = the CSAK candidate
   if(n < 400) return;                                                          // history still loading: try again next second
   int j = n - 1;
   if(r[j].time + 900 != b0) { rc_bar[si] = b0; return; }                       // a gap: not the bar that just closed
   MqlRates h4[];
   int nh = CopyRates(sym, PERIOD_H4, 0, 60, h4);
   if(nh < 25) return;
   rc_bar[si] = b0;
   if(inPos) return;
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1320) return;

   // M15 indicators: BB 20,2 (population sd), EMA 50, LWMA 5 / 10 of lows and highs, Wilder ATR 14
   double c[], mid[], sdv[], e50[], atr[];
   ArrayResize(c, n); ArrayResize(mid, n); ArrayResize(sdv, n); ArrayResize(e50, n); ArrayResize(atr, n);
   for(int i = 0; i < n; i++) c[i] = r[i].close;
   double ka = 2.0 / 51.0;
   e50[0] = c[0]; atr[0] = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
   {
      e50[i] = e50[i - 1] + ka * (c[i] - e50[i - 1]);
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr[i] = atr[i - 1] + (tr - atr[i - 1]) / 14.0;
   }
   for(int i = 19; i < n; i++)
   {
      double s = 0, s2 = 0;
      for(int q = i - 19; q <= i; q++) { s += c[q]; s2 += c[q] * c[q]; }
      double m = s / 20.0;
      mid[i] = m; sdv[i] = MathSqrt(MathMax(s2 / 20.0 - m * m, 0));
   }
   double lo = MathMin(mid[j], e50[j]), hi = MathMax(mid[j], e50[j]);
   double top = mid[j] + 2 * sdv[j], bot = mid[j] - 2 * sdv[j];
   int dir = 0;
   if(r[j].open < lo && r[j].close > hi && r[j].close <= top) dir = 1;
   else if(r[j].open > hi && r[j].close < lo && r[j].close >= bot) dir = -1;
   if(dir == 0) return;

   // the last H4 candle closed by the CSAK's close: its position inside its own BB 20,2
   datetime cclose = r[j].time + 900;
   int hk = -1;
   for(int i = nh - 1; i >= 19; i--) if(h4[i].time + 14400 <= cclose) { hk = i; break; }
   if(hk < 19) return;
   double hs = 0, hs2 = 0;
   for(int q = hk - 19; q <= hk; q++) { hs += h4[q].close; hs2 += h4[q].close * h4[q].close; }
   double hm4 = hs / 20.0, hsd = MathSqrt(MathMax(hs2 / 20.0 - hm4 * hm4, 0));
   if(hsd <= 0) return;
   double pos = (h4[hk].close - hm4) / (2 * hsd) * dir;                         // signed: negative = the opposite half
   if(pos > -InpRcsH4Pos) return;

   // an M15 Extreme the other way in the candles before the CSAK
   bool ext = false;
   for(int i = j - InpRcsExtLb; i <= j - 1; i++)
   {
      if(i < 30) continue;
      double l5 = 0, l10 = 0, h5 = 0, h10 = 0, w5 = 0, w10 = 0;
      for(int q = 0; q < 10; q++)
      {
         double w = 10 - q;
         l10 += w * r[i - q].low; h10 += w * r[i - q].high; w10 += w;
         if(q < 5) { double v = 5 - q; l5 += v * r[i - q].low; h5 += v * r[i - q].high; w5 += v; }
      }
      l5 /= w5; l10 /= w10; h5 /= w5; h10 /= w10;
      double tb = mid[i] + 2 * sdv[i], bb = mid[i] - 2 * sdv[i];
      if(dir == 1 && MathMin(l5, l10) < bb) ext = true;
      if(dir == -1 && MathMax(h5, h10) > tb) ext = true;
   }
   if(!ext) return;

   // the cost gate: median spread of the CSAK's M5 bars against ATR(14, M15)
   double pnt = SymbolInfoDouble(sym, SYMBOL_POINT);
   MqlRates m5[];
   int n5 = CopyRates(sym, PERIOD_M5, r[j].time, r[j].time + 899, m5);
   double spr = 0;
   if(n5 > 0)
   {
      double sv[]; ArrayResize(sv, n5);
      for(int i = 0; i < n5; i++) sv[i] = m5[i].spread * pnt;
      ArraySort(sv);
      spr = n5 % 2 == 1 ? sv[n5 / 2] : (sv[n5 / 2 - 1] + sv[n5 / 2]) / 2;
   }
   double now_spr = tk.ask - tk.bid;
   if(spr <= 0) spr = now_spr;
   if(atr[j] <= 0 || spr > InpRcsSprAtr * atr[j]) return;
   if(DayPaused()) return;                                                      // daily target reached

   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double swl = r[j].low, swh = r[j].high;
   for(int i = j - InpRcsSwing + 1; i <= j; i++) { swl = MathMin(swl, r[i].low); swh = MathMax(swh, r[i].high); }
   double entry = dir == 1 ? tk.ask : tk.bid;
   double sl = NormalizeDouble(dir == 1 ? swl - now_spr : swh + now_spr, dg);
   double risk = (entry - sl) * dir;
   if(risk <= now_spr) return;
   double stopLv = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * pnt;
   if((dir == 1 ? tk.bid - sl : sl - tk.ask) <= stopLv) return;
   double mn = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), vs = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpRcsLot / vs + 1e-9) * vs), 2);
   trade.SetExpertMagicNumber(InpRcsMagic); trade.SetTypeFillingBySymbol(sym);
   bool ok = dir == 1 ? trade.Buy(lot, sym, 0, sl, 0, "RCS") : trade.Sell(lot, sym, 0, sl, 0, "RCS");
   if(!ok) RcsEvent(StringFormat("ERROR | RCS %s order failed: %d %s", sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double riskUsd = ts > 0 ? risk / ts * tv * lot : 0;
   string side = dir == 1 ? "BUY" : "SELL";
   double lv[4]; color lc[4]; string lb[4];
   lv[0] = entry; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   lv[2] = mid[j]; lc[2] = clrGoldenrod; lb[2] = "mid BB"; lv[3] = e50[j]; lc[3] = clrDarkViolet; lb[3] = "EMA 50";
   string fn = Snap(sym, PERIOD_M15, "RCE", lv, lc, lb, 0, 0, 0, 0, false);
   RcsEvent(StringFormat("RCS %s %s | M15 CSAK %s through mid BB %s and EMA 50 %s after an Extreme %s, H4 close in the %s half of its band "
                         "(%.2f), spread %.2f ATR | %s %.2f lot at %s, SL %s beyond the %d-candle swing (risk $%.2f), no TP, out after %d h",
                         side, sym, dir == 1 ? "up" : "down", PriceStr(sym, mid[j]), PriceStr(sym, e50[j]), dir == 1 ? "down" : "up",
                         dir == 1 ? "lower" : "upper", pos * dir, spr / atr[j], side, lot, PriceStr(sym, entry), PriceStr(sym, sl),
                         InpRcsSwing, riskUsd, InpRcsHoldH) + Img(fn));
   if(RcsPosition(sym, pt)) RcsRemember(pt);
}

void RcsOnTimer()
{
   if(!InpRcsOn) return;
   if(!rc_ready) RcsInit();
   for(int q = ArraySize(rc_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(rc_known[q])) { RcsReportClosed(rc_known[q]); ArrayRemove(rc_known, q, 1); }
   datetime now = TimeCurrent();
   for(int i = 0; i < ArraySize(rc_sym); i++) RcsSymbol(i, now);
}
//+------------------------------------------------------------------+
