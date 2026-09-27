# PyInstaller runs this on the native macOS architecture.
from pathlib import Path
import os

ROOT = Path(SPECPATH).parent
ARCH = os.environ['APP_ARCH']
MINIMUM = os.environ['MACOSX_DEPLOYMENT_TARGET']

a = Analysis(
    [str(ROOT/'app/mac_entry.py')],
    pathex=[str(ROOT/'app')],
    binaries=[(str(ROOT/'vendor/bin/ffmpeg'), 'bin'),
              (str(ROOT/'vendor/bin/ffprobe'), 'bin')],
    datas=[(str(ROOT/'app/models'), 'models'),
           (str(ROOT/'vendor/licenses'), 'licenses'),
           (str(ROOT/'THIRD_PARTY.md'), '.')],
    hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='BeatCutStudio',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=False, console=False, argv_emulation=False,
          target_arch=ARCH, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BeatCut Studio')
app = BUNDLE(coll, name='BeatCut Studio.app', icon=None,
             bundle_identifier='local.beatcut.studio',
             info_plist={
                 'CFBundleShortVersionString':'0.3.0',
                 'CFBundleVersion':'3',
                 'LSMinimumSystemVersion':MINIMUM,
                 'NSHighResolutionCapable':True,
                 'NSPrincipalClass':'NSApplication',
             })
