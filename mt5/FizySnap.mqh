//+------------------------------------------------------------------+
//| FizySnap.mqh - MT5 chart screenshots for the Telegram events.     |
//| Opens a temporary chart, draws the levels (and the Asian range or |
//| the RSI2 indicators), saves a PNG to MQL5\Files and closes it.     |
//| The event line then ends with " | IMG:<file>" and the workflow    |
//| watcher sends the picture with the message.                       |
//+------------------------------------------------------------------+
string SnapName(string tag, string sym)
{
   string t = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS);
   StringReplace(t, ".", ""); StringReplace(t, ":", ""); StringReplace(t, " ", "_");
   string s = sym; StringReplace(s, ".", "_");
   return StringFormat("snap_%s_%s_%s_%d.png", tag, s, t, (int)(GetTickCount() % 1000));
}

void SnapLine(long cid, string name, double price, color c, string text)
{
   if(price <= 0) return;
   ObjectCreate(cid, name, OBJ_HLINE, 0, 0, price);
   ObjectSetInteger(cid, name, OBJPROP_COLOR, c);
   ObjectSetInteger(cid, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(cid, name, OBJPROP_WIDTH, 1);
   ObjectSetString(cid, name, OBJPROP_TEXT, text);
}

// BBMA template drawn on the snapshot (v2.22, owner: "chart pasangkan template bbma terus"):
// BB 20,2 (population sd, as MT5's Bands), LWMA 5 / 10 of the highs and of the lows, EMA 50, EMA 90.
// Drawn as trend-line segments, so the colours are fixed and no .tpl file is needed on the runner.
bool g_snap_bbma = true;

void SnapSeg(long cid, string name, datetime t0, double v0, datetime t1, double v1, color c, int w, int style)
{
   if(v0 <= 0 || v1 <= 0) return;
   ObjectCreate(cid, name, OBJ_TREND, 0, t0, v0, t1, v1);
   ObjectSetInteger(cid, name, OBJPROP_COLOR, c);
   ObjectSetInteger(cid, name, OBJPROP_WIDTH, w);
   ObjectSetInteger(cid, name, OBJPROP_STYLE, style);
   ObjectSetInteger(cid, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(cid, name, OBJPROP_RAY_LEFT, false);
   ObjectSetInteger(cid, name, OBJPROP_BACK, true);
   ObjectSetInteger(cid, name, OBJPROP_SELECTABLE, false);
}

void SnapBBMA(long cid, string sym, ENUM_TIMEFRAMES tf)
{
   MqlRates r[];
   int n = CopyRates(sym, tf, 0, 500, r);
   if(n < 120) return;
   double mid[], top[], bot[], e50[], e90[], h5[], h10[], l5[], l10[];
   ArrayResize(mid, n); ArrayResize(top, n); ArrayResize(bot, n); ArrayResize(e50, n); ArrayResize(e90, n);
   ArrayResize(h5, n); ArrayResize(h10, n); ArrayResize(l5, n); ArrayResize(l10, n);
   ArrayInitialize(mid, 0); ArrayInitialize(top, 0); ArrayInitialize(bot, 0);
   ArrayInitialize(h5, 0); ArrayInitialize(h10, 0); ArrayInitialize(l5, 0); ArrayInitialize(l10, 0);
   e50[0] = r[0].close; e90[0] = r[0].close;
   for(int i = 1; i < n; i++)
   {
      e50[i] = e50[i - 1] + 2.0 / 51.0 * (r[i].close - e50[i - 1]);
      e90[i] = e90[i - 1] + 2.0 / 91.0 * (r[i].close - e90[i - 1]);
   }
   for(int i = 19; i < n; i++)
   {
      double s = 0, s2 = 0;
      for(int q = i - 19; q <= i; q++) { s += r[q].close; s2 += r[q].close * r[q].close; }
      double m = s / 20.0, sd = MathSqrt(MathMax(s2 / 20.0 - m * m, 0));
      mid[i] = m; top[i] = m + 2 * sd; bot[i] = m - 2 * sd;
   }
   for(int i = 9; i < n; i++)
   {
      double a5 = 0, b5 = 0, w5 = 0, a10 = 0, b10 = 0, w10 = 0;
      for(int q = 0; q < 10; q++)
      {
         double w = 10 - q; a10 += w * r[i - q].high; b10 += w * r[i - q].low; w10 += w;
         if(q < 5) { double v = 5 - q; a5 += v * r[i - q].high; b5 += v * r[i - q].low; w5 += v; }
      }
      h5[i] = a5 / w5; l5[i] = b5 / w5; h10[i] = a10 / w10; l10[i] = b10 / w10;
   }
   int from = MathMax(100, n - 220);
   for(int i = from; i < n; i++)
   {
      datetime t0 = r[i - 1].time, t1 = r[i].time; string k = IntegerToString(i);
      SnapSeg(cid, "bb_t" + k, t0, top[i - 1], t1, top[i], clrDimGray, 1, STYLE_SOLID);
      SnapSeg(cid, "bb_b" + k, t0, bot[i - 1], t1, bot[i], clrDimGray, 1, STYLE_SOLID);
      SnapSeg(cid, "bb_m" + k, t0, mid[i - 1], t1, mid[i], clrDarkGray, 1, STYLE_DOT);
      SnapSeg(cid, "ma_h5" + k, t0, h5[i - 1], t1, h5[i], clrMediumVioletRed, 1, STYLE_SOLID);
      SnapSeg(cid, "ma_h10" + k, t0, h10[i - 1], t1, h10[i], clrMediumVioletRed, 1, STYLE_SOLID);
      SnapSeg(cid, "ma_l5" + k, t0, l5[i - 1], t1, l5[i], clrDarkCyan, 1, STYLE_SOLID);
      SnapSeg(cid, "ma_l10" + k, t0, l10[i - 1], t1, l10[i], clrDarkCyan, 1, STYLE_SOLID);
      SnapSeg(cid, "ema50_" + k, t0, e50[i - 1], t1, e50[i], clrRoyalBlue, 2, STYLE_SOLID);
      SnapSeg(cid, "ema90_" + k, t0, e90[i - 1], t1, e90[i], clrDarkOrange, 2, STYLE_SOLID);
   }
   ObjectCreate(cid, "bbma_legend", OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(cid, "bbma_legend", OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(cid, "bbma_legend", OBJPROP_XDISTANCE, 8);
   ObjectSetInteger(cid, "bbma_legend", OBJPROP_YDISTANCE, 24);   // an object text holds at most 63 characters
   ObjectSetInteger(cid, "bbma_legend", OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(cid, "bbma_legend", OBJPROP_FONTSIZE, 8);
   ObjectSetString(cid, "bbma_legend", OBJPROP_TEXT, "BBMA* BB20 grey, MA5/10 purple/teal, EMA50 blue, EMA90 orange");   // * = drawn as objects
}

// levels[] / colors[] / labels[]: horizontal lines; r0..r1 / rhi..rlo: shaded box (0 = none);
// rsi = add SMA 200, SMA 5 and RSI(2) like the RSI2 rules
string Snap(string sym, ENUM_TIMEFRAMES tf, string tag, double &levels[], color &colors[], string &labels[],
            datetime r0, datetime r1, double rhi, double rlo, bool rsi)
{
   long cid = ChartOpen(sym, tf);
   if(cid == 0) { Print("snap: ChartOpen failed ", GetLastError()); return ""; }
   ChartSetInteger(cid, CHART_MODE, CHART_CANDLES);
   ChartSetInteger(cid, CHART_SHOW_GRID, false);
   ChartSetInteger(cid, CHART_AUTOSCROLL, true);
   ChartSetInteger(cid, CHART_SHIFT, true);
   ChartSetInteger(cid, CHART_SCALE, 3);
   ChartSetInteger(cid, CHART_SHOW_VOLUMES, CHART_VOLUME_HIDE);
   ChartSetInteger(cid, CHART_SHOW_ASK_LINE, false);
   ChartSetInteger(cid, CHART_COLOR_BACKGROUND, clrWhite);
   ChartSetInteger(cid, CHART_COLOR_FOREGROUND, clrBlack);
   ChartSetInteger(cid, CHART_COLOR_CANDLE_BULL, clrSeaGreen);
   ChartSetInteger(cid, CHART_COLOR_CANDLE_BEAR, clrIndianRed);
   ChartSetInteger(cid, CHART_COLOR_CHART_UP, clrSeaGreen);
   ChartSetInteger(cid, CHART_COLOR_CHART_DOWN, clrIndianRed);
   ChartSetInteger(cid, CHART_COLOR_CHART_LINE, clrDimGray);
   ChartSetInteger(cid, CHART_COLOR_BID, clrDimGray);
   if(rsi)
   {
      int h200 = iMA(sym, tf, 200, 0, MODE_SMA, PRICE_CLOSE);
      int h5   = iMA(sym, tf, 5, 0, MODE_SMA, PRICE_CLOSE);
      int hr   = iRSI(sym, tf, 2, PRICE_CLOSE);
      if(h200 != INVALID_HANDLE) ChartIndicatorAdd(cid, 0, h200);
      if(h5 != INVALID_HANDLE)   ChartIndicatorAdd(cid, 0, h5);
      if(hr != INVALID_HANDLE)   ChartIndicatorAdd(cid, 1, hr);
   }
   if(!rsi && g_snap_bbma)
   {
      int hb = iCustom(sym, tf, "FizyBBMA");                    // v2.24: the BBMA lines as an indicator (objects did not show live)
      if(hb == INVALID_HANDLE || !ChartIndicatorAdd(cid, 0, hb))
      {
         Print("snap: FizyBBMA indicator unavailable (", GetLastError(), "), drawing the lines as objects");
         SnapBBMA(cid, sym, tf);
      }
      else
      {
         ObjectCreate(cid, "bbma_legend", OBJ_LABEL, 0, 0, 0);
         ObjectSetInteger(cid, "bbma_legend", OBJPROP_CORNER, CORNER_LEFT_UPPER);
         ObjectSetInteger(cid, "bbma_legend", OBJPROP_XDISTANCE, 8);
         ObjectSetInteger(cid, "bbma_legend", OBJPROP_YDISTANCE, 24);
         ObjectSetInteger(cid, "bbma_legend", OBJPROP_COLOR, clrBlack);
         ObjectSetInteger(cid, "bbma_legend", OBJPROP_FONTSIZE, 8);
         ObjectSetString(cid, "bbma_legend", OBJPROP_TEXT, "BBMA: BB20 grey, MA5/10 purple/teal, EMA50 blue, EMA90 orange");
      }
      int ha = iATR(sym, tf, 14);
      if(ha != INVALID_HANDLE) ChartIndicatorAdd(cid, 1, ha);
   }
   if(r1 > r0 && rhi > rlo)
   {
      ObjectCreate(cid, "snap_box", OBJ_RECTANGLE, 0, r0, rhi, r1, rlo);
      ObjectSetInteger(cid, "snap_box", OBJPROP_COLOR, clrLightSteelBlue);
      ObjectSetInteger(cid, "snap_box", OBJPROP_FILL, true);
      ObjectSetInteger(cid, "snap_box", OBJPROP_BACK, true);
   }
   for(int i = 0; i < ArraySize(levels); i++)
      SnapLine(cid, "snap_l" + IntegerToString(i), levels[i], i < ArraySize(colors) ? colors[i] : clrBlue, i < ArraySize(labels) ? labels[i] : "");
   ChartRedraw(cid);
   Sleep(g_snap_bbma && !rsi ? 3000 : 2000);     // let the chart load its bars, indicators and the BBMA lines
   ChartRedraw(cid);
   string fn = SnapName(tag, sym);
   bool ok = ChartScreenShot(cid, fn, 1000, g_snap_bbma && !rsi ? 720 : 620, ALIGN_RIGHT);
   if(!ok) Print("snap: ChartScreenShot failed ", GetLastError());
   ChartClose(cid);
   return ok ? fn : "";
}

string Img(string fn) { return fn == "" ? "" : " | IMG:" + fn; }
//+------------------------------------------------------------------+
