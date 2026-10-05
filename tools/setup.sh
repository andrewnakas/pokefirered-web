#!/bin/sh
# Fetch the toolchain and the pinned upstream decompilation.  Linux, no root.
#
#   sh tools/setup.sh
#
# Produces, all inside this checkout (nothing is installed system-wide):
#   toolchain/arm-bin/usr/bin/arm-none-eabi-*   ARM binutils (as, ld, objcopy, ...)
#   toolchain/agbcc-install/                    agbcc, old_agbcc, agbcc_arm, libgcc.a, libc.a
#   upstream/                                   pret/pokefirered at the pinned revision
#
# No ROM is downloaded, and no asset is copied out of this tree. See README.md.
set -e

HERE="$(cd "$(dirname "$0")/.." && pwd)"
TC="$HERE/toolchain"
mkdir -p "$TC/dl"

# Pinned revisions. Change these deliberately; the sha1 match is pinned to them.
PFR_REV=037335f4c725d7c9aecdac87066f2002b4bd7e14
AGBCC_REV=da598c1d918402c42c0c0d7128ba14567f3175e9

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }; }
need git; need make; need gcc; need g++; need python3; need dpkg-deb; need curl

# ---------------------------------------------------------------------------
# 1. ARM binutils.
#
# There is no sudo on the fleet box, so instead of `apt install
# binutils-arm-none-eabi` we download the same .deb (apt-get download needs no
# root) and unpack it into the checkout.  If you already have devkitARM or a
# system arm-none-eabi-as, set SKIP_BINUTILS=1 and it is used from PATH instead.
#
# NOTE: this package has no arm-none-eabi-gcc and no arm-none-eabi-cpp, so
# `make modern` is NOT available from it.  The agbcc build (MODERN=0) does not
# need either -- it preprocesses with the host `cc -E`.  The sha1-matching
# target is the agbcc one anyway.
# ---------------------------------------------------------------------------
if [ -z "$SKIP_BINUTILS" ] && [ ! -x "$TC/arm-bin/usr/bin/arm-none-eabi-as" ]; then
    if command -v arm-none-eabi-as >/dev/null 2>&1; then
        echo "== ARM binutils already on PATH, using those"
        SKIP_BINUTILS=1
    elif command -v apt-get >/dev/null 2>&1; then
        echo "== ARM binutils"
        ( cd "$TC/dl" && apt-get download binutils-arm-none-eabi )
        mkdir -p "$TC/arm-bin"
        dpkg-deb -x "$TC"/dl/binutils-arm-none-eabi_*.deb "$TC/arm-bin"
    else
        echo "No arm-none-eabi-as and no apt-get. Install binutils-arm-none-eabi"
        echo "or devkitARM yourself, then re-run with SKIP_BINUTILS=1."
        exit 1
    fi
fi
[ -d "$TC/arm-bin/usr/bin" ] && PATH="$TC/arm-bin/usr/bin:$PATH"
export PATH
arm-none-eabi-as --version | head -1

# ---------------------------------------------------------------------------
# 2. agbcc.  Builds clean against a modern host gcc (tested: gcc 15.2.0) with
#    no patches and no extra flags; upstream's own BASE_CFLAGS already carry
#    what gcc 14+ needs.  agbcc_arm IS required (src/librfu_intr.c).
# ---------------------------------------------------------------------------
if [ ! -f "$TC/agbcc-install/.ok" ]; then
    echo "== agbcc"
    [ -d "$TC/agbcc/.git" ] || git clone https://github.com/pret/agbcc.git "$TC/agbcc"
    ( cd "$TC/agbcc" && git checkout -q "$AGBCC_REV" && sh build.sh )
    A="$TC/agbcc"; P="$TC/agbcc-install"
    rm -rf "$P"; mkdir -p "$P/bin" "$P/include" "$P/lib"
    cp "$A/agbcc" "$A/old_agbcc" "$A/agbcc_arm" "$P/bin/"
    cp -R "$A/libc/include/." "$P/include/"
    cp -R "$A/ginclude/." "$P/include/"
    cp "$A/libgcc.a" "$A/libc.a" "$P/lib/"
    { echo "agbcc $AGBCC_REV"; gcc --version | head -1; } > "$P/.ok"
fi
cat "$TC/agbcc-install/.ok"

# ---------------------------------------------------------------------------
# 3. The decompilation.  A shallow fetch of exactly the pinned commit.
# ---------------------------------------------------------------------------
if [ ! -d "$HERE/upstream/.git" ]; then
    echo "== pret/pokefirered"
    git clone --filter=blob:none --no-checkout https://github.com/pret/pokefirered.git "$HERE/upstream"
fi
( cd "$HERE/upstream" && git checkout -q "$PFR_REV" && git log -1 --format='upstream %H %ad' --date=short )

echo
echo "setup OK.  Next: sh tools/build.sh"
