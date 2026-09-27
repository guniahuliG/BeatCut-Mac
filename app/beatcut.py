#!/usr/bin/env python3
"""BeatCut MVP: randomized bass-accent montage, local processing only."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
import numpy as np
from audio_analysis import SAMPLE_RATE, detect_accents, choose_cuts

VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
AUDIO_EXT = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus'}
BASE = Path(__file__).resolve().parent


def execute(args):
    p = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, check=False)
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8', errors='replace')[-4000:])
    return p.stdout


def probe(path):
    data = json.loads(execute(['ffprobe', '-v', 'error', '-show_streams',
                              '-show_format', '-of', 'json', path]))
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    def duration(stream):
        try:
            value = float((stream or {}).get('duration', data.get('format', {}).get('duration', 0)))
            return value if math.isfinite(value) and value > 0 else 0
        except (ValueError, TypeError):
            return 0
    return {'video': video, 'audio': audio, 'video_duration': duration(video)}


def source_plan(videos, lengths, fps, rng):
    """Avoid recently sampled source ranges when enough footage is available."""
    recent, plan = [], []
    for nframes in lengths:
        seconds = nframes/fps
        eligible = [v for v in videos if v['duration'] >= seconds+2/fps]
        if not eligible:
            raise ValueError('No source video is long enough for a shot.')
        chosen = None
        for _ in range(60):
            source = eligible[int(rng.integers(len(eligible)))]
            start = float(rng.uniform(0, max(0, source['duration']-seconds-2/fps)))
            chosen = (source, start)
            overlap = any(source['path'] == old['source'] and
                          start < old['start']+old['frames']/fps and
                          start+seconds > old['start'] for old in recent)
            if not overlap:
                break
        source, start = chosen
        item = {'source': source['path'], 'start': round(start, 6), 'frames': int(nframes)}
        plan.append(item)
        recent.append(item)
        recent = recent[-5:]
    return plan


def parser():
    p = argparse.ArgumentParser(description='Randomized video montage on bass accents.')
    p.add_argument('--video-dir', type=Path, default=BASE/'video')
    p.add_argument('--audio-dir', type=Path, default=BASE/'audio')
    p.add_argument('--audio', type=Path, help='Choose a specific track instead of folder selection')
    p.add_argument('--output-dir', type=Path, default=BASE/'output')
    p.add_argument('--density', type=float, default=.5, help='0=calmer, 1=more rapid cuts')
    p.add_argument('--min-shot', type=float, default=.35, help='Minimum shot duration in seconds')
    p.add_argument('--max-shot', type=float, default=5., help='Maximum shot duration in seconds')
    p.add_argument('--duration', type=float, help='Use only the first N seconds of the track')
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--size', default='1280x720', help='Even width x height; e.g. 1080x1920')
    p.add_argument('--fit', choices=['crop', 'pad'], default='crop')
    p.add_argument('--seed', type=int, help='Repeatable random choices')
    p.add_argument('--crf', type=int, default=20)
    p.add_argument('--preset', choices=['ultrafast','superfast','veryfast','faster','fast','medium','slow'], default='veryfast')
    p.add_argument('--dry-run', action='store_true', help='Save montage plan without rendering')
    return p


def main():
    p = parser()
    a = p.parse_args()
    if not (0 <= a.density <= 1):
        p.error('--density must be between 0 and 1')
    if not (1 <= a.fps <= 120 and math.isfinite(a.min_shot) and math.isfinite(a.max_shot)
            and 0 < a.min_shot <= a.max_shot and a.max_shot >= 1/a.fps):
        p.error('Invalid fps or shot duration limits')
    if a.duration is not None and (not math.isfinite(a.duration) or a.duration <= 0):
        p.error('--duration must be positive')
    if not 0 <= a.crf <= 51:
        p.error('--crf must be between 0 and 51')
    try:
        width, height = map(int, a.size.lower().split('x'))
        assert 2 <= width <= 7680 and 2 <= height <= 7680 and width % 2 == height % 2 == 0
    except (ValueError, AssertionError):
        p.error('--size must contain two even dimensions, e.g. 1280x720')
    for folder in (a.video_dir, a.audio_dir, a.output_dir):
        folder.mkdir(parents=True, exist_ok=True)
    for binary in ('ffmpeg', 'ffprobe'):
        if shutil.which(binary) is None:
            raise RuntimeError(f'{binary} is not installed or is not on PATH. See README.')
    video_files = sorted(x.resolve() for x in a.video_dir.iterdir() if x.is_file() and x.suffix.lower() in VIDEO_EXT)
    audio_files = sorted(x.resolve() for x in a.audio_dir.iterdir() if x.is_file() and x.suffix.lower() in AUDIO_EXT)
    if not video_files:
        raise ValueError(f'Put a video in {a.video_dir}')
    seed = a.seed if a.seed is not None else int.from_bytes(os.urandom(8), 'little')
    rng = np.random.default_rng(seed)
    if a.audio:
        music = a.audio.resolve()
        if not music.is_file():
            raise ValueError(f'Audio file not found: {music}')
    elif audio_files:
        music = audio_files[int(rng.integers(len(audio_files)))]
    else:
        raise ValueError(f'Put a music track in {a.audio_dir}')
    videos = []
    for path in video_files:
        try:
            info = probe(path)
            if info['video'] and info['video_duration'] > a.min_shot+2/a.fps:
                videos.append({'path': str(path), 'duration': info['video_duration']})
            else:
                print(f'Skipping unsuitable video: {path.name}', flush=True)
        except RuntimeError as exc:
            print(f'Skipping unreadable video: {path.name}: {exc}', flush=True)
    if not videos:
        raise ValueError('No usable video sources with a known duration.')
    max_shot = min(a.max_shot, max(v['duration'] for v in videos)-2/a.fps)
    max_shot = math.floor(max_shot*a.fps)/a.fps
    min_shot = math.ceil(a.min_shot*a.fps)/a.fps
    if max_shot < min_shot:
        raise ValueError('Sources are too short for --min-shot.')
    print(f'Track: {music.name} | seed: {seed}', flush=True)
    with tempfile.TemporaryDirectory(prefix='beatcut_') as temp:
        work = Path(temp)
        raw = work/'audio.f32'
        command = ['ffmpeg','-v','error','-nostdin','-y','-i',music]
        if a.duration:
            command += ['-t',str(a.duration)]
        command += ['-map','0:a:0','-vn','-ac','1','-ar',str(SAMPLE_RATE),'-f','f32le',raw]
        execute(command)
        count = raw.stat().st_size//4
        if count < SAMPLE_RATE/a.fps:
            raise ValueError('The music track is empty or too short.')
        samples = np.memmap(raw, mode='r', dtype='<f4', shape=(count,))
        try:
            duration = count/SAMPLE_RATE
            times, strengths = detect_accents(samples)
        finally:
            samples._mmap.close()
            del samples
        total_frames = int(math.ceil(duration*a.fps))
        cuts, fallback = choose_cuts(times, strengths, total_frames, a.fps, rng,
                                    a.density, min_shot, max_shot)
        if not len(times):
            print('No clear accents found; using timed cuts.', flush=True)
        plan = source_plan(videos, np.diff(cuts), a.fps, rng)
        name = 'montage_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
        output = a.output_dir/(name+'.mp4')
        report = a.output_dir/(name+'.json')
        metadata = {'seed': seed, 'music': str(music), 'duration': duration,
                    'fps': a.fps, 'size': a.size, 'accent_count': len(times),
                    'cut_frames': cuts, 'timed_fallback_frames': fallback,
                    'segments': plan, 'rendered': False,
                    'note': 'Bass-weighted transient heuristic, not instrument separation.'}
        report.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{len(times)} accents; {len(plan)} shots; {len(fallback)} timed cuts.', flush=True)
        if a.dry_run:
            print(f'Plan: {report.resolve()}')
            return
        scale = f'scale={width}:{height}:force_original_aspect_ratio='
        if a.fit == 'crop':
            geometry = scale+f'increase,crop={width}:{height}'
        else:
            geometry = scale+f'decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black'
        names = []
        for i, shot in enumerate(plan):
            segment = work/f'shot_{i:05d}.mp4'
            filters = (f'setpts=PTS-STARTPTS,fps={a.fps},'+geometry+
                       f',setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration={shot["frames"]/a.fps:.6f}')
            execute(['ffmpeg','-v','error','-nostdin','-y','-ss',shot['start'],
                     '-i',shot['source'],'-map','0:v:0','-an','-sn','-dn','-vf',filters,
                     '-frames:v',shot['frames'],'-c:v','libx264','-preset',a.preset,
                     '-crf',a.crf,'-threads','2','-bf','0','-video_track_timescale','90000',segment])
            names.append(f"file '{segment.name}'")
            print(f'Rendered shot {i+1}/{len(plan)}', flush=True)
        concat = work/'concat.txt'
        concat.write_text('\n'.join(names)+'\n', encoding='ascii')
        # Stage on the destination filesystem, then atomically publish the finished video.
        staged = a.output_dir/('.'+name+'.partial.mp4')
        try:
            execute(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','1','-i',concat,
                     '-i',music,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',
                     '-b:a','192k','-af','asetpts=PTS-STARTPTS','-t',f'{duration:.9f}',
                     '-movflags','+faststart',staged])
            os.replace(staged, output)
        finally:
            staged.unlink(missing_ok=True)
        metadata['rendered'] = True
        metadata['output'] = str(output.resolve())
        report.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Done: {output.resolve()}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        sys.exit(130)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
