"""Tk controls; strobe requires an explicit warning acknowledgement."""
import tkinter as tk
from tkinter import ttk, messagebox
from fx_core import DEFAULTS


class Controls(ttk.Frame):
    def __init__(self,parent,duration,changed,analyze):
        super().__init__(parent,padding=8)
        self.changed=changed; self.vars={}; self.ack=False
        values=dict(DEFAULTS,end=duration)
        for k,v in values.items():
            cls=tk.BooleanVar if isinstance(v,bool) else tk.StringVar if isinstance(v,str) else tk.DoubleVar
            self.vars[k]=cls(value=v)
        scope=ttk.LabelFrame(self,text='Общий участок эффектов',padding=6);scope.pack(fill='x')
        self.slider(scope,'start','Начало, сек',0,duration)
        self.slider(scope,'end','Конец, сек',0,duration)
        self.slider(scope,'fade','Плавные края, сек',0,1)
        ttk.Label(scope,text='Все включённые эффекты используют этот участок.',wraplength=340).pack(anchor='w')
        book=ttk.Notebook(self);book.pack(fill='both',expand=True,pady=6)
        movement=ttk.Frame(book,padding=6);face=ttk.Frame(book,padding=6)
        speed=ttk.Frame(book,padding=6);flash=ttk.Frame(book,padding=6)
        for widget,name in [(movement,'Движение'),(face,'Лицо'),(speed,'Слоумо'),(flash,'Вспышки')]:book.add(widget,text=name)
        random_tab=ttk.Frame(book,padding=6);book.add(random_tab,text='Рандом')
        self.toggle(random_tab,'random_mode','Случайные включения эффектов')
        ttk.Label(random_tab,text='Сначала включите нужные эффекты на их вкладках.\nЧастота ниже — примерное число появлений за минуту, НЕ скорость тряски или мигания.',wraplength=330).pack(anchor='w',pady=6)
        for key,label in [('face','Лицо'),('slow','Слоумо'),('zoom','Зум'),('shake','Тряска'),('flash','Серии вспышек')]:
            self.slider(random_tab,'rate_'+key,label+' — раз/мин',0,30)
        self.slider(random_tab,'random_min','Длительность: от, сек',.1,5)
        self.slider(random_tab,'random_max','Длительность: до, сек',.1,8)
        ttk.Label(random_tab,text='Если «от» больше «до», границы меняются местами. На коротком участке редкий эффект может не появиться. Разные эффекты могут совпадать; одинаковые не перекрываются.',wraplength=330).pack(anchor='w',pady=5)
        ttk.Button(random_tab,text='Перемешать эффекты',command=self.reshuffle).pack(fill='x',pady=4)
        ttk.Button(random_tab,text='Показать моменты эффектов',command=self.show_schedule).pack(fill='x')
        ttk.Label(random_tab,text='По времени, без привязки к битам. Длительность общая для всех типов. Сила задаётся на вкладках эффектов. Стробоскоп — только после подтверждения.',wraplength=330).pack(anchor='w',pady=5)
        self.toggle(movement,'zoom','Zoom In / Out')
        mode=ttk.Combobox(movement,textvariable=self.vars['zoom_mode'],state='readonly',
                         values=['Пульс','Приближение','Отдаление']);mode.pack(fill='x')
        self.slider(movement,'zoom_amount','Сила зума',0,1)
        self.slider(movement,'zoom_period','Период, сек',.3,8)
        self.toggle(movement,'shake','Тряска')
        self.slider(movement,'shake_amount','Смещение / размер кадра',0,.12)
        self.slider(movement,'shake_hz','Частота тряски, Гц',.5,20)
        self.slider(movement,'shake_roll','Поворот, градусы',0,12)
        self.slider(movement,'crop','Запас приближения',1,2)
        ttk.Label(movement,text='За краями используется отражение изображения.\nУвеличьте запас, если оно заметно.',wraplength=330).pack(anchor='w',pady=8)
        ttk.Button(face,text='1. Проанализировать лицо',command=analyze).pack(fill='x')
        self.toggle(face,'face','2. Включить фиксацию лица')
        self.slider(face,'face_strength','Сила фиксации',0,1)
        self.slider(face,'smooth','Сглаживание, сек',0,.6)
        self.toggle(face,'face_roll','Компенсировать наклон')
        self.toggle(face,'face_size','Удерживать размер лица')
        self.slider(face,'target_size','Расстояние между глазами / ширина',.05,.3)
        ttk.Label(face,text='Локальный анализ, без отправки видео. Автовыбор крупного лица; лучше один человек в кадре. При потере фиксация ослабевает. Ручного выбора человека пока нет.',wraplength=330).pack(anchor='w',pady=10)
        self.toggle(speed,'slow','Слоумо → плавный догон')
        self.slider(speed,'speed','Минимальная скорость',.2,1)
        ttk.Label(speed,text='В первой половине участка видео замедляется, во второй ускоряется, чтобы сохранить общую длину. Музыка не замедляется. Склейки внутри участка могут сместиться относительно ударов.\n\nБез дорисовки промежуточных кадров: сильное замедление может быть ступенчатым.',wraplength=330).pack(anchor='w',pady=12)
        ttk.Label(flash,text='ВНИМАНИЕ: быстрые вспышки могут вызвать приступ при фоточувствительности. Низкая яркость не гарантирует безопасность.',wraplength=330,foreground='#a32626').pack(anchor='w',pady=8)
        ttk.Checkbutton(flash,text='Включить белые вспышки',variable=self.vars['flash'],command=self.confirm_flash).pack(anchor='w')
        self.slider(flash,'flash_alpha','Яркость вспышки',0,1)
        self.slider(flash,'flash_hz','Частота, Гц',1,15)
        self.slider(flash,'flash_duty','Доля периода с белым кадром',.05,.8)
        ttk.Label(flash,text='При низком FPS или пропуске кадров в предпросмотре частота выглядит иначе. Оценивайте финальный экспорт осторожно.',wraplength=330).pack(anchor='w',pady=10)
        ttk.Button(self,text='Выключить все эффекты',command=self.disable).pack(fill='x')
        for key,var in self.vars.items():
            if key!='flash':var.trace_add('write',lambda *_:self.changed())

    def reshuffle(self):
        self.vars['random_seed'].set(int(self.vars['random_seed'].get())+1)

    def show_schedule(self):
        from fx_random import events
        p=self.snapshot()
        window=tk.Toplevel(self);window.title('Моменты эффектов — текущая расстановка')
        text=tk.Text(window,width=65,height=25,wrap='word')
        scroll=ttk.Scrollbar(window,command=text.yview)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.configure(yscrollcommand=scroll.set)
        lines=[f"Seed: {int(p['random_seed'])}. Рандом: {'включён' if p['random_mode'] else 'выключен'}.",
               'Список — снимок текущих настроек; после изменений откройте его заново.\n']
        for key,label in [('face','Лицо'),('slow','Слоумо'),('zoom','Зум'),('shake','Тряска'),('flash','Серии вспышек')]:
            seq=events(p,key)
            lines.append(f'{label}: {len(seq)} включений')
            lines.extend(f'  {a:.2f} — {b:.2f} с' for a,b in seq)
        text.insert('1.0','\n'.join(lines));text.configure(state='disabled')

    def slider(self,parent,key,label,lo,hi):
        row=ttk.Frame(parent);row.pack(fill='x',pady=4)
        text=tk.StringVar()
        def update(*_):
            try:text.set(f'{self.vars[key].get():.2f}')
            except tk.TclError:pass
        self.vars[key].trace_add('write',update);update()
        ttk.Label(row,text=label).pack(anchor='w')
        line=ttk.Frame(row);line.pack(fill='x')
        ttk.Scale(line,from_=lo,to=hi,variable=self.vars[key]).pack(side='left',fill='x',expand=True)
        ttk.Label(line,textvariable=text,width=6,anchor='e').pack(side='right')

    def toggle(self,parent,key,label):
        ttk.Checkbutton(parent,text=label,variable=self.vars[key]).pack(anchor='w',pady=4)

    def confirm_flash(self):
        if self.vars['flash'].get() and not self.ack:
            self.ack=messagebox.askyesno('Предупреждение о вспышках',
                'Быстрые белые вспышки могут вызвать приступ, головную боль или дискомфорт.\n'
                'Не включайте их при фоточувствительности и предупредите зрителей.\n\n'
                'Включить эффект в предпросмотре и экспорте?',parent=self)
            if not self.ack:self.vars['flash'].set(False)
        self.changed()

    def disable(self):
        for k in ('face','slow','zoom','shake','flash'):self.vars[k].set(False)
        self.changed()

    def snapshot(self):
        result={k:v.get() for k,v in self.vars.items()}
        result['flash']=result['flash'] and self.ack
        return result
