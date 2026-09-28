"""Run in CI from inside the frozen app; no network, display or user media."""
from pathlib import Path
import json
import subprocess
import threading
import cv2
import numpy as np
from PIL import Image
from fx_core import DEFAULTS, transform, source_time
from fx_media import prepare, analyze, export, Reader
from studio_engine import Cancelled


def main(report,source):
    import unittest
    import io
    from test_fx import EffectsTests
    from test_random_fx import RandomEffectsTests
    from test_release05 import ReleaseTests
    from test_source_selection import SourceSelectionTests
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(EffectsTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(RandomEffectsTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReleaseTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(SourceSelectionTests))
    # A windowed PyInstaller executable can have sys.stderr=None.
    test_log=io.StringIO()
    result=unittest.TextTestRunner(stream=test_log,verbosity=1).run(suite)
    if not result.wasSuccessful():raise AssertionError(test_log.getvalue())
    report=Path(report);cache=report/'fx-cache';cache.mkdir(exist_ok=True)
    cancel=threading.Event();progress=lambda n,s:None
    data=prepare(source,cache,cancel,progress)
    track=analyze(data['proxy'],cancel,progress)
    assert len(track)==data['count']
    Image.fromarray(np.zeros((8,8,3),np.uint8))
    params=dict(DEFAULTS,start=.1,end=min(3.,data['duration']),zoom=True,shake=True,
                slow=True,flash=True,face=True)
    # Synthetic tracking coordinates exercise stabilization even on generated footage.
    track[:,0]=.45;track[:,1]=.4;track[:,2]=.14;track[:,4]=1
    target=report/'all-effects.mp4'
    export(data,target,params,track,cancel,progress)
    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(target)]))['streams']
    v=next(s for s in streams if s['codec_type']=='video')
    assert int(v['nb_frames'])==data['count']
    assert abs(float(v['duration'])-data['duration'])<1/data['fps']
    assert any(s['codec_type']=='audio' for s in streams)
    # Cancellation must not replace a pre-existing destination.
    before=target.read_bytes();cancel.set()
    try:export(data,target,params,track,cancel,progress)
    except Cancelled:pass
    else:raise AssertionError('Cancellation was ignored')
    assert target.read_bytes()==before
    cancel.clear()
    # Check the final export against the shared full-resolution frame transform.
    original=Reader(data['master']);rendered=Reader(target)
    try:
        index=min(37,data['count']-1);t=index/data['fps'];st=source_time(t,params)
        expected=transform(original.get(int(st*data['fps']+1e-6)),t,st,params,track,data['fps'])
        actual=rendered.get(index)
        error=float(np.abs(actual.astype(float)-expected.astype(float)).mean())
        assert error<15,error
    finally:original.close();rendered.close()
    random_params=dict(params,random_mode=True,random_seed=31.,random_min=.15,random_max=.6,
                       rate_zoom=60.,rate_slow=60.,rate_face=60.,rate_shake=60.,rate_flash=60.)
    random_output=report/'random-effects.mp4'
    export(data,random_output,random_params,track,cancel,progress)
    random_info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(random_output)]))
    random_video=next(s for s in random_info['streams'] if s['codec_type']=='video')
    assert int(random_video['nb_frames'])==data['count']
    assert any(s['codec_type']=='audio' for s in random_info['streams'])
    return {'random_export_frames':int(random_video['nb_frames']),
            'effects_export_frames':data['count'],'model_analyzed_frames':len(track),
            'export_pixel_mae':error,'cancel_preserves_output':True,'opencv':cv2.__version__}
