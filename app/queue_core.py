"""Sequential jobs, cross-project path protection and final-only publication."""
from pathlib import Path
import copy
import os
import tempfile
import json
from studio_engine import render,check,Cancelled
from job_gate import serialized


def validate_jobs(jobs):
    if not jobs:raise ValueError('Нет включённых проектов.')
    protected=set();outputs=set()
    for job in jobs:
        for path in job['videos']+[job['music']]:
            path=Path(path).resolve()
            if not path.is_file():raise ValueError('Файл не найден: '+str(path))
            protected.add(str(path).casefold())
        if job['settings'].get('color_match'):
            ref=Path(job['settings'].get('color_reference','')).resolve()
            if not ref.is_file():raise ValueError('Не найден эталон цвета.')
            protected.add(str(ref).casefold())
    for job in jobs:
        out=Path(job['output']).resolve();key=str(out).casefold()
        if out.suffix.lower()!='.mp4':raise ValueError('Результат должен иметь расширение .mp4.')
        if key in protected or str(out.with_suffix('.beatcut.json')).casefold() in protected:
            raise ValueError('Результат или отчёт совпадает с исходником одного из проектов: '+str(out))
        if key in outputs:raise ValueError('У проектов одинаковый файл результата: '+str(out))
        if out.is_dir():raise ValueError('Вместо файла выбрана папка.')
        outputs.add(key)
    return jobs


@serialized
def process_job(job,cancel,progress):
    from fx_media import prepare,analyze,export
    out=Path(job['output']).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    # Existing final output remains intact until all stages have succeeded.
    with tempfile.TemporaryDirectory(prefix='.beatcut-job-',dir=out.parent) as temp:
        work=Path(temp);draft=work/'draft.mp4'
        fx=copy.deepcopy(job.get('fx'))
        metadata=render(job['videos'],job['music'],draft,job['settings'],cancel,
                        lambda n,s:progress(n*(.5 if fx else .95),s))
        final=draft
        if fx:
            data=prepare(draft,work,cancel,lambda n,s:progress(50+n*.15,s))
            fx['end']=min(fx['end'],data['duration'])
            if fx['end']<=fx['start']:raise ValueError('Участок эффектов вне готового ролика.')
            raw=analyze(data['proxy'],cancel,lambda n,s:progress(65+n*.1,s)) if fx['face'] else None
            final=work/'effects.mp4'
            export(data,final,fx,raw,cancel,lambda n,s:progress(75+n*.24,s))
            metadata['post_effects']=fx
        check(cancel);os.replace(final,out)
        metadata['output']=str(out);metadata['project_name']=job['name']
        try:out.with_suffix('.beatcut.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:progress(99,'MP4 готов; не удалось записать отчёт JSON.')
    progress(100,'Готово')


def run_jobs(jobs,cancel,emit,processor=process_job):
    jobs=copy.deepcopy(jobs);results=[]
    for i,job in enumerate(jobs):
        if cancel.is_set():
            results.append((job['name'],'пропущено после отмены',''));continue
        emit('status',(i,job['name']+': запуск…'))
        try:
            processor(job,cancel,lambda n,s,idx=i:emit('progress',(idx,n,s)))
            results.append((job['name'],'готово',str(job['output'])))
        except Cancelled:
            cancel.set();results.append((job['name'],'остановлено',''))
        except Exception as exc:results.append((job['name'],'ошибка',str(exc)))
        emit('result',(i,results[-1]))
    emit('done',results)
    return results
