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
   Sleep(2000);                                  // let the chart load its bars and indicators
   ChartRedraw(cid);
   string fn = SnapName(tag, sym);
   bool ok = ChartScreenShot(cid, fn, 1000, 620, ALIGN_RIGHT);
   if(!ok) Print("snap: ChartScreenShot failed ", GetLastError());
   ChartClose(cid);
   return ok ? fn : "";
}

string Img(string fn) { return fn == "" ? "" : " | IMG:" + fn; }
//+------------------------------------------------------------------+
