//+------------------------------------------------------------------+
//| ExportCal: no trading. Writes the MQL5 economic calendar history  |
//| (moderate and high importance events: actual, forecast, previous, |
//| impact on the currency) from InpFrom to MQL5\Files\cal\           |
//| calendar.csv, then closes the terminal. Calendar times are trade  |
//| server time (same clock as the M5 export).                        |
//+------------------------------------------------------------------+
#property strict
input datetime InpFrom = D'2020.01.01 00:00';

int  n = 0;
bool done = false;

int OnInit() { EventSetTimer(3); return(INIT_SUCCEEDED); }
void OnDeinit(const int r) { EventKillTimer(); }

string V(long x) { return x == LONG_MIN ? "" : DoubleToString(x / 1000000.0, 6); }

string Clean(string s) { StringReplace(s, "\"", "'"); StringReplace(s, ",", ";"); return s; }

void OnTimer()
{
   n++;
   if(done) return;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) && n < 80) return;
   if(n < 6) return;
   MqlCalendarValue v[];
   ResetLastError();
   int k = CalendarValueHistory(v, InpFrom, TimeTradeServer() + 7 * 86400);
   if(k <= 0 && n < 140) { if(n % 10 == 0) Print("calendar not ready yet, error ", GetLastError()); return; }
   done = true;
   EventKillTimer();
   FolderCreate("cal");
   int h = FileOpen("cal\\calendar.csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
   FileWriteString(h, "id,event_id,time,period,revision,actual,forecast,prev,revised_prev,impact,importance,currency,country,event_code,name,unit,multiplier,type,sector\n");
   int kept = 0;
   for(int i = 0; i < k; i++)
   {
      MqlCalendarEvent e;
      if(!CalendarEventById(v[i].event_id, e)) continue;
      if(e.importance < CALENDAR_IMPORTANCE_MODERATE) continue;
      MqlCalendarCountry c;
      if(!CalendarCountryById(e.country_id, c)) continue;
      FileWriteString(h, StringFormat("%I64u,%I64u,%I64d,%I64d,%d,%s,%s,%s,%s,%d,%d,%s,%s,%s,%s,%d,%d,%d,%d\n",
                      v[i].id, v[i].event_id, (long)v[i].time, (long)v[i].period, v[i].revision,
                      V(v[i].actual_value), V(v[i].forecast_value), V(v[i].prev_value), V(v[i].revised_prev_value),
                      (int)v[i].impact_type, (int)e.importance, c.currency, c.code, Clean(e.event_code), Clean(e.name),
                      (int)e.unit, (int)e.multiplier, (int)e.type, (int)e.sector));
      kept++;
   }
   FileClose(h);
   int m = FileOpen("cal\\meta.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   FileWriteString(m, StringFormat("calendar values %d, kept (moderate/high) %d, from %s, server time %s, server offset %+d h, error %d\r\n",
                   k, kept, TimeToString(InpFrom, TIME_DATE), TimeToString(TimeTradeServer(), TIME_DATE | TIME_MINUTES),
                   (int)MathRound((TimeTradeServer() - TimeGMT()) / 3600.0), GetLastError()));
   FileClose(m);
   TerminalClose(0);
}
//+------------------------------------------------------------------+
