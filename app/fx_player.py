"""Lightweight Tk player. macOS afplay audio clock is approximate, not sample-locked."""
from pathlib import Path
import subprocess
import sys
import time
import wave
import tkinter as tk
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
from fx_core import source_time, transform
from fx_media import Reader


class Player(ttk.Frame):
    def __init__(self,parent,data,cache,parameters,track,status):
        super().__init__(parent,padding=8)
        self.data=data;self.cache=Path(cache);self.parameters=parameters;self.track=track;self.status=status
        self.reader=Reader(data['proxy']);self.position=0.;self.playing=False;self.closed=False
        self.audio_process=None;self.drag=False;self.photo=None;self.original=tk.BooleanVar(value=False)
        self.image=ttk.Label(self,anchor='center');self.image.pack(fill='both',expand=True)
        self.seek=ttk.Scale(self,from_=0,to=data['duration']);self.seek.pack(fill='x',pady=8)
        self.seek.bind('<ButtonPress-1>',self.begin_seek)
        self.seek.bind('<ButtonRelease-1>',self.end_seek)
        self.seek.bind('<KeyRelease>',self.end_seek)
        buttons=ttk.Frame(self);buttons.pack(fill='x')
        self.button=ttk.Button(buttons,text='▶ Воспроизвести',command=self.toggle);self.button.pack(side='left')
        ttk.Button(buttons,text='В начало',command=self.rewind).pack(side='left',padx=4)
        ttk.Checkbutton(buttons,text='Без эффектов',variable=self.original,command=self.redraw).pack(side='left',padx=6)
        self.time_label=ttk.Label(buttons,text='');self.time_label.pack(side='right')
        ttk.Label(self,text='Предпросмотр ≤ 640×360; экспорт — в разрешении черновика.\n'
                  'Звук: приблизительная синхронизация; при перегрузке видеокадры пропускаются.',wraplength=580).pack(anchor='w',pady=8)
        self.after(100,self.tick)

    def stop_audio(self):
        if self.audio_process is not None:
            if self.audio_process.poll() is None:
                self.audio_process.terminate()
                try:self.audio_process.wait(timeout=1)
                except subprocess.TimeoutExpired:self.audio_process.kill();self.audio_process.wait()
            self.audio_process=None

    def start_audio(self):
        self.stop_audio()
        if not self.data['audio']:return
        if sys.platform=='darwin':
            segment=self.cache/'playing.wav'
            # Bounded-memory copying, no system Python or player installation required.
            with wave.open(self.data['audio'],'rb') as src, wave.open(str(segment),'wb') as dst:
                dst.setparams(src.getparams())
                src.setpos(min(src.getnframes(),int(self.position*src.getframerate())))
                while True:
                    block=src.readframes(65536)
                    if not block:break
                    dst.writeframesraw(block)
            command=['/usr/bin/afplay',str(segment)]
        else:
            command=['ffplay','-nodisp','-autoexit','-loglevel','error','-ss',str(self.position),self.data['audio']]
        try:self.audio_process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError:self.status('Не удалось включить звук предпросмотра. Экспорт сохранит музыку.')

    def toggle(self):
        if self.playing:self.pause();return
        if self.position>=self.data['duration']-1/self.data['fps']:self.position=0
        self.start_audio();self.origin=time.monotonic()-self.position
        self.playing=True;self.button.configure(text='⏸ Пауза')

    def pause(self):
        if self.playing:self.position=min(self.data['duration'],time.monotonic()-self.origin)
        self.playing=False;self.stop_audio();self.button.configure(text='▶ Воспроизвести')

    def rewind(self):
        self.pause();self.position=0;self.seek.set(0);self.redraw()

    def begin_seek(self,event=None):
        self.pause();self.drag=True

    def end_seek(self,event=None):
        self.pause();self.drag=False;self.position=float(self.seek.get());self.redraw()

    def redraw(self):
        if self.closed:return
        try:
            p=self.parameters();t=min(self.position,self.data['duration']-1/self.data['fps'])
            st=t if self.original.get() else source_time(t,p)
            i=min(self.data['count']-1,max(0,int(st*self.data['fps']+1e-6)))
            frame=self.reader.get(i)
            if not self.original.get():frame=transform(frame,t,st,p,self.track(),self.data['fps'])
            image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            image.thumbnail((max(160,self.image.winfo_width()),max(90,self.image.winfo_height())),Image.Resampling.BILINEAR)
            self.photo=ImageTk.PhotoImage(image);self.image.configure(image=self.photo)
            self.time_label.configure(text=f'{self.position:.2f} / {self.data["duration"]:.2f} с')
        except Exception as e:
            self.pause();self.status('Предпросмотр: '+str(e))

    def tick(self):
        if self.closed:return
        if self.playing:
            self.position=time.monotonic()-self.origin
            if self.position>=self.data['duration']:
                self.pause();self.position=self.data['duration']
            if not self.drag:self.seek.set(self.position)
            self.redraw()
        self.after(25,self.tick)

    def close(self):
        self.pause();self.closed=True;self.reader.close()
