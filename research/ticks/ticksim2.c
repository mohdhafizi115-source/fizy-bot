// Tick-level simulator, FLIP frozen-stop family with extra ideas (round 131). Prices in cents, times in ms (server time).
#include <stdint.h>
#include <math.h>
typedef struct { double D, lock, K, spm, tgt, minstep, be_at, be_off, pyr_at, minbody, maxbody;
                 int timer_ms, maxn, cut_ms, start_ms, end_ms, tstop_min, pyr_max, re_mode, cool_min, d1, flip_dir, big_mode, rnd_pct, seed; } P;
#define DAYMS 86400000LL
#define REC(T, PNL, ET, O) { xt[m] = (T); xp[m] = (PNL); xe[m] = (ET); xo[m] = (O); m++; }
int sim(const int64_t *t, const int32_t *b, const int32_t *a, int64_t n, const P *p, int64_t *xt, double *xp, int64_t *xe, int32_t *xo)
{
    int m = 0, s = 0, locked = 0, started = 0, done = 0, allow = 0, have_prev = 0, skip = 0, nent = 0, nadd = 0;
    double ent = 0, sl = 0, pb = 0, ps = 0, dpnl = 0, dopen = 0, dclose = 0, dhi = 0, dlo = 0;
    double ae[8], asl[8]; int64_t aet[8]; int al[8];
    int64_t curday = -1, next_eval = 0, pend_ok = 0, ent_t = 0; int arm = 0;
    for (int64_t i = 0; i < n; i++) {
        double bid = b[i] / 100.0, ask = bid + (a[i] - b[i]) / 100.0 * p->spm, spr = ask - bid;
        int64_t day = t[i] / DAYMS, tod = t[i] % DAYMS;
        if (day != curday) {
            if (curday >= 0) { double body = fabs(dclose - dopen); allow = dclose < dopen ? 1 : (dclose > dopen ? -1 : 0); have_prev = 1;
                skip = (body < p->minbody) || (p->maxbody > 0 && body > p->maxbody);
                if (p->flip_dir) allow = -allow;
                if (skip && p->big_mode == 1 && body >= p->minbody) { skip = 0; allow = -allow; }
                if (skip && p->big_mode == 2 && body >= p->minbody) { skip = 0; allow = 0; }
                if (p->rnd_pct > 0) { uint64_t h = (uint64_t)(day * 2654435761ULL + p->seed * 40503ULL); h ^= h >> 13; h *= 0x9E3779B97F4A7C15ULL; h ^= h >> 29;
                    skip = (int)(h % 100) < p->rnd_pct; } }
            if (!p->d1) allow = 0;
            curday = day; dopen = bid; dpnl = 0; done = 0; started = 0; pb = ps = 0; nent = 0;
        }
        dclose = bid;
        int wd = (int)((day + 4) % 7);
        int live = wd >= 1 && wd <= 5 && tod >= p->start_ms && tod < p->end_ms && have_prev && !skip;
        if (!live) {
            if (s != 0) { double px = s == 1 ? bid : ask; REC(t[i], (px - ent) * s, ent_t, nent);
                for (int j = 0; j < nadd; j++) if (al[j]) REC(t[i], (px - ae[j]) * s, aet[j], 100 + j);
                s = 0; nadd = 0; }
            pb = ps = 0; continue;
        }
        if (done) continue;
        if (!started) { started = 1; dhi = ask; dlo = bid; if (allow >= 0) pb = bid + p->K; if (allow <= 0) ps = bid - p->K; pend_ok = 0; arm = 0; }
        if (ask > dhi) dhi = ask;
        if (bid < dlo) dlo = bid;
        if (s == 0) {
            if ((p->cut_ms > 0 && tod >= p->cut_ms) || (p->maxn > 0 && nent >= p->maxn)) { pb = ps = 0; continue; }
            if (t[i] < pend_ok) continue;
            if (arm) { arm = 0;   // arm the waiting stop now (after a cooldown)
                if (allow >= 0) pb = p->re_mode == 1 ? fmax(ask + p->K, dhi) : ask + p->K;
                if (allow <= 0) ps = p->re_mode == 1 ? fmin(bid - p->K, dlo) : bid - p->K;
                pend_ok = 0; continue;
            }
            if (pb > 0 && ask >= pb) { s = 1; ent = ask; sl = ent - spr - p->D; }
            else if (ps > 0 && bid <= ps) { s = -1; ent = bid; sl = ent + spr + p->D; }
            if (s != 0) { pb = ps = 0; locked = 0; nadd = 0; nent++; ent_t = t[i]; next_eval = t[i] + p->timer_ms; }
            continue;
        }
        double px = s == 1 ? bid : ask;
        // pyramid adds: own fixed stop
        for (int j = 0; j < nadd; j++) if (al[j] && (px - asl[j]) * s <= 0) { REC(t[i], (px - ae[j]) * s, aet[j], 100 + j); al[j] = 0; }
        int hit = (px - sl) * s <= 0;
        int tstop = !hit && !locked && p->tstop_min > 0 && t[i] - ent_t >= p->tstop_min * 60000LL;
        if (hit || tstop) {
            double pnl = (px - ent) * s; REC(t[i], pnl, ent_t, nent); dpnl += pnl;
            for (int j = 0; j < nadd; j++) if (al[j]) { REC(t[i], (px - ae[j]) * s, aet[j], 100 + j); al[j] = 0; }
            int os = s; s = 0; nadd = 0;
            if (dpnl >= p->tgt) { done = 1; continue; }
            if (p->cool_min > 0) { pend_ok = t[i] + p->cool_min * 60000LL; pb = ps = 0; arm = 1; }
            else if (allow == 0) { if (os == 1) ps = bid - p->K; else pb = ask + p->K; }
            else if (allow > 0) pb = p->re_mode == 1 ? fmax(ask + p->K, dhi) : ask + p->K;
            else ps = p->re_mode == 1 ? fmin(bid - p->K, dlo) : bid - p->K;
            continue;
        }
        if (t[i] < next_eval) continue;
        next_eval = t[i] + p->timer_ms;
        double pr = (px - ent) * s, ns = sl;
        if (!locked) { if (pr >= p->lock) { ns = ent + s * (p->lock - p->D); if ((ns - sl) * s < 0) ns = sl; locked = 1; sl = ns; } else ns = px - s * p->D; }
        if (p->be_at > 0 && pr >= p->be_at) { double q = ent + s * p->be_off; if ((q - ns) * s > 0) ns = q; }
        if ((ns - sl) * s >= p->minstep - 1e-9) sl = ns;
        if (p->pyr_at > 0 && nadd < p->pyr_max && nadd < 8 && pr >= p->pyr_at * (nadd + 1)) {
            double e = s == 1 ? ask : bid; ae[nadd] = e; asl[nadd] = e - s * (p->D + spr); aet[nadd] = t[i]; al[nadd] = 1; nadd++;
        }
    }
    return m;
}
