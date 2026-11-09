//+------------------------------------------------------------------+
//| FizyLEG.mqh - gold M1 LEG FADE, the owner's own rule, demo only, |
//| included by FizyLB.mq5.  v2.10 (9 Nov): the first entry needs the|
//| price at least InpLegMinDist ($8) beyond EMA 50 (owner chose     |
//| round 69 row 3: "jarak ema terlalu dekat").                      |
//| v2.06: lots 1/1/2/2/3 x base by entry   |
//| number (owner's order; round 56f).  v2.05: no EMA side filter.   |
//| v2.04 (6 Nov 2026): TP = price touches                           |
//| EMA 50 (whole basket, closed by the EA), owner's order. v2.03:    |
//| the zigzag runs on                                               |
//| WICKS (low of the bottom candle, high of the top candle), the     |
//| owner's way of counting ("kira dari wick"). v2.02: age 60 -> 20,  |
//| the owner's order ("kekerapan dia dalam range 20-23 candle").     |
//| Tested first (round 56c, research/legfade56.py): age 20 PF 0.80,  |
//| $100 account stopped out 95 times in the last 12 months.          |
//|                                                                  |
//| THE OWNER'S ORDER (6 Nov): "ea akan baca pergerakan bilangan     |
//| candle di m1, buat range. jika dah sampai tahap max, entry. jika |
//| naik lagi entry lagi. TP di max perjalanan seterusnya. tiada sl" |
//| He chose: fade the leg (SELL an up leg, BUY a down leg), at most  |
//| 5 entries of the same lot (no doubling). Built on his explicit    |
//| instruction although it has no stop loss and round 55 found no    |
//| edge in leg age; round 56 (research/legfade56.py) tests this exact |
//| rule on a $100 account, see CLAUDE.md.                             |
//|                                                                  |
//| RULES                                                            |
//|  leg     online zigzag of InpLegPct (0.10%, ~$4) on today's       |
//|          closed M1 highs / lows (server day): a leg starts at the |
//|          lowest wick (up) or highest wick (down)                  |
//|  entry   when the current leg is InpLegAge (60) candles old       |
//|          (round 54: 90% of legs are shorter), fade it at market,  |
//|          01:30-22:00 server, weekdays, only when no LEG position  |
//|          is open                                                  |
//|  adds    every time price runs another InpLegPct beyond the LAST  |
//|          entry, one more in the same direction, up to InpLegMax   |
//|  TP      each position InpLegTpPct (0.35%, ~$14) back the other   |
//|          way: round 54's 90th-percentile leg size                 |
//|  SL      NONE (owner's order). No time exit; holds overnight and  |
//|          pays swap. Only the broker's stop-out limits the loss.   |
//| Events go to MQL5\Files\leg_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpLegOn     = true;
input string InpLegSymbol = "XAUUSD";
input double InpLegLot    = 0.01;
input long   InpLegMagic  = 260321;
input double InpLegPct    = 0.10;     // zigzag reversal and add step, % of price
input int    InpLegAge    = 20;       // leg age in M1 candles that triggers the first entry (60 until 6 Nov evening)
input double InpLegTpPct  = 0.35;     // fixed TP distance, % of price (only when InpLegTpEma = 0)
input bool   InpLegEmaSide = false;   // v2.05: entries no longer need the EMA on the far side (owner: the EMA is only the TP)
input int    InpLegTpEma  = 50;       // v2.04: close the whole basket when price touches this EMA(M1); 0 = fixed TP
input int    InpLegMax    = 5;        // most positions open at once
input double InpLegMinDist = 8.0;     // v2.10: fade only when the last close is at least this $ beyond EMA 50 (0 = off)
input string InpLegMult   = "1,1,2,2,3"; // v2.06: lot of entry 1..5 = InpLegLot x this (owner: bigger lots from entry 3 to cover the floating ones)

string   lg_sym = "";
bool     lg_ready = false;
datetime lg_bar = 0;
ulong    lg_known[];
int      lg_ema = INVALID_HANDLE;

void LegEvent(string msg)
{
   int h = FileOpen("leg_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("leg event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("LEG EVENT ", msg);
}

// open LEG positions: count, direction of the basket (+1 buy / -1 sell) and the price of the newest entry
int LegBasket(int &dir, double &last)
{
   int n = 0; datetime newest = 0; dir = 0; last = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpLegMagic || PositionGetString(POSITION_SYMBOL) != lg_sym) continue;
      n++;
      bool known = false;
      for(int q = 0; q < ArraySize(lg_known); q++) if(lg_known[q] == t) known = true;
      if(!known) { int m = ArraySize(lg_known); ArrayResize(lg_known, m + 1); lg_known[m] = t; }
      dir = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);
      if(ot >= newest) { newest = ot; last = PositionGetDouble(POSITION_PRICE_OPEN); }
   }
   return n;
}

void LegInit()
{
   lg_ready = true;
   lg_sym = SymResolve(InpLegSymbol);
   if(lg_sym == "") { LegEvent("ERROR | M1 leg fade: symbol " + InpLegSymbol + " not found"); return; }
   SymbolSelect(lg_sym, true);
   if(InpLegTpEma > 0) lg_ema = iMA(lg_sym, PERIOD_M1, InpLegTpEma, 0, MODE_EMA, PRICE_CLOSE);
   int dir; double last;
   int n = LegBasket(dir, last);
   LegEvent(StringFormat("LEG ONLINE | %s M1: a %.2f%% zigzag leg %d candles old is faded at market; another entry "
                         "every %.2f%% further, up to %d; %s; NO stop loss (owner's rule), "
                         "lot %.2f | %d open position(s)", lg_sym, InpLegPct, InpLegAge, InpLegPct, InpLegMax,
                         InpLegTpEma > 0 ? StringFormat("only when price is at least $%.2f beyond EMA %d; TP when price touches the EMA", InpLegMinDist, InpLegTpEma) : StringFormat("TP %.2f%% back per position", InpLegTpPct),
                         InpLegLot, n));
}

void LegReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1, typ = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { inPx = HistoryDealGetDouble(d, DEAL_PRICE); typ = HistoryDealGetInteger(d, DEAL_TYPE); }
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = reason == DEAL_REASON_TP ? "LEG TP HIT" : (reason == DEAL_REASON_SO ? "LEG STOP OUT" : "LEG CLOSED");
   string why = reason == DEAL_REASON_TP ? "take profit" : (reason == DEAL_REASON_SO ? "broker stop-out, margin gone"
              : (reason == DEAL_REASON_EXPERT ? StringFormat("price touched EMA %d", InpLegTpEma) : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(lg_sym, PERIOD_M1, "LGX", lv, lc, lb, 0, 0, 0, 0, false);
   LegEvent(StringFormat("%s %s | %s from %s closed at %s (%s), profit $%.2f", what, lg_sym, typ == DEAL_TYPE_BUY ? "BUY" : "SELL",
                         PriceStr(lg_sym, inPx), PriceStr(lg_sym, outPx), why, profit) + Img(fn));
}

double LegEma()                                                                // EMA of the last CLOSED M1 bar
{
   double v[];
   if(lg_ema == INVALID_HANDLE || CopyBuffer(lg_ema, 0, 1, 1, v) != 1) return 0;
   return v[0];
}

bool LegOpen(int dir, int num, string why)
{
   if(DayPaused()) return false;                                        // daily target reached: no first entry, no adds
   MqlTick tk;
   if(!SymbolInfoTick(lg_sym, tk)) return false;
   int dg = (int)SymbolInfoInteger(lg_sym, SYMBOL_DIGITS);
   double px = dir == 1 ? tk.ask : tk.bid;
   double tp = InpLegTpEma > 0 ? 0 : NormalizeDouble(px * (1.0 + dir * InpLegTpPct / 100.0), dg);   // EMA mode: the EA closes
   double mn = SymbolInfoDouble(lg_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(lg_sym, SYMBOL_VOLUME_STEP);
   string mp[]; double mult = 1;
   int nm = StringSplit(InpLegMult, ',', mp);
   if(num >= 1 && num <= nm) mult = StringToDouble(mp[num - 1]);
   if(mult <= 0) mult = 1;
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpLegLot * mult / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpLegMagic); trade.SetTypeFillingBySymbol(lg_sym);
   bool ok = dir == 1 ? trade.Buy(lot, lg_sym, 0, 0, tp, "LEG " + IntegerToString(num))
                      : trade.Sell(lot, lg_sym, 0, 0, tp, "LEG " + IntegerToString(num));
   if(!ok) LegEvent(StringFormat("ERROR | leg %s order failed: %d %s", lg_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return false;
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = px; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = tp > 0 ? tp : LegEma(); lc[1] = clrSeaGreen; lb[1] = tp > 0 ? "TP" : "EMA";
   string fn = Snap(lg_sym, PERIOD_M1, "LGE", lv, lc, lb, 0, 0, 0, 0, false);
   LegEvent(StringFormat("LEG %s %s | entry %d of %d | %s | %s %.2f lot at %s, %s, no SL", dir == 1 ? "BUY" : "SELL",
                         lg_sym, num, InpLegMax, why, dir == 1 ? "BUY" : "SELL", lot, PriceStr(lg_sym, px),
                         tp > 0 ? "TP " + PriceStr(lg_sym, tp) : StringFormat("TP at the EMA %d touch (now %s)", InpLegTpEma, PriceStr(lg_sym, LegEma()))) + Img(fn));
   return true;
}

void LegOnTimer()
{
   if(!InpLegOn) return;
   if(!lg_ready) LegInit();
   if(lg_sym == "") return;
   for(int q = ArraySize(lg_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(lg_known[q])) { LegReportClosed(lg_known[q]); ArrayRemove(lg_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(lg_sym, tk) || now - tk.time > 600) return;              // market closed
   MqlDateTime ns; TimeToStruct(now, ns);
   int nowhm = ns.hour * 60 + ns.min;
   int dir; double last;
   int n = LegBasket(dir, last);

   // ---- TP at the EMA (v2.04): the whole basket closes when the closing price side touches the EMA
   if(n > 0 && InpLegTpEma > 0)
   {
      double ev = LegEma();
      if(ev > 0 && ((dir == -1 && tk.ask <= ev) || (dir == 1 && tk.bid >= ev)))
      {
         trade.SetExpertMagicNumber(InpLegMagic); trade.SetTypeFillingBySymbol(lg_sym);
         for(int i = PositionsTotal() - 1; i >= 0; i--)
         {
            ulong t = PositionGetTicket(i);
            if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpLegMagic || PositionGetString(POSITION_SYMBOL) != lg_sym) continue;
            if(!trade.PositionClose(t)) LegEvent(StringFormat("ERROR | leg close %s failed: %d %s", lg_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         }
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
         return;
      }
   }

   // ---- adds: price has run another step beyond the newest entry, against the basket
   if(n > 0 && n < InpLegMax && nowhm >= 90 && nowhm < 1425 && last > 0)
   {
      double step = last * InpLegPct / 100.0;
      if((dir == -1 && tk.bid >= last + step) || (dir == 1 && tk.ask <= last - step))
      {
         LegOpen(dir, n + 1, StringFormat("price ran another %.2f%% beyond the last entry %s", InpLegPct, PriceStr(lg_sym, last)));
         return;
      }
   }

   // ---- first entry: once per new M1 bar, rebuild today's zigzag from the closed bars
   datetime b0 = iTime(lg_sym, PERIOD_M1, 0);
   if(b0 == 0 || b0 == lg_bar) return;
   MqlDateTime d0; TimeToStruct(b0, d0); d0.hour = 0; d0.min = 0; d0.sec = 0;
   datetime dayStart = StructToTime(d0);
   MqlRates r[];
   int m = CopyRates(lg_sym, PERIOD_M1, dayStart, b0 - 1, r);                   // today's closed bars
   if(m < 2) { lg_bar = b0; return; }
   lg_bar = b0;
   double pct = InpLegPct / 100.0;
   int d_ = 0, ext = 0, piv = 0, lo0 = 0, hi0 = 0;
   bool fired = false, fireNow = false;
   for(int k = 1; k < m; k++)                                                    // same order as research/legfade56.py (wick mode)
   {
      fireNow = false;
      if(d_ == 0)
      {
         if(r[k].low < r[lo0].low) lo0 = k;
         if(r[k].high > r[hi0].high) hi0 = k;
         if(r[k].high >= r[lo0].low * (1 + pct)) { d_ = 1; piv = lo0; ext = k; fired = false; }
         else if(r[k].low <= r[hi0].high * (1 - pct)) { d_ = -1; piv = hi0; ext = k; fired = false; }
         continue;
      }
      if(d_ == 1)
      {
         if(r[k].high > r[ext].high) ext = k;
         else if(r[k].low <= r[ext].high * (1 - pct)) { piv = ext; d_ = -1; ext = k; fired = false; continue; }
      }
      else
      {
         if(r[k].low < r[ext].low) ext = k;
         else if(r[k].high >= r[ext].low * (1 + pct)) { piv = ext; d_ = 1; ext = k; fired = false; continue; }
      }
      if(!fired && k - piv >= InpLegAge) { fired = true; fireNow = true; }
   }
   int j = m - 1;
   if(!fireNow) return;                                                         // fires once per leg, the bar it turns 60
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(n > 0 || st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1320) return;
   if(InpLegTpEma > 0 && InpLegEmaSide)                                         // optional: EMA on the far side (off: owner, 6 Nov)
   {
      double ev = LegEma();
      if(ev <= 0 || (d_ == 1 && r[j].close <= ev) || (d_ == -1 && r[j].close >= ev)) return;
   }
   if(InpLegTpEma > 0 && InpLegMinDist > 0)                                     // v2.10: EMA far enough away to pay
   {
      double ev = LegEma();
      double dist = d_ == 1 ? r[j].close - ev : ev - r[j].close;               // up leg -> sell above the EMA, down leg -> buy below
      if(ev <= 0 || dist < InpLegMinDist) return;
   }
   double pivPx = d_ == 1 ? r[piv].low : r[piv].high;
   double move = MathAbs(r[j].close - pivPx);
   LegOpen(-d_, 1, StringFormat("the %s leg from %s is %d candles old (+%s), faded", d_ == 1 ? "UP" : "DOWN",
                                PriceStr(lg_sym, pivPx), j - piv, DoubleToString(move, 2)));
}
//+------------------------------------------------------------------+
