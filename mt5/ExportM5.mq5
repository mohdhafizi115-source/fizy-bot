//+------------------------------------------------------------------+
//| ExportM5: no trading. Loads the broker's M5 history for every    |
//| symbol in InpSyms from InpFrom and writes one CSV per symbol to  |
//| MQL5\Files\m5data\ (epoch server time, OHLC, tick volume, spread |
//| in points) plus meta.txt, then closes the terminal.              |
//+------------------------------------------------------------------+
#property strict
input string   InpSyms = "XAUUSD,BTCUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,EURNZD,GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY";
input datetime InpFrom = D'2020.01.01 00:00';
input int      InpSymTimeout = 300;                    // seconds per symbol for the history download

int  n = 0;
bool busy = false;

int OnInit() { EventSetTimer(3); return(INIT_SUCCEEDED); }
void OnDeinit(const int r) { EventKillTimer(); }

string Res(string b)
{
   string c[] = {"", ".m", "m", ".a", "_m"}; bool cu;
   for(int i = 0; i < ArraySize(c); i++) if(SymbolExist(b + c[i], cu)) return b + c[i];
   return "";
}

// history loader after the MQL5 documentation pattern "Organizing Data Access", with a deadline
int LoadHistory(string s, ENUM_TIMEFRAMES tf, datetime start, uint deadline)
{
   datetime first = 0, times[100];
   SymbolSelect(s, true);
   if(SeriesInfoInteger(s, tf, SERIES_FIRSTDATE, first) && first > 0 && first <= start) return 1;
   if(SeriesInfoInteger(s, PERIOD_M1, SERIES_TERMINAL_FIRSTDATE, first) && first > 0)
   {
      CopyTime(s, tf, first + PeriodSeconds(tf), 1, times);
      if(SeriesInfoInteger(s, tf, SERIES_FIRSTDATE, first) && first > 0 && first <= start) return 2;
   }
   int maxb = (int)TerminalInfoInteger(TERMINAL_MAXBARS);
   datetime srv = 0;
   while(!SeriesInfoInteger(s, PERIOD_M1, SERIES_SERVER_FIRSTDATE, srv) && GetTickCount() < deadline && !IsStopped()) Sleep(50);
   if(srv > start) start = srv;
   int fail = 0;
   while(GetTickCount() < deadline && !IsStopped())
   {
      while(!SeriesInfoInteger(s, tf, SERIES_SYNCHRONIZED) && GetTickCount() < deadline && !IsStopped()) Sleep(20);
      int bars = Bars(s, tf);
      if(bars > 0)
      {
         if(bars >= maxb) return -2;
         if(SeriesInfoInteger(s, tf, SERIES_FIRSTDATE, first) && first > 0 && first <= start) return 0;
      }
      int got = CopyTime(s, tf, bars, 100, times);
      if(got > 0)
      {
         if(times[0] <= start) return 0;
         if(bars + got >= maxb) return -2;
         fail = 0;
      }
      else
      {
         fail++;
         if(fail >= 300) return -5;
         Sleep(50);
      }
   }
   return -3;
}

void OnTimer()
{
   n++;
   if(busy) return;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) && n < 80) return;
   if(n < 6) return;
   busy = true;
   EventKillTimer();
   FolderCreate("m5data");
   int mh = FileOpen("m5data\\meta.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   FileWriteString(mh, StringFormat("connected %d, max bars %d, from %s\r\n", (int)TerminalInfoInteger(TERMINAL_CONNECTED),
                   (int)TerminalInfoInteger(TERMINAL_MAXBARS), TimeToString(InpFrom, TIME_DATE)));
   FileWriteString(mh, "base,symbol,digits,point,tick_size,tick_value,contract,load_code,bars,first,last,median_spread_pts\r\n");
   string parts[]; int k = StringSplit(InpSyms, ',', parts);
   for(int j = 0; j < k; j++)
   {
      string s = Res(parts[j]);
      if(s == "") { FileWriteString(mh, parts[j] + ",not found\r\n"); FileFlush(mh); continue; }
      SymbolSelect(s, true);
      int code = LoadHistory(s, PERIOD_M5, InpFrom, GetTickCount() + (uint)InpSymTimeout * 1000);
      MqlRates r[];
      int m = -1;
      for(int t = 0; t < 10 && m <= 0; t++) { m = CopyRates(s, PERIOD_M5, InpFrom, TimeCurrent(), r); if(m <= 0) Sleep(1000); }
      if(m > 0)
      {
         int fh = FileOpen("m5data\\" + parts[j] + ".csv", FILE_WRITE | FILE_TXT | FILE_ANSI);
         int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
         FileWriteString(fh, "t,o,h,l,c,v,s\n");
         for(int i = 0; i < m; i++)
            FileWriteString(fh, StringFormat("%I64d,%s,%s,%s,%s,%I64d,%d\n", (long)r[i].time, DoubleToString(r[i].open, dg),
                            DoubleToString(r[i].high, dg), DoubleToString(r[i].low, dg), DoubleToString(r[i].close, dg),
                            r[i].tick_volume, r[i].spread));
         FileClose(fh);
      }
      int sp[]; ArrayResize(sp, MathMax(m, 1)); sp[0] = 0;
      for(int i = 0; i < m; i++) sp[i] = r[i].spread;
      if(m > 0) ArraySort(sp);
      FileWriteString(mh, StringFormat("%s,%s,%d,%s,%s,%s,%.0f,%d,%d,%s,%s,%d\r\n", parts[j], s, (int)SymbolInfoInteger(s, SYMBOL_DIGITS),
                      DoubleToString(SymbolInfoDouble(s, SYMBOL_POINT), 8), DoubleToString(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE), 8),
                      DoubleToString(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE), 6), SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE),
                      code, m, m > 0 ? TimeToString(r[0].time, TIME_DATE | TIME_MINUTES) : "-",
                      m > 0 ? TimeToString(r[m - 1].time, TIME_DATE | TIME_MINUTES) : "-", m > 0 ? sp[m / 2] : -1));
      FileFlush(mh);
   }
   FileClose(mh);
   int dh = FileOpen("m5data\\done.txt", FILE_WRITE | FILE_TXT | FILE_ANSI); FileWriteString(dh, "done\r\n"); FileClose(dh);
   TerminalClose(0);
}
//+------------------------------------------------------------------+
