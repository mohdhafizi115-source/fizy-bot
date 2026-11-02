//+------------------------------------------------------------------+
//| FizySR.mqh - gold M15 support / resistance zones, ALERTS ONLY (no |
//| trading), included by FizyLB.mq5.                                 |
//| Zones (same algorithm as research/srzones.py): 5-bar swing highs  |
//| and lows of the last 480 closed M15 bars, clustered within 1 x    |
//| ATR(M15, 14) (a cluster spans <= 2 ATR), >= 2 touches, widened by |
//| 0.15 ATR, overlaps merged while <= 2.5 ATR wide.                  |
//| Sends a zone map with a short analysis at 01:30, 08:00 and 15:00  |
//| server time (and at the first shift of the day), and a chart when |
//| the price enters a zone from outside (one alert per zone area per |
//| 4 hours, 01:30-22:00). The entry / SL / TP ideas are labelled as  |
//| untested: on 6.6 years of gold, zone entries had PF 0.87-1.00     |
//| (random entries 0.94; research/srzones.py, capped zones).         |
//| Events go to MQL5\Files\sr_events.txt (forwarded to Telegram).    |
//+------------------------------------------------------------------+
input string InpSrSymbol      = "XAUUSD";
input bool   InpSrOn          = true;
input bool   InpSrMapOnStart  = false;      // one map when the EA starts (the workflow sets it for the first shift of the day)
input int    InpSrLookback    = 480;        // closed M15 bars (5 days)
input int    InpSrCooldownMin = 240;

string   sr_sym = "";
bool     sr_ready = false, sr_startMap = false;
datetime sr_bar = 0, sr_lastTry = 0;
double   sr_lo[], sr_hi[];
int      sr_cnt[];
double   sr_atr = 0, sr_prevClose = 0;
double   sr_aMid[];
datetime sr_aTime[];
int      sr_mapKey = 0;
int      sr_h50 = INVALID_HANDLE, sr_h200 = INVALID_HANDLE, sr_h450 = INVALID_HANDLE, sr_h4200 = INVALID_HANDLE;
string   SR_NOTE = "Not a tested edge: zone entries on 6.6 years of gold had PF 0.87-1.00 (random entries 0.94). Info only, no auto trade";

void SrEvent(string msg)
{
   int h = FileOpen("sr_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("sr event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("SR EVENT ", msg);
}

double SrBuf(int handle, int shift)
{
   double b[];
   if(handle == INVALID_HANDLE || CopyBuffer(handle, 0, shift, 1, b) < 1) return 0;
   return b[0];
}

int SrTrend(int hf, int hs)
{
   double a = SrBuf(hf, 1), b = SrBuf(hs, 1);
   if(a <= 0 || b <= 0) return 0;
   return a > b ? 1 : -1;
}

string SrTrendTxt(int t) { return t > 0 ? "UP" : (t < 0 ? "DOWN" : "-"); }
string SrP(double v)     { return PriceStr(sr_sym, v); }

void SrCompute()
{
   MqlRates r[];
   int n = CopyRates(sr_sym, PERIOD_M15, 1, InpSrLookback, r);       // r[0] oldest, r[n-1] the last closed bar
   ArrayResize(sr_lo, 0); ArrayResize(sr_hi, 0); ArrayResize(sr_cnt, 0);
   if(n < 100) return;
   // ATR(14) with Wilder smoothing, as in the research (pandas ewm alpha 1/14)
   double atr = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   sr_atr = atr;
   sr_prevClose = r[n - 1].close;
   if(sr_atr <= 0) return;
   double p[]; int m = 0;
   for(int i = 2; i < n - 2; i++)                                      // fractals, confirmed by 2 closed bars
   {
      if(r[i].high > MathMax(MathMax(r[i - 2].high, r[i - 1].high), MathMax(r[i + 1].high, r[i + 2].high))) { ArrayResize(p, m + 1); p[m++] = r[i].high; }
      if(r[i].low < MathMin(MathMin(r[i - 2].low, r[i - 1].low), MathMin(r[i + 1].low, r[i + 2].low)))     { ArrayResize(p, m + 1); p[m++] = r[i].low; }
   }
   if(m < 2) return;
   ArraySort(p);
   double cl[], ch[]; int cc[]; int k = 0;
   double sum = p[0], mn = p[0], mx = p[0]; int cnt = 1;
   for(int i = 1; i <= m; i++)
   {
      if(i < m && p[i] - sum / cnt <= sr_atr && p[i] - mn <= 2 * sr_atr) { sum += p[i]; cnt++; mx = p[i]; continue; }
      if(cnt >= 2) { ArrayResize(cl, k + 1); ArrayResize(ch, k + 1); ArrayResize(cc, k + 1); cl[k] = mn - 0.15 * sr_atr; ch[k] = mx + 0.15 * sr_atr; cc[k] = cnt; k++; }
      if(i < m) { sum = p[i]; mn = p[i]; mx = p[i]; cnt = 1; }
   }
   for(int i = 0; i < k; i++)                                          // merge overlaps (cl is sorted) while <= 2.5 ATR wide
   {
      int z = ArraySize(sr_lo);
      double lo = cl[i];
      if(z > 0 && cl[i] <= sr_hi[z - 1])
      {
         if(MathMax(sr_hi[z - 1], ch[i]) - sr_lo[z - 1] <= 2.5 * sr_atr) { sr_hi[z - 1] = MathMax(sr_hi[z - 1], ch[i]); sr_cnt[z - 1] += cc[i]; continue; }
         lo = (cl[i] + sr_hi[z - 1]) / 2;                               // too wide: split in the middle of the overlap
         sr_hi[z - 1] = lo;
      }
      ArrayResize(sr_lo, z + 1); ArrayResize(sr_hi, z + 1); ArrayResize(sr_cnt, z + 1);
      sr_lo[z] = lo; sr_hi[z] = ch[i]; sr_cnt[z] = cc[i];
   }
}

string SrZ(int i) { return StringFormat("%s-%s (%dx)", SrP(sr_lo[i]), SrP(sr_hi[i]), sr_cnt[i]); }

// the nearest zones above / below a price (up to nmax), nearest first
string SrList(double px, bool above, int nmax)
{
   string s = ""; int got = 0;
   if(above) { for(int i = 0; i < ArraySize(sr_lo) && got < nmax; i++) if(sr_lo[i] > px) { s += (s == "" ? "" : ", ") + SrZ(i); got++; } }
   else      { for(int i = ArraySize(sr_lo) - 1; i >= 0 && got < nmax; i--) if(sr_hi[i] < px) { s += (s == "" ? "" : ", ") + SrZ(i); got++; } }
   return s == "" ? "none in the last 5 days" : s;
}

void SrText(long cid, string nm, datetime t, double price, string txt, color c, int anchor)
{
   ObjectCreate(cid, nm, OBJ_TEXT, 0, t, price);
   ObjectSetString(cid, nm, OBJPROP_TEXT, txt);
   ObjectSetInteger(cid, nm, OBJPROP_COLOR, c);
   ObjectSetInteger(cid, nm, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(cid, nm, OBJPROP_ANCHOR, anchor);
}

// M15 chart with the zones (resistance red, support green, the alerted zone darker) and optional idea lines
string SrSnap(string tag, int active, double &lv[], color &lc[], string &lb[])
{
   MqlRates r[];
   int n = CopyRates(sr_sym, PERIOD_M15, 0, 200, r);                 // about what the picture shows
   if(n < 20) return "";
   double px = SymbolInfoDouble(sr_sym, SYMBOL_BID);
   double vlo = px, vhi = px;
   for(int i = 0; i < n; i++) { vlo = MathMin(vlo, r[i].low); vhi = MathMax(vhi, r[i].high); }
   for(int i = 0; i < ArraySize(lv); i++) if(lv[i] > 0) { vlo = MathMin(vlo, lv[i]); vhi = MathMax(vhi, lv[i]); }
   int z = ArraySize(sr_lo);
   for(int i = 0; i < z; i++)                                          // show at least the nearest zone above and below
   {
      if(sr_hi[i] < vlo && sr_hi[i] > vlo - 6 * sr_atr && (i == z - 1 || sr_lo[i + 1] >= vlo)) vlo = sr_lo[i];
      if(sr_lo[i] > vhi && sr_lo[i] < vhi + 6 * sr_atr && (i == 0 || sr_hi[i - 1] <= vhi)) vhi = sr_hi[i];
   }
   double pad = (vhi - vlo) * 0.04;
   long cid = ChartOpen(sr_sym, PERIOD_M15);
   if(cid == 0) { Print("sr snap: ChartOpen failed ", GetLastError()); return ""; }
   ChartSetInteger(cid, CHART_MODE, CHART_CANDLES); ChartSetInteger(cid, CHART_SHOW_GRID, false);
   ChartSetInteger(cid, CHART_AUTOSCROLL, true); ChartSetInteger(cid, CHART_SHIFT, true); ChartSetDouble(cid, CHART_SHIFT_SIZE, 18);
   ChartSetInteger(cid, CHART_SCALE, 2);
   ChartSetInteger(cid, CHART_SHOW_VOLUMES, CHART_VOLUME_HIDE); ChartSetInteger(cid, CHART_SHOW_ASK_LINE, false);
   ChartSetInteger(cid, CHART_SHOW_TRADE_LEVELS, false); ChartSetInteger(cid, CHART_SHOW_TRADE_HISTORY, false);   // the account's own orders
   ChartSetInteger(cid, CHART_COLOR_BACKGROUND, clrWhite); ChartSetInteger(cid, CHART_COLOR_FOREGROUND, clrBlack);
   ChartSetInteger(cid, CHART_COLOR_CANDLE_BULL, clrSeaGreen); ChartSetInteger(cid, CHART_COLOR_CANDLE_BEAR, clrIndianRed);
   ChartSetInteger(cid, CHART_COLOR_CHART_UP, clrSeaGreen); ChartSetInteger(cid, CHART_COLOR_CHART_DOWN, clrIndianRed);
   ChartSetInteger(cid, CHART_COLOR_CHART_LINE, clrDimGray); ChartSetInteger(cid, CHART_COLOR_BID, clrDimGray);
   ChartSetInteger(cid, CHART_SCALEFIX, true);
   ChartSetDouble(cid, CHART_FIXED_MAX, vhi + pad); ChartSetDouble(cid, CHART_FIXED_MIN, vlo - pad);
   datetime t0 = r[0].time - 100 * 900, t1 = TimeCurrent() + 2 * 86400, tl = r[n - 1].time + 2 * 900;
   for(int i = 0; i < z; i++)
   {
      if(sr_hi[i] < vlo - pad || sr_lo[i] > vhi + pad) continue;
      bool res = sr_lo[i] > px, sup = sr_hi[i] < px;
      color c = res ? (i == active ? C'250,160,160' : (i % 2 == 0 ? C'255,218,218' : C'255,200,200'))     // neighbours alternate shades
                    : (sup ? (i == active ? C'140,215,160' : (i % 2 == 0 ? C'210,240,216' : C'190,232,200')) : C'255,228,170');
      string nm = "sr_z" + IntegerToString(i);
      ObjectCreate(cid, nm, OBJ_RECTANGLE, 0, t0, sr_hi[i], t1, sr_lo[i]);
      ObjectSetInteger(cid, nm, OBJPROP_COLOR, c); ObjectSetInteger(cid, nm, OBJPROP_FILL, true); ObjectSetInteger(cid, nm, OBJPROP_BACK, true);
      SrText(cid, "sr_t" + IntegerToString(i), tl, sr_hi[i], (res ? "R " : (sup ? "S " : "")) + SrZ(i),
             res ? clrFireBrick : (sup ? clrDarkGreen : clrDarkGoldenrod), ANCHOR_LEFT_LOWER);
   }
   for(int i = 0; i < ArraySize(lv); i++)
   {
      if(lv[i] <= 0) continue;
      color c = i < ArraySize(lc) ? lc[i] : clrBlue;
      string lab = i < ArraySize(lb) ? lb[i] : "";
      SnapLine(cid, "sr_l" + IntegerToString(i), lv[i], c, lab);
      ObjectSetInteger(cid, "sr_l" + IntegerToString(i), OBJPROP_WIDTH, 2);
      SrText(cid, "sr_lt" + IntegerToString(i), tl, lv[i], lab + " " + SrP(lv[i]), c, ANCHOR_LEFT_UPPER);   // under the line, right margin
   }
   ChartRedraw(cid); Sleep(2000); ChartRedraw(cid);
   string fn = SnapName(tag, sr_sym);
   bool ok = ChartScreenShot(cid, fn, 1000, 620, ALIGN_RIGHT);
   if(!ok) Print("sr snap: ChartScreenShot failed ", GetLastError());
   ChartClose(cid);
   return ok ? fn : "";
}

void SrMap(string why, string tag)
{
   double px = SymbolInfoDouble(sr_sym, SYMBOL_BID);
   int t1 = SrTrend(sr_h50, sr_h200), t4 = SrTrend(sr_h450, sr_h4200);
   string view;
   if(t1 > 0 && t4 >= 0)      view = "Bias: uptrend. Buy ideas at support after an M15 close back above the zone; sell only after an M15 close below a support zone";
   else if(t1 < 0 && t4 <= 0) view = "Bias: downtrend. Sell ideas at resistance after an M15 close back below the zone; buy only after an M15 close above a resistance zone";
   else                       view = "Bias: mixed (H1 and H4 disagree). Zones are weaker; wait for a clear M15 close through a zone";
   string inside = "";
   for(int i = 0; i < ArraySize(sr_lo); i++) if(px >= sr_lo[i] && px <= sr_hi[i]) inside = " | Price is inside the zone " + SrZ(i);
   double none[]; color nc[]; string nl[];
   string fn = SrSnap(tag, -1, none, nc, nl);
   SrEvent(StringFormat("SR ZONE MAP %s | %s | Price %s, H1 trend %s, H4 trend %s, ATR(M15) %s%s | Resistance: %s | Support: %s | %s | %s",
                        sr_sym, why, SrP(px), SrTrendTxt(t1), SrTrendTxt(t4), SrP(sr_atr), inside,
                        SrList(px, true, 3), SrList(px, false, 3), view, SR_NOTE) + Img(fn));
}

void SrInit()
{
   sr_ready = true;
   sr_sym = SymResolve(InpSrSymbol);
   if(sr_sym == "") { Print("SR: symbol not found ", InpSrSymbol); return; }
   SymbolSelect(sr_sym, true);
   sr_h50 = iMA(sr_sym, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE); sr_h200 = iMA(sr_sym, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);
   sr_h450 = iMA(sr_sym, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE); sr_h4200 = iMA(sr_sym, PERIOD_H4, 200, 0, MODE_EMA, PRICE_CLOSE);
   sr_startMap = InpSrMapOnStart;
   SrEvent(StringFormat("SR ONLINE | %s M15 zones (last 5 days, >= 2 touches): map at 01:30, 08:00 and 15:00 server, "
                        "chart when the price enters a zone (01:30-22:00) | alerts only, no trading", sr_sym));
}

void SrOnTimer()
{
   if(!InpSrOn) return;
   if(!sr_ready) SrInit();
   if(sr_sym == "") return;
   MqlTick tk;
   if(!SymbolInfoTick(sr_sym, tk) || TimeCurrent() - tk.time > 600) return;   // market closed
   MqlDateTime st; TimeToStruct(TimeCurrent(), st);
   if(st.day_of_week == 0 || st.day_of_week == 6) return;
   datetime b = iTime(sr_sym, PERIOD_M15, 0);
   if(b != sr_bar || (ArraySize(sr_lo) == 0 && TimeCurrent() - sr_lastTry >= 30))
   {
      sr_bar = b; sr_lastTry = TimeCurrent();
      SrCompute();
   }
   if(ArraySize(sr_lo) == 0 || sr_atr <= 0) return;
   int minute = st.hour * 60 + st.min;
   int key = st.day_of_year * 10000 + minute;
   if((minute == 90 || minute == 480 || minute == 900) && sr_mapKey != key)
   {
      sr_mapKey = key; sr_startMap = false;
      SrMap(minute == 90 ? "Day start" : (minute == 480 ? "London open" : "Before New York"), "SRM");
      return;
   }
   if(sr_startMap) { sr_startMap = false; SrMap("Today's map", "SRM"); return; }
   if(minute < 90 || minute >= 1320) return;
   double px = tk.bid, a = sr_atr;
   for(int i = 0; i < ArraySize(sr_lo); i++)
   {
      bool sup = sr_prevClose > sr_hi[i] && px <= sr_hi[i] && px >= sr_lo[i] - a;     // coming down into support
      bool res = sr_prevClose < sr_lo[i] && px >= sr_lo[i] && px <= sr_hi[i] + a;     // coming up into resistance
      if(!sup && !res) continue;
      double mid = (sr_lo[i] + sr_hi[i]) / 2;
      bool recent = false;
      for(int q = ArraySize(sr_aMid) - 1; q >= 0; q--)
      {
         if(TimeCurrent() - sr_aTime[q] > InpSrCooldownMin * 60) { ArrayRemove(sr_aMid, q, 1); ArrayRemove(sr_aTime, q, 1); continue; }
         if(MathAbs(sr_aMid[q] - mid) < a) recent = true;
      }
      if(recent) continue;
      int m = ArraySize(sr_aMid); ArrayResize(sr_aMid, m + 1); ArrayResize(sr_aTime, m + 1); sr_aMid[m] = mid; sr_aTime[m] = TimeCurrent();
      int t1 = SrTrend(sr_h50, sr_h200);
      string ctx, idea, brk, next;
      double lv[3]; color lc[3]; string lb[3];
      if(sup)
      {
         double en = sr_hi[i], sl = sr_lo[i] - 0.3 * a, tp = en + 2 * (en - sl);
         double bsl = sr_hi[i] + 0.3 * a, btp = sr_lo[i] - 2 * (bsl - sr_lo[i]);
         ctx  = t1 > 0 ? "H1 trend UP: support with the trend" : (t1 < 0 ? "H1 trend DOWN: support against the trend (weaker)" : "H1 trend flat");
         idea = StringFormat("Idea BUY: only after an M15 close back above %s. Entry %s, SL %s, TP %s (2R)", SrP(en), SrP(en), SrP(sl), SrP(tp));
         brk  = StringFormat("If an M15 bar closes below %s (zone broken): SELL idea, SL %s, TP %s (2R)", SrP(sr_lo[i]), SrP(bsl), SrP(btp));
         next = "Next resistance: " + SrList(sr_hi[i], true, 1);
         lv[0] = en; lc[0] = clrRoyalBlue; lb[0] = "BUY idea";
         lv[1] = sl; lc[1] = clrRed;       lb[1] = "SL";
         lv[2] = tp; lc[2] = clrGreen;     lb[2] = "TP 2R";
      }
      else
      {
         double en = sr_lo[i], sl = sr_hi[i] + 0.3 * a, tp = en - 2 * (sl - en);
         double bsl = sr_lo[i] - 0.3 * a, btp = sr_hi[i] + 2 * (sr_hi[i] - bsl);
         ctx  = t1 < 0 ? "H1 trend DOWN: resistance with the trend" : (t1 > 0 ? "H1 trend UP: resistance against the trend (weaker)" : "H1 trend flat");
         idea = StringFormat("Idea SELL: only after an M15 close back below %s. Entry %s, SL %s, TP %s (2R)", SrP(en), SrP(en), SrP(sl), SrP(tp));
         brk  = StringFormat("If an M15 bar closes above %s (zone broken): BUY idea, SL %s, TP %s (2R)", SrP(sr_hi[i]), SrP(bsl), SrP(btp));
         next = "Next support: " + SrList(sr_lo[i], false, 1);
         lv[0] = en; lc[0] = clrRoyalBlue; lb[0] = "SELL idea";
         lv[1] = sl; lc[1] = clrRed;       lb[1] = "SL";
         lv[2] = tp; lc[2] = clrGreen;     lb[2] = "TP 2R";
      }
      string fn = SrSnap("SRZ", i, lv, lc, lb);
      SrEvent(StringFormat("SR PRICE IN %s ZONE %s | Price %s entered %s | %s | %s | %s | %s | %s", sup ? "SUPPORT" : "RESISTANCE", sr_sym,
                           SrP(px), SrZ(i), ctx, idea, brk, next, SR_NOTE) + Img(fn));
      break;                                                             // one alert per check
   }
}
//+------------------------------------------------------------------+
