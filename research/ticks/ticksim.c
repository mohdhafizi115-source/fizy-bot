// Tick-level simulator of GOLD FLIP (FizyFLP.mqh v2.43-v2.47). Prices in cents (int32), times in ms (server time).
#include <stdint.h>
#include <math.h>
typedef struct { double D, lock, be, T, k, step, K, tgt, minstep, spm; int mode, timer_ms, d1, reset_min; } P;
#define DAYMS 86400000LL
int sim(const int64_t *t, const int32_t *b, const int32_t *a, int64_t n, const P *p, int64_t *xt, double *xp)
{
    int m = 0, pos = 0, locked = 0, started = 0, done = 0, allow = 0, have_prev = 0;
    double ent = 0, sl = 0, pb = 0, ps = 0, dpnl = 0, dopen = 0, dclose = 0;
    int64_t curday = -1, next_eval = 0, pend_t = 0;
    for (int64_t i = 0; i < n; i++) {
        double bid = b[i] / 100.0, ask = bid + (a[i] - b[i]) / 100.0 * p->spm, spr = ask - bid;
        int64_t day = t[i] / DAYMS, tod = t[i] % DAYMS;
        if (day != curday) {
            if (curday >= 0) { allow = dclose < dopen ? 1 : (dclose > dopen ? -1 : 0); have_prev = 1; }
            if (!p->d1) allow = 0;
            curday = day; dopen = bid; dpnl = 0; done = 0; started = 0; pb = ps = 0;
        }
        dclose = bid;
        int wd = (int)((day + 4) % 7);
        int live = wd >= 1 && wd <= 5 && tod >= 5400000 && tod < 84600000 && have_prev;
        if (pos != 0 && !live) { double px = pos == 1 ? bid : ask; xt[m] = t[i]; xp[m++] = (px - ent) * pos; pos = 0; continue; }
        if (!live) { pb = ps = 0; continue; }
        if (done) continue;
        if (pos == 0) {
            if (!started) { started = 1; if (allow >= 0) pb = bid + p->K; if (allow <= 0) ps = bid - p->K; pend_t = -1; }
            if (p->reset_min > 0 && pend_t >= 0 && t[i] - pend_t >= p->reset_min * 60000LL) {
                if (pb > 0) pb = ask + p->K;
                if (ps > 0) ps = bid - p->K;
                pend_t = t[i];
            }
            if (pb > 0 && ask >= pb) { pos = 1; ent = ask; sl = ent - spr - p->D; pb = ps = 0; locked = 0; next_eval = t[i] + p->timer_ms; }
            else if (ps > 0 && bid <= ps) { pos = -1; ent = bid; sl = ent + spr + p->D; pb = ps = 0; locked = 0; next_eval = t[i] + p->timer_ms; }
            continue;
        }
        if (pos == 1) {
            if (bid <= sl) {
                double pnl = bid - ent; xt[m] = t[i]; xp[m++] = pnl; dpnl += pnl; pos = 0;
                if (dpnl >= p->tgt) { done = 1; continue; }
                if (allow == 0) { pos = -1; ent = bid; sl = ask + p->D; locked = 0; next_eval = t[i] + p->timer_ms; }
                else { pb = ask + p->K; pend_t = t[i]; }
                continue;
            }
            if (t[i] < next_eval) continue;
            next_eval = t[i] + p->timer_ms;
            double pr = bid - ent, ns = sl;
            switch (p->mode) {
            case 0: if (!locked) { if (pr >= p->lock) { ns = fmax(sl, ent + p->lock - p->D); locked = 1; sl = ns; } else ns = bid - p->D; } break;
            case 1: if (pr >= p->lock) ns = fmax(ent + p->be, bid - p->T); break;
            case 2: if (pr >= p->lock) ns = ent + p->be + floor((pr - p->lock) / p->step + 1e-9) * p->step; break;
            case 3: ns = bid - fmax(p->T, p->D - p->k * fmax(pr, 0.0)); break;
            case 4: if (pr >= p->lock || locked) { ns = bid - p->T; locked = 1; } break;
            default: break;
            }
            if (ns >= sl + p->minstep - 1e-9) sl = ns;
        } else {
            if (ask >= sl) {
                double pnl = ent - ask; xt[m] = t[i]; xp[m++] = pnl; dpnl += pnl; pos = 0;
                if (dpnl >= p->tgt) { done = 1; continue; }
                if (allow == 0) { pos = 1; ent = ask; sl = bid - p->D; locked = 0; next_eval = t[i] + p->timer_ms; }
                else { ps = bid - p->K; pend_t = t[i]; }
                continue;
            }
            if (t[i] < next_eval) continue;
            next_eval = t[i] + p->timer_ms;
            double pr = ent - ask, ns = sl;
            switch (p->mode) {
            case 0: if (!locked) { if (pr >= p->lock) { ns = fmin(sl, ent - p->lock + p->D); locked = 1; sl = ns; } else ns = ask + p->D; } break;
            case 1: if (pr >= p->lock) ns = fmin(ent - p->be, ask + p->T); break;
            case 2: if (pr >= p->lock) ns = ent - p->be - floor((pr - p->lock) / p->step + 1e-9) * p->step; break;
            case 3: ns = ask + fmax(p->T, p->D - p->k * fmax(pr, 0.0)); break;
            case 4: if (pr >= p->lock || locked) { ns = ask + p->T; locked = 1; } break;
            default: break;
            }
            if (ns <= sl - p->minstep + 1e-9) sl = ns;
        }
    }
    return m;
}
