//+------------------------------------------------------------------+
//| FizyHA.mq5 - the owner's Heikin Ashi + EMA 10/30 + Stochastic    |
//| scalper (round 66, 9 Nov 2026). Standalone EA for testing: put   |
//| it on an M1 gold chart or run it in the Strategy Tester.         |
//|                                                                  |
//| BUY (sell is the mirror):                                        |
//|  1 EMA 10 above EMA 30 (optionally both rising)                  |
//|  2 the previous HA candle is an INDECISION candle: a shadow above|
//|    AND below, body <= InpBodyMax x its range (smaller = better)  |
//|  3 the last closed HA candle is BULLISH with NO lower shadow     |
//|  4 Stochastic 14,3,3 main line not overbought (< 80)             |
//|  entry at market on the next bar, SL at the nearest swing low    |
//|  (lowest low of the last InpSwingBars bars minus the spread),    |
//|  TP = InpTpAtr x ATR(14). One position at a time.                |
//|                                                                  |
//| Backtest on the broker's M1 data, 7 Sep - 6 Nov 2026, 0.01 lot:  |
//| every variant lost in both months (PF 0.75-0.86). These defaults |
//| are the least-losing cell (body 0.3, TP 1.5 ATR, slope on):      |
//| PF 0.82 / 0.83, -$277 / -$219 a month. Demo accounts only.       |
//+------------------------------------------------------------------+
#property copyright "FIZY BOT"
#property version   "1.00"

#include <Trade\Trade.mqh>

input double InpLot        = 0.01;   // lot
input double InpBodyMax    = 0.3;    // indecision: max body as a share of the HA range
input bool   InpSlope      = true;   // EMA 10 and EMA 30 must also be rising (falling for sells)
input int    InpEmaFast    = 10;
input int    InpEmaSlow    = 30;
input int    InpStochK     = 14;
input int    InpStochD     = 3;
input int    InpStochSlow  = 3;
input double InpStochOB    = 80;     // buy only if %K is below this
input double InpStochOS    = 20;     // sell only if %K is above this
input int    InpSwingBars  = 10;     // SL at the lowest low / highest high of the last N bars
input double InpTpAtr      = 1.5;    // TP in ATR(14)
input int    InpMaxBars    = 100;    // close after this many bars at most (0 = never)
input string InpStart      = "01:30"; // entries from (server time)
input string InpEnd        = "22:00"; // entries until (server time)
input string InpFlat       = "23:45"; // close everything before the rollover (server time)
input bool   InpBuy        = true;
input bool   InpSell       = true;
input long   InpMagic      = 260322;
input bool   InpDemoOnly   = true;   // refuse to trade on a real account

CTrade   trade;
int      hFast = INVALID_HANDLE, hSlow = INVALID_HANDLE, hSto = INVALID_HANDLE, hAtr = INVALID_HANDLE;
datetime lastBar = 0;
double   cPrev = 0;
const int HA_WARM = 300;             // bars used to seed the HA open (converges fast)

int HM(const string s) { return (int)StringToInteger(StringSubstr(s, 0, 2)) * 60 + (int)StringToInteger(StringSubstr(s, 3, 2)); }

int OnInit()
{
   if(InpDemoOnly && AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
   {
      Print("FizyHA: not a demo account, EA disabled (InpDemoOnly = true)");
      return INIT_FAILED;
   }
   hFast = iMA(_Symbol, _Period, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   hSlow = iMA(_Symbol, _Period, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   hSto  = iStochastic(_Symbol, _Period, InpStochK, InpStochD, InpStochSlow, MODE_SMA, STO_LOWHIGH);
   hAtr  = iATR(_Symbol, _Period, 14);
   if(hFast == INVALID_HANDLE || hSlow == INVALID_HANDLE || hSto == INVALID_HANDLE || hAtr == INVALID_HANDLE)
   {
      Print("FizyHA: indicator handle failed");
      return INIT_FAILED;
   }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   if(_Period != PERIOD_M1) Print("FizyHA: tested on M1; this chart is ", EnumToString(_Period));
   Print("FizyHA started on ", _Symbol, " ", EnumToString(_Period), ": body <= ", DoubleToString(InpBodyMax, 2),
         ", TP ", DoubleToString(InpTpAtr, 1), " ATR, slope ", (InpSlope ? "on" : "off"), ", lot ", DoubleToString(InpLot, 2));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hFast); IndicatorRelease(hSlow); IndicatorRelease(hSto); IndicatorRelease(hAtr);
}

// our open position on this symbol: ticket, or 0
ulong MyPos()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic) return t;
   }
   return 0;
}

// Heikin Ashi of closed bars 1 and 2 (series order: index 0 = bar 1)
bool HA(double &ho[], double &hc[], double &hh[], double &hl[])
{
   MqlRates r[];
   ArraySetAsSeries(r, true);
   int n = CopyRates(_Symbol, _Period, 1, HA_WARM, r);
   if(n < 50) return false;
   double o = (r[n - 1].open + r[n - 1].close) / 2, c = 0;
   ArrayResize(ho, 2); ArrayResize(hc, 2); ArrayResize(hh, 2); ArrayResize(hl, 2);
   for(int i = n - 1; i >= 0; i--)
   {
      c = (r[i].open + r[i].high + r[i].low + r[i].close) / 4;
      if(i < n - 1) o = (o + cPrev) / 2;
      cPrev = c;
      if(i <= 1)
      {
         ho[i] = o; hc[i] = c;
         hh[i] = MathMax(r[i].high, MathMax(o, c));
         hl[i] = MathMin(r[i].low, MathMin(o, c));
      }
   }
   return true;
}
void OnTick()
{
   ulong pos = MyPos();
   MqlDateTime now; TimeToStruct(TimeCurrent(), now);
   int hm = now.hour * 60 + now.min;

   // exits that the broker does not handle: rollover flat and the bar limit
   if(pos != 0 && PositionSelectByTicket(pos))
   {
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      int held = iBarShift(_Symbol, _Period, opened, false);
      if(hm >= HM(InpFlat) || (InpMaxBars > 0 && held >= InpMaxBars))
      {
         if(trade.PositionClose(pos))
            Print("FizyHA: closed ", pos, (hm >= HM(InpFlat) ? " before the rollover" : " after the bar limit"));
         return;
      }
   }

   datetime bt = iTime(_Symbol, _Period, 0);
   if(bt == lastBar) return;          // signals only once per new bar
   lastBar = bt;
   if(pos != 0) return;
   if(hm < HM(InpStart) || hm >= HM(InpEnd)) return;

   double ho[], hc[], hh[], hl[];
   if(!HA(ho, hc, hh, hl)) return;
   double ef[], es[], k[], at[];
   ArraySetAsSeries(ef, true); ArraySetAsSeries(es, true); ArraySetAsSeries(k, true); ArraySetAsSeries(at, true);
   if(CopyBuffer(hFast, 0, 1, 2, ef) < 2 || CopyBuffer(hSlow, 0, 1, 2, es) < 2 ||
      CopyBuffer(hSto, 0, 1, 1, k) < 1 || CopyBuffer(hAtr, 0, 1, 1, at) < 1) return;

   const double eps = _Point * 0.5;
   // [1] = the previous candle (indecision), [0] = the last closed candle (signal)
   double top1 = MathMax(ho[1], hc[1]), bot1 = MathMin(ho[1], hc[1]), rng1 = hh[1] - hl[1];
   bool indecision = rng1 > 0 && top1 < hh[1] - eps && bot1 > hl[1] + eps && (top1 - bot1) <= InpBodyMax * rng1;
   if(!indecision) return;

   double top0 = MathMax(ho[0], hc[0]), bot0 = MathMin(ho[0], hc[0]);
   int dir = 0;
   if(InpBuy && hc[0] > ho[0] && bot0 - hl[0] <= eps && ef[0] > es[0] &&
      (!InpSlope || (ef[0] > ef[1] && es[0] > es[1])) && k[0] < InpStochOB) dir = 1;
   else if(InpSell && hc[0] < ho[0] && hh[0] - top0 <= eps && ef[0] < es[0] &&
      (!InpSlope || (ef[0] < ef[1] && es[0] < es[1])) && k[0] > InpStochOS) dir = -1;
   if(dir == 0) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double spread = ask - bid;
   int lo = iLowest(_Symbol, _Period, MODE_LOW, InpSwingBars, 1), hi = iHighest(_Symbol, _Period, MODE_HIGH, InpSwingBars, 1);
   if(lo < 0 || hi < 0) return;
   int dg = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double sl, tp;
   string why = "EMA" + IntegerToString(InpEmaFast) + "/" + IntegerToString(InpEmaSlow) + " aligned, HA indecision then " +
                (dir == 1 ? "bullish (no lower shadow)" : "bearish (no upper shadow)") + ", %K " + DoubleToString(k[0], 1);
   if(dir == 1)
   {
      sl = NormalizeDouble(iLow(_Symbol, _Period, lo) - spread, dg);
      tp = NormalizeDouble(ask + InpTpAtr * at[0], dg);
      if(bid - sl <= minDist) { Print("FizyHA: buy skipped, swing low too close"); return; }
      if(trade.Buy(InpLot, _Symbol, ask, sl, tp, "FizyHA buy"))
         Print("FizyHA BUY ", DoubleToString(ask, dg), " SL ", DoubleToString(sl, dg), " TP ", DoubleToString(tp, dg), " | ", why);
   }
   else
   {
      sl = NormalizeDouble(iHigh(_Symbol, _Period, hi) + spread, dg);
      tp = NormalizeDouble(bid - InpTpAtr * at[0], dg);
      if(sl - ask <= minDist) { Print("FizyHA: sell skipped, swing high too close"); return; }
      if(trade.Sell(InpLot, _Symbol, bid, sl, tp, "FizyHA sell"))
         Print("FizyHA SELL ", DoubleToString(bid, dg), " SL ", DoubleToString(sl, dg), " TP ", DoubleToString(tp, dg), " | ", why);
   }
}
//+------------------------------------------------------------------+
