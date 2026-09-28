"""Keep the montage builder and add a separate non-destructive effects workspace."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from studio import App as MontageApp
from fx_editor import Editor
from batch_workspace import BatchManager


class App(MontageApp):
    def __init__(self):
        super().__init__()
        self.editors=[]
        self.batch_windows=[]
        self.setup_video_list()
        self.title('BeatCut Studio 0.5 • монтаж + эффекты')
        self.start_button.configure(text='1. Собрать черновик')
        self.open_button.configure(text='2. Предпросмотр / эффекты')
        ttk.Button(self.start_button.master,text='Открыть MP4…',command=self.open_existing).pack(side='left',padx=4)
        self.queue_button=ttk.Button(self,text='Очередь 1–5 треков…',command=self.open_batch)
        self.queue_button.pack(fill='x',padx=12,pady=4)
        self.status.set('Соберите черновик, затем откройте «Предпросмотр / эффекты». Можно открыть готовый MP4.')

    def setup_video_list(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        button=next(w for w in descendants(self)
                    if isinstance(w,ttk.Button) and w.cget('text')=='Открыть видео…')
        button.configure(text='Добавить видео…')
        panel=button.master
        holder=ttk.Frame(panel);holder.grid(row=3,column=0,columnspan=2,sticky='ew',pady=6)
        self.video_list=tk.Listbox(holder,height=5,selectmode='extended',exportselection=False)
        scroll=ttk.Scrollbar(holder,orient='vertical',command=self.video_list.yview)
        self.video_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.video_list.pack(fill='both',expand=True)
        self.video_list.bind('<<ListboxSelect>>',self.show_video_path)
        self.video_path=tk.StringVar()
        ttk.Label(panel,textvariable=self.video_path,wraplength=650).grid(row=4,column=0,columnspan=2,sticky='w')
        actions=ttk.Frame(panel);actions.grid(row=5,column=0,columnspan=2,sticky='w')
        ttk.Button(actions,text='Удалить выбранные из списка',command=self.remove_videos).pack(side='left')
        ttk.Button(actions,text='Очистить список',command=self.clear_videos).pack(side='left',padx=6)
        self.refresh_video_list()

    def refresh_video_list(self):
        self.video_list.delete(0,'end')
        for i,path in enumerate(self.videos,1):
            self.video_list.insert('end',f'{i}. {Path(path).name}')
        self.video_label.set(f'Исходников: {len(self.videos)}. Повторный выбор добавляет файлы.'
                             if self.videos else 'Добавьте один или несколько исходников.')
        self.video_path.set('')

    def show_video_path(self,event=None):
        indices=self.video_list.curselection()
        self.video_path.set(self.videos[indices[0]] if indices else '')

    def add_video_paths(self,paths):
        if self.busy:return 0
        known={str(Path(p).resolve()) for p in self.videos}
        added=0
        for path in paths:
            canonical=str(Path(path).resolve())
            if canonical not in known:
                self.videos.append(canonical);known.add(canonical);added+=1
        self.refresh_video_list()
        return added

    def pick_video(self):
        if self.busy:
            messagebox.showinfo('Идёт сборка','Дождитесь завершения или остановите сборку.',parent=self);return
        paths=filedialog.askopenfilenames(parent=self,title='Добавить видео к существующему списку',
            filetypes=[('Видео','*.mp4 *.mov *.mkv *.avi *.webm *.m4v'),('Все файлы','*')])
        if paths:
            added=self.add_video_paths(paths)
            self.status.set(f'Добавлено: {added}. Всего исходников: {len(self.videos)}. Повторы пропущены.')

    def remove_videos(self):
        if self.busy:return
        for index in reversed(self.video_list.curselection()):del self.videos[index]
        self.refresh_video_list()
        self.status.set('Выбранные исходники убраны только из списка. Файлы на диске не удалены.')

    def clear_videos(self):
        if self.busy or not self.videos:return
        if messagebox.askyesno('Очистить список?',
                'Убрать все исходники из списка? Файлы на диске останутся.',parent=self):
            self.videos.clear();self.refresh_video_list()

    def open_batch(self):
        self.batch_windows=[w for w in self.batch_windows if w.winfo_exists()]
        if self.batch_windows:
            self.batch_windows[0].lift();return
        try:base=self.settings()
        except (ValueError,tk.TclError) as e:
            messagebox.showerror('Проверьте общие настройки',str(e),parent=self);return
        self.batch_windows.append(BatchManager(self,base))

    def open_result(self):
        if self.last_output:self.editors.append(Editor(self,self.last_output))

    def open_existing(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self,title='Открыть видео для эффектов',
                    filetypes=[('Видео','*.mp4 *.mov *.m4v *.mkv'),('Все файлы','*')])
        if path:self.editors.append(Editor(self,path))

    def close(self):
        self.batch_windows=[w for w in self.batch_windows if w.winfo_exists()]
        if any(w.busy for w in self.batch_windows):
            messagebox.showinfo('Очередь работает','Остановите очередь и дождитесь остановки.',parent=self);return
        self.editors=[e for e in self.editors if e.winfo_exists()]
        if any(e.busy for e in self.editors):
            messagebox.showinfo('Идёт расчёт','Сначала остановите расчёт в окне эффектов и дождитесь остановки.');return
        if self.busy:
            super().close();return
        for w in self.batch_windows:w.close()
        for e in self.editors:e.close()
        super().close()


if __name__=='__main__':App().mainloop()
