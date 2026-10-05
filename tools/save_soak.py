#!/usr/bin/env python3
"""Does the battery save survive leaving the page?  Asked many times, both ways.

Reproduces the `pokegold` agent's controlled experiment on this page.  No
gameplay: the mGBA core writes a .srm shortly after boot, so one cycle is ~25 s.

    boot the ROM, wait, read IndexedDB      -> {".../pokefirered.srm": 131072}
    NAVIGATE AWAY, come back, read again    -> {}   <- stock EmulatorJS destroys it

The cause is `emulator.js:1092`: a `beforeunload` listener that fires EmulatorJS's
`exit` event, whose handler ends in `FS.unmount("/data/saves")`, after which the
IndexedDB store backing that mount comes back empty.  It is a race against the
page dying, so it PASSES SOMETIMES -- which is why this runs many cycles and why
a single green run means nothing.

    python3 tools/save_soak.py ROM --cycles 6            # the shipped page
    python3 tools/save_soak.py ROM --cycles 6 --keep-ejs-unload   # the bug, on purpose
    python3 tools/save_soak.py ROM --cycles 6 --both    # both arms, same browser

Two rules this harness follows, both learned the hard way:
  * read IndexedDB on a FRESH page load with NO ROM picked. The core clobbers the
    save file on boot, and `getSaveFile()` with no argument writes before it reads.
  * ENUMERATE the databases. `indexedDB.open(name)` creates a missing database,
    which then truthfully reports itself empty -- identical to a destroyed save.

Exit 0 only if every cycle of the shipped arm kept the save.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cdp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_arm(tab, base, rom, cycles, keep, boot_secs, verbose=True):
    """One arm of the experiment. Returns a list of per-cycle dicts."""
    qs = "mute=1&autostart=1" + ("&ejsunload=keep" if keep else "")
    rows = []
    for n in range(cycles):
        # --- load the page and the ROM, let the core write its save ---
        if not tab.goto(f"{base}?{qs}"):
            rows.append({"cycle": n, "error": "navigation never completed"})
            continue
        tab.set_file_input("#file", [str(rom)])
        started = False
        for _ in range(180):
            if tab.js("window.__pfr.started === true"):
                started = True
                break
            time.sleep(0.5)
        if not started:
            rows.append({"cycle": n, "error": "core never started"})
            continue
        end = time.time() + boot_secs
        while time.time() < end:
            time.sleep(0.25)
            tab.js("0")
        tab.js("window.__pfr.save('soak')")
        time.sleep(1.5)
        before = tab.js("window.__pfr.idbSave()", await_promise=True, timeout=30) or {}

        # --- LEAVE THE PAGE. This is the step that breaks it. ---
        # Navigating away in the same tab is what fires beforeunload; closing the
        # tab over CDP can skip it entirely.
        tab.goto("about:blank")
        time.sleep(2.5)

        # --- come back, and look WITHOUT picking a ROM ---
        # goto() waits for the NEW document, so this cannot read the old page's
        # __pfr and call it a result.
        if not tab.goto(f"{base}?{qs}"):
            rows.append({"cycle": n, "error": "navigation back never completed"})
            continue
        after = tab.js("window.__pfr.idbSave()", await_promise=True, timeout=30) or {}

        kept = bool(before.get("sha1") and after.get("sha1") == before.get("sha1")
                    and after.get("len") == before.get("len"))
        rows.append({
            "cycle": n, "kept": kept,
            "before_files": before.get("files", {}), "after_files": after.get("files", {}),
            "before": (before.get("sha1") or "none")[:12],
            "after": (after.get("sha1") or "none")[:12],
            "db": after.get("db"), "databases": after.get("databases"),
        })
        if verbose:
            mark = "kept" if kept else "LOST"
            print(f"    cycle {n}: {mark:>4}  before {rows[-1]['before']} "
                  f"{before.get('files')}  ->  after {rows[-1]['after']} "
                  f"{after.get('files')}", flush=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=pathlib.Path)
    ap.add_argument("--cycles", type=int, default=6)
    ap.add_argument("--boot-secs", type=float, default=16.0)
    ap.add_argument("--keep-ejs-unload", action="store_true",
                    help="leave EmulatorJS's beforeunload in place (reproduce the bug)")
    ap.add_argument("--both", action="store_true", help="run both arms")
    ap.add_argument("--port", type=int, default=8588)
    ap.add_argument("--cdp-port", type=int, default=9588)
    a = ap.parse_args()

    srv = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "serve.py"), str(a.port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    base = f"http://localhost:{a.port}/index.html"
    rom = str(a.rom.resolve())
    chrome = None
    out = {}
    try:
        chrome = cdp.Chrome(port=a.cdp_port, headless=True)
        arms = []
        if a.both:
            arms = [("stock EmulatorJS (its beforeunload left in place)", True),
                    ("this page (that listener dropped, we do the save-out)", False)]
        else:
            arms = [("stock EmulatorJS (its beforeunload left in place)", True)] \
                if a.keep_ejs_unload else \
                [("this page (that listener dropped, we do the save-out)", False)]
        for label, keep in arms:
            print(f"\n== {label}: {a.cycles} cycles", flush=True)
            # a fresh tab per arm, so one arm's storage state cannot colour the next
            tab = chrome.tab("about:blank")
            rows = run_arm(tab, base, rom, a.cycles, keep, a.boot_secs)
            chrome.close_tab(tab)
            kept = sum(1 for r in rows if r.get("kept"))
            print(f"   -> kept {kept}/{len(rows)}", flush=True)
            out["keep" if keep else "fixed"] = rows
    finally:
        if chrome:
            chrome.kill()
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()

    outdir = ROOT / "out"
    outdir.mkdir(exist_ok=True)
    (outdir / "save_soak.json").write_text(json.dumps(out, indent=2))
    print(f"\nwritten to {outdir / 'save_soak.json'}")

    fixed = out.get("fixed")
    if fixed is None:
        return 0                     # only the deliberately-broken arm was run
    bad = [r for r in fixed if not r.get("kept")]
    print(f"shipped page: kept {len(fixed) - len(bad)}/{len(fixed)} cycles")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
