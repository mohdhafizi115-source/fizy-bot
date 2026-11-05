//+------------------------------------------------------------------+
//| FizySPK.mqh - gold M1 spike fade, demo only, included by          |
//| FizyLB.mq5. The first M1 rule that ever passed on this broker's   |
//| own data (research/scalpcost37.py, spike38.py, spike39.py;        |
//| spk44.py, spk45.py; JustMarkets M1 2020-03 .. 2026-11, at the     |
//| v1.98 settings 2,230 trades, 1.31 a day: PF 1.34 after spread,    |
//| halves 1.47 / 1.33, stress 1.27, +$1,445 per 0.01 lot, last 12    |
//| months +$1,049, max drawdown $162 (recovered in 2 days), 44 of    |
//| 75 months positive, every year 1.09 or better and 2022 at 1.65,   |
//| so it is not just the gold uptrend.                               |
//| Rules, all on closed M1 bars:                                     |
//|   1. COST GATE: ATR(14, M1) >= InpSpkAtrSpread x the current      |
//|      spread. This gate is what makes the rule work - on M1 the    |
//|      move has to dwarf the cost. Its sweep is monotone, which is  |
//|      the signature of a real cost effect and not a fitted filter: |
//|      gate 4 / 6 / 8 / 10 / 12 -> PF 1.13 / 1.21 / 1.34 / 1.44 /  |
//|      1.50 at k 2.5. Round 42 also checked that it works FORWARD   |
//|      rather than in hindsight: ATR now against ATR in 20 minutes  |
//|      correlates 0.945, and against the next 20 minutes' range     |
//|      0.692, so a volatile minute really does predict volatile     |
//|      minutes after it.                                            |
//|   2. SIGNAL: the bar that just closed fell (close < open) and its |
//|      range >= InpSpkAtr x ATR(14, M1 up to the bar before it).    |
//|   3. BUY at the next bar's open. SL = that bar's low - 0.2 ATR.   |
//|      NO take profit; out after 45 minutes (v1.97, see below).     |
//|   Signal bars 01:30-22:00 server, one position at a time.         |
//| Only the BUY side is traded: fading UP spikes scored PF 0.92 and  |
//| lost money, so it is left out.                                    |
//| v1.98 (round 45, research/spk45.py) lowered InpSpkAtr from 3.0 to |
//| 2.5, which doubles the trade rate, on the owner's call: "asalkan  |
//| aku nak ea trade banyak kali dan profit". k 2.5 is a SUPERSET of  |
//| k 3.0, so its headline +$1,445 already contains the +$1,163 that  |
//| k 3.0 made, and a plateau sweep could not settle this. What       |
//| decided it was measuring each spike-size band ON ITS OWN, with no |
//| overlap, so no band could borrow another's profit:                |
//|   2.0-2.5 ATR  3,352 trades  PF 0.96  -$193   <- the floor        |
//|   2.5-3.0 ATR  1,195 trades  PF 1.17  +$351   <- what k 2.5 adds  |
//|   3.0-3.5 ATR    500 trades  PF 1.89  +$763   <- the real edge    |
//|   3.5-4.0 ATR    228 trades  PF 1.14  +$61                        |
//|   4.0-5.0 ATR    197 trades  PF 0.89  -$54                        |
//| So the band k 2.5 adds does carry its own edge and this is not    |
//| just more exposure - but it is a THIN one: PF 1.17 against a 1.15 |
//| threshold, stress 1.10 against 1.05, and on its own it draws down |
//| $256 and never recovers, on $351 of profit. It only works blended |
//| with the strong 3.0-3.5 core, which fills its gaps: the blend     |
//| draws down $162 and recovers in 2 days, and its profit per dollar |
//| of drawdown is 8.9 against 8.1 for k 3.0 alone. Below 2.5 the     |
//| next band LOSES, so 2.5 is the floor, not a step on a ramp.       |
//| The cost of the change: PF 1.53 -> 1.34 and the longest losing    |
//| run goes from 27 trades to 36. The owner was shown both and chose |
//| the trade count. Set InpSpkAtr back to 3.0 to undo it.            |
//| Plateau at k 2.5: SL 0.1-0.75 ATR -> 1.23-1.34, hold 20-120 min   |
//| -> 1.26-1.38, gate 6-16 -> 1.21-1.50 and monotone to 12; all of   |
//| them pass. Controls: random 0.84-1.21, the UP side 0.95, and the  |
//| 2.5-3.0 band on the UP side 0.96. The one-position-at-a-time rule |
//| discards only 2.7% of signals, so the hold is not the limit.      |
//| v1.97 (round 44, research/spk44.py) REMOVED the take profit.      |
//| Round 42 measured that under the cost gate gold's variance ratio  |
//| keeps falling out to 60 minutes (0.96 at 1 min -> 0.845 at 60),   |
//| so the reversion was still running when the old TP cut it off.    |
//| The TP sweep is unambiguous: 0.5 / 0.75 / 1.0 x the spike range   |
//| give PF 1.30 / 1.39 / 1.33, while 1.5 / 2 / 3 / 5 / none give     |
//| 1.49 / 1.47 / 1.51 / 1.53 / 1.53. The old 0.75 sat in the WORST   |
//| zone. The hold plateau is wide: 30 / 45 / 60 / 90 / 120 min give  |
//| 1.51 / 1.53 / 1.55 / 1.64 / 1.58; 45 was taken instead of the     |
//| 90-minute peak because its halves are level (1.54 / 1.53) and     |
//| every single year is 1.06 or better. The SL plateau still peaks   |
//| where it was: 0.1 / 0.2 / 0.3 ATR give 1.48 / 1.53 / 1.54.        |
//| Net effect: PF 1.37 -> 1.53, +$675 -> +$1,163 per 0.01 lot, last  |
//| 12 months +$519 -> +$933. The price: win rate 30% -> 20%, a       |
//| deeper drawdown (-$87 -> -$144, but it recovered in 20 days       |
//| instead of 84) and longer losing runs (15 -> 27 in a row).        |
//| Random entries with the same mechanics score 0.72-1.25 and the UP |
//| side 0.91, so neither control survives.                           |
//| v1.99 (6 Nov, the owner's explicit override) trades for FREQUENCY |
//| and a high win rate instead of profit: k 2.0 and TP 0.5 x the     |
//| spike range. He was shown three options with full numbers and     |
//| chose this one knowing it FAILS the project's pass rule:          |
//|   PF 1.08 (threshold 1.15) and stress 0.99 (threshold 1.05).      |
//|   Halves 1.12 / 1.08 pass, 5,750 trades = 3.37 a day, win rate    |
//|   37.4%, 48 of 80 months positive, +$535 over 6.7 years = about   |
//|   $80 a year per 0.01 lot, max drawdown -$200.                    |
//| What it replaced (v1.98, k 2.5 / no TP): PF 1.34, +$216 a year,    |
//| win 17.3%, drawdown -$162. So this choice costs about 62% of the  |
//| profit to buy 2.6x the trades and a win rate that feels like      |
//| scalping. His words, repeatedly: "aku nak scalping, untung makan  |
//| sikit-sikit ... 1 hari aku tunggu trade langsung tak ada, kalau   |
//| ada pun 1 2 je. apa scalping macam tu."                           |
//| The research behind the refusals that led here, so nobody redoes  |
//| them: lowering the GATE below 8 adds losing trades (the 6-8 band  |
//| alone is PF 0.90, -$29 a year, drawdown -$291 never recovered),   |
//| and lowering k below 2.0 does the same (the 2.0-2.5 band is PF    |
//| 0.96). Gate 8 and k 2.5 are both floors of the PROFIT-maximising  |
//| setting; k 2.0 is below that floor on purpose, for the trade      |
//| count. Range scalping (buy the bottom of the day's range, sell    |
//| the top, M1, gated) is PF 0.77-0.95 at a 50% win rate, worse than |
//| random, and is not what this is.                                  |
//| To go back to the profit-maximising rule: InpSpkAtr 2.5,          |
//| InpSpkTpRange 0.                                                  |
//| Events go to MQL5\Files\spk_events.txt (forwarded to Telegram).   |
//+------------------------------------------------------------------+
input bool   InpSpkOn        = true;
input string InpSpkSymbol    = "XAUUSD";
input double InpSpkLot       = 0.01;
input long   InpSpkMagic     = 260320;
input double InpSpkAtr       = 2.0;      // the spike's range, in ATR(14, M1); 2.0 since v1.99 (owner's override)
input double InpSpkAtrSpread = 8.0;      // the cost gate: ATR(M1) must be at least this x the spread
input double InpSpkSlAtr     = 0.2;      // SL this far below the spike's low, in ATR(M1)
input double InpSpkTpRange   = 0.5;      // TP this much of the spike's range above its close; 0 = no TP. 0.5 since v1.99
input int    InpSpkHoldMin   = 45;       // close at market after this many minutes

string   sp_sym = "";
bool     sp_ready = false;
datetime sp_bar = 0;
ulong    sp_known[];

void SpkEvent(string msg)
{
   int h = FileOpen("spk_events.txt", FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("spike event file error ", GetLastError()); return; }
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES) + " | " + msg + "\r\n");
   FileClose(h);
   Print("SPIKE EVENT ", msg);
}

bool SpkPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetInteger(POSITION_MAGIC) == InpSpkMagic && PositionGetString(POSITION_SYMBOL) == sp_sym) { ticket = t; return true; }
   }
   return false;
}

void SpkInit()
{
   sp_ready = true;
   sp_sym = SymResolve(InpSpkSymbol);
   if(sp_sym == "") { SpkEvent("ERROR | M1 spike fade: symbol " + InpSpkSymbol + " not found"); return; }
   SymbolSelect(sp_sym, true);
   ulong t;
   if(SpkPosition(t)) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = t; }
   SpkEvent(StringFormat("SPIKE ONLINE | %s M1: BUY when a down bar of %.1f x ATR(M1) closes AND ATR(M1) >= %.0f x the spread "
                         "(the cost gate), SL %.1f ATR below its low, %s, out after %d min, lot %.2f | %d open position(s)",
                         sp_sym, InpSpkAtr, InpSpkAtrSpread, InpSpkSlAtr,
                         InpSpkTpRange > 0 ? StringFormat("TP %.2f of its range", InpSpkTpRange)
                                           : "no TP, the reversion is left to run",
                         InpSpkHoldMin, InpSpkLot, ArraySize(sp_known)));
}

void SpkReportClosed(ulong pos)
{
   if(!HistorySelectByPosition(pos)) return;
   double profit = 0, outPx = 0, inPx = 0; long reason = -1;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) inPx = HistoryDealGetDouble(d, DEAL_PRICE);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) { outPx = HistoryDealGetDouble(d, DEAL_PRICE); reason = HistoryDealGetInteger(d, DEAL_REASON); }
   }
   if(outPx == 0) return;
   string what = reason == DEAL_REASON_SL ? "SPIKE SL HIT" : (reason == DEAL_REASON_TP ? "SPIKE TP HIT" : "SPIKE CLOSED");
   string why = reason == DEAL_REASON_SL ? "stop loss below the spike low"
              : (reason == DEAL_REASON_TP ? StringFormat("take profit, %.2f of the spike range", InpSpkTpRange)
              : (reason == DEAL_REASON_EXPERT ? StringFormat("%d minutes up", InpSpkHoldMin) : "closed outside the EA"));
   double lv[2]; color lc[2]; string lb[2];
   lv[0] = inPx; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = outPx; lc[1] = profit >= 0 ? clrSeaGreen : clrIndianRed; lb[1] = "exit";
   string fn = Snap(sp_sym, PERIOD_M1, "SPX", lv, lc, lb, 0, 0, 0, 0, false);
   SpkEvent(StringFormat("%s %s | BUY from %s closed at %s (%s), profit $%.2f", what, sp_sym, PriceStr(sp_sym, inPx),
                         PriceStr(sp_sym, outPx), why, profit) + Img(fn));
}

void SpkOnTimer()
{
   if(!InpSpkOn) return;
   if(!sp_ready) SpkInit();
   if(sp_sym == "") return;
   for(int q = ArraySize(sp_known) - 1; q >= 0; q--)
      if(!PositionSelectByTicket(sp_known[q])) { SpkReportClosed(sp_known[q]); ArrayRemove(sp_known, q, 1); }
   MqlTick tk;
   datetime now = TimeCurrent();
   if(!SymbolInfoTick(sp_sym, tk) || now - tk.time > 600) return;              // market closed
   ulong pt;
   if(SpkPosition(pt))
   {
      bool known = false;
      for(int q = 0; q < ArraySize(sp_known); q++) if(sp_known[q] == pt) known = true;
      if(!known) { int m = ArraySize(sp_known); ArrayResize(sp_known, m + 1); sp_known[m] = pt; }
      PositionSelectByTicket(pt);
      MqlDateTime ns; TimeToStruct(now, ns);
      long held = (long)(now - (datetime)PositionGetInteger(POSITION_TIME));
      if(held >= (long)InpSpkHoldMin * 60 || ns.hour * 60 + ns.min >= 1350)    // time exit, and never past 22:30
      {
         trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
         if(!trade.PositionClose(pt)) SpkEvent(StringFormat("ERROR | spike close %s failed: %d %s", sp_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
      }
      return;                                                                  // one position at a time
   }
   datetime b0 = iTime(sp_sym, PERIOD_M1, 0);
   if(b0 == 0 || b0 == sp_bar) return;                                         // act once per new M1 bar
   MqlRates r[];
   int n = CopyRates(sp_sym, PERIOD_M1, 1, 40, r);                             // closed bars, r[n-1] = the bar that just closed
   if(n < 30) return;                                                          // history not loaded yet: retry next tick
   sp_bar = b0;
   int j = n - 1;
   // ATR(14) Wilder over the bars BEFORE the signal bar, as in the test
   double atr = r[1].high - r[1].low;
   for(int i = 2; i < j; i++)
   {
      double tr = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr += (tr - atr) / 14.0;
   }
   if(atr <= 0) return;
   double spread = tk.ask - tk.bid;
   if(spread <= 0 || atr < InpSpkAtrSpread * spread) return;                   // the cost gate
   double rng = r[j].high - r[j].low;
   if(r[j].close >= r[j].open || rng < InpSpkAtr * atr) return;                // only a DOWN spike of the right size
   MqlDateTime st; TimeToStruct(r[j].time, st);
   int hm = st.hour * 60 + st.min;
   if(st.day_of_week == 0 || st.day_of_week == 6 || hm < 90 || hm >= 1320) return;
   int dg = (int)SymbolInfoInteger(sp_sym, SYMBOL_DIGITS);
   double sl = NormalizeDouble(r[j].low - InpSpkSlAtr * atr, dg);
   double tp = InpSpkTpRange > 0 ? NormalizeDouble(r[j].close + InpSpkTpRange * rng, dg) : 0.0;   // 0 = no TP
   if(tk.ask <= sl || (tp > 0 && tk.ask >= tp)) return;                        // the price already left the setup
   double mn = SymbolInfoDouble(sp_sym, SYMBOL_VOLUME_MIN), sv = SymbolInfoDouble(sp_sym, SYMBOL_VOLUME_STEP);
   double lot = NormalizeDouble(MathMax(mn, MathFloor(InpSpkLot / sv + 1e-9) * sv), 2);
   trade.SetExpertMagicNumber(InpSpkMagic); trade.SetTypeFillingBySymbol(sp_sym);
   bool ok = trade.Buy(lot, sp_sym, 0, sl, tp, "SPIKE");
   if(!ok) SpkEvent(StringFormat("ERROR | spike %s order failed: %d %s", sp_sym, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   trade.SetExpertMagicNumber(InpMagic); trade.SetTypeFillingBySymbol(InpSymbol);
   if(!ok) return;
   double lv[]; color lc[]; string lb[];
   int nl = tp > 0 ? 3 : 2;
   ArrayResize(lv, nl); ArrayResize(lc, nl); ArrayResize(lb, nl);
   lv[0] = tk.ask; lc[0] = clrBlue; lb[0] = "entry"; lv[1] = sl; lc[1] = clrIndianRed; lb[1] = "SL";
   if(nl == 3) { lv[2] = tp; lc[2] = clrSeaGreen; lb[2] = "TP"; }
   string fn = Snap(sp_sym, PERIOD_M1, "SPF", lv, lc, lb, 0, 0, 0, 0, false);
   SpkEvent(StringFormat("SPIKE BUY %s | an M1 bar dropped %s (%.1f x ATR) and ATR %s is %.0f x the spread %.2f | BUY %.2f lot at %s, "
                         "SL %s, %s, out after %d min", sp_sym, PriceStr(sp_sym, rng), rng / atr, PriceStr(sp_sym, atr),
                         atr / spread, spread, lot, PriceStr(sp_sym, tk.ask), PriceStr(sp_sym, sl),
                         tp > 0 ? "TP " + PriceStr(sp_sym, tp) : "no TP: the reversion is left to run",
                         InpSpkHoldMin) + Img(fn));
   int m = ArraySize(sp_known);
   if(SpkPosition(pt)) { ArrayResize(sp_known, m + 1); sp_known[m] = pt; }
}
//+------------------------------------------------------------------+
