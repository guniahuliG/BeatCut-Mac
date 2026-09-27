"""Effects workspace: immutable cached montage, live controls, explicit final export."""
from pathlib import Path
import json
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from fx_controls import Controls
from fx_core import smooth_track
from fx_media import prepare, analyze, export
from fx_player import Player
from studio_engine import Cancelled


class Editor(tk.Toplevel):
    def __init__(self,parent,source):
        super().__init__(parent)
        self.title('BeatCut 0.3 • эффекты и предпросмотр');self.geometry('1120x800');self.minsize(950,720)
        self.source=Path(source).resolve();self.cache=tempfile.TemporaryDirectory(prefix='beatcut-preview-')
        self.events=queue.Queue();self.cancel=threading.Event();self.busy=False;self.closed=False
        self.data=None;self.player=None;self.raw=None;self.smoothed=None;self.smoothing=None;self.controls=None
        self.refresh_id=None;self.last_output=None
        self.status=tk.StringVar(value='Подготовка предпросмотра…')
        self.main=ttk.Frame(self);self.main.pack(fill='both',expand=True)
        footer=ttk.Frame(self,padding=8);footer.pack(fill='x')
        self.bar=ttk.Progressbar(footer,maximum=100);self.bar.pack(fill='x')
        ttk.Label(footer,textvariable=self.status,wraplength=1050).pack(anchor='w',pady=4)
        buttons=ttk.Frame(footer);buttons.pack(fill='x')
        self.export_button=ttk.Button(buttons,text='Экспорт MP4 с эффектами…',command=self.save,state='disabled');self.export_button.pack(side='left')
        ttk.Button(buttons,text='Остановить расчёт',command=self.cancel.set).pack(side='left',padx=8)
        self.settings_button=ttk.Button(buttons,text='Сохранить настройки JSON…',command=self.save_settings,state='disabled');self.settings_button.pack(side='right')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.poll)
        self.launch('prepared',lambda progress:prepare(self.source,self.cache.name,self.cancel,progress))

    def launch(self,kind,operation):
        if self.busy:return
        self.busy=True;self.cancel.clear();self.export_button.configure(state='disabled')
        def worker():
            try:
                result=operation(lambda n,s:self.events.put(('progress',(n,s))))
                self.events.put((kind,result))
            except Cancelled:self.events.put(('cancelled',None))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        if self.closed:return
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':self.bar['value']=value[0];self.status.set(value[1]);continue
                self.busy=False
                if kind=='prepared':
                    self.data=value
                    side=ttk.Frame(self.main);side.pack(side='right',fill='y')
                    canvas=tk.Canvas(side,width=385,highlightthickness=0)
                    scroll=ttk.Scrollbar(side,orient='vertical',command=canvas.yview)
                    scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
                    canvas.configure(yscrollcommand=scroll.set)
                    self.controls=Controls(canvas,value['duration'],self.changed,self.track_faces)
                    window=canvas.create_window((0,0),window=self.controls,anchor='nw')
                    self.controls.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
                    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
                    self.player=Player(self.main,value,self.cache.name,self.controls.snapshot,self.track,self.status.set)
                    self.player.pack(side='left',fill='both',expand=True)
                    self.after(150,self.player.redraw)
                    self.settings_button.configure(state='normal')
                    self.status.set('Черновик зафиксирован. Включайте эффекты и настраивайте при проигрывании.')
                elif kind=='tracked':
                    self.raw=value;self.smoothing=None;self.changed()
                    visible=sum(value[:,4]>.5) if len(value) else 0
                    self.status.set(f'Лицо найдено уверенно в {visible} из {len(value)} кадров. Теперь включите фиксацию.')
                elif kind=='exported':
                    self.status.set('Сохранено: '+str(value))
                    messagebox.showinfo('Экспорт завершён',str(value),parent=self)
                elif kind=='error':
                    self.status.set('Ошибка: '+value);messagebox.showerror('BeatCut',value,parent=self)
                else:self.status.set('Расчёт остановлен. Существующий файл результата не изменён.')
                if self.data:self.export_button.configure(state='normal')
        except queue.Empty:pass
        self.after(100,self.poll)

    def track(self):
        if self.raw is None:return None
        amount=self.controls.vars['smooth'].get()
        if amount!=self.smoothing:
            self.smoothed=smooth_track(self.raw,amount,self.data['fps']);self.smoothing=amount
        return self.smoothed

    def changed(self):
        if self.refresh_id is not None:self.after_cancel(self.refresh_id)
        self.refresh_id=self.after(80,self.refresh)

    def refresh(self):
        self.refresh_id=None
        if self.player and not self.player.playing:self.player.redraw()

    def track_faces(self):
        if self.busy or not self.data:return
        self.player.pause()
        self.launch('tracked',lambda progress:analyze(self.data['proxy'],self.cancel,progress))

    def save(self):
        if self.busy or not self.data:return
        p=self.controls.snapshot()
        if p['end']<=p['start']:
            messagebox.showerror('Участок','Конец должен быть позже начала.',parent=self);return
        if p['face'] and self.raw is None:
            messagebox.showinfo('Фиксация лица','Сначала нажмите «Проанализировать лицо» во вкладке «Лицо».',parent=self);return
        name=filedialog.asksaveasfilename(parent=self,title='Экспорт с эффектами',defaultextension='.mp4',
             filetypes=[('MP4','*.mp4')],initialfile=self.source.stem+'_effects.mp4')
        if not name:return
        output=Path(name).resolve()
        if output==self.source or Path(self.cache.name) in output.parents:
            messagebox.showerror('Другой файл','Выберите новый файл: исходный черновик нужно сохранить.',parent=self);return
        self.player.pause();self.last_output=output
        # Immutable snapshot: changing sliders during export does not alter that export.
        data=dict(self.data);raw=self.raw.copy() if self.raw is not None else None
        self.status.set('Экспорт использует настройки на момент нажатия кнопки.')
        def operation(progress):
            export(data,output,p,raw,self.cancel,progress)
            return output
        self.launch('exported',operation)

    def save_settings(self):
        if not self.controls:return
        name=filedialog.asksaveasfilename(parent=self,title='Настройки эффектов (отчёт)',
              defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='beatcut-effects.json')
        if name:
            try:
                Path(name).write_text(json.dumps({'version':'0.3','source':str(self.source),
                    'effects':self.controls.snapshot(),'note':'Settings report only; not a reloadable project.'},ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as e:messagebox.showerror('Не удалось сохранить',str(e),parent=self)

    def close(self):
        if self.busy:
            if messagebox.askyesno('Идёт расчёт','Остановить? После остановки закройте окно ещё раз.',parent=self):self.cancel.set()
            return
        if self.player:self.player.close()
        self.closed=True
        if self.refresh_id:self.after_cancel(self.refresh_id)
        self.cache.cleanup();self.destroy()
