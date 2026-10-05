#!/usr/bin/env python3
"""Headless browser test for the web target.  Audio stays muted throughout.

    python3 tools/browser_test.py /path/to/pokefirered.gba [--show] [--secs 120]

What it actually checks, in order:

  1. the page loads with no console exception;
  2. a ROM handed to the real <input type=file> is read in the browser, and the
     sha1 computed there matches the sha1 on disk  (-> "read into memory");
  3. no network request leaves the page carrying the ROM  (-> "never uploaded");
  4. the core boots and the canvas is actually drawing  (mean luma, not just
     "no error"): black-but-running is the failure this catches;
  5. scripted button presses walk the intro -> title -> main menu -> NEW GAME,
     with a screenshot at each step, and the frames must differ from each other;
  6. the core's save file survives a full page reload through IndexedDB.

Screenshots and a report land in out/.  Exit code 0 only if every check passed.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cdp  # noqa: E402
import pngstat  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"

# libretro joypad ids
B, SELECT, START, UP, DOWN, LEFT, RIGHT, A = 0, 2, 3, 4, 5, 6, 7, 8


class Report:
    def __init__(self):
        self.rows: list[tuple[str, bool | None, str]] = []

    def add(self, name, ok, detail=""):
        self.rows.append((name, ok, detail))
        mark = {True: "PASS", False: "FAIL", None: "unverified"}[ok]
        print(f"  [{mark:>10}] {name}" + (f"  {detail}" if detail else ""), flush=True)

    @property
    def failed(self):
        return any(ok is False for _, ok, _ in self.rows)


def wait_for(fn, secs, step=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return None


def pump(tab, secs):
    """Let the emulator run wall-clock time. rAF needs real time to pass."""
    end = time.time() + secs
    while time.time() < end:
        time.sleep(0.25)
        tab.js("0")           # keeps the CDP socket warm, surfaces exceptions early


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8585)
    ap.add_argument("--cdp-port", type=int, default=9585)
    ap.add_argument("--show", action="store_true", help="run a visible browser")
    ap.add_argument("--secs", type=float, default=75.0,
                    help="seconds of gameplay to drive after boot")
    a = ap.parse_args()

    if not a.rom.is_file():
        print(f"no such ROM: {a.rom}")
        return 2
    disk_sha1 = hashlib.sha1(a.rom.read_bytes()).hexdigest()
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    rep = Report()
    print(f"ROM  {a.rom}  sha1 {disk_sha1}")

    srv = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "serve.py"), str(a.port),
         "--rom", str(a.rom)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1.0)
    base = f"http://localhost:{a.port}/index.html"
    chrome = None
    try:
        chrome = cdp.Chrome(port=a.cdp_port, headless=not a.show)
        tab = chrome.tab("about:blank")
        tab.call("Network.enable")

        # ---------------------------------------------------------------- 1
        tab.call("Page.navigate", url=f"{base}?mute=1&autostart=1")
        ready = wait_for(lambda: tab.js("!!(window.__pfr && window.__pfr.version)"), 20)
        rep.add("page loads", bool(ready))
        if not ready:
            return 1

        # ---------------------------------------------------------------- 2
        # The real path a person takes: the file picker.
        tab.set_file_input("#file", [str(a.rom.resolve())])
        page_sha1 = wait_for(lambda: tab.js("window.__pfr.sha1"), 60)
        size = tab.js("window.__pfr.size")
        rep.add("ROM read in the browser via <input type=file>",
                page_sha1 == disk_sha1,
                f"page sha1 {page_sha1} size {size}")

        # ---------------------------------------------------------------- 4
        started = wait_for(lambda: tab.js("window.__pfr.started === true"), 90)
        rep.add("mGBA core booted the ROM", bool(started))
        if not started:
            for line in tab.console()[-25:]:
                print("    | " + line)
            return 1

        vol = tab.js("window.EJS_emulator.volume === 0 || window.EJS_emulator.muted === true")
        rep.add("audio muted for the whole test", bool(vol),
                "EJS_volume=0 + chrome --mute-audio")

        # ---------------------------------------------------------------- 3
        # Ground truth from the network layer, not from the page's own claim.
        reqs = [e["params"]["request"] for e in tab.events
                if e["method"] == "Network.requestWillBeSent"]
        outbound = sorted({r["url"].split("?")[0] for r in reqs
                           if not r["url"].startswith(
                               (f"http://localhost:{a.port}/", "blob:", "data:", "about:"))})
        sending = [r for r in reqs if r.get("method") in ("POST", "PUT", "PATCH")]
        blocked = tab.js("JSON.stringify(window.__pfr.blocked)")
        blocked = json.loads(blocked or "[]")
        rep.add("ROM never leaves the page",
                not outbound and not sending,
                f"{len(reqs)} requests, all same-origin/blob; 0 POST/PUT; "
                f"{len(blocked)} cross-origin attempt(s) blocked by the page"
                + (f"; LEAKED: {outbound}" if outbound else ""))
        if blocked:
            for u in blocked:
                print(f"       blocked: {u}")

        # ---------------------------------------------------------------- 5
        # Walk the boot sequence.  FireRed: Game Freak logo -> Nidorino/Gengar
        # intro -> title screen -> main menu -> NEW GAME -> Oak's speech.
        scr = tab.js("JSON.stringify(window.__pfr.screen())")
        scr = json.loads(scr) if scr else None
        box = scr["box"] if scr and scr.get("ok") else None
        rep.add("emulator canvas is laid out", bool(box),
                f"{scr and scr['w']}x{scr and scr['h']} internal")

        shots = []

        def step(name, secs, presses=()):
            for ident, n in presses:
                for _ in range(n):
                    tab.js(f"window.__pfr.press({ident}, 110)")
                    time.sleep(0.5)
            pump(tab, secs)
            p = OUT / f"{len(shots):02d}-{name}.png"
            tab.screenshot(p)
            # measured from the screenshot, cropped to the emulator's own screen
            st = pngstat.luma(p, box)
            shots.append((name, st, p))
            print(f"    {name:<22} mean={st['mean']:<7} lit={st['lit']:<7} {p.name}",
                  flush=True)
            return st

        budget = max(20.0, a.secs)
        step("boot", min(9.0, budget * 0.12))
        step("intro", min(14.0, budget * 0.19), [(A, 2)])
        step("title", min(12.0, budget * 0.16), [(START, 2)])
        step("main-menu", min(10.0, budget * 0.13), [(A, 1)])
        step("new-game", min(14.0, budget * 0.19), [(A, 3)])
        step("oak-speech", min(16.0, budget * 0.21), [(A, 6)])

        drawing = [s for s in shots if s[1]["mean"] > 3.0]
        rep.add("the emulator screen is drawing (not a black screen)",
                len(drawing) >= 4,
                f"{len(drawing)}/{len(shots)} frames with mean luma > 3 "
                f"(measured on the screenshot: the page cannot read its own "
                f"WebGL canvas)")

        # frames must not all be identical -- that would be a stuck first frame
        hashes = {hashlib.sha1(p.read_bytes()).hexdigest() for _, _, p in shots}
        rep.add("picture changes between steps (not one frozen frame)",
                len(hashes) >= 4, f"{len(hashes)} distinct of {len(shots)} screenshots")

        lumas = [s[1]["mean"] for s in shots]
        rep.add("ran past the intro into the game's own screens",
                len(shots) == 6 and max(lumas) > 40 and lumas[-1] > 40,
                f"luma means {['%.0f' % v for v in lumas]}")

        # ---------------------------------------------------------------- 6
        # Saves.  Reaching an in-game SAVE takes a 20-minute scripted
        # playthrough, so this exercises the same machinery a level down: write
        # a known pattern into the file the mGBA core uses for the cartridge's
        # flash, persist it, then kill the tab and come back.  What is proven is
        # the round trip through IndexedDB across a real page load, which is the
        # part that breaks.  See STATUS.md for what this does NOT prove.
        seeded = tab.js("window.__pfr.seedSave(131072)", await_promise=True, timeout=60)
        rep.add("core save file written and flushed to IndexedDB",
                bool(seeded and seeded.get("len")),
                f"{seeded['path']} {seeded['len']} B sha1 {seeded['sha1'][:12]}"
                if seeded else "")
        pump(tab, 7.0)                       # let the page's own flush timer fire
        tab.js("window.__pfr.save('before-close')")
        # the state of durable storage at the moment we walk away
        before = tab.js("window.__pfr.idbSave()", await_promise=True, timeout=30)
        rep.add("save is in IndexedDB before the reload",
                bool(before and before.get("sha1")),
                f"{before and before.get('found')} {before and before.get('len')} B "
                f"sha1 {(before or {}).get('sha1', '')[:12]}")

        console_before = tab.console()
        # Leave the page the way a person does: navigate away IN THE SAME TAB,
        # which fires beforeunload.  Closing the tab over CDP can skip that, and
        # beforeunload is exactly where EmulatorJS's save-destroying exit handler
        # lives (it ends in FS.unmount("/data/saves")).  An earlier version of
        # this test closed the tab and so never exercised the path that breaks.
        tab.goto("about:blank")
        time.sleep(2.5)
        tab.goto(f"{base}?mute=1&autostart=1")
        # read durable storage BEFORE the ROM is picked: no core is running, so
        # nothing can have rewritten it between the reload and the check
        after = tab.js("window.__pfr.idbSave()", await_promise=True, timeout=30)
        rep.add("the save store is not empty after leaving the page",
                bool(after and after.get("files")),
                f"db {after and after.get('db')} files {after and after.get('files')}")
        rep.add("save survives a full page reload",
                bool(before and after and before.get("sha1")
                     and before["sha1"] == after.get("sha1")
                     and before["len"] == after.get("len")),
                f"before {(before or {}).get('sha1', 'none')[:12]} "
                f"({before and before.get('len')} B) -> "
                f"after {(after or {}).get('sha1', 'none')[:12]} "
                f"({after and after.get('len')} B)")

        tab.set_file_input("#file", [str(a.rom.resolve())])
        restarted = wait_for(lambda: tab.js("window.__pfr.started === true"), 90)
        reloaded_file = tab.js("window.__pfr.readSave()", await_promise=True, timeout=30) \
            if restarted else None
        rep.add("the core picks that save file back up",
                bool(reloaded_file and reloaded_file.get("len") == (before or {}).get("len")),
                f"{reloaded_file and reloaded_file.get('path')} "
                f"{reloaded_file and reloaded_file.get('len')} B")
        if restarted:
            pump(tab, 10.0)
            tab.js(f"window.__pfr.press({A}, 110)")
            pump(tab, 6.0)
            p = OUT / "06-after-reload.png"
            tab.screenshot(p)
            st = pngstat.luma(p, box)
            rep.add("still running after the reload", st["mean"] > 3.0,
                    f"mean luma {st['mean']}")

        # ---------------------------------------------------------------- 7
        # The path a person actually takes: no ?autostart, so EmulatorJS shows
        # its Play button and the first click is what starts the game and the
        # audio context.  Everything above runs with autostart=1, which would
        # happily hide a broken start button.
        chrome.close_tab(tab)
        tab = chrome.tab("about:blank")
        tab.call("Page.navigate", url=f"{base}?mute=1")
        wait_for(lambda: tab.js("!!(window.__pfr && window.__pfr.version)"), 20)
        tab.set_file_input("#file", [str(a.rom.resolve())])
        btn = wait_for(lambda: tab.js(
            "!!document.querySelector('.ejs_start_button')"), 90)
        rep.add("Play button appears when autostart is off", bool(btn))
        if btn:
            tab.js("document.querySelector('.ejs_start_button').click()")
            clicked = wait_for(lambda: tab.js("window.__pfr.started === true"), 90)
            rep.add("clicking Play starts the game", bool(clicked))
            if clicked:
                pump(tab, 12.0)
                p = OUT / "07-manual-start.png"
                tab.screenshot(p)
                st = pngstat.luma(p, box)
                rep.add("manual start draws a picture", st["mean"] > 3.0,
                        f"mean luma {st['mean']}")

        errs = [l for l in console_before + tab.console()
                if "[exception]" in l or "Uncaught" in l]
        rep.add("no uncaught JavaScript exception", not errs,
                errs[0][:120] if errs else "")

    finally:
        if chrome:
            chrome.kill()
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()

    print()
    (OUT / "report.json").write_text(json.dumps(
        [{"check": n, "result": ok, "detail": d} for n, ok, d in rep.rows], indent=2))
    n_pass = sum(1 for _, ok, _ in rep.rows if ok is True)
    print(f"{n_pass}/{len(rep.rows)} checks passed. "
          f"screenshots + report.json in {OUT}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
