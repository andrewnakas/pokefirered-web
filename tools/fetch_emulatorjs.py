#!/usr/bin/env python3
"""Fetch the browser runtime into web/data/.

EmulatorJS 4.2.3 (GPL-3.0) plus its libretro mGBA core (MPL-2.0).  mGBA here is
itself an emscripten/WebAssembly build -- what is emulated is the Game Boy
Advance, not re-implemented in JavaScript.

We pull the two npm tarballs straight off registry.npmjs.org over HTTPS, because
this box has no node and no npm.  `npm pack @emulatorjs/emulatorjs@4.2.3` fetches
the identical files.

    python3 tools/fetch_emulatorjs.py            # into web/data
    python3 tools/fetch_emulatorjs.py --check    # just say whether it is there

web/data/ is gitignored: the runtime is a third-party binary, not our source.
"""
import argparse
import hashlib
import io
import pathlib
import shutil
import sys
import tarfile
import urllib.request

VERSION = "4.2.3"
PACKAGES = ("emulatorjs", "core-mgba")
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
# The cores we keep.  EmulatorJS picks between them at runtime: with the mgba
# report JSON carrying no `options.defaultWebGL2`, it resolves to the -legacy
# (WebGL1) build, so that one is the file actually loaded -- keep both so a
# future core report flipping that flag does not 404.
#
# The -thread- variants are deliberately skipped: they need SharedArrayBuffer,
# which needs COOP/COEP response headers, which would make this page impossible
# to open from a file:// URL or to embed in an iframe. Single-threaded mGBA runs
# a GBA at full speed on anything from the last decade.
CORE_KEEP = {"mgba-wasm.data", "mgba-legacy-wasm.data", "reports/mgba.json"}
CORE_MAIN = "mgba-legacy-wasm.data"


def fetch(pkg: str) -> bytes:
    url = f"https://registry.npmjs.org/@emulatorjs/{pkg}/-/{pkg}-{VERSION}.tgz"
    print(f"  GET {url}")
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def extract(blob: bytes, dest: pathlib.Path, strip: str, only=None) -> int:
    n = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or not m.name.startswith(strip):
                continue
            rel = m.name[len(strip):].lstrip("/")
            if only is not None and rel not in only:
                continue
            if ".." in pathlib.PurePosixPath(rel).parts:
                continue
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(m)
            if src is None:
                continue
            out.write_bytes(src.read())
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    loader = DATA / "loader.js"
    core = DATA / "cores" / CORE_MAIN
    have = loader.is_file() and core.is_file()
    if a.check:
        print("runtime present" if have else "runtime MISSING -- run tools/fetch_emulatorjs.py")
        return 0 if have else 1
    if have and not a.force:
        print(f"already present in {DATA} (use --force to refetch)")
        return 0

    if DATA.exists():
        shutil.rmtree(DATA)
    DATA.mkdir(parents=True)

    print(f"EmulatorJS {VERSION} -> {DATA}")
    blob = fetch("emulatorjs")
    n = extract(blob, DATA, "package/data")
    print(f"  {n} files")

    print(f"mGBA core {VERSION} -> {DATA / 'cores'}")
    blob = fetch("core-mgba")
    n = extract(blob, DATA / "cores", "package", only=CORE_KEEP)
    if n != len(CORE_KEEP):
        print(f"  ERROR: expected {sorted(CORE_KEEP)} in the core package, got {n} files")
        return 1
    for name in sorted(CORE_KEEP):
        f = DATA / "cores" / name
        print(f"  {name} {f.stat().st_size / 1e6:.1f} MB "
              f"sha1 {hashlib.sha1(f.read_bytes()).hexdigest()}")

    (DATA / "THIRD_PARTY.txt").write_text(
        f"EmulatorJS {VERSION} -- GPL-3.0 -- https://github.com/EmulatorJS/EmulatorJS\n"
        f"libretro mGBA core {VERSION} -- MPL-2.0 -- https://github.com/mgba-emu/mgba\n"
        "Fetched by tools/fetch_emulatorjs.py. Not part of this project's source.\n")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
