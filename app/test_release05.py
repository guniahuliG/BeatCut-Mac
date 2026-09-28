"""Release regression tests. GUI/integration entry points also used on Linux."""
from pathlib import Path
import tempfile
import threading
import unittest
import numpy as np
from fx_core import DEFAULTS,source_time
from fx_random import events
from queue_core import validate_jobs,run_jobs,process_job
from studio_engine import Cancelled
from color_lut import match_lut


class ReleaseTests(unittest.TestCase):
    def test_rewind_depth_direction_endpoints(self):
        p=dict(DEFAULTS,start=1.,end=5.,rewind=True,rewind_amount=1.)
        self.assertLess(source_time(3.5,p),source_time(3.,p))
        self.assertAlmostEqual(source_time(3.8,p),1.)
        self.assertAlmostEqual(source_time(5.,p),5.)
        self.assertLess(source_time(2.6,dict(p,rewind_amount=.25)),source_time(2.6,p))
        for t in np.linspace(1,5,501):self.assertTrue(1<=source_time(t,p)<=5)

    def test_random_rewind_outside_identity(self):
        p=dict(DEFAULTS,start=0.,end=60.,random_mode=True,rewind=True,rate_rewind=5.)
        seq=events(p,'rewind');self.assertEqual(len(seq),5)
        self.assertEqual(source_time(60,p),60)
        a,b=seq[0];self.assertLess(source_time(a+.65*(b-a),p),source_time(a+.5*(b-a),p))
        self.assertEqual(seq,events(dict(p,rewind_amount=.4),'rewind'))

    def test_color_identity_and_blend(self):
        stats=(np.array([90.,120.,140.]),np.array([20.,30.,40.]))
        self.assertIn('val*1.000000+0.000000',match_lut(stats,stats,1))
        other=(np.array([140.,150.,150.]),np.array([30.,35.,30.]))
        self.assertEqual(match_lut(stats,other,0),match_lut(stats,stats,1))
        self.assertNotEqual(match_lut(stats,other,.5),match_lut(stats,other,1))

    def test_collision_other_project_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a.mp4';b=Path(tmp)/'b.mp4';a.touch();b.touch()
            def job(out):return dict(name='x',videos=[str(a)],music=str(b),output=out,settings={})
            with self.assertRaises(ValueError):validate_jobs([job(a)])
            with self.assertRaises(ValueError):validate_jobs([job(Path(tmp)/'out.mp4')]*2)
            second=job(Path(tmp)/'safe.mp4');second['videos']=[str(b)]
            with self.assertRaises(ValueError):validate_jobs([job(b),second])

    def test_queue_failure_continues_and_snapshot(self):
        jobs=[dict(name=str(i),output='x',settings={'value':i}) for i in range(5)]
        seen=[]
        def processor(job,cancel,progress):
            seen.append(job['settings']['value']);jobs[-1]['settings']['value']=99
            if job['name']=='1':raise ValueError('test')
            progress(100,'done')
        result=run_jobs(jobs,threading.Event(),lambda *a:None,processor)
        self.assertEqual(seen,list(range(5)))
        self.assertEqual(result[1][1],'ошибка');self.assertEqual(result[4][1],'готово')

    def test_queue_cancel_skips_remaining(self):
        jobs=[dict(name=str(i),output='x') for i in range(5)]
        def processor(job,cancel,progress):raise Cancelled()
        result=run_jobs(jobs,threading.Event(),lambda *a:None,processor)
        self.assertEqual(result[0][1],'остановлено')
        self.assertTrue(all(row[1]=='пропущено после отмены' for row in result[1:]))

    def test_gate_serializes_threads(self):
        from job_gate import serialized
        import time
        counter=[0,0]
        @serialized
        def work(cancel):
            counter[0]+=1;counter[1]=max(counter);time.sleep(.03);counter[0]-=1
        threads=[threading.Thread(target=work,args=(threading.Event(),)) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(counter[1],1)


def integration(folder):
    import subprocess,json
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    source=folder/'source.mp4';ref=folder/'reference.mp4';music=folder/'music.wav'
    for target,filters in [(source,'null'),(ref,'eq=brightness=0.08:saturation=0.8')]:
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=30',
                        '-vf',filters,'-t','4','-c:v','libx264','-threads','2',str(target)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=220:sample_rate=44100','-t','1.5',str(music)],check=True)
    settings=dict(density=.8,variety=.5,min_shot=.25,max_shot=.6,effect_rate=1.,effects=['fade'],transition=.12,
                  duration=1.5,seed=4,size=(160,90),fps=30,fit='crop',crf=25,preset='ultrafast',
                  repeat_policy='Без повторов',repeat_cooldown=8.,color_match=True,color_reference=str(ref),color_strength=.5)
    fx=dict(DEFAULTS,end=1.5,rewind=True,random_mode=True,rate_rewind=30.,random_min=.3,random_max=.8,
            zoom=True,rate_zoom=30.,random_seed=4.)
    jobs=[dict(name=f'job{i}',videos=[str(source)],music=str(music),output=folder/f'job{i}.mp4',
               settings=dict(settings,seed=i),fx=fx if i%2 else None) for i in range(5)]
    validate_jobs(jobs)
    result=run_jobs(jobs,threading.Event(),lambda *args:None)
    assert all(r[1]=='готово' for r in result),result
    for job in jobs:
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(job['output'])]))
        v=next(s for s in data['streams'] if s['codec_type']=='video')
        assert int(v['nb_frames'])==45,data
        assert any(s['codec_type']=='audio' for s in data['streams'])
        subprocess.run(['ffmpeg','-v','error','-i',str(job['output']),'-f','null','-'],check=True)
    # A mid-render cancellation must preserve pre-existing final bytes.
    old=jobs[0]['output'].read_bytes();cancel=threading.Event()
    def stop(n,s):
        if n>=8:cancel.set()
    try:process_job(jobs[0],cancel,stop)
    except Cancelled:pass
    else:raise AssertionError('No cancellation')
    assert jobs[0]['output'].read_bytes()==old
    print('INTEGRATION PASS: five sequential MP4s, color, transitions, rewind, audio, 45 frames, cancellation')


def gui(folder):
    import time
    from unittest.mock import patch
    from studio_next import App
    from batch_workspace import BatchManager
    from fx_editor import Editor
    import tkinter.messagebox as boxes
    folder=Path(folder);app=App();errors=[]
    app.report_callback_exception=lambda *args:errors.append(str(args))
    boxes.showerror=lambda *args,**kw:errors.append(str(args))
    boxes.showinfo=lambda *args,**kw:None
    def pump(condition,seconds=40):
        end=time.monotonic()+seconds
        while not condition() and time.monotonic()<end:app.update();time.sleep(.02)
        assert condition(),'GUI timeout'
        assert not errors,errors
    try:
        cfg=app.settings();cfg.update(size=(160,90),fps=30,preset='ultrafast',color_match=False)
        b=BatchManager(app,cfg);app.batch_windows.append(b)
        b.add_tab();b.add_tab();b.add_tab();assert len(b.tabs)==5
        for i,tab in enumerate(b.tabs):
            tab.videos=[str(folder/'source.mp4')];tab.audio.set(str(folder/'music.wav'))
            tab.output.set(str(folder/f'gui{i}.mp4'));tab.duration.set('.5');tab.refresh()
        t=b.tabs[0];t.configure_fx();t.fx_controls.vars['rewind'].set(True);t.fx_enabled.set(True)
        assert t.snapshot()['fx']['rewind']
        t.fx_controls.vars['flash'].set(True);assert not t.snapshot()['fx']['flash']
        t.fx_controls.vars['flash'].set(False)
        # Check the actual queue button path, using lightweight simulated work for GUI isolation.
        def fake_run(jobs,cancel,emit):
            for i,j in enumerate(jobs):emit('progress',(i,100,'test'));emit('result',(i,(j['name'],'готово',str(j['output']))))
            emit('done',[(j['name'],'готово',str(j['output'])) for j in jobs])
        with patch('batch_workspace.run_jobs',fake_run):b.start();pump(lambda:not b.busy)
        assert b.bar['value']==100 and b.tabs[4].last_output
        b.close()
        e=Editor(app,folder/'job0.mp4');app.editors.append(e)
        app.update();assert e.data is None and not e.busy
        e.begin_prepare();pump(lambda:not e.busy)
        assert e.player and not e.player.live_preview.get()
        with patch.object(e.player.reader,'get',side_effect=AssertionError('decoded while disabled')):
            e.player.redraw();e.player.toggle()
        assert not e.player.playing
        e.player.live_preview.set(True);e.player.set_live_preview();assert e.player.photo is not None
        e.controls.vars['rewind'].set(True);e.player.position=.3;e.player.redraw()
        e.player.live_preview.set(False);e.player.set_live_preview();assert e.player.photo is None
        assert not errors,errors
        print('GUI PASS: five tabs, independent snapshots, batch controls, effects, disabled preview does not decode')
    finally:app.close()


if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='--integration':integration(sys.argv[2])
    elif len(sys.argv)>1 and sys.argv[1]=='--gui':gui(sys.argv[2])
    else:unittest.main()
