"""Run inside the packaged executable, without relying on system Python/FFmpeg."""
import json
import math
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import wave
import numpy as np
import tkinter as tk
from studio_engine import render, EFFECTS


def main(report):
    report = Path(report).resolve()
    report.mkdir(parents=True, exist_ok=True)
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Smoke test must run inside the packaged app')
    bundle = Path(sys._MEIPASS).resolve()
    for name in ('ffmpeg', 'ffprobe'):
        found = Path(shutil.which(name) or '/missing').resolve()
        if not found.is_relative_to(bundle):
            raise RuntimeError(f'{name} is not loaded from the bundle: {found}')
    tcl = tk.Tcl()
    tcl_version = tcl.eval('info patchlevel')
    sr = 22050; seconds = 4
    samples = np.zeros(sr*seconds, dtype=np.float32)
    for t in np.arange(.25, seconds, .25):
        x = np.arange(int(.12*sr))/sr
        kick = .7*np.sin(2*np.pi*65*x)*np.exp(-35*x)
        start = int(t*sr)
        samples[start:start+len(kick)] += kick
    music = report/'music.wav'; video = report/'source.mp4'
    with wave.open(str(music), 'wb') as f:
        f.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
        f.writeframes((samples*32767).astype('<i2').tobytes())
    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','lavfi','-i',
                    'testsrc2=size=160x90:rate=30','-t','6','-c:v','libx264','-threads','2',str(video)],check=True)
    settings = dict(density=.9,variety=.8,min_shot=.25,max_shot=1.1,effect_rate=1.,
                    transition=.16,duration=seconds,seed=42,size=(160,90),fps=30,
                    fit='crop',crf=25,preset='ultrafast')
    results = []
    for effect in list(EFFECTS.values())+['cut']:
        cfg = dict(settings, effects=[] if effect == 'cut' else [effect])
        output = report/(effect+'.mp4')
        metadata = render([video],music,output,cfg,threading.Event(),lambda n,t:None)
        data = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
        streams = data['streams']
        v = next(x for x in streams if x['codec_type']=='video')
        a = next(x for x in streams if x['codec_type']=='audio')
        assert int(v['nb_frames']) == seconds*30
        assert abs(float(v['duration'])-seconds) < 1/30
        assert abs(float(a['duration'])-seconds) < .1
        if effect != 'cut':
            assert any(t['effect']==effect and t['frames']>0 for t in metadata['transitions'])
        p = subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],capture_output=True,text=True)
        assert p.returncode == 0 and not p.stderr, p.stderr
        results.append({'effect':effect,'frames':int(v['nb_frames'])})
    from fx_smoke import main as test_effects
    effects_results = test_effects(report, report/'cut.mp4')
    from test_release05 import integration
    integration(report/'release05')
    (report/'self-test.json').write_text(json.dumps({'architecture':platform.machine(),
        'macOS':platform.mac_ver()[0],'tcl':tcl_version,'tests':results,
        'effects':effects_results},indent=2))
    print('Packaged render tests passed')
