"""Deterministic effects shared by the preview and full-resolution export."""
import math
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

DEFAULTS = dict(start=0., end=10., fade=.12, crop=1.12,
    face=False, face_strength=1., smooth=.08, face_roll=True, face_size=False,
    target_size=.14, slow=False, speed=.5, rewind=False, rewind_amount=.75,
    zoom=False, zoom_amount=.20, zoom_period=2., zoom_mode='Пульс', shake=False,
    shake_amount=.025, shake_hz=8., shake_roll=2., flash=False, flash_hz=6.,
    flash_alpha=.4, flash_duty=.15)
from fx_random import RANDOM_DEFAULTS, active, local_params
DEFAULTS.update(RANDOM_DEFAULTS)


def envelope(t, p):
    a,b=p['start'],p['end']
    if b<=a or t<a or t>=b:return 0.
    f=min(p['fade'], (b-a)/2)
    if f<=0:return 1.
    x=min(1.,(t-a)/f,(b-t)/f)
    return x*x*(3-2*x)


def source_time(t,p):
    """Rewind takes priority over slow motion; returns to timeline at event end."""
    if p.get('random_mode'):
        interval=active(p,'rewind',t)
        if interval is not None:return rewind_time(t,*interval,p.get('rewind_amount',.75))
        interval=active(p,'slow',t)
        if interval is None:return t
        p=local_params(p,'slow',interval)
    a,b=p['start'],p['end']
    if p.get('rewind') and b>a and a<=t<b:
        return rewind_time(t,a,b,p.get('rewind_amount',.75))
    if not p.get('slow') or b<=a or not a<t<b:return t
    u=(t-a)/(b-a)
    return t-(1-p['speed'])*(b-a)*(1-math.cos(2*math.pi*u))/(2*math.pi)


def rewind_time(t,a,b,amount):
    if not a<=t<b or b<=a:return t
    u=(t-a)/(b-a);depth=.42*float(np.clip(amount,.25,1.25))
    if u<=.4:v=(u/.4)*depth
    elif u<=.7:v=depth*(1-(u-.4)/.3)
    else:v=(u-.7)/.3
    return a+v*(b-a)


def smooth_track(raw, seconds, fps):
    if raw is None:return None
    result=raw.copy()
    # columns: centre x,y; eye distance; roll radians; confidence; scene index.
    edges=np.r_[0,np.flatnonzero(np.diff(raw[:,5]))+1,len(raw)]
    for a,b in zip(edges[:-1],edges[1:]):
        if b-a>1 and seconds>0:
            result[a:b,:4]=gaussian_filter1d(raw[a:b,:4],max(.01,seconds*fps),axis=0,mode='nearest')
    return result


def transform(frame, t, st, p, track=None, fps=30):
    if p.get('random_mode'):
        # Independent scopes; fixed order makes overlapping effects reproducible.
        # Crop is applied only once, not compounded by every geometric effect.
        scopes=[]
        for kind in ('face','zoom','shake','flash'):
            interval=active(p,kind,t)
            if interval is not None and (kind!='face' or track is not None):
                scopes.append((kind,local_params(p,kind,interval)))
        # Track coordinates refer to the original frame: face transform comes first.
        # Add overscan after geometric transforms, before the white overlay.
        geometries=[q for kind,q in scopes if kind!='flash']
        for kind,q in scopes:
            if kind=='flash':continue
            q['crop']=1.
            frame=transform(frame,t,st,q,track,fps)
        if geometries and p['crop']!=1:
            strongest=max(geometries,key=lambda q:envelope(t,q))
            crop_params=dict(strongest,face=False,shake=False,flash=False,zoom=True,
                             zoom_amount=0.,crop=p['crop'])
            frame=transform(frame,t,st,crop_params,track,fps)
        for kind,q in scopes:
            if kind=='flash':frame=transform(frame,t,st,q,track,fps)
        return frame
    h,w=frame.shape[:2]; gain=envelope(t,p)
    # With every effect off, return original pixels (no hidden crop).
    geometry=gain>0 and (p['zoom'] or p['shake'] or (p['face'] and track is not None))
    if geometry:
        center=np.array([w*.5,h*.5]); target=center.copy()
        scale=1+(p['crop']-1)*gain; angle=0.
        if p['face'] and track is not None and len(track):
            row=track[min(len(track)-1,max(0,int(st*fps)))]
            strength=gain*p['face_strength']*row[4]
            point=np.array([row[0]*w,row[1]*h])
            center=center*(1-strength)+point*strength
            target=target*(1-strength)+np.array([w*.5,h*.38])*strength
            if p['face_roll']:angle+=math.degrees(row[3])*strength
            if p['face_size']:
                scale*=1+(np.clip(p['target_size']/max(row[2],.01),.65,2.5)-1)*strength
        if p['zoom']:
            u=((t-p['start'])/max(.2,p['zoom_period']))%1
            z=(1-math.cos(2*math.pi*u))/2
            if p['zoom_mode']=='Приближение':z=u*u*(3-2*u)
            elif p['zoom_mode']=='Отдаление':z=1-u*u*(3-2*u)
            scale*=1+gain*p['zoom_amount']*z
        if p['shake']:
            q=2*math.pi*p['shake_hz']*(t-p['start'])
            amount=gain*p['shake_amount']*min(w,h)
            target+=amount*np.array([.7*math.sin(q)+.3*math.sin(q*1.71+.4),
                                     .7*math.sin(q*1.13+.8)+.3*math.sin(q*2.07)])
            angle+=gain*p['shake_roll']*math.sin(q*.83)
        matrix=cv2.getRotationMatrix2D(tuple(center),angle,float(scale))
        matrix[:,2]+=target-center
        frame=cv2.warpAffine(frame,matrix,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    if p['flash'] and gain>0:
        phase=((t-p['start'])*p['flash_hz'])%1
        if phase<p['flash_duty']:
            alpha=p['flash_alpha']*gain
            frame=cv2.addWeighted(frame,1-alpha,np.full_like(frame,255),alpha,0)
    return frame
