"""Resource-conscious sequential queue: independent source/audio setup per track."""
from pathlib import Path
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from studio_engine import render,Cancelled

VIDEO_TYPES=[('Видео','*.mp4 *.mov *.mkv *.avi *.webm *.m4v'),('Все файлы','*')]
AUDIO_TYPES=[('Музыка','*.mp3 *.wav *.m4a *.flac *.aac *.ogg *.opus'),('Все файлы','*')]


class TrackTab(ttk.Frame):
    def __init__(self,parent,index,base):
        super().__init__(parent,padding=10);self.index=index;self.base=dict(base);self.videos=[]
        self.name=tk.StringVar(value=f'Трек {index}');self.audio=tk.StringVar();self.output=tk.StringVar()
        self.duration=tk.StringVar(value='0');self.seed=tk.StringVar();self.repeat=tk.StringVar(value=base.get('repeat_policy','Редкие повторы'))
        self.cooldown=tk.StringVar(value=str(base.get('repeat_cooldown',8.)))
        self.color_enabled=tk.BooleanVar(value=bool(base.get('color_match',False)))
        self.color_reference=tk.StringVar(value=str(base.get('color_reference','')))
        self.color_strength=tk.DoubleVar(value=float(base.get('color_strength',.55)))
        self.status=tk.StringVar(value='Добавьте видео и укажите аудиотрек.')
        self.columnconfigure(1,weight=1)
        ttk.Label(self,text='Название').grid(row=0,column=0,sticky='w')
        ttk.Entry(self,textvariable=self.name).grid(row=0,column=1,sticky='ew',pady=3)
        actions=ttk.Frame(self);actions.grid(row=1,column=0,columnspan=2,sticky='ew')
        ttk.Button(actions,text='Добавить видео…',command=self.add).pack(side='left')
        ttk.Button(actions,text='Удалить выбранные',command=self.remove).pack(side='left',padx=5)
        self.list=tk.Listbox(self,height=6,selectmode='extended',exportselection=False)
        self.list.grid(row=2,column=0,columnspan=2,sticky='nsew',pady=4)
        self.rowconfigure(2,weight=1)
        ttk.Label(self,text='Музыка').grid(row=3,column=0,sticky='w')
        music=ttk.Frame(self);music.grid(row=3,column=1,sticky='ew')
        ttk.Entry(music,textvariable=self.audio).pack(side='left',fill='x',expand=True)
        ttk.Button(music,text='Выбрать…',command=self.pick_audio).pack(side='right')
        ttk.Label(self,text='Результат MP4').grid(row=4,column=0,sticky='w')
        out=ttk.Frame(self);out.grid(row=4,column=1,sticky='ew')
        ttk.Entry(out,textvariable=self.output).pack(side='left',fill='x',expand=True)
        ttk.Button(out,text='Куда…',command=self.pick_output).pack(side='right')
        opts=ttk.LabelFrame(self,text='Настройки этого трека',padding=6);opts.grid(row=5,column=0,columnspan=2,sticky='ew',pady=6)
        ttk.Label(opts,text='Длительность, сек. (0 = весь трек)').grid(row=0,column=0,sticky='w')
        ttk.Entry(opts,textvariable=self.duration,width=10).grid(row=0,column=1,sticky='w')
        ttk.Label(opts,text='Seed').grid(row=0,column=2,sticky='e',padx=(10,2))
        ttk.Entry(opts,textvariable=self.seed,width=12).grid(row=0,column=3,sticky='w')
        ttk.Label(opts,text='Повторы исходных моментов').grid(row=1,column=0,sticky='w')
        ttk.Combobox(opts,textvariable=self.repeat,values=['Редкие повторы','Без повторов','Свободно'],state='readonly',width=20).grid(row=1,column=1,sticky='w')
        ttk.Label(opts,text='Пауза, сек.').grid(row=1,column=2,sticky='e',padx=(10,2))
        ttk.Entry(opts,textvariable=self.cooldown,width=8).grid(row=1,column=3,sticky='w')
        ttk.Checkbutton(opts,text='SDR color match',variable=self.color_enabled).grid(row=2,column=0,sticky='w')
        ttk.Entry(opts,textvariable=self.color_reference).grid(row=2,column=1,columnspan=2,sticky='ew')
        ttk.Button(opts,text='Эталон…',command=self.pick_color).grid(row=2,column=3,sticky='w')
        ttk.Label(opts,text='Сила').grid(row=3,column=0,sticky='w')
        ttk.Scale(opts,from_=0,to=1,variable=self.color_strength).grid(row=3,column=1,columnspan=3,sticky='ew')
        ttk.Label(self,text='Каждая вкладка имеет свои видео, музыку, имя и результат. Экспорт выполняется последовательно — одновременно только одна работа.',wraplength=680).grid(row=6,column=0,columnspan=2,sticky='w')
        ttk.Label(self,textvariable=self.status,wraplength=680).grid(row=7,column=0,columnspan=2,sticky='w',pady=6)

    def add(self):
        paths=filedialog.askopenfilenames(parent=self,title=f'Видео для {self.name.get()}',filetypes=VIDEO_TYPES)
        known={str(Path(x).resolve()) for x in self.videos}
        for p in paths:
            p=str(Path(p).resolve())
            if p not in known:self.videos.append(p);known.add(p)
        self.refresh()

    def refresh(self):
        self.list.delete(0,'end')
        for i,p in enumerate(self.videos,1):self.list.insert('end',f'{i}. {Path(p).name}')
        self.status.set(f'{len(self.videos)} видеофрагмент(ов).')

    def remove(self):
        for i in reversed(self.list.curselection()):del self.videos[i]
        self.refresh()

    def pick_audio(self):
        p=filedialog.askopenfilename(parent=self,title=f'Музыка для {self.name.get()}',filetypes=AUDIO_TYPES)
        if p:self.audio.set(p)

    def pick_color(self):
        p=filedialog.askopenfilename(parent=self,title=f'SDR-эталон цвета для {self.name.get()}',filetypes=VIDEO_TYPES)
        if p:self.color_reference.set(p)

    def pick_output(self):
        p=filedialog.asksaveasfilename(parent=self,title=f'Результат {self.name.get()}',defaultextension='.mp4',filetypes=[('MP4','*.mp4')],initialfile=f'{self.name.get().replace(" ","_")}.mp4')
        if p:self.output.set(p)

    def snapshot(self):
        if not self.videos:raise ValueError(f'{self.name.get()}: не добавлены исходные видео.')
        if not Path(self.audio.get()).is_file():raise ValueError(f'{self.name.get()}: выберите существующий аудиотрек.')
        out=Path(self.output.get()).resolve()
        if out.suffix.lower()!='.mp4':raise ValueError(f'{self.name.get()}: выберите путь результата с расширением .mp4.')
        duration=float(self.duration.get().replace(',','.'))
        cooldown=float(self.cooldown.get().replace(',','.'))
        seed=int(self.seed.get()) if self.seed.get().strip() else None
        if not math.isfinite(duration) or duration<0 or not math.isfinite(cooldown) or cooldown<0:
            raise ValueError(f'{self.name.get()}: проверьте длительность и паузу повторов.')
        settings=dict(self.base,duration=duration,seed=seed,repeat_policy=self.repeat.get(),repeat_cooldown=cooldown,
                      color_match=bool(self.color_enabled.get()),color_reference=self.color_reference.get().strip(),
                      color_strength=float(self.color_strength.get()))
        if settings['color_match'] and not Path(settings['color_reference']).is_file():
            raise ValueError(f'{self.name.get()}: выберите существующий SDR-эталон цвета.')
        return dict(name=self.name.get().strip() or f'Трек {self.index}',videos=list(self.videos),music=self.audio.get(),output=out,settings=settings)
