"""Local, cancellable rendering. Transition END is locked to the selected accent.
Only two videos enter any transition filter; memory does not grow with shot count.
"""
from pathlib import Path
import json
import math
import os
import shutil
import subprocess
import tempfile
import numpy as np
from audio_analysis import SAMPLE_RATE, detect_accents
from source_selection import source_plan
from job_gate import serialized
from color_lut import sample_range,match_lut

EFFECTS = {'Наплыв': 'fade', 'Сдвиг влево': 'slideleft',
           'Сдвиг вправо': 'slideright', 'Шторка вверх': 'wipeup',
           'Круговое раскрытие': 'circleopen', 'Пикселизация': 'pixelize'}


class Cancelled(Exception):
    pass


def check(cancel):
    if cancel.is_set():
        raise Cancelled('Рендеринг отменён')


def run(args, cancel):
    check(cancel)
    # communicate(timeout) drains both pipes: no deadlock on a verbose decoder.
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    p = subprocess.Popen(list(map(str, args)), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=flags)
    try:
        while True:
            check(cancel)
            try:
                out, err = p.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                pass
    except BaseException:
        p.kill()
        p.communicate()
        raise
    if p.returncode:
        raise RuntimeError(err.decode('utf-8', errors='replace')[-3000:])
    return out


def timeline(times, strengths, total, fps, rng, density, variety, minimum, maximum):
    lo, hi = max(1, math.ceil(minimum*fps)), max(1, math.floor(maximum*fps))
    hi = max(lo, hi)
    candidates = {}
    for t, w in zip(times, strengths):
        f = round(float(t)*fps)
        if 0 < f < total:
            candidates[f] = max(candidates.get(f, 0.), float(w))
    fs = np.array(sorted(candidates), dtype=int)
    ws = np.array([candidates[f] for f in fs])
    if len(ws):
        ws = np.minimum(ws/max(float(np.percentile(ws, 85)), 1e-9), 4.)
    cuts, timed, burst = [0], [], 0
    while total-cuts[-1] > hi:
        last = cuts[-1]
        base = np.clip((3.4-2.7*density)*fps, lo, hi)
        if burst == 0 and rng.random() < variety*(.1+.4*density):
            burst = int(rng.integers(2, 5))
        if burst:
            target = np.clip(rng.uniform(.35,.8)*fps, lo, hi)
            burst -= 1
        else:
            target = np.clip(base*np.exp(rng.normal(0,.65*variety)), lo, hi)
        valid = (fs >= last+lo) & (fs <= last+hi) & (fs <= total-lo)
        options, weights = fs[valid], ws[valid]
        if len(options):
            distance = np.abs(options-last-target)/max(.25*fps, .3*target)
            score = -.5*distance**2 + np.log(.25+weights)
            if variety < .001:
                chosen = int(options[np.argmax(score)])
            else:
                score = score/max(.08,variety)
                prob = np.exp(score-score.max()); prob /= prob.sum()
                chosen = int(rng.choice(options,p=prob))
        else:
            chosen = min(last+hi, total-lo)
            timed.append(chosen)
        cuts.append(chosen)
    cuts.append(total)
    return cuts, timed


@serialized
def render(videos, music, output, s, cancel, progress):
    for binary in ('ffmpeg','ffprobe'):
        if not shutil.which(binary):
            raise ValueError('Не найден '+binary+'. Установите FFmpeg; см. инструкцию.')
    output, music = Path(output).resolve(), Path(music).resolve()
    paths = [Path(v).resolve() for v in videos]
    protected=paths+[music]
    if s.get('color_match'):protected.append(Path(s.get('color_reference','')).resolve())
    if output in protected or output.with_suffix('.beatcut.json') in protected:
        raise ValueError('Нельзя сохранять результат поверх исходного файла.')
    if not music.is_file() or not paths:
        raise ValueError('Выберите музыку и видео.')
    if s['min_shot'] > s['max_shot']:
        raise ValueError('Минимальная длина кадра больше максимальной.')
    output.parent.mkdir(parents=True, exist_ok=True)
    fps = s['fps']
    seed = s['seed'] if s['seed'] is not None else int.from_bytes(os.urandom(8),'little')
    rng = np.random.default_rng(seed)
    sources = []
    progress(1, 'Проверка исходных файлов…')
    for v in paths:
        data = json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',v],cancel))
        stream = next((x for x in data['streams'] if x['codec_type']=='video'
                       and not x.get('disposition',{}).get('attached_pic')), None)
        if stream:
            try:
                duration = float(stream.get('duration',data.get('format',{}).get('duration',0)))
            except (TypeError,ValueError):
                duration = 0
            if math.isfinite(duration) and duration > s['min_shot']+2/fps:
                transfer=str(stream.get('color_transfer','')).lower()
                if s.get('color_match') and transfer in ('smpte2084','arib-std-b67'):
                    raise ValueError('Автоцветовой match сейчас поддерживает SDR. HDR/PQ/HLG отключите или предварительно преобразуйте в SDR.')
                sources.append({'path':str(v),'duration':duration,'color_transfer':transfer})
    reference_stats=None
    if s.get('color_match'):
        reference=Path(s.get('color_reference','')).resolve()
        if not reference.is_file():raise ValueError('Выберите существующее эталонное SDR-видео для color match.')
        refdata=json.loads(run(['ffprobe','-v','error','-show_streams','-of','json',reference],cancel))
        refstream=next((x for x in refdata['streams'] if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),None)
        if not refstream:raise ValueError('В эталоне цвета нет видеодорожки.')
        if str(refstream.get('color_transfer','')).lower() in ('smpte2084','arib-std-b67'):
            raise ValueError('HDR/PQ/HLG-эталон нельзя использовать для SDR color match.')
        reference_stats=sample_range(reference,0.,None,5)
    if not sources:
        raise ValueError('Нет подходящих видео: проверьте длительность и формат.')
    # Reserve source handles for transitions; no shortening of the music timeline.
    longest = max(v['duration'] for v in sources)-3/fps
    maximum = min(s['max_shot'],longest/1.35 if s['effects'] and s['effect_rate'] else longest)
    maximum = math.floor(maximum*fps)/fps
    minimum = math.ceil(s['min_shot']*fps)/fps
    if maximum < minimum:
        raise ValueError('Видео слишком короткое для выбранных кадров и переходов.')
    with tempfile.TemporaryDirectory(prefix='beatcut_') as td:
        work = Path(td); raw = work/'music.f32'
        progress(3,'Анализ ударов и акцентов…')
        args = ['ffmpeg','-v','error','-nostdin','-y','-i',music]
        if s['duration']:
            args += ['-t',s['duration']]
        run(args+['-map','0:a:0','-vn','-ac','1','-ar',SAMPLE_RATE,'-f','f32le',raw],cancel)
        count = raw.stat().st_size//4
        if count < SAMPLE_RATE/fps:
            raise ValueError('Аудио пустое или слишком короткое.')
        audio = np.memmap(raw,dtype='<f4',mode='r',shape=(count,))
        try:
            times, weights = detect_accents(audio)
        finally:
            audio._mmap.close(); del audio
        check(cancel)
        duration = count/SAMPLE_RATE; total = math.ceil(duration*fps)
        cuts, fallback = timeline(times,weights,total,fps,rng,s['density'],s['variety'],minimum,maximum)
        lengths = np.diff(cuts).astype(int).tolist()
        transitions = []; incoming = [0]; previous = None
        for i in range(len(lengths)-1):
            effect, n = 'cut', 0
            if s['effects'] and rng.random() < s['effect_rate']:
                pool = [e for e in s['effects'] if e != previous] or s['effects']
                effect = str(rng.choice(pool))
                n = min(round(s['transition']*fps*rng.uniform(1-.4*s['variety'],1+.4*s['variety'])),
                        math.floor(.35*min(lengths[i],lengths[i+1])))
                if n < 2:
                    effect, n = 'cut', 0
                previous = effect
            transitions.append({'effect':effect,'frames':int(n),'end_frame':cuts[i+1]})
            incoming.append(int(n))
        plan = source_plan(sources,[n+d for n,d in zip(lengths,incoming)],fps,rng,
                           s.get('repeat_policy','Редкие повторы'),s.get('repeat_cooldown',8.),
                           starts=[a-d for a,d in zip(cuts[:-1],incoming)],ends=cuts[1:],
                           cancel=lambda:check(cancel))
        repeats=sum(bool(item.get('repeat')) for item in plan)
        color_filters=[]
        if s.get('color_match'):
            progress(7,'Анализ SDR-цвета выбранных фрагментов…')
            for i,shot in enumerate(plan):
                source_stats=sample_range(shot['source'],shot['start'],shot['frames']/fps,4)
                color_filters.append(match_lut(source_stats,reference_stats,s.get('color_strength',.55)))
                if i%5==0:check(cancel)
        progress(7,f'Акцентов: {len(times)}; фрагментов: {len(plan)}; повторов моментов: {repeats}; переходов: {sum(t["frames"]>0 for t in transitions)}')
        w,h = s['size']
        geometry = (f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}' if s['fit']=='crop'
                    else f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black')
        head = ['ffmpeg','-v','error','-nostdin','-y','-filter_threads','1','-filter_complex_threads','1']
        encoding = ['-an','-c:v','libx264','-preset',s['preset'],'-crf',s['crf'],
                    '-threads','2','-bf','0','-r',fps,'-pix_fmt','yuv420p','-video_track_timescale','90000']
        clips=[]
        for i,shot in enumerate(plan):
            clip=work/f'clip_{i:05d}.mp4'
            vf=f'setpts=PTS-STARTPTS,fps={fps},{geometry},setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=1'
            if color_filters:vf+=','+color_filters[i]
            run(head+['-ss',shot['start'],'-i',shot['source'],'-map','0:v:0','-vf',vf,
                      '-frames:v',shot['frames']]+encoding+[clip],cancel)
            clips.append(clip)
            progress(8+42*(i+1)/len(plan),f'Подготовка фрагмента {i+1}/{len(plan)}')
        pieces=[]
        for i,shot in enumerate(plan):
            outgoing = transitions[i]['frames'] if i < len(transitions) else 0
            core_frames = lengths[i]-outgoing
            core=work/f'core_{i:05d}.mp4'
            vf=f'trim=start_frame={incoming[i]}:end_frame={incoming[i]+core_frames},setpts=PTS-STARTPTS'
            run(head+['-i',clips[i],'-vf',vf,'-frames:v',core_frames]+encoding+[core],cancel)
            pieces.append(core)
            if outgoing:
                trans=work/f'trans_{i:05d}.mp4'; start=shot['frames']-outgoing
                # xfade offset 0 on short source handles; keep exactly outgoing frames.
                graph=(f'[0:v]trim=start_frame={start}:end_frame={shot["frames"]},setpts=PTS-STARTPTS,fps={fps},settb=AVTB[a];'
                       f'[1:v]trim=end_frame={outgoing},setpts=PTS-STARTPTS,fps={fps},settb=AVTB[b];'
                       f'[a][b]xfade=transition={transitions[i]["effect"]}:duration={(outgoing-1)/fps:.9f}:offset=0,'
                       f'format=yuv420p,settb=1/{fps},setpts=N[v]')
                run(head+['-i',clips[i],'-i',clips[i+1],'-filter_complex',graph,
                          '-map','[v]','-frames:v',outgoing]+encoding+[trans],cancel)
                pieces.append(trans)
            progress(50+43*(i+1)/len(plan),f'Сборка склеек и переходов {i+1}/{len(plan)}')
        concat=work/'concat.txt'
        concat.write_text(''.join(f"file '{p.name}'\n" for p in pieces),encoding='ascii')
        fd,staged=tempfile.mkstemp(prefix='.beatcut_',suffix='.mp4',dir=output.parent)
        os.close(fd)
        try:
            progress(95,'Добавление музыки и сохранение MP4…')
            run(head+['-f','concat','-safe','1','-i',concat,'-i',music,'-map','0:v:0','-map','1:a:0',
                      '-c:v','copy','-c:a','aac','-b:a','192k','-af','asetpts=PTS-STARTPTS',
                      '-t',f'{duration:.9f}','-movflags','+faststart',staged],cancel)
            check(cancel)
            os.replace(staged,output)
        finally:
            Path(staged).unlink(missing_ok=True)
        metadata={'seed':seed,'settings':s,'audio':str(music),'duration':duration,
                  'accent_count':len(times),'cuts':cuts,'timed_fallback':fallback,
                  'segments':plan,'transitions':transitions,
                              'range_diversity': 'source-time selection per repeat_policy',
            'repeat_policy': s.get('repeat_policy','Редкие повторы'),
            'repeat_cooldown_seconds': s.get('repeat_cooldown',8.),
            'source_range_repeats':sum(bool(item.get('repeat')) for item in plan),
            'source_range_overlap_policy':s.get('repeat_policy','Редкие повторы'),
            'transition_alignment':'Transitions end at the selected accent; music is not shortened.'}
        # Video success is not lost if optional metadata cannot be written.
        try:
            output.with_suffix('.beatcut.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:
            progress(99,'Видео сохранено; не удалось записать JSON-план.')
        progress(100,'Готово!')
        return metadata
