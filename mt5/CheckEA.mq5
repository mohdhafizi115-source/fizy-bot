//+------------------------------------------------------------------+
//| CheckEA: read-only check that an EA runs in the terminal on the  |
//| GitHub Windows runner. Writes account / symbol facts to a file   |
//| (no account number, no balance) and closes the terminal.         |
//+------------------------------------------------------------------+
#property strict
input string InpSymbol = "XAUUSD.m";
int ticks = 0;

int OnInit() { EventSetTimer(2); return(INIT_SUCCEEDED); }
void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
{
   ticks++;
   bool conn = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   if(!conn && ticks < 120) return;                // wait up to 4 minutes for the connection
   SymbolSelect(InpSymbol, true);
   MqlTick tk; bool hasTick = SymbolInfoTick(InpSymbol, tk);
   int h = FileOpen("mt5_ea_check.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, StringFormat("EA ran: yes, connected %d after %d s\r\n", conn, ticks * 2));
      FileWriteString(h, StringFormat("server %s, demo %d, company %s\r\n", AccountInfoString(ACCOUNT_SERVER),
                      AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO, AccountInfoString(ACCOUNT_COMPANY)));
      FileWriteString(h, StringFormat("algo trading: terminal %d, account %d, expert %d, program %d\r\n",
                      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED), AccountInfoInteger(ACCOUNT_TRADE_ALLOWED),
                      AccountInfoInteger(ACCOUNT_TRADE_EXPERT), MQLInfoInteger(MQL_TRADE_ALLOWED)));
      FileWriteString(h, StringFormat("balance > 0: %d, currency %s, leverage 1:%d, margin mode %d\r\n",
                      AccountInfoDouble(ACCOUNT_BALANCE) > 0, AccountInfoString(ACCOUNT_CURRENCY),
                      AccountInfoInteger(ACCOUNT_LEVERAGE), AccountInfoInteger(ACCOUNT_MARGIN_MODE)));
      FileWriteString(h, StringFormat("%s: tick %d bid %.2f ask %.2f, digits %d, stops level %d, freeze %d, vol min %.2f step %.2f, filling %d, contract %.0f\r\n",
                      InpSymbol, hasTick, tk.bid, tk.ask, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS),
                      (int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL), (int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_FREEZE_LEVEL),
                      SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN), SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP),
                      (int)SymbolInfoInteger(InpSymbol, SYMBOL_FILLING_MODE), SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_CONTRACT_SIZE)));
      FileWriteString(h, StringFormat("server time %s, GMT %s (server offset %+d h)\r\n", TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
                      TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS), (int)MathRound((TimeCurrent() - TimeGMT()) / 3600.0)));
      FileClose(h);
   }
   EventKillTimer();
   TerminalClose(0);
}
//+------------------------------------------------------------------+
