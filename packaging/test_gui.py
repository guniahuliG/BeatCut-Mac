"""Linux virtual-display GUI smoke test; not a macOS compatibility claim.
Usage: xvfb-run -a python packaging/test_gui.py /absolute/path/to/sample.mp4
"""
from pathlib import Path
import sys
import time
import traceback
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'app'))
from studio_next import App
from fx_editor import Editor

app=App();errors=[]
app.report_callback_exception=lambda *args:errors.append(''.join(traceback.format_exception(*args)))
editor=Editor(app,sys.argv[1]);app.editors.append(editor)
# Fail tests rather than block on a modal error dialog.
import tkinter.messagebox as boxes
boxes.showerror=lambda *args,**kwargs:errors.append(str(args))
boxes.showinfo=lambda *args,**kwargs:None

def wait_until(predicate,timeout=30):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.update();time.sleep(.02)
    assert predicate(),'Timed out'
    assert not errors,errors

try:
    editor.begin_prepare()
    wait_until(lambda:not editor.busy)
    assert editor.data and editor.player and editor.controls
    app.update();editor.player.live_preview.set(True);editor.player.redraw();assert editor.player.photo is not None
    editor.controls.vars['zoom'].set(True)
    editor.controls.vars['shake'].set(True)
    editor.player.toggle()
    started=editor.player.position
    end=time.monotonic()+.6
    while time.monotonic()<end:app.update();time.sleep(.01)
    assert editor.player.position>started
    editor.player.pause()
    editor.player.seek.set(.8);editor.player.end_seek()
    assert abs(editor.player.position-.8)<.01
    editor.track_faces();wait_until(lambda:not editor.busy)
    assert editor.raw is not None
    editor.controls.vars['face'].set(True);editor.player.redraw()
    assert not editor.controls.snapshot()['flash']
    editor.controls.disable();app.update()
    assert not errors,errors
    # Footer remains visible; long controls are reached with the vertical scrollbar.
    assert editor.export_button.winfo_ismapped()
    print('GUI PASS: open, prepare, play, live controls, seek, analyze, redraw, safe defaults, close')
finally:
    if editor.busy:editor.cancel.set();wait_until(lambda:not editor.busy)
    app.close()
