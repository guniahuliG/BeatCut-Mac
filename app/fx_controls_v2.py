"""Clean consolidated effect controls, including safe strobe acknowledgement."""
import tkinter as tk
from tkinter import ttk, messagebox
from fx_core import DEFAULTS


class Controls(ttk.Frame):
    def __init__(self,parent,duration,changed,analyze):
        super().__init__(parent,padding=8);self.changed=changed;self.vars={};self.ack=False
        for key,value in dict(DEFAULTS,end=float(duration)).items():
            cls=tk.BooleanVar if isinstance(value,bool) else tk.StringVar if isinstance(value,str) else tk.DoubleVar
            self.vars[key]=cls(value=value)
        scope=ttk.LabelFrame(self,text='Область эффектов',padding=6);scope.pack(fill='x')
        self.slider(scope,'start','Начало, сек',0,duration)
        self.slider(scope,'end','Конец, сек',0,duration)
        self.slider(scope,'fade','Плавность краёв, сек',0,1)
        book=ttk.Notebook(self);book.pack(fill='both',expand=True,pady=6)
        motion=ttk.Frame(book,padding=6);face=ttk.Frame(book,padding=6)
        speed=ttk.Frame(book,padding=6);flash=ttk.Frame(book,padding=6)
        random=ttk.Frame(book,padding=6)
        for pane,title in [(motion,'Движение'),(face,'Лицо'),(speed,'Скорость'),(flash,'Вспышки'),(random,'Рандом')]:
            book.add(pane,text=title)
        self.toggle(motion,'zoom','Zoom In / Out')
        ttk.Combobox(motion,textvariable=self.vars['zoom_mode'],state='readonly',values=['Пульс','Приближение','Отдаление']).pack(fill='x')
        self.slider(motion,'zoom_amount','Сила зума',0,1)
        self.slider(motion,'zoom_period','Период, сек',.3,8)
        self.toggle(motion,'shake','Тряска')
        self.slider(motion,'shake_amount','Смещение, доля кадра',0,.12)
        self.slider(motion,'shake_hz','Частота тряски, Гц',.5,20)
        self.slider(motion,'shake_roll','Поворот, градусы',0,12)
        self.slider(motion,'crop','Запас кадрирования',1,2)
        ttk.Button(face,text='Проанализировать лицо',command=analyze).pack(fill='x')
        self.toggle(face,'face','Включить фиксацию лица')
        self.slider(face,'face_strength','Сила фиксации',0,1)
        self.slider(face,'smooth','Сглаживание, сек',0,.6)
        self.toggle(face,'face_roll','Компенсировать наклон')
        self.toggle(face,'face_size','Удерживать размер лица')
        self.slider(face,'target_size','Целевой размер лица',.05,.3)
        ttk.Label(face,text='Локальный анализ. В сцене с несколькими людьми возможны переключения между лицами.',wraplength=330).pack(anchor='w',pady=6)
        self.toggle(speed,'slow','Слоумо → плавный догон')
        self.slider(speed,'speed','Минимальная скорость',.2,1)
        self.toggle(speed,'rewind','Перемотка вперёд → обратно')
        self.slider(speed,'rewind_amount','Глубина перемотки',.25,1.25)
        ttk.Label(speed,text='Реверс показывает короткий отрезок вперёд, возвращается назад и продолжает видео. Музыка остаётся неизменной.',wraplength=330).pack(anchor='w',pady=6)
        ttk.Label(flash,text='ВНИМАНИЕ: вспышки могут быть опасны при фоточувствительности.',foreground='#a32626',wraplength=330).pack(anchor='w',pady=8)
        ttk.Checkbutton(flash,text='Белые вспышки',variable=self.vars['flash'],command=self.confirm_flash).pack(anchor='w')
        self.slider(flash,'flash_alpha','Яркость',0,1)
        self.slider(flash,'flash_hz','Мигание, Гц',1,15)
        self.slider(flash,'flash_duty','Длительность вспышки',.05,.8)
        self.toggle(random,'random_mode','Случайно размещать эффекты')
        for key,label in [('face','Фиксация лица'),('slow','Слоумо'),('rewind','Перемотка'),('zoom','Зум'),('shake','Тряска'),('flash','Серии вспышек')]:
            self.slider(random,'rate_'+key,label+' — событий/мин',0,30)
        self.slider(random,'random_min','Эпизод: от, сек',.1,5)
        self.slider(random,'random_max','Эпизод: до, сек',.1,8)
        ttk.Button(random,text='Перемешать расписание',command=self.reshuffle).pack(fill='x',pady=4)
        ttk.Button(random,text='Показать моменты',command=self.show_schedule).pack(fill='x')
        ttk.Label(random,text='Seed гарантирует одинаковое расписание в предпросмотре и экспорте. События не привязаны к битам музыки.',wraplength=330).pack(anchor='w',pady=6)
        ttk.Button(self,text='Выключить эффекты',command=self.disable).pack(fill='x')
        for key,var in self.vars.items():
            if key!='flash':var.trace_add('write',lambda *_:self.changed())

    def slider(self,parent,key,label,lo,hi):
        row=ttk.Frame(parent);row.pack(fill='x',pady=3)
        shown=tk.StringVar()
        def update(*_):
            try:shown.set(f'{float(self.vars[key].get()):.2f}')
            except (tk.TclError,ValueError):shown.set('—')
        self.vars[key].trace_add('write',update);update()
        ttk.Label(row,text=label).pack(anchor='w')
        line=ttk.Frame(row);line.pack(fill='x')
        ttk.Scale(line,from_=lo,to=hi,variable=self.vars[key]).pack(side='left',fill='x',expand=True)
        ttk.Label(line,textvariable=shown,width=6,anchor='e').pack(side='right')

    def toggle(self,parent,key,label):
        ttk.Checkbutton(parent,text=label,variable=self.vars[key]).pack(anchor='w',pady=4)

    def confirm_flash(self):
        if self.vars['flash'].get() and not self.ack:
            self.ack=messagebox.askyesno('Предупреждение о вспышках',
                'Быстрые белые вспышки могут вызвать приступ или дискомфорт при фоточувствительности. Включить?',parent=self)
            if not self.ack:self.vars['flash'].set(False)
        self.changed()

    def reshuffle(self):
        self.vars['random_seed'].set(int(self.vars['random_seed'].get())+1)
        self.changed()

    def show_schedule(self):
        from fx_random import events
        p=self.snapshot();win=tk.Toplevel(self);win.title('Расписание эффектов')
        text=tk.Text(win,width=60,height=22,wrap='word');scroll=ttk.Scrollbar(win,command=text.yview)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True);text.configure(yscrollcommand=scroll.set)
        labels=[('face','Лицо'),('slow','Слоумо'),('rewind','Перемотка'),('zoom','Зум'),('shake','Тряска'),('flash','Вспышки')]
        lines=[f"Seed: {int(p['random_seed'])}"]
        for key,label in labels:
            seq=events(p,key);lines.append(f'{label}: {len(seq)} эпизодов')
            lines.extend(f'  {a:.2f}—{b:.2f} сек' for a,b in seq)
        text.insert('1.0','\n'.join(lines));text.configure(state='disabled')

    def disable(self):
        for key in ('face','slow','rewind','zoom','shake','flash'):
            self.vars[key].set(False)
        self.changed()

    def snapshot(self):
        result={key:var.get() for key,var in self.vars.items()}
        result['flash']=bool(result['flash'] and self.ack)
        return result
