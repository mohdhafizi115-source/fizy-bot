// Generic OCO stop-order simulator on real ticks. Prices in cents (int), levels in dollars (double).
// Events sorted by place time. One position at a time; an event placed while a position is open is skipped.
#include <stdint.h>
static int64_t lb(const int64_t*t,int64_t n,int64_t x){int64_t lo=0,hi=n;while(lo<hi){int64_t m=(lo+hi)/2;if(t[m]<x)lo=m+1;else hi=m;}return lo;}
int sim(const int64_t*t,const int32_t*b,const int32_t*a,int64_t n,int ne,const int64_t*tp_,const double*bl,const double*sl_,
        const double*sld,const double*tpd,const int64_t*texp,const int64_t*texit,int both,
        int64_t*ot,double*op,int64_t*ox,int32_t*od){
  int k=0; int64_t busy=0;
  for(int e=0;e<ne;e++){
    if(tp_[e]<busy) continue;
    int64_t i=lb(t,n,tp_[e]); int dir=0; double ent=0; int64_t ti=0;
    double B=bl[e]*100.0, S=sl_[e]*100.0;
    for(;i<n && t[i]<texp[e];i++){
      if(B>0 && a[i]>=B){dir=1; ent=a[i]; break;}   // fill at the tick that crosses (includes slippage)
      if(S>0 && b[i]<=S){dir=-1; ent=b[i]; break;}
    }
    if(!dir) continue;
    ti=t[i]; double SL=sld[e]*100.0, TP=tpd[e]*100.0; double pnl=0; int64_t xt=0;
    for(;i<n;i++){
      if(t[i]>=texit[e]){ pnl = dir>0 ? b[i]-ent : ent-a[i]; xt=t[i]; break; }
      if(dir>0){ if(b[i]<=ent-SL || (TP>0 && b[i]>=ent+TP)){pnl=b[i]-ent; xt=t[i]; break;} }
      else     { if(a[i]>=ent+SL || (TP>0 && a[i]<=ent-TP)){pnl=ent-a[i]; xt=t[i]; break;} }
    }
    if(i>=n){ pnl = dir>0 ? b[n-1]-ent : ent-a[n-1]; xt=t[n-1]; }
    ot[k]=ti; op[k]=pnl/100.0; ox[k]=xt; od[k]=dir; k++; busy=xt;
    (void)both;
  }
  return k;
}
