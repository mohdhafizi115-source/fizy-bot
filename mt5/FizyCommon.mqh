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

//+------------------------------------------------------------------+
//| DAILY PROFIT TARGET (v2.07, owner 8 Nov: "target ea hanya 25     |
//| dollar sehari. lepas achive dalam sehari tu, pausekan ea sambung |
//| ke esok pulak"). Today's REALISED profit of every EA trade (magic |
//| 260300-260399, profit + swap + commission of closing deals since |
//| 00:00 server = 06:00 MYT in winter) reaching InpDayTarget stops   |
//| NEW entries in every module until the next server day. Open       |
//| positions keep their own exits (SL / TP / EMA / time).            |
//+------------------------------------------------------------------+
input double InpDayTarget = 25.0;        // $; 0 = no daily target

datetime dt_day = 0;          // server day the flags below belong to
bool     dt_hit = false;
datetime dt_last = 0;
double   dt_pnl = 0;

double DayRealised()
{
   MqlDateTime s; TimeToStruct(TimeCurrent(), s); s.hour = 0; s.min = 0; s.sec = 0;
   datetime d0 = StructToTime(s);
   if(!HistorySelect(d0, TimeCurrent() + 60)) return 0;
   double p = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      long mg = HistoryDealGetInteger(d, DEAL_MAGIC);
      if(mg < 260300 || mg > 260399) continue;
      long en = HistoryDealGetInteger(d, DEAL_ENTRY);
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY && en != DEAL_ENTRY_INOUT) continue;
      p += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
   }
   return p;
}

void DayEvent(string msg)
{
   int h = FileOpen("flb_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("EVENT ", msg);
}

// call once a minute from OnTimer, and before every new entry
bool DayPaused()
{
   if(InpDayTarget <= 0) return false;
   MqlDateTime s; TimeToStruct(TimeCurrent(), s); s.hour = 0; s.min = 0; s.sec = 0;
   datetime d0 = StructToTime(s);
   if(d0 != dt_day) { dt_day = d0; dt_hit = false; dt_last = 0; }
   if(dt_hit) return true;
   if(TimeCurrent() - dt_last >= 20)                                   // re-read the history at most every 20 s
   {
      dt_last = TimeCurrent();
      dt_pnl = DayRealised();
      if(dt_pnl >= InpDayTarget)
      {
         dt_hit = true;
         DayEvent(StringFormat("DAILY TARGET REACHED | today's closed profit $%.2f >= $%.2f: no new trades until 06:00 MYT "
                               "tomorrow (00:00 server); open positions keep their own exits", dt_pnl, InpDayTarget));
         return true;
      }
   }
   return false;
}
