"""Cancellable proxy preparation, local face analysis and atomic effect export."""
from pathlib import Path
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import cv2
import numpy as np
from studio_engine import Cancelled, check, run
from fx_core import source_time, transform, smooth_track
from job_gate import serialized


def model_path():
    root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).parent
    return root/'models/face_detection_yunet_2023mar.onnx'


def detector():
    return cv2.FaceDetectorYN.create(str(model_path()),'',(320,320),.75,.3,5000)


def info(path):
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))
    v=next(s for s in data['streams'] if s['codec_type']=='video')
    from fractions import Fraction
    fps=float(Fraction(v.get('avg_frame_rate','0/1')))
    if not math.isfinite(fps) or not 1<=fps<=120:raise ValueError('Неподдерживаемая частота кадров.')
    return dict(width=int(v['width']),height=int(v['height']),fps=fps,
                audio=any(s['codec_type']=='audio' for s in data['streams']))


@serialized
def prepare(source, cache, cancel, progress):
    """Normalize a constant-FPS full-resolution master; proxy has identical frames.
    This extra encode costs time but makes arbitrary VFR/phone inputs predictable.
    """
    cache=Path(cache); original=info(source); fps=min(60,round(original['fps']))
    master=cache/'master.mp4'; proxy=cache/'proxy.mp4'; audio=cache/'audio.wav'
    progress(0,'Подготовка постоянной частоты кадров…')
    run(['ffmpeg','-v','error','-nostdin','-y','-i',str(source),'-map','0:v:0','-map','0:a:0?',
         '-vf',f'fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1','-c:v','libx264',
         '-preset','veryfast','-crf','18','-threads','2','-c:a','aac','-b:a','192k',str(master)],cancel)
    progress(40,'Подготовка облегчённого предпросмотра…')
    run(['ffmpeg','-v','error','-nostdin','-y','-i',str(master),'-an','-vf',
         'scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2',
         '-c:v','libx264','-preset','ultrafast','-crf','22','-g','1','-threads','2',str(proxy)],cancel)
    if original['audio']:
        progress(80,'Подготовка звука…')
        run(['ffmpeg','-v','error','-nostdin','-y','-i',str(master),'-vn','-ar','44100',
             '-ac','2','-c:a','pcm_s16le',str(audio)],cancel)
    cap=cv2.VideoCapture(str(proxy))
    try:
        count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or count<1:raise RuntimeError('Не удалось открыть видео для предпросмотра.')
    finally:cap.release()
    return dict(master=str(master),proxy=str(proxy),audio=str(audio) if audio.exists() else None,
                fps=fps,count=count,duration=count/fps)


@serialized
def analyze(proxy, cancel, progress):
    cap=cv2.VideoCapture(str(proxy)); detect=detector(); rows=[]
    count=max(1,int(cap.get(cv2.CAP_PROP_FRAME_COUNT))); fps=cap.get(cv2.CAP_PROP_FPS)
    previous=None; last=None; miss=0; scene=0
    try:
        while True:
            check(cancel); ok,frame=cap.read()
            if not ok:break
            h,w=frame.shape[:2]
            thumb=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(32,18)).astype(float)/255
            cut=previous is not None and np.mean(np.abs(thumb-previous))>.26
            previous=thumb
            if cut:last=None;miss=0;scene+=1
            detect.setInputSize((w,h)); _,faces=detect.detect(frame)
            chosen=None
            if faces is not None:
                if last is None:chosen=max(faces,key=lambda f:f[2]*f[3])
                else:
                    def distance(f):
                        return np.linalg.norm((f[4:6]+f[6:8])/2/np.array([w,h])-last[:2])
                    candidate=min(faces,key=distance)
                    # Do not jump to a far-away face during a brief loss.
                    if distance(candidate)<.25:chosen=candidate
            if chosen is not None:
                eyes=np.array([chosen[4:6],chosen[6:8]])
                eyes=eyes[np.argsort(eyes[:,0])]; d=eyes[1]-eyes[0]
                last=np.array([eyes[:,0].mean()/w,eyes[:,1].mean()/h,
                               np.linalg.norm(d)/w,math.atan2(d[1],d[0]),1.,scene])
                miss=0; rows.append(last.copy())
            else:
                miss+=1
                row=np.array([.5,.38,.14,0.,0.,scene]) if last is None else last.copy()
                row[4]=max(0,1-miss/max(1,.3*fps)); rows.append(row)
                if miss>fps:last=None
            if len(rows)%15==0:progress(100*len(rows)/count,'Локальный анализ лица…')
    finally:cap.release()
    return np.asarray(rows,dtype=np.float64).reshape(-1,6)


class Reader:
    def __init__(self,path):
        self.cap=cv2.VideoCapture(str(path)); self.pos=0; self.last=None; self.index=-1
        if not self.cap.isOpened():raise RuntimeError('Не удалось открыть видео: '+str(path))
    def get(self,index):
        if index==self.index and self.last is not None:return self.last.copy()
        if index<self.pos or index-self.pos>12:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES,index); self.pos=index
        while self.pos<=index:
            ok,frame=self.cap.read()
            if not ok:raise RuntimeError(f'Не удалось прочитать кадр {index}.')
            self.pos+=1
        self.last=frame; self.index=index
        return frame.copy()
    def close(self):self.cap.release()


@serialized
def export(data, output, params, raw_track, cancel, progress):
    output=Path(output); reader=Reader(data['master']); proc=None
    track=smooth_track(raw_track,params['smooth'],data['fps'])
    if params['face'] and track is None:raise ValueError('Сначала выполните анализ лица.')
    fps=data['fps']; count=data['count']
    # Temporary output on the destination filesystem: existing output survives failures.
    try:
        with tempfile.TemporaryDirectory(prefix='.beatcut-fx-',dir=output.parent) as tmp:
            tmp=Path(tmp); silent=tmp/'video.mp4'; final=tmp/'final.mp4'
            first=reader.get(0); h,w=first.shape[:2]
            with (tmp/'ffmpeg.log').open('w+b') as log:
                cmd=['ffmpeg','-v','error','-nostdin','-y','-f','rawvideo','-pix_fmt','bgr24',
                     '-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264',
                     '-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-threads','2',str(silent)]
                proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
                try:
                    for i in range(count):
                        check(cancel); t=i/fps; st=source_time(t,params)
                        index=min(count-1,max(0,int(st*fps+1e-6)))
                        frame=transform(reader.get(index),t,st,params,track,fps)
                        proc.stdin.write(frame.tobytes())
                        if i%10==0:progress(90*i/count,'Экспорт эффектов…')
                    proc.stdin.close()
                    while proc.poll() is None:check(cancel);time.sleep(.05)
                    if proc.returncode:raise RuntimeError('FFmpeg не завершил экспорт.')
                except BrokenPipeError:
                    log.seek(0);raise RuntimeError(log.read().decode(errors='replace')[-3000:])
                finally:
                    if proc.poll() is None:
                        proc.kill();proc.wait()
                    if not proc.stdin.closed:proc.stdin.close()
            progress(95,'Сохранение музыки…')
            run(['ffmpeg','-v','error','-nostdin','-y','-i',str(silent),'-i',data['master'],
                 '-map','0:v:0','-map','1:a:0?','-c','copy','-t',str(count/fps),
                 '-movflags','+faststart',str(final)],cancel)
            check(cancel);os.replace(final,output)
    finally:reader.close()
    progress(100,'Экспорт готов: '+output.name)
