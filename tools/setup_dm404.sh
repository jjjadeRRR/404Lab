#!/bin/sh
# Builds the DM-404 emulator on Linux, outside this repository. DM-404 is a separate project with its own licences (see its LICENSE),
# used as an external tool: nothing of it is copied here. Output: $LAB404_DEPS/dm-404/build/qemu/qemu-system-arm
set -e
deps=${LAB404_DEPS:-$HOME/lab404-deps}
repo=https://github.com/nickpetty/dm-404.git
pin=cbccf0d
version=11.1.2
qemu_sha256=731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016
dm=$deps/dm-404
q=$dm/third_party/qemu
mkdir -p "$deps"
[ -d "$dm/.git" ] || git clone -q "$repo" "$dm"
git -C "$dm" checkout -q "$pin"
if [ ! -d "$q" ]; then
    archive=$dm/third_party/qemu-$version.tar.xz
    [ -f "$archive" ] || curl -sSfL -o "$archive" "https://download.qemu.org/qemu-$version.tar.xz"
    echo "$qemu_sha256  $archive" | sha256sum -c -
    tar -xf "$archive" -C "$dm/third_party"
    mv "$dm/third_party/qemu-$version" "$q"
fi
# Not git apply: inside the DM-404 checkout it silently skips paths outside that repository's index.
for p in "$dm"/core/qemu/patches/*.patch; do
    stamp=$q/.applied-$(basename "$p")
    [ -f "$stamp" ] && continue
    patch -d "$q" -p1 --forward --silent < "$p"
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
    for f in ff ffunicode ffsystem; do gcc -O2 -c "frontend/ThirdParty/fatfs/$f.c" -o "build/$f.o"; done
    g++ -std=c++20 -O2 tools/fatimg.cpp frontend/Source/FatImage.cpp build/ff.o build/ffunicode.o build/ffsystem.o -o build/fatimg
fi
[ -f build/internal-blank.img ] || build/fatimg create build/internal-blank.img 16384 exfat bare SP-404MKII
echo "blank drive: $dm/build/internal-blank.img"
