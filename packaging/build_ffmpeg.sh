#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${MACOSX_DEPLOYMENT_TARGET:?Set macOS deployment target}"
PY="$PWD/.venv/bin/python"
PREFIX="$PWD/vendor"
mkdir -p build/sources build/native "$PREFIX/bin" "$PREFIX/licenses"
"$PY" packaging/download.py ffmpeg build/sources/ffmpeg.tar.xz
"$PY" packaging/download.py x264 build/sources/x264.tar.gz
mkdir -p build/native/ffmpeg build/native/x264
tar -xJf build/sources/ffmpeg.tar.xz -C build/native/ffmpeg --strip-components=1
tar -xzf build/sources/x264.tar.gz -C build/native/x264 --strip-components=1
export CC=clang
export CFLAGS="-O2 -mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
export LDFLAGS="-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
JOBS="$(sysctl -n hw.logicalcpu)"
# No Homebrew runtime libraries. Disable optional external codec detection.
# Assembly disabled for a simple native build without nasm and CPU assumptions.
(
 cd build/native/x264
 ./configure --prefix="$PREFIX" --enable-static --disable-cli --disable-opencl --disable-asm \
   --extra-cflags="$CFLAGS" --extra-ldflags="$LDFLAGS"
 make -j"$JOBS"
 make install
)
(
 cd build/native/ffmpeg
 ./configure --prefix="$PREFIX" --disable-autodetect --disable-shared --enable-static \
   --disable-doc --disable-debug --disable-ffplay --disable-x86asm --disable-network \
   --enable-gpl --enable-libx264 \
   --extra-cflags="-I$PREFIX/include $CFLAGS" --extra-ldflags="-L$PREFIX/lib $LDFLAGS"
 make -j"$JOBS"
 make install
)
cp build/native/ffmpeg/COPYING.GPLv2 "$PREFIX/licenses/FFmpeg-GPLv2.txt"
cp build/native/ffmpeg/LICENSE.md "$PREFIX/licenses/FFmpeg-LICENSE.md"
cp build/native/x264/COPYING "$PREFIX/licenses/x264-COPYING.txt"
"$PREFIX/bin/ffmpeg" -version
"$PREFIX/bin/ffprobe" -version
