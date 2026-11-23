// Round 162: the owner's video EA. Always in the market, 0.01 lot.
// A position gets an initial SL X$ away (X>=90 = none). Once it is +A$ the SL trails T$ behind
// (updated once a second, never loosened) and an opposite STOP order sits G$ inside the SL
// (buy: sell stop at SL+G; sell: buy stop at SL-G), moving with it. The stop fill opens the
// new position; the old one exits on its SL. An initial-SL hit (no trail yet) reverses at market.
// Trading 01:30-23:30 server weekdays; everything closed at 23:30. start: 0 buy, 1 sell, 2 random.
#include <stdint.h>
#include <stdlib.h>
typedef struct { double A, T, G, X; int start, seed; double K; } P;
typedef struct { int on, dir; double e, sl; int tr; } Pos;
static int64_t ne; static int64_t *ot; static double *op;
static void cl(Pos *p, double px, int64_t t) { double v = p->dir > 0 ? px - p->e : p->e - px; ot[ne] = t; op[ne++] = v; p->on = 0; }
int sim(const int64_t *t, const int32_t *bi, const int32_t *ai, int64_t n, P *q, int64_t *xt, double *xp) {
  ot = xt; op = xp; ne = 0; srand(q->seed);
  Pos ps[2] = {{0}}; int pend = 0, pdir = 0; double plev = 0; int oco = 0; double ohi = 0, olo = 0; int64_t lastday = -1, lastupd = 0;
  for (int64_t i = 0; i < n; i++) {
    int64_t tt = t[i]; double b = bi[i] / 100.0, a = ai[i] / 100.0;
    int64_t day = tt / 86400000; int mins = (int)((tt / 60000) % 1440); int wd = (int)((day + 4) % 7); // 0=Sun
    int open = (wd >= 1 && wd <= 5) && mins >= 90 && mins < 1410;
    if (!open) { for (int k = 0; k < 2; k++) if (ps[k].on) cl(&ps[k], ps[k].dir > 0 ? b : a, tt); pend = 0; oco = 0; continue; }
    if (day != lastday && q->start == 3) { lastday = day; if (!ps[0].on && !ps[1].on) { oco = 1; ohi = a + q->K; olo = b - q->K; } }
    if (oco) { int d = 0; if (a >= ohi) d = 1; else if (b <= olo) d = -1;
      if (d) { oco = 0; ps[0].on = 1; ps[0].dir = d; ps[0].e = d > 0 ? a : b; ps[0].tr = 0; ps[0].sl = q->X >= 90 ? 0 : (d > 0 ? ps[0].e - q->X : ps[0].e + q->X); } }
    if (day != lastday) { lastday = day; if (!ps[0].on && !ps[1].on) {
        int d = q->start == 0 ? 1 : q->start == 1 ? -1 : (rand() & 1 ? 1 : -1);
        ps[0].on = 1; ps[0].dir = d; ps[0].e = d > 0 ? a : b; ps[0].sl = q->X >= 90 ? 0 : (d > 0 ? ps[0].e - q->X : ps[0].e + q->X); ps[0].tr = 0; } }
    // pending stop fill
    if (pend) { int hit = pdir > 0 ? a >= plev : b <= plev;
      if (hit) { int k = ps[0].on ? 1 : 0; if (ps[k].on) k = 0; // free slot
        if (!ps[k].on) { ps[k].on = 1; ps[k].dir = pdir; ps[k].e = pdir > 0 ? a : b; ps[k].tr = 0;
          ps[k].sl = q->X >= 90 ? 0 : (pdir > 0 ? ps[k].e - q->X : ps[k].e + q->X); }
        pend = 0; } }
    // SL hits
    int nopen = ps[0].on + ps[1].on;
    for (int k = 0; k < 2; k++) { Pos *p = &ps[k]; if (!p->on || (p->sl == 0 && !p->tr)) continue;
      int hit = p->dir > 0 ? b <= p->sl : a >= p->sl;
      if (hit) { int was_tr = p->tr; int d = p->dir; cl(p, p->dir > 0 ? b : a, tt);
        if (!was_tr && nopen == 1) { p->on = 1; p->dir = -d; p->e = -d > 0 ? a : b; p->tr = 0; p->sl = -d > 0 ? p->e - q->X : p->e + q->X; pend = 0; }
      } }
    // trail once a second
    if (tt - lastupd >= 1000) { lastupd = tt;
      for (int k = 0; k < 2; k++) { Pos *p = &ps[k]; if (!p->on) continue;
        double pr = p->dir > 0 ? b - p->e : p->e - a;
        if (!p->tr && pr >= q->A) { p->tr = 1; p->sl = p->dir > 0 ? b - q->T : a + q->T; }
        else if (p->tr) { if (p->dir > 0) { double s = b - q->T; if (s > p->sl + 0.0999) p->sl = s; } else { double s = a + q->T; if (s < p->sl - 0.0999) p->sl = s; } }
        if (p->tr && (ps[0].on + ps[1].on) == 1) { pend = 1; pdir = -p->dir; plev = p->dir > 0 ? p->sl + q->G : p->sl - q->G; }
      } }
  }
  return (int)ne;
}
