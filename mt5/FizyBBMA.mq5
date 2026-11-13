//+------------------------------------------------------------------+
//| FizyBBMA.mq5 - the BBMA template as one indicator with fixed      |
//| colours, for the Telegram chart screenshots (v2.24, 13 Nov 2026). |
//| BB 20,2 (population sd, as MT5's Bands) grey, LWMA 5 / 10 of the   |
//| highs purple and of the lows teal, EMA 50 blue, EMA 90 orange.     |
//| v2.22 drew these as trend-line objects; on the live shift's charts |
//| the objects did not show (13 Nov USDJPY snap), an indicator does.  |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_buffers 9
#property indicator_plots   9
#property indicator_type1  DRAW_LINE
#property indicator_color1 clrDimGray
#property indicator_label1 "BB top"
#property indicator_type2  DRAW_LINE
#property indicator_color2 clrDarkGray
#property indicator_style2 STYLE_DOT
#property indicator_label2 "BB mid"
#property indicator_type3  DRAW_LINE
#property indicator_color3 clrDimGray
#property indicator_label3 "BB bottom"
#property indicator_type4  DRAW_LINE
#property indicator_color4 clrMediumVioletRed
#property indicator_label4 "LWMA 5 high"
#property indicator_type5  DRAW_LINE
#property indicator_color5 clrMediumVioletRed
#property indicator_label5 "LWMA 10 high"
#property indicator_type6  DRAW_LINE
#property indicator_color6 clrDarkCyan
#property indicator_label6 "LWMA 5 low"
#property indicator_type7  DRAW_LINE
#property indicator_color7 clrDarkCyan
#property indicator_label7 "LWMA 10 low"
#property indicator_type8  DRAW_LINE
#property indicator_color8 clrRoyalBlue
#property indicator_width8 2
#property indicator_label8 "EMA 50"
#property indicator_type9  DRAW_LINE
#property indicator_color9 clrDarkOrange
#property indicator_width9 2
#property indicator_label9 "EMA 90"

double bTop[], bMid[], bBot[], h5[], h10[], l5[], l10[], e50[], e90[];

int OnInit()
{
   SetIndexBuffer(0, bTop); SetIndexBuffer(1, bMid); SetIndexBuffer(2, bBot);
   SetIndexBuffer(3, h5); SetIndexBuffer(4, h10); SetIndexBuffer(5, l5); SetIndexBuffer(6, l10);
   SetIndexBuffer(7, e50); SetIndexBuffer(8, e90);
   for(int p = 0; p < 9; p++) PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   PlotIndexSetInteger(0, PLOT_DRAW_BEGIN, 19); PlotIndexSetInteger(1, PLOT_DRAW_BEGIN, 19); PlotIndexSetInteger(2, PLOT_DRAW_BEGIN, 19);
   for(int p = 3; p < 7; p++) PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, 9);
   IndicatorSetString(INDICATOR_SHORTNAME, "BBMA");
   return INIT_SUCCEEDED;
}

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   if(rates_total < 20) return 0;
   int start = prev_calculated > 1 ? prev_calculated - 1 : 0;
   for(int i = start; i < rates_total; i++)
   {
      if(i == 0) { e50[i] = close[i]; e90[i] = close[i]; }
      else
      {
         e50[i] = e50[i - 1] + 2.0 / 51.0 * (close[i] - e50[i - 1]);
         e90[i] = e90[i - 1] + 2.0 / 91.0 * (close[i] - e90[i - 1]);
      }
      if(i >= 19)
      {
         double s = 0, s2 = 0;
         for(int q = i - 19; q <= i; q++) { s += close[q]; s2 += close[q] * close[q]; }
         double m = s / 20.0, sd = MathSqrt(MathMax(s2 / 20.0 - m * m, 0));
         bMid[i] = m; bTop[i] = m + 2 * sd; bBot[i] = m - 2 * sd;
      }
      else { bMid[i] = EMPTY_VALUE; bTop[i] = EMPTY_VALUE; bBot[i] = EMPTY_VALUE; }
      if(i >= 9)
      {
         double a5 = 0, b5 = 0, w5 = 0, a10 = 0, b10 = 0, w10 = 0;
         for(int q = 0; q < 10; q++)
         {
            double w = 10 - q; a10 += w * high[i - q]; b10 += w * low[i - q]; w10 += w;
            if(q < 5) { double v = 5 - q; a5 += v * high[i - q]; b5 += v * low[i - q]; w5 += v; }
         }
         h5[i] = a5 / w5; l5[i] = b5 / w5; h10[i] = a10 / w10; l10[i] = b10 / w10;
      }
      else { h5[i] = EMPTY_VALUE; l5[i] = EMPTY_VALUE; h10[i] = EMPTY_VALUE; l10[i] = EMPTY_VALUE; }
   }
   return rates_total;
}
//+------------------------------------------------------------------+
