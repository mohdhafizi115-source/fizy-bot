//+------------------------------------------------------------------+
//| FizyCommon.mqh - helpers shared by the FizyLB modules:           |
//| broker symbol names, price formatting, London time, and the      |
//| silent clean-up of positions left by removed modules (RSI2).     |
//+------------------------------------------------------------------+

// broker name for a plain symbol: try the plain name and common suffixes
string SymResolve(string base)
{
   string cands[] = { "", ".m", "m", ".", "#", ".pro", ".std", ".ecn", ".r" };
   for(int i = 0; i < ArraySize(cands); i++)
   {
      string n = base + cands[i];
      bool custom;
      if(SymbolExist(n, custom)) return n;
   }
   return "";
}

string PriceStr(string s, double v) { return DoubleToString(v, (int)SymbolInfoInteger(s, SYMBOL_DIGITS)); }

int CmnDim(int y, int m)
{
   if(m == 2) return ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0) ? 29 : 28;
   if(m == 4 || m == 6 || m == 9 || m == 11) return 30;
   return 31;
}

// 00:00 UTC of the last Sunday of a month
datetime CmnLastSunday(int y, int m)
{
   MqlDateTime d; d.year = y; d.mon = m; d.day = CmnDim(y, m); d.hour = 0; d.min = 0; d.sec = 0;
   datetime t = StructToTime(d);
   MqlDateTime x; TimeToStruct(t, x);
   return t - x.day_of_week * 86400;
}

// London local time from the computer's UTC clock (BST from the last Sunday of March to the last Sunday of October, 01:00 UTC)
datetime LondonTime()
{
   datetime g = TimeGMT();
   MqlDateTime d; TimeToStruct(g, d);
   datetime a = CmnLastSunday(d.year, 3) + 3600, b = CmnLastSunday(d.year, 10) + 3600;
   return g + ((g >= a && g < b) ? 3600 : 0);
}

// RSI2 was removed on 1 Nov 2026 (it lost on 6.6 years of broker data). Close anything it may have left open, silently.
#define RSI2_OLD_MAGIC 260309
datetime cm_lastClean = 0;
void CloseLeftovers()
{
   if(TimeCurrent() - cm_lastClean < 60) return;
   cm_lastClean = TimeCurrent();
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != RSI2_OLD_MAGIC) continue;
      string s = PositionGetString(POSITION_SYMBOL);
      MqlTick tk;
      if(!SymbolInfoTick(s, tk) || TimeCurrent() - tk.time > 300) continue;   // market closed
      trade.SetTypeFillingBySymbol(s);
      if(trade.PositionClose(t)) Print("old RSI2 position closed: ", s);
      trade.SetTypeFillingBySymbol(InpSymbol);
   }
}
//+------------------------------------------------------------------+
