//+------------------------------------------------------------------+
//| SignalCheck: no trading. Recomputes the RSI2 H1 rules on the     |
//| closed H1 bars of today for every symbol and lists the signals,   |
//| plus the latest values and price freshness. Closes the terminal.  |
//+------------------------------------------------------------------+
#property strict
input string InpSyms = "BTCUSD,XAUUSD,EURUSD,GBPUSD,AUDUSD,NZDUSD,USDJPY,USDCHF,USDCAD,EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,EURNZD,GBPJPY,GBPCHF,GBPAUD,GBPCAD,GBPNZD,AUDJPY,AUDCHF,AUDCAD,AUDNZD,NZDJPY,NZDCHF,NZDCAD,CADJPY,CADCHF,CHFJPY";
int n = 0;
int OnInit() { EventSetTimer(3); return(INIT_SUCCEEDED); }
void OnDeinit(const int r) { EventKillTimer(); }
string Res(string b) { string c[] = {"", ".m"}; bool cu; for(int i = 0; i < 2; i++) if(SymbolExist(b + c[i], cu)) return b + c[i]; return ""; }
void OnTimer()
{
   n++;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) && n < 40) return;
   if(n < 8) return;                                     // give the history a few seconds to load
   EventKillTimer();
   int h = FileOpen("signal_check.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   datetime now = TimeCurrent();
   MqlDateTime d; TimeToStruct(now, d); d.hour = 0; d.min = 0; d.sec = 0; datetime day = StructToTime(d) - 86400;   // yesterday 00:00
   FileWriteString(h, "server time " + TimeToString(now, TIME_DATE | TIME_MINUTES) + "; signals on closed H1 bars since " + TimeToString(day, TIME_DATE) + "\r\n");
   int pos = 0; for(int i = PositionsTotal() - 1; i >= 0; i--) { ulong t = PositionGetTicket(i); if(t > 0 && PositionGetInteger(POSITION_MAGIC) == 260309) pos++; }
   FileWriteString(h, StringFormat("open RSI2 positions (magic 260309): %d\r\n", pos));
   string parts[]; int k = StringSplit(InpSyms, ',', parts);
   for(int j = 0; j < k; j++)
   {
      string s = Res(parts[j]); if(s == "") { FileWriteString(h, parts[j] + ": not found\r\n"); continue; }
      SymbolSelect(s, true);
      MqlRates r[]; int m = CopyRates(s, PERIOD_H1, 1, 300, r);
      if(m < 215) { FileWriteString(h, StringFormat("%s: only %d H1 bars\r\n", s, m)); continue; }
      double up = 0, dn = 0, rsi[]; ArrayResize(rsi, m); rsi[0] = 50;
      for(int i = 1; i < m; i++) { double x = r[i].close - r[i - 1].close; up = 0.5 * MathMax(x, 0) + 0.5 * up; dn = 0.5 * MathMax(-x, 0) + 0.5 * dn; rsi[i] = dn == 0 ? 100 : 100 - 100 / (1 + up / dn); }
      string sig = "";
      for(int i = 200; i < m; i++)
      {
         if(r[i].time < day) continue;
         double s200 = 0; for(int q = i - 199; q <= i; q++) s200 += r[q].close; s200 /= 200;
         if(r[i].close > s200 && rsi[i] < 10) sig += StringFormat(" BUY@%s(rsi %.1f)", TimeToString(r[i].time, TIME_DATE | TIME_MINUTES), rsi[i]);
         if(r[i].close < s200 && rsi[i] > 90) sig += StringFormat(" SELL@%s(rsi %.1f)", TimeToString(r[i].time, TIME_DATE | TIME_MINUTES), rsi[i]);
      }
      double s200 = 0; for(int q = m - 200; q < m; q++) s200 += r[q].close; s200 /= 200;
      MqlTick tk; bool hasT = SymbolInfoTick(s, tk);
      FileWriteString(h, StringFormat("%s: last bar %s close %s %s SMA200, RSI2 %.1f, tick age %d min%s\r\n", s,
                      TimeToString(r[m - 1].time, TIME_DATE | TIME_MINUTES), DoubleToString(r[m - 1].close, (int)SymbolInfoInteger(s, SYMBOL_DIGITS)),
                      r[m - 1].close > s200 ? "above" : "below", rsi[m - 1], hasT ? (int)((now - tk.time) / 60) : -1, sig == "" ? " | no signal" : " | SIGNALS:" + sig));
   }
   FileClose(h);
   TerminalClose(0);
}
