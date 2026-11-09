//+------------------------------------------------------------------+
//| FizyHA.mqh - gold M1 Heikin Ashi + EMA 10/30 + Stochastic, the   |
//| owner's rule, demo only, included by FizyLB.mq5 (v2.08, 9 Nov).  |
//|                                                                  |
//| THE OWNER'S RULE (9 Nov): "ema10 30 / heikin ashi / stoch 14,3,3"|
//| BUY (sell is the mirror):                                        |
//|  1 EMA 10 above EMA 30, both rising                              |
//|  2 the previous HA candle is an INDECISION candle: a shadow above|
//|    AND below, small body (<= InpHaBodyMax x its HA range)        |
//|  3 the last closed HA candle is BULLISH with NO lower shadow     |
//|  4 Stochastic 14,3,3 main line not overbought (< 80)             |
//|  entry at market, SL at the nearest swing low (lowest low of the |
//|  last InpHaSwing bars minus the spread), TP 1:1 to the SL size   |
//|  ("TP adjust 1:1 ikut saiz sl"). One position at a time,          |
//|  entries 01:30-22:00 server, flat 23:45 or after 100 bars.        |
//| Live on his order ("buat live terus"). Tested first: round 66    |
//| (TP in ATR) lost in both of the last 2 months, PF 0.75-0.86;     |
//| round 67 (research/ha67.py) has the 1:1 TP. See CLAUDE.md.       |
//| Respects the $25 daily target (DayPaused).                       |
//| Events go to MQL5\Files\ha_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpHaOn       = false;   // OFF since 9 Nov (owner: lost twice, "aku tak nak")
input string InpHaSymbol   = "XAUUSD";
input double InpHaLot      = 0.01;
input long   InpHaMagic    = 260322;
input double InpHaBodyMax  = 0.3;     // indecision: max HA body as a share of the HA range
input bool   InpHaSlope    = true;    // EMA 10 and EMA 30 must also be rising (falling for sells)
input int    InpHaSwing    = 10;      // SL at the lowest low / highest high of the last N closed M1 bars
input double InpHaRR       = 1.0;     // TP = this x the SL distance (owner: 1:1)
input int    InpHaMaxBars  = 100;     // close after this many M1 bars

string   ha_sym = "";
bool     ha_ready = false;
datetime ha_bar = 0;
ulong    ha_known[];
int      ha_f = INVALID_HANDLE, ha_s = INVALID_HANDLE, ha_k = INVALID_HANDLE;

void HaEvent(string msg)
{
   int h = FileOpen("ha_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("ha event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("HA EVENT ", msg);
}

ulong HaPos()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpHaMagic || PositionGetString(POSITION_SYMBOL) != ha_sym) continue;
      bool known = false;
      for(int q = 0; q < ArraySize(ha_known); q++) if(ha_known[q] == t) known = true;
      if(!known) { int m = ArraySize(ha_known); ArrayResize(ha_known, m + 1); ha_known[m] = t; }
      return t;
   }
   return 0;
}

void HaInit()
{
   ha_ready = true;
   ha_sym = SymResolve(InpHaSymbol);
   if(ha_sym == "") { HaEvent("ERROR | M1 Heikin Ashi: symbol " + InpHaSymbol + " not found"); return; }
   SymbolSelect(ha_sym, true);
   ha_f = iMA(ha_sym, PERIOD_M1, 10, 0, MODE_EMA, PRICE_CLOSE);
   ha_s = iMA(ha_sym, PERIOD_M1, 30, 0, MODE_EMA, PRICE_CLOSE);
   ha_k = iStochastic(ha_sym, PERIOD_M1, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
   int n = HaPos() != 0 ? 1 : 0;
   HaEvent(StringFormat("HA ONLINE | %s M1: EMA 10/30 aligned%s, HA indecision (body <= %.0f%%) then HA candle with no "
                        "lower / upper shadow, Stoch 14,3,3 not overbought / oversold; SL at the %d-bar swing, TP %.1f:1 to the SL, "
                        "lot %.2f | %d open position(s)", ha_sym, InpHaSlope ? " and sloping" : "", InpHaBodyMax * 100,
                        InpHaSwing, InpHaRR, InpHaLot, n));
}

void HaReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, typ = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); typ = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = reason == DEAL_REASON_TP ? "HA TP HIT" : (reason == DEAL_REASON_SL ? "HA SL HIT" : "HA CLOSED");
   string why = reason == DEAL_REASON_TP ? "take profit 1:1" : (reason == DEAL_REASON_SL ? "stop loss at the swing"
              : (reason == DEAL_REASON_EXPERT ? "time exit (100 bars or 23:45 rollover)" : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(ha_sym, PERIOD_M1, "HAX", lv, lc, lb, 0, 0, 0, 0, false);
   HaEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, ha_sym, typ == DEAL_TYPE_BUY ? "BUY" : "SELL",
                        PriceStr(ha_sym, inPx), PriceStr(ha_sym, outPx), why, profit) + Img(fn));
}

void HaOnTimer()
{
   if(!InpHaOn) return;
   if(!ha_ready) HaInit();
   if(ha_sym == "") return;
   ulong pos = HaPos();
   for(int q = ArraySize(ha_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(ha_known[q])) { HaReportClosed(ha_known[q]); ArrayRemove(ha_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(ha_sym, tk) || now - tk.time > 600) return;              // market closed
   MqlDateTime ns; TimeToStruct(now, ns);
   int nowhm = ns.hour * 60 + ns.min;

   // ---- time exits the broker does not handle
   if(pos != 0 && PositionSelectByTicket(pos))
   {
      int held = iBarShift(ha_sym, PERIOD_M1, (datetime)PositionGetInteger(POSITION_TIME), false);
      if(nowhm >= 1425 || (InpHaMaxBars > 0 && held >= InpHaMaxBars))
      {
         trade.SetExpertMagicNumber(InpHaMagic); trade.SetTypeFillingBySymbol(ha_sym);
         if(!trade.PositionClose(pos)) HaEvent(StringFormat("ERROR | HA close %s failed: %d %s", ha_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;
   }

   // ---- signal: once per new M1 bar, from closed bars only
   datetime b0 = iTime(ha_sym, PERIOD_M1, 0);
   if(b0 == 0 || b0 == ha_bar) return;
   ha_bar = b0;
   if(ns.day_of_week == 0 || ns.day_of_week == 6 || nowhm < 90 || nowhm >= 1320) return;
   if(DayPaused()) return;                                                      // daily target reached: no new trades

   MqlRates r[];
   ArraySetAsSeries(r, true);
   int n = CopyRates(ha_sym, PERIOD_M1, 1, 300, r);                             // r[0] = last closed bar
   if(n < 50) return;
   double ho[2], hc[2], hh[2], hl[2];
   double o = (r[n - 1].open + r[n - 1].close) / 2, cp = 0;
   for(int i = n - 1; i >= 0; i--)
   {
      double c = (r[i].open + r[i].high + r[i].low + r[i].close) / 4;
      if(i < n - 1) o = (o + cp) / 2;
      cp = c;
      if(i <= 1) { ho[i] = o; hc[i] = c; hh[i] = MathMax(r[i].high, MathMax(o, c)); hl[i] = MathMin(r[i].low, MathMin(o, c)); }
   }
   double ef[], es[], kk[];
   ArraySetAsSeries(ef, true); ArraySetAsSeries(es, true); ArraySetAsSeries(kk, true);
   if(CopyBuffer(ha_f, 0, 1, 2, ef) < 2 || CopyBuffer(ha_s, 0, 1, 2, es) < 2 || CopyBuffer(ha_k, 0, 1, 1, kk) < 1) return;

   double pt = SymbolInfoDouble(ha_sym, SYMBOL_POINT), eps = pt * 0.5;
   double top1 = MathMax(ho[1], hc[1]), bot1 = MathMin(ho[1], hc[1]), rng1 = hh[1] - hl[1];
   if(!(rng1 > 0 && top1 < hh[1] - eps && bot1 > hl[1] + eps && (top1 - bot1) <= InpHaBodyMax * rng1)) return;
   double top0 = MathMax(ho[0], hc[0]), bot0 = MathMin(ho[0], hc[0]);
   int dir = 0;
   if(hc[0] > ho[0] && bot0 - hl[0] <= eps && ef[0] > es[0] && (!InpHaSlope || (ef[0] > ef[1] && es[0] > es[1])) && kk[0] < 80) dir = 1;
   else if(hc[0] < ho[0] && hh[0] - top0 <= eps && ef[0] < es[0] && (!InpHaSlope || (ef[0] < ef[1] && es[0] < es[1])) && kk[0] > 20) dir = -1;
   if(dir == 0) return;

   double lo = r[0].low, hi = r[0].high;
   for(int i = 1; i < InpHaSwing && i < n; i++) { lo = MathMin(lo, r[i].low); hi = MathMax(hi, r[i].high); }
   int dg = (int)SymbolInfoInteger(ha_sym, SYMBOL_DIGITS);
   double spread = tk.ask - tk.bid;
   double minDist = SymbolInfoInteger(ha_sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   double px = dir == 1 ? tk.ask : tk.bid;
   double sl = NormalizeDouble(dir == 1 ? lo - spread : hi + spread, dg);
   double risk = (px - sl) * dir;
   if(risk <= minDist + spread) return;                                        // swing too close to price
   double tp = NormalizeDouble(px + dir * InpHaRR * risk, dg);
   trade.SetExpertMagicNumber(InpHaMagic); trade.SetTypeFillingBySymbol(ha_sym);
   bool ok = dir == 1 ? trade.Buy(InpHaLot, ha_sym, 0, sl, tp, "HA M1") : trade.Sell(InpHaLot, ha_sym, 0, sl, tp, "HA M1");
   if(!ok) HaEvent(StringFormat("ERROR | HA %s order failed: %d %s", ha_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   HaPos();
   double lv[3]; color lc[3]; string lb[3];
   lv[0] = px; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL"; lv[2] = tp; lc[2] = clrSeaGreen; lb[2] = "TP";
   string fn = Snap(ha_sym, PERIOD_M1, "HAE", lv, lc, lb, 0, 0, 0, 0, false);
   HaEvent(StringFormat("HA %s %s | EMA10 %s EMA30, HA indecision then %s, Stoch %.0f | %s %.2f lot at %s, SL %s (swing), TP %s (1:1, $%.2f)",
                        dir == 1 ? "BUY" : "SELL", ha_sym, dir == 1 ? ">" : "<", dir == 1 ? "bullish HA with no lower shadow" : "bearish HA with no upper shadow",
                        kk[0], dir == 1 ? "BUY" : "SELL", InpHaLot, PriceStr(ha_sym, px), PriceStr(ha_sym, sl), PriceStr(ha_sym, tp),
                        risk * InpHaRR * InpHaLot * 100) + Img(fn));
}
//+------------------------------------------------------------------+
