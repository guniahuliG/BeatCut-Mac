"""Deterministic independent event schedules, shared by player and exporter."""
from functools import lru_cache
from bisect import bisect_right
import random

KINDS=('face','slow','rewind','zoom','shake','flash')
RANDOM_DEFAULTS=dict(random_mode=False,random_seed=1.,random_min=.4,random_max=1.5,
                     rate_face=4.,rate_slow=4.,rate_rewind=2.,rate_zoom=10.,rate_shake=8.,rate_flash=0.)


@lru_cache(maxsize=256)
def schedule(kind,start,end,rate,minimum,maximum,seed):
    if end<=start or rate<=0:return ()
    minimum,maximum=sorted((max(.1,minimum),max(.1,maximum)))
    rng=random.Random(f'beatcut-events-v1:{int(seed)}:{kind}')
    expected=(end-start)*rate/60
    count=int(expected)+(rng.random()<expected-int(expected))
    # Same-effect events have gaps and never overlap, including slow-motion ramps.
    capacity=int((end-start)/(minimum+.05))
    count=min(count,capacity,10000)
    if count<=0:return ()
    cell=(end-start)/count
    result=[]
    for i in range(count):
        duration=rng.uniform(minimum,min(maximum,cell-.05))
        a=start+i*cell+rng.uniform(0,cell-duration)
        result.append((a,a+duration))
    return tuple(result)


def events(p,kind):
    if not p.get('random_mode') or not p.get(kind):return ()
    return schedule(kind,float(p['start']),float(p['end']),float(p.get('rate_'+kind,0)),
                    float(p['random_min']),float(p['random_max']),int(p['random_seed']))


def active(p,kind,t):
    seq=events(p,kind)
    i=bisect_right(seq,(t,float('inf')))-1
    if i>=0 and seq[i][0]<=t<seq[i][1]:return seq[i]
    return None


def local_params(p,kind,interval):
    q=dict(p,random_mode=False,start=interval[0],end=interval[1])
    for key in KINDS:q[key]=key==kind
    return q
