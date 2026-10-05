#!/bin/sh
# Build Pokemon FireRed (USA, Europe) (Rev 1) from the pinned decompilation and
# check the result byte-for-byte against the user's own ROM.
#
#   sh tools/build.sh [path/to/your/pokefirered.gba] [extra make args]
#
# With no ROM path the build still runs and still checks itself against
# upstream's firered_rev1.sha1 (upstream ships the expected hash; the ROM is
# only needed to prove it is YOUR dump that matches).
#
# Output: upstream/pokefirered_rev1.gba  (gitignored, never committed)
set -e

HERE="$(cd "$(dirname "$0")/.." && pwd)"
TC="$HERE/toolchain"
ROM="$1"; [ $# -gt 0 ] && shift

[ -d "$HERE/upstream/src" ] || { echo "run tools/setup.sh first"; exit 1; }
[ -f "$TC/agbcc-install/.ok" ] || { echo "run tools/setup.sh first"; exit 1; }
[ -d "$TC/arm-bin/usr/bin" ] && PATH="$TC/arm-bin/usr/bin:$PATH"
export PATH

cd "$HERE/upstream"
[ -x tools/agbcc/bin/agbcc ] || cp -R "$TC/agbcc-install" tools/agbcc

# Host tools (gbagfx, preproc, scaninc, mid2agb, ...). Needs libpng-dev.
make -f make_tools.mk -j"$(nproc)"

# GAME_VERSION=FIRERED GAME_REVISION=1 -> version 1.1, the (USA, Europe) (Rev 1)
# cartridge.  `compare_` makes the build fail if the sha1 is wrong, so a clean
# exit here already means "matched".  Revision 0 is a different ROM; revision 10
# is the Nintendo Switch Online release.
make compare_firered_rev1 -j"$(nproc)" "$@"

BUILT="$HERE/upstream/pokefirered_rev1.gba"
echo
echo "built    $(sha1sum "$BUILT")"
if [ -n "$ROM" ]; then
    echo "yours    $(sha1sum "$ROM")"
    if cmp -s "$BUILT" "$ROM"; then
        echo "MATCH: the build is byte-identical to your ROM."
    else
        echo "NO MATCH: your ROM is a different dump. Expected (USA, Europe) (Rev 1),"
        echo "  sha1 dd5945db9b930750cb39d00c84da8571feebf417.  Other revisions upstream"
        echo "  can match instead -- see upstream/*.sha1 and use that make target:"
        echo "    firered (rev 0), firered_rev1, firered_switch, leafgreen*, ..."
        exit 1
    fi
fi
