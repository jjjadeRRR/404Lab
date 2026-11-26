#!/bin/sh
# Builds the DM-404 emulator on Linux and macOS, outside this repository. DM-404 is a separate project with its own licences (see its LICENSE),
# used as an external tool: nothing of it is copied here. Output: $LAB404_DEPS/dm-404/build/qemu/qemu-system-arm
set -e
deps=${LAB404_DEPS:-$HOME/lab404-deps}
repo=https://github.com/nickpetty/dm-404.git
pin=cbccf0d
version=11.1.2
qemu_sha256=731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016
case $(uname -s) in
    Linux) fx_name=libsp404fx.so; fx_flag=-shared ;;
    Darwin) fx_name=sp404fx.dylib; fx_flag=-dynamiclib ;;
    *) echo "Use this script on Linux or macOS. See docs/STAND.md for Windows." >&2; exit 1 ;;
esac
cc=${CC:-cc}
cxx=${CXX:-c++}
mkdir -p "$deps"
deps=$(cd "$deps" && pwd)
dm=$deps/dm-404
q=$dm/third_party/qemu
[ -d "$dm/.git" ] || git clone -q "$repo" "$dm"
git -C "$dm" checkout -q "$pin"
if [ ! -d "$q" ]; then
    archive=$dm/third_party/qemu-$version.tar.xz
    [ -f "$archive" ] || curl -sSfL -o "$archive" "https://download.qemu.org/qemu-$version.tar.xz"
    if command -v sha256sum >/dev/null 2>&1; then
        echo "$qemu_sha256  $archive" | sha256sum -c -
    else
        echo "$qemu_sha256  $archive" | shasum -a 256 -c -
    fi
    tar -xf "$archive" -C "$dm/third_party"
    mv "$dm/third_party/qemu-$version" "$q"
fi
# Not git apply: inside the DM-404 checkout it silently skips paths outside that repository's index.
for p in "$dm"/core/qemu/patches/*.patch; do
    stamp=$q/.applied-$(basename "$p")
    [ -f "$stamp" ] && continue
    patch -d "$q" -p1 -N -s < "$p"
    touch "$stamp"
    echo "applied $(basename "$p")"
done
(cd "$dm/core/qemu" && find hw include -type f) | while read -r f; do
    mkdir -p "$(dirname "$q/$f")"
    cp "$dm/core/qemu/$f" "$q/$f"
done
mkdir -p "$dm/build/qemu"
cd "$dm/build/qemu"
[ -f build.ninja ] || "$q/configure" --target-list=arm-softmmu --disable-docs --disable-werror --disable-tools --disable-guest-agent \
    --disable-sdl --disable-gtk --disable-vnc --disable-opengl --disable-curses
ninja qemu-system-arm
echo "built: $dm/build/qemu/qemu-system-arm"
# A blank formatted internal drive, as the DM-404 app makes on first run. Runs use it through a temporary overlay.
cd "$dm"
if [ ! -f build/fatimg ]; then
    for f in ff ffunicode ffsystem; do "$cc" -O2 -c "frontend/ThirdParty/fatfs/$f.c" -o "build/$f.o"; done
    "$cxx" -std=c++20 -O2 tools/fatimg.cpp frontend/Source/FatImage.cpp build/ff.o build/ffunicode.o build/ffsystem.o -o build/fatimg
fi
[ -f build/internal-blank.img ] || build/fatimg create build/internal-blank.img 16384 exfat bare SP-404MKII
echo "blank drive: $dm/build/internal-blank.img"

# Upstream's FX script targets MSYS2. Build the same sources as a native
# shared library so the emulator can load the 48 DaisySP-backed effects.
daisy=third_party/DaisySP
[ -d "$daisy/Source" ] || git clone -q --depth 1 https://github.com/electro-smith/DaisySP.git "$daisy"
[ -f "$daisy/DaisySP-LGPL/Source/daisysp-lgpl.h" ] || git -C "$daisy" submodule update --init --depth 1
mkdir -p build/fx
# Relative source paths here have no whitespace. Keeping them relative also
# lets LAB404_DEPS itself contain spaces.
set --
for dir in $(find "$daisy/Source" "$daisy/DaisySP-LGPL/Source" -type d); do
    set -- "$@" "-I$dir"
done
"$cxx" "$fx_flag" -fPIC -std=c++17 -O2 -ffast-math -DSP404FX_BUILD -D_USE_MATH_DEFINES -Icore/fx "$@" \
    core/fx/*.cpp $(find "$daisy/Source" "$daisy/DaisySP-LGPL/Source" -name '*.cpp') -o "build/fx/$fx_name"
cp "build/fx/$fx_name" "build/qemu/$fx_name"
echo "built: $dm/build/qemu/$fx_name"
