"""Deterministic source-range selection with optional reuse limits.

Overlap prevention is based on source timecodes, not visual similarity.
"""
from pathlib import Path
import math

POLICIES={
    'Свободно':'free','Свободный рандом':'free','free':'free',
    'Редкие повторы':'rare','rare':'rare',
    'Без повторов':'never','never':'never'
}


def _subtract(ranges, start, end):
    out=[]
    for a,b in ranges:
        if end<=a or start>=b:out.append((a,b));continue
        if a<start:out.append((a,start))
        if end<b:out.append((end,b))
    return [(a,b) for a,b in out if b>a]


def _free_starts(ranges, shot):
    return [(a,b-shot) for a,b in ranges if b-a>=shot]


def _pick_candidate(groups,rng,pack=False):
    """Pick a valid start; pack mode avoids fragmenting unused footage."""
    choices=[]
    for path,windows in groups.items():
        for lo,hi in windows:
            if hi>=lo:choices.append((path,lo,hi))
    if not choices:return None
    if pack:
        best=max(hi-lo for _,lo,hi in choices)
        choices=[x for x in choices if x[2]-x[1]>=best]
        path,lo,hi=choices[int(rng.integers(len(choices)))]
        return path,int(lo if rng.random()<.5 else hi)
    weights=[hi-lo+1 for _,lo,hi in choices]
    total=sum(weights);draw=int(rng.integers(total))
    for (path,lo,hi),weight in zip(choices,weights):
        if draw<weight:return path,int(lo+rng.integers(hi-lo+1))
        draw-=weight
    path,lo,hi=choices[-1];return path,int(hi)


def source_plan(videos,lengths,fps,rng,policy='Редкие повторы',cooldown=8.,
                diversity=.8,starts=None,ends=None,cancel=None):
    """Plan clip selections.

    - never: source-frame ranges do not overlap anywhere in the project;
    - rare: reuse is delayed by `cooldown` seconds when the source pool allows it;
      if all remaining material is blocked, reuse is allowed rather than failing;
    - free: source ranges may repeat at any time.

    The `lengths` values are source clip lengths in frames (including transition
    handles). Optional `starts`/`ends` provide output-timeline times in frames.
    """
    if policy not in POLICIES:raise ValueError('Неизвестный режим повторов.')
    mode=POLICIES[policy]
    if not math.isfinite(float(cooldown)) or cooldown<0:raise ValueError('Интервал повтора должен быть неотрицательным.')
    if not math.isfinite(float(diversity)) or not 0<=diversity<=1:raise ValueError('Разнообразие должно быть от 0 до 1.')
    if not math.isfinite(float(fps)) or fps<=0:raise ValueError('Некорректная частота кадров.')
    lengths=[int(n) for n in lengths]
    if any(n<=0 for n in lengths):raise ValueError('Длина каждого фрагмента должна быть больше нуля.')
    if starts is None:
        starts=[];cursor=0
        for n in lengths:starts.append(cursor);cursor+=n
    if ends is None:ends=[a+n for a,n in zip(starts,lengths)]
    if len(starts)!=len(lengths) or len(ends)!=len(lengths):raise ValueError('Длины плана не совпадают.')
    sources={}
    for video in videos:
        path=str(Path(video['path']).resolve())
        cap=max(0,math.floor(float(video['duration'])*fps)-2)
        sources[path]=max(sources.get(path,0),cap)
    if not sources:raise ValueError('Не выбраны исходные видео.')
    unused={p:[(0,cap)] for p,cap in sources.items() if cap>0}
    used={p:[] for p in sources};history=[];plan=[None]*len(lengths);last_path=None
    order=sorted(range(len(lengths)),key=lambda i:-lengths[i]) if mode=='never' else list(range(len(lengths)))
    for i in order:
        if cancel:cancel()
        n=lengths[i]
        # Free mode samples any valid point and does not update exclusion ranges.
        if mode=='free':
            groups={p:[(0,cap-n)] for p,cap in sources.items() if cap>=n}
        else:
            groups={p:_free_starts(ranges,n) for p,ranges in unused.items()}
            groups={p:r for p,r in groups.items() if r}
            if not groups and mode=='rare':
                # Exclude source ranges used too recently. If this leaves no
                # candidate, relax the cooldown rather than breaking the montage.
                allowed={p:[(0,cap)] for p,cap in sources.items() if cap>=n}
                output_start=float(starts[i])/fps
                for item in history:
                    if output_start-float(item['output_end'])/fps < cooldown:
                        p=item['source'];a=item['_a'];b=item['_b']
                        allowed[p]=_subtract(allowed.get(p,[]),a,b)
                groups={p:_free_starts(ranges,n) for p,ranges in allowed.items()}
                groups={p:r for p,r in groups.items() if r}
                if not groups:groups={p:[(0,cap-n)] for p,cap in sources.items() if cap>=n}
        candidate=_pick_candidate(groups,rng,pack=(mode=='never' or bool(unused.get(next(iter(groups),'')))))
        if candidate is None:
            raise ValueError('Для режима «Без повторов» не хватает уникального исходного видеоучастка. Добавьте видео, сократите длину монтажа или выберите «Редкие повторы».')
        path,a=candidate;b=a+n
        repeat=any(path==x['source'] and a<x['_b'] and b>x['_a'] for x in history)
        plan[i]={'source':path,'start':a/fps,'frames':n,'end':b/fps,
                 'output_start':int(starts[i]),'output_end':int(ends[i]),'repeat':repeat}
        if mode!='free':
            used[path].append((a,b));unused[path]=_subtract(unused[path],a,b)
        history.append({'source':path,'_a':a,'_b':b,'output_end':int(ends[i])})
        last_path=path
    # Drop private frame-grid bookkeeping; stable timecode values remain.
    return plan
