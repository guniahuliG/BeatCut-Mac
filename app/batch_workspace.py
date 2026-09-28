"""Up to five independently configured tracks, rendered in a sequential queue."""
from pathlib import Path
import copy
import json
import subprocess
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from batch_manager import TrackTab
from queue_core import validate_jobs,run_jobs
from fx_controls_v2 import Controls


class ProjectTab(TrackTab):
    def __init__(self,parent,index,base):
        super().__init__(parent,index,copy.deepcopy(base))
        self.include=tk.BooleanVar(value=True);self.fx_enabled=tk.BooleanVar(value=False)
        self.fx_window=None;self.fx_controls=None;self.last_output=None
        self.color_enabled=tk.BooleanVar(value=base.get('color_match',False))
        self.reference=tk.StringVar(value=base.get('color_reference',''))
        self.strength=tk.DoubleVar(value=base.get('color_strength',.55))
        extra=ttk.LabelFrame(self,text='Обработка этого проекта',padding=6)
        extra.grid(row=8,column=0,columnspan=2,sticky='ew')
        ttk.Checkbutton(extra,text='Включить проект в очередь',variable=self.include).pack(anchor='w')
        ttk.Checkbutton(extra,text='Подгонять цвет SDR',variable=self.color_enabled).pack(anchor='w')
        row=ttk.Frame(extra);row.pack(fill='x')
        ttk.Entry(row,textvariable=self.reference).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Эталон…',command=self.pick_reference).pack(side='right')
        row=ttk.Frame(extra);row.pack(fill='x')
        ttk.Label(row,text='Сила цвета 0–1').pack(side='left')
        ttk.Scale(row,from_=0,to=1,variable=self.strength).pack(side='left',fill='x',expand=True)
        ttk.Label(row,textvariable=self.strength,width=8).pack(side='right')
        ttk.Checkbutton(extra,text='Применить эффекты после монтажа',variable=self.fx_enabled).pack(anchor='w')
        ttk.Button(extra,text='Настроить эффекты этого трека…',command=self.configure_fx).pack(fill='x')

    def pick_reference(self):
        name=filedialog.askopenfilename(parent=self,title='Эталон SDR',filetypes=[('Видео','*.mp4 *.mov *.mkv *.m4v'),('Все','*')])
        if name:self.reference.set(name)

    def configure_fx(self):
        if self.fx_window and self.fx_window.winfo_exists():self.fx_window.deiconify();self.fx_window.lift();return
        try:
            if not Path(self.audio.get()).is_file():raise ValueError('Сначала выберите музыку.')
            duration=float(self.duration.get().replace(',','.'))
            if duration<=0:
                probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',self.audio.get()],timeout=20))
                duration=float(probe['format']['duration'])
            if not 0<duration<86400:raise ValueError('Неподдерживаемая длительность.')
        except Exception as e:messagebox.showerror('Длительность',str(e),parent=self);return
        self.fx_window=tk.Toplevel(self);self.fx_window.title('Эффекты: '+self.name.get());self.fx_window.geometry('460x750')
        canvas=tk.Canvas(self.fx_window,highlightthickness=0)
        scroll=ttk.Scrollbar(self.fx_window,command=canvas.yview);scroll.pack(side='right',fill='y')
        canvas.pack(fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
        self.fx_controls=Controls(canvas,duration,lambda:None,lambda:messagebox.showinfo('Лицо','Анализ автоматически выполнится при обработке проекта, если включена фиксация.',parent=self.fx_window))
        win=canvas.create_window((0,0),window=self.fx_controls,anchor='nw')
        self.fx_controls.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        self.fx_window.protocol('WM_DELETE_WINDOW',self.fx_window.withdraw)

    def snapshot(self):
        job=super().snapshot()
        if job['settings']['seed'] is not None and job['settings']['seed']<0:raise ValueError('Seed должен быть неотрицательным.')
        job['settings']=copy.deepcopy(job['settings'])
        job['settings'].update(color_match=self.color_enabled.get(),color_reference=self.reference.get().strip(),color_strength=self.strength.get())
        if not 0<=self.strength.get()<=1:raise ValueError('Сила цвета должна быть 0–1.')
        if self.fx_enabled.get():
            if self.fx_controls is None:raise ValueError(job['name']+': сначала настройте эффекты.')
            job['fx']=self.fx_controls.snapshot()
            if job['fx']['end']<=job['fx']['start']:raise ValueError('Конец эффектов должен быть позже начала.')
        return job


class BatchManager(tk.Toplevel):
    def __init__(self,parent,base):
        super().__init__(parent);self.title('BeatCut 0.5 • очередь треков');self.geometry('920x850')
        self.base=copy.deepcopy(base);self.tabs=[];self.busy=False;self.closed=False
        self.cancel=threading.Event();self.events=queue.Queue();self.locked=[];self.running_tabs=[]
        self.status=tk.StringVar(value='Настройте проекты. Обработка строго по одному; предпросмотр не запускается.')
        ttk.Label(self,textvariable=self.status,wraplength=880).pack(fill='x',padx=10,pady=5)
        actions=ttk.Frame(self,padding=8);actions.pack(fill='x')
        self.add_button=ttk.Button(actions,text='+ Трек (до 5)',command=self.add_tab);self.add_button.pack(side='left')
        self.run_button=ttk.Button(actions,text='Обработать очередь',command=self.start);self.run_button.pack(side='left',padx=5)
        self.stop_button=ttk.Button(actions,text='Остановить очередь',command=self.cancel.set,state='disabled');self.stop_button.pack(side='left')
        ttk.Button(actions,text='Результат выбранного трека…',command=self.open_result).pack(side='left',padx=5)
        self.bar=ttk.Progressbar(self,maximum=100);self.bar.pack(fill='x',padx=10)
        self.notebook=ttk.Notebook(self);self.notebook.pack(fill='both',expand=True,padx=10,pady=8)
        for _ in range(3):self.add_tab()
        self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)

    def add_tab(self):
        if self.busy or len(self.tabs)>=5:return
        holder=ttk.Frame(self.notebook);canvas=tk.Canvas(holder,highlightthickness=0)
        scroll=ttk.Scrollbar(holder,command=canvas.yview);scroll.pack(side='right',fill='y')
        canvas.pack(fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
        tab=ProjectTab(canvas,len(self.tabs)+1,self.base);self.tabs.append(tab)
        win=canvas.create_window((0,0),window=tab,anchor='nw')
        tab.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        self.notebook.add(holder,text=tab.name.get())
        tab.name.trace_add('write',lambda *_,t=tab,h=holder:self.notebook.tab(h,text=t.name.get() or 'Трек'))
        self.notebook.select(holder)
        self.add_button.configure(state='disabled' if len(self.tabs)==5 else 'normal')

    def lock(self,widget):
        for child in widget.winfo_children():
            if 'state' in child.keys():
                self.locked.append((child,child.cget('state')))
                try:child.configure(state='disabled')
                except tk.TclError:pass
            self.lock(child)

    def start(self):
        if self.busy:return
        try:
            tabs=[t for t in self.tabs if t.include.get() and (t.videos or t.audio.get() or t.output.get())]
            jobs=validate_jobs([t.snapshot() for t in tabs])
            existing=[str(j['output']) for j in jobs if Path(j['output']).exists()]
            if existing and not messagebox.askyesno('Заменить результаты?','Будут заменены:\n'+'\n'.join(existing),parent=self):return
        except (ValueError,tk.TclError) as e:messagebox.showerror('Проверьте очередь',str(e),parent=self);return
        self.running_tabs=tabs;self.cancel.clear();self.busy=True;self.bar['value']=0
        for tab in self.tabs:
            self.lock(tab)
            if tab.fx_window:self.lock(tab.fx_window)
        for tab in tabs:tab.status.set('В очереди');tab.last_output=None
        self.run_button.configure(state='disabled');self.add_button.configure(state='disabled');self.stop_button.configure(state='normal')
        self.status.set('Расчёт. Используется снимок настроек на момент запуска.')
        threading.Thread(target=run_jobs,args=(jobs,self.cancel,lambda k,v:self.events.put((k,v))),daemon=True).start()

    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    i,n,text=value;self.bar['value']=(i*100+n)/len(self.running_tabs)
                    self.running_tabs[i].status.set(text);self.status.set(f'{i+1}/{len(self.running_tabs)}: '+text)
                elif kind=='status':
                    i,text=value;self.running_tabs[i].status.set(text)
                elif kind=='result':
                    i,(name,state,extra)=value;tab=self.running_tabs[i];tab.status.set(state+': '+extra)
                    if state=='готово':tab.last_output=extra
                elif kind=='done':
                    self.busy=False
                    for widget,state in self.locked:
                        try:widget.configure(state=state)
                        except tk.TclError:pass
                    self.locked=[];self.run_button.configure(state='normal');self.stop_button.configure(state='disabled')
                    self.add_button.configure(state='normal' if len(self.tabs)<5 else 'disabled')
                    for tab,(_,state,extra) in zip(self.running_tabs,value):tab.status.set(state+': '+extra)
                    self.status.set('Очередь остановлена.' if self.cancel.is_set() else 'Очередь завершена; проверьте статусы проектов.')
                    if not self.cancel.is_set():self.bar['value']=100
                    messagebox.showinfo('Результаты','\n'.join(f'{n}: {s}\n{v}' for n,s,v in value),parent=self)
        except queue.Empty:pass
        self.after(100,self.poll)

    def open_result(self):
        if self.busy:return
        tab=self.tabs[self.notebook.index('current')]
        if not tab.last_output:messagebox.showinfo('Результат','Сначала обработайте выбранный трек.',parent=self);return
        from fx_editor import Editor
        editor=Editor(self.master,tab.last_output);self.master.editors.append(editor)

    def close(self):
        if self.busy:
            messagebox.showinfo('Идёт расчёт','Остановите очередь и дождитесь её остановки.',parent=self);return
        self.closed=True
        for tab in self.tabs:
            if tab.fx_window:tab.fx_window.destroy()
        self.destroy()
