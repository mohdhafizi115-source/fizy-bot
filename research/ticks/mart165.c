// Round 165 (copy of mart164.c + flex 3): live MART (v2.57) on REAL TICKS with the video's trailing exit + opposite stop.
// Basket: lots k x 0.01 (k = 1, 2, 3 ...), add every S$ against the LAST entry, unlimited, no SL.
// Flat: OCO buy stop ask + K / sell stop bid - K. Exit:
//   mode 0 (live): close when the basket nets +Tgt (bid/ask), then flat -> OCO.
//   mode 1 (trail): once the basket nets >= +A$, a basket stop line trails T$ (price) behind bid (buy) / ask (sell),
//      never loosened, AND never below the price where the basket nets +Lk$ (lock). Exit when price hits the line.
//      flip G>=0: an opposite STOP sits G$ inside the line (buy basket: sell stop at line + G) and moves with it;
//      its fill opens a NEW basket the other way (lot 0.01) while the old one exits on its line. G<0: after the exit,
//      flat -> OCO pair.
// Weekdays 24 h like live; overnight swap -0.71 (buy) / -0.84 (sell) per 0.01 lot; stop-out at equity <= 40% of margin
// (1:3000, 0.01 lot = price/3000 $); a blow-up closes everything and ends the run.
#include <stdint.h>
#include <math.h>
typedef struct { double S, K, Tgt, A, T, G, Lk, B0; int mode; int flex; } P;
typedef struct { int on, dir, n; double sumL, sumLE, last, line; int tr; } Bk;
typedef struct { double net, worstfl, maxlots; int baskets, wins, blown, flips; int64_t blowt; } R;
static double fl(Bk *k, double b, double a) { double px = k->dir > 0 ? b : a; return k->dir * (k->sumL * px - k->sumLE); }
static void open1(Bk *k, int d, double px) { k->on = 1; k->dir = d; k->n = 1; k->sumL = 1; k->sumLE = px; k->last = px; k->tr = 0; k->line = 0; }
int sim(const int64_t *t, const int32_t *bi, const int32_t *ai, const float *atr, int64_t i0, int64_t i1, P *q, R *r) {
  Bk bk[2] = {{0}}; double bal = q->B0; int oco = 0; double ohi = 0, olo = 0; int pend = 0, pdir = 0; double plev = 0;
  int64_t lastday = -1, lastupd = 0; r->net = 0; r->worstfl = 0; r->maxlots = 0; r->baskets = r->wins = r->blown = r->flips = 0; r->blowt = 0;
  for (int64_t i = i0; i < i1; i++) {
    int64_t tt = t[i]; double b = bi[i] / 100.0, a = ai[i] / 100.0;
    int64_t day = tt / 86400000; int wd = (int)((day + 4) % 7);
    if (wd == 0 || wd == 6) continue;
    if (day != lastday) { if (lastday >= 0) for (int k = 0; k < 2; k++) if (bk[k].on) bal += bk[k].sumL * (bk[k].dir > 0 ? -0.71 : -0.84) * (wd == 4 ? 3 : 1); lastday = day; }
    double u = q->flex ? atr[i] : 1.0; double S = q->S * u, K = q->K * u, A = q->A * (q->flex == 3 ? 1.0 : u), T = q->T * u, G = q->G >= 0 ? q->G * u : -1, Tgt = q->Tgt * (q->flex == 2 ? u : 1.0);
    int nopen = bk[0].on + bk[1].on;
    if (!nopen && !oco && !pend) { oco = 1; ohi = a + K; olo = b - K; }
    if (oco) { int d = a >= ohi ? 1 : (b <= olo ? -1 : 0); if (d) { oco = 0; open1(&bk[0], d, d > 0 ? a : b); } }
    if (pend) { int hit = pdir > 0 ? a >= plev : b <= plev;
      if (hit) { int s = bk[0].on ? 1 : 0; open1(&bk[s], pdir, pdir > 0 ? a : b); pend = 0; r->flips++; } }
    // adds
    for (int k = 0; k < 2; k++) { Bk *x = &bk[k]; if (!x->on) continue;
      while (1) { double lvl = x->dir > 0 ? x->last - S : x->last + S; int hit = x->dir > 0 ? a <= lvl : b >= lvl;
        if (!hit) break; x->n++; double px = x->dir > 0 ? a : b; if (fabs(px - lvl) > S) px = px; x->sumL += x->n; x->sumLE += x->n * px; x->last = px; } }
    // equity / stop-out
    double flt = 0, lots = 0; for (int k = 0; k < 2; k++) if (bk[k].on) { flt += fl(&bk[k], b, a); lots += bk[k].sumL; }
    if (flt < r->worstfl) r->worstfl = flt; if (lots > r->maxlots) r->maxlots = lots;
    if (lots > 0 && bal + flt <= 0.4 * lots * b / 3000.0) { r->blown = 1; r->blowt = tt; r->net = -q->B0; return 1; }
    // exits
    for (int k = 0; k < 2; k++) { Bk *x = &bk[k]; if (!x->on) continue; double f = fl(x, b, a);
      if (q->mode == 0) { if (f >= Tgt) { bal += f; r->baskets++; r->wins += f > 0; x->on = 0; } continue; }
      if (x->tr) { int hit = x->dir > 0 ? b <= x->line : a >= x->line;
        if (hit) { bal += f; r->baskets++; r->wins += f > 0; x->on = 0; if (pend && bk[0].on + bk[1].on == 0) pend = 0; } } }
    if (q->mode == 1 && tt - lastupd >= 1000) { lastupd = tt;
      for (int k = 0; k < 2; k++) { Bk *x = &bk[k]; if (!x->on) continue; double f = fl(x, b, a);
        double lockpx = x->dir > 0 ? (q->Lk + x->sumLE) / x->sumL : (x->sumLE - q->Lk) / x->sumL;
        if (!x->tr && f >= A) { x->tr = 1; x->line = x->dir > 0 ? fmax(b - T, lockpx) : fmin(a + T, lockpx); }
        else if (x->tr) { if (x->dir > 0) { double s = fmax(b - T, lockpx); if (s > x->line + 0.0999) x->line = s; }
                          else { double s = fmin(a + T, lockpx); if (s < x->line - 0.0999) x->line = s; } }
        if (x->tr && G >= 0 && bk[0].on + bk[1].on == 1) { pend = 1; pdir = -x->dir; plev = x->dir > 0 ? x->line + G : x->line - G; } } }
  }
  for (int k = 0; k < 2; k++) if (bk[k].on) { bal += fl(&bk[k], bi[i1 - 1] / 100.0, ai[i1 - 1] / 100.0); }
  r->net = bal - q->B0; return 0;
}
