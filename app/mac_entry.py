"""Frozen app entry. Local bundled binaries take precedence over any user PATH."""
from pathlib import Path
import os
import sys

if getattr(sys, 'frozen', False):
    resources = Path(sys._MEIPASS)
    binaries = resources/'bin'
    os.environ['PATH'] = str(binaries)+os.pathsep+os.environ.get('PATH', '/usr/bin:/bin')

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--self-test':
        from smoke_test import main
        main(Path(sys.argv[2]))
    else:
        try:
            from studio import App
            App().mainloop()
        except Exception:
            import traceback
            logdir = Path.home()/'Library/Logs/BeatCut Studio'
            logdir.mkdir(parents=True, exist_ok=True)
            log = logdir/'startup-error.txt'
            log.write_text(traceback.format_exc(), encoding='utf-8')
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk(); root.withdraw()
                messagebox.showerror('BeatCut Studio', 'Не удалось запустить приложение. Журнал ошибки:\n'+str(log))
                root.destroy()
            except Exception:
                pass
            sys.exit(1)
