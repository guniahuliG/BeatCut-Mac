# Third-party components

This is an experimental local video editor. The Python application sources in `app/` and the build scripts are MIT-licensed; that license does not replace the licenses of bundled dependencies.

The frozen application includes Python (PSF license), Tcl/Tk (their permissive license terms), NumPy and SciPy (BSD licenses and additional wheel notices, including numerical libraries), and the PyInstaller bootloader (GPL with its bootloader exception). PyInstaller's bootloader exception permits distribution of frozen applications under their own licenses. See the actual notices collected into `Contents/Resources/licenses` / `Contents/Frameworks/licenses` in the macOS bundle; PyInstaller may use symlinks between these locations.

FFmpeg is built as a separate executable with `--enable-gpl --enable-libx264`, without `--enable-nonfree`. x264 is GPL-licensed. This is NOT an LGPL-only FFmpeg build. Preserve the FFmpeg/x264 license texts and corresponding source when redistributing these executables. The workflow produces `Sources-*` artifacts containing the exact FFmpeg/x264 source archives and the build scripts used. There are no local source patches. Those source artifacts expire after 14 days, so save them along with the app. If you redistribute binaries, provide the corresponding source and required notices to recipients under the applicable licenses; a temporary CI artifact alone is not a permanent source offer.

Python installer, FFmpeg and x264 download URLs and SHA256 values are fixed in `packaging/downloads.json`. Python package versions are fixed in `requirements-build.txt`. Python and Tcl/Tk license texts are stored in `packaging/licenses`; package notices are collected from installed distributions during the build.

Upstream sources and license information:

- Python: https://www.python.org/ and https://github.com/python/cpython/tree/v3.12.10
- Tcl/Tk: https://www.tcl-lang.org/
- NumPy: https://numpy.org/
- SciPy: https://scipy.org/
- PyInstaller: https://pyinstaller.org/en/stable/license.html
- FFmpeg: https://ffmpeg.org/legal.html and https://ffmpeg.org/releases/
- x264: https://www.videolan.org/developers/x264.html

Codec patent obligations can vary by jurisdiction and use. Review them before commercial distribution. This file is a component inventory, not legal advice.
