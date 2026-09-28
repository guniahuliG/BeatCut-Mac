"""Conservative per-clip SDR color matching using FFmpeg's native LUT filter.

Samples several frames from each source range, compares robust BGR distributions
with a reference clip, and emits bounded per-channel affine LUT expressions.
"""
import math
import cv2
import numpy as np


def sample_range(path, start=0., duration=None, count=5):
    cap=cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():raise ValueError('Не удалось открыть видео для анализа цвета: '+str(path))
        fps=cap.get(cv2.CAP_PROP_FPS) or 30.
        nframes=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total=nframes/fps if fps>0 else 0
        stop=total if duration is None else min(total,start+max(0.,duration))
        if stop<=start:raise ValueError('Пустой участок при анализе цвета.')
        times=np.linspace(start,stop,max(1,count+2))[1:-1]
        frames=[]
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC,float(t)*1000)
            ok,frame=cap.read()
            if ok:
                frame=cv2.resize(frame,(160,90),interpolation=cv2.INTER_AREA)
                frames.append(frame.reshape(-1,3))
        if not frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES,0);ok,frame=cap.read()
            if not ok:raise ValueError('Не удалось прочитать кадры для анализа цвета.')
            frames=[cv2.resize(frame,(160,90),interpolation=cv2.INTER_AREA).reshape(-1,3)]
        pixels=np.concatenate(frames).astype(np.float32)
        lo=np.percentile(pixels,5,axis=0);hi=np.percentile(pixels,95,axis=0)
        keep=np.all((pixels>=lo)&(pixels<=hi),axis=1)
        pixels=pixels[keep] if keep.sum()>32 else pixels
        return pixels.mean(axis=0),np.maximum(pixels.std(axis=0),4.)
    finally:cap.release()


def match_lut(source, reference, strength=.55):
    sm,ss=source;rm,rs=reference
    alpha=float(np.clip(strength,0,1))
    gain=np.clip(rs/ss,.65,1.55)
    offset=np.clip(rm-sm*gain,-36,36)*alpha
    gain=1+(gain-1)*alpha
    # FFmpeg lutrgb channel names are RGB; samples use OpenCV's BGR order.
    values={name:(float(g),float(o)) for name,g,o in zip('bgr',gain,offset)}
    def expr(g,o):
        return "clip(val*%.6f%+.6f\\,0\\,255)"%(g,o)
    return 'lutrgb='+':'.join(f"{channel}='{expr(*values[channel])}'" for channel in 'rgb')
