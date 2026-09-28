"""BeatCut Studio — Tkinter desktop interface. Run: python studio.py"""
from pathlib import Path
import math
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from studio_engine import render, Cancelled, EFFECTS

SIZES={'HD 1280×720':(1280,720),'Full HD 1920×1080':(1920,1080),
       'Вертикально 1080×1920':(1080,1920),'Квадрат 1080×1080':(1080,1080),
       'Быстрый тест 640×360':(640,360)}
STYLES={'Спокойный':(.2,.35,.7,6,.2,.3),
        'Клиповый':(.65,.8,.35,4,.45,.18),
        'Динамичный':(.9,1.,.25,2.5,.65,.12)}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('BeatCut Studio • монтаж под музыку')
        self.geometry('870x820'); self.minsize(720,600)
        self.events=queue.Queue(); self.cancel=threading.Event()
        self.busy=False; self.videos=[]; self.last_output=None
        self.audio=tk.StringVar(); self.output=tk.StringVar()
        self.status=tk.StringVar(value='Выберите файлы, настройте стиль и нажмите «Рендеринг».')
        self.video_label=tk.StringVar(value='Видео не выбрано')
        self.vars={}; self.effects={name:tk.BooleanVar(value=True) for name in EFFECTS}
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('TButton',padding=7)
        style.configure('Title.TLabel',font=('Arial',19,'bold'))
        outer=ttk.Frame(self,padding=12); outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='BeatCut Studio',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='Случайные фрагменты • акценты музыки • разные переходы').pack(anchor='w',pady=(0,10))
        canvas=tk.Canvas(outer,highlightthickness=0)
        scrollbar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y'); canvas.pack(fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body=ttk.Frame(canvas,padding=(0,0,12,8))
        win=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        files=ttk.LabelFrame(body,text='1. Файлы',padding=10); files.pack(fill='x',pady=6)
        files.columnconfigure(1,weight=1)
        ttk.Button(files,text='Открыть видео…',command=self.pick_video).grid(row=0,column=0,sticky='w')
        ttk.Label(files,textvariable=self.video_label,wraplength=450).grid(row=0,column=1,sticky='w',padx=8)
        ttk.Button(files,text='Открыть аудио…',command=self.pick_audio).grid(row=1,column=0,sticky='w')
        ttk.Entry(files,textvariable=self.audio).grid(row=1,column=1,sticky='ew',padx=8)
        ttk.Button(files,text='Сохранить как…',command=self.pick_output).grid(row=2,column=0,sticky='w')
        ttk.Entry(files,textvariable=self.output).grid(row=2,column=1,sticky='ew',padx=8)
        edit=ttk.LabelFrame(body,text='2. Характер монтажа',padding=10); edit.pack(fill='x',pady=6)
        presets=ttk.Frame(edit); presets.pack(fill='x')
        ttk.Label(presets,text='Быстрый стиль:').pack(side='left')
        for name in STYLES:
            ttk.Button(presets,text=name,command=lambda n=name:self.preset(n)).pack(side='left',padx=3)
        self.slider(edit,'density','Плотность склеек',0,1,.65,True)
        self.slider(edit,'variety','Разнообразие ритма',0,1,.8,True)
        self.slider(edit,'min_shot','Минимальный кадр, сек.',.2,2,.35)
        self.slider(edit,'max_shot','Максимальный кадр, сек.',1,10,4)
        ttk.Label(edit,text='Разнообразие меняет разброс длительностей и вероятность коротких серий.').pack(anchor='w')
        self.repeat_policy=tk.StringVar(value='Редкие повторы')
        self.repeat_cooldown=tk.DoubleVar(value=8.)
        repeat=ttk.LabelFrame(edit,text='Повтор исходных моментов',padding=8); repeat.pack(fill='x',pady=(8,0))
        ttk.Combobox(repeat,textvariable=self.repeat_policy,values=['Свободно','Редкие повторы','Без повторов'],state='readonly').pack(fill='x')
        row=ttk.Frame(repeat); row.pack(fill='x',pady=4)
        ttk.Label(row,text='Пауза до повтора, сек. готового видео:').pack(side='left')
        ttk.Spinbox(row,from_=0,to=600,increment=1,textvariable=self.repeat_cooldown,width=7).pack(side='right')
        ttk.Label(repeat,text='«Без повторов» запрещает повторное использование исходного участка за весь монтаж и остановится до рендера, если материала не хватит.').pack(anchor='w')
        color=ttk.LabelFrame(edit,text='Выравнивание цвета SDR по эталону',padding=8);color.pack(fill='x',pady=(8,0))
        self.color_enabled=tk.BooleanVar(value=False);self.color_reference=tk.StringVar()
        ttk.Checkbutton(color,text='Смягчённо подгонять цвет каждого фрагмента',variable=self.color_enabled).pack(anchor='w')
        cr=ttk.Frame(color);cr.pack(fill='x',pady=3)
        ttk.Entry(cr,textvariable=self.color_reference).pack(side='left',fill='x',expand=True)
        ttk.Button(cr,text='Эталон…',command=self.pick_color_reference).pack(side='right')
        ttk.Label(color,text='Коррекция по средним BGR-статистикам исходного фрагмента; только SDR, мягкая сила по умолчанию. Не профессиональный grade.').pack(anchor='w')
        row=ttk.Frame(color);row.pack(fill='x')
        ttk.Label(row,text='Сила match, 0–100%').pack(side='left')
        self.color_strength=tk.DoubleVar(value=.55)
        ttk.Scale(row,from_=0,to=1,variable=self.color_strength).pack(side='left',fill='x',expand=True)
        trans=ttk.LabelFrame(body,text='3. Переходы — вперемешку с обычными склейками',padding=10)
        trans.pack(fill='x',pady=6)
        self.slider(trans,'effect_rate','Частота переходов',0,1,.45,True)
        self.slider(trans,'transition','Длительность перехода, сек.',.07,.6,.18)
        checks=ttk.Frame(trans); checks.pack(fill='x')
        for i,(name,var) in enumerate(self.effects.items()):
            ttk.Checkbutton(checks,text=name,variable=var).grid(row=i//3,column=i%3,sticky='w',padx=7,pady=2)
        ttk.Label(trans,text='Переход заканчивается на акценте; соседние эффекты по возможности не повторяются.').pack(anchor='w',pady=(5,0))
        export=ttk.LabelFrame(body,text='4. Экспорт',padding=10); export.pack(fill='x',pady=6)
        self.size=tk.StringVar(value='HD 1280×720'); self.fps=tk.StringVar(value='30')
        self.fit=tk.StringVar(value='Заполнить с обрезкой'); self.quality=tk.StringVar(value='Обычное')
        self.duration=tk.StringVar(value='0'); self.seed=tk.StringVar()
        rows=[('Размер',self.size,list(SIZES)),('Кадров в секунду',self.fps,['24','25','30','60']),
              ('Вписывание',self.fit,['Заполнить с обрезкой','Вписать с полями']),
              ('Качество',self.quality,['Быстрый черновик','Обычное','Высокое'])]
        export.columnconfigure(1,weight=1)
        for i,(label,var,values) in enumerate(rows):
            ttk.Label(export,text=label).grid(row=i,column=0,sticky='w',padx=(0,12),pady=3)
            ttk.Combobox(export,textvariable=var,values=values,state='readonly').grid(row=i,column=1,sticky='ew',pady=3)
        for i,(label,var) in enumerate([('Длина, сек. (0 = весь трек)',self.duration),
                                       ('Seed (пусто = новый вариант)',self.seed)],start=4):
            ttk.Label(export,text=label).grid(row=i,column=0,sticky='w',pady=3)
            ttk.Entry(export,textvariable=var).grid(row=i,column=1,sticky='ew',pady=3)
        footer=ttk.Frame(self,padding=12); footer.pack(fill='x')
        self.bar=ttk.Progressbar(footer,maximum=100); self.bar.pack(fill='x')
        ttk.Label(footer,textvariable=self.status,wraplength=790).pack(anchor='w',pady=5)
        buttons=ttk.Frame(footer); buttons.pack(fill='x')
        self.start_button=ttk.Button(buttons,text='▶  Рендеринг',command=self.start); self.start_button.pack(side='left')
        self.stop_button=ttk.Button(buttons,text='Остановить',command=self.stop,state='disabled'); self.stop_button.pack(side='left',padx=8)
        self.open_button=ttk.Button(buttons,text='Открыть результат',command=self.open_result,state='disabled'); self.open_button.pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.poll)

    def slider(self,parent,key,label,lo,hi,value,percent=False):
        row=ttk.Frame(parent); row.pack(fill='x',pady=5)
        ttk.Label(row,text=label,width=30).pack(side='left')
        var=tk.DoubleVar(value=value); self.vars[key]=var
        text=tk.StringVar()
        def update(*_):
            text.set(f'{var.get()*100:.0f}%' if percent else f'{var.get():.2f}')
        var.trace_add('write',update); update()
        ttk.Label(row,textvariable=text,width=7,anchor='e').pack(side='right')
        ttk.Scale(row,variable=var,from_=lo,to=hi).pack(side='left',fill='x',expand=True)

    def preset(self,name):
        for key,value in zip(('density','variety','min_shot','max_shot','effect_rate','transition'),STYLES[name]):
            self.vars[key].set(value)

    def pick_video(self):
        paths=filedialog.askopenfilenames(title='Выберите одно или несколько видео',filetypes=[('Видео','*.mp4 *.mov *.mkv *.avi *.webm *.m4v'),('Все файлы','*')])
        if paths:
            self.videos=list(paths)
            self.video_label.set(f'{len(paths)} файл(ов): '+', '.join(Path(x).name for x in paths)[:130])

    def pick_audio(self):
        p=filedialog.askopenfilename(title='Выберите музыкальный трек',filetypes=[('Музыка','*.mp3 *.wav *.m4a *.flac *.aac *.ogg *.opus'),('Все файлы','*')])
        if p:self.audio.set(p)

    def pick_output(self):
        p=filedialog.asksaveasfilename(title='Куда сохранить видео',defaultextension='.mp4',filetypes=[('MP4','*.mp4')],initialfile='montage.mp4')
        if p:self.output.set(p)

    def pick_color_reference(self):
        path=filedialog.askopenfilename(parent=self,title='Выберите SDR-видео как эталон цвета',
            filetypes=[('Видео','*.mp4 *.mov *.mkv *.m4v'),('Все файлы','*')])
        if path:self.color_reference.set(path)

    def settings(self):
        s={key:float(var.get()) for key,var in self.vars.items()}
        duration=float(self.duration.get().replace(',','.'))
        if not math.isfinite(duration) or duration<0:raise ValueError('Длина должна быть 0 или положительным числом.')
        seed=int(self.seed.get()) if self.seed.get().strip() else None
        if seed is not None and seed<0:raise ValueError('Seed должен быть целым неотрицательным числом.')
        if s['min_shot']>s['max_shot']:raise ValueError('Минимальный кадр больше максимального.')
        if not math.isfinite(float(self.repeat_cooldown.get())) or self.repeat_cooldown.get()<0:
            raise ValueError('Пауза до повтора должна быть неотрицательным числом.')
        crf,preset={'Быстрый черновик':(25,'ultrafast'),'Обычное':(20,'veryfast'),'Высокое':(18,'medium')}[self.quality.get()]
        s.update(duration=duration,seed=seed,size=SIZES[self.size.get()],fps=int(self.fps.get()),
                 fit='crop' if self.fit.get()=='Заполнить с обрезкой' else 'pad',crf=crf,preset=preset,
                 repeat_policy=self.repeat_policy.get(),repeat_cooldown=float(self.repeat_cooldown.get()),
                 color_match=bool(self.color_enabled.get()),color_strength=float(self.color_strength.get()),
                 color_reference=self.color_reference.get().strip(),
                 effects=[EFFECTS[name] for name,var in self.effects.items() if var.get()])
        if s['color_match'] and not Path(s['color_reference']).is_file():
            raise ValueError('Для цветового match выберите эталонное SDR-видео.')
        return s

    def start(self):
        if self.busy:return
        try:
            s=self.settings()
            if not self.videos or not Path(self.audio.get()).is_file():raise ValueError('Выберите видео и аудио.')
            if not self.output.get():raise ValueError('Укажите, куда сохранить результат.')
            output=Path(self.output.get()).resolve()
            if output.suffix.lower()!='.mp4':raise ValueError('Результат нужно сохранить с расширением .mp4.')
            if output in [Path(x).resolve() for x in self.videos+[self.audio.get()]]:
                raise ValueError('Результат не должен перезаписывать исходник.')
            if output.exists() and not messagebox.askyesno('Заменить файл?',f'Заменить {output.name}?'):return
        except (ValueError,tk.TclError) as e:
            messagebox.showerror('Проверьте настройки',str(e)); return
        self.busy=True; self.cancel.clear(); self.bar['value']=0
        self.start_button['state']='disabled'; self.stop_button['state']='normal'; self.open_button['state']='disabled'
        # Snapshot all widget values in the main thread; worker only sends queue events.
        videos=list(self.videos); music=self.audio.get()
        def worker():
            try:
                render(videos,music,output,s,self.cancel,lambda n,t:self.events.put(('progress',(n,t))))
                self.events.put(('done',str(output)))
            except Cancelled:self.events.put(('cancelled',None))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    self.bar['value']=value[0]; self.status.set(value[1])
                else:
                    self.busy=False; self.start_button['state']='normal'; self.stop_button['state']='disabled'
                    if kind=='done':
                        self.last_output=value; self.open_button['state']='normal'
                        self.status.set('Готово: '+value)
                    elif kind=='error':
                        self.status.set('Ошибка рендеринга. Исходники не изменены.')
                        messagebox.showerror('Не удалось собрать видео',value)
                    else:self.status.set('Рендеринг остановлен.')
        except queue.Empty:pass
        self.after(100,self.poll)

    def stop(self):
        self.cancel.set(); self.status.set('Остановка… Анализ аудио завершит текущий этап.')

    def open_result(self):
        if not self.last_output:return
        try:
            if sys.platform=='win32':os.startfile(self.last_output)
            else:subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',self.last_output])
        except OSError as e:messagebox.showerror('Не удалось открыть',str(e))

    def close(self):
        if self.busy:
            if messagebox.askyesno('Остановить рендер?', 'Остановить рендеринг? После остановки закройте окно ещё раз.'):
                self.stop()
            return
        self.destroy()


if __name__=='__main__':
    App().mainloop()
