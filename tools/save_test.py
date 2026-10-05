#!/usr/bin/env python3
"""The real save test: play to the overworld, use the game's own SAVE, reload.

browser_test.py proves the core's save file round-trips through IndexedDB.
This proves the thing a player cares about: a save made from the game's own
Start menu is still there after closing and reopening the page.

    python3 tools/save_test.py /path/to/pokefirered.gba

It mashes A (with START to confirm the two naming screens) until it is in the
bedroom in Pallet Town, then drives Start -> down -> down -> SAVE -> yes, and
watches the core's .srm change.  Then it throws the tab away, comes back, and
checks the bytes in IndexedDB are the ones the game wrote.  Audio stays muted.

Screenshots in out/save/.  Exit 0 only if the game's own save survived.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import cdp  # noqa: E402
import pngstat  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "save"
B, SELECT, START, UP, DOWN, LEFT, RIGHT, A = 0, 2, 3, 4, 5, 6, 7, 8


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8587)
    ap.add_argument("--cdp-port", type=int, default=9587)
    ap.add_argument("--intro-secs", type=float, default=170.0,
                    help="seconds of A-mashing before trying to save")
    ap.add_argument("--tries", type=int, default=4)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    srv = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "serve.py"), str(a.port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    url = f"http://localhost:{a.port}/index.html?mute=1&autostart=1"
    chrome = None
    ok = False
    try:
        chrome = cdp.Chrome(port=a.cdp_port, headless=True)

        def open_game(t=None):
            # Reuse the SAME tab and navigate, rather than closing and opening a
            # new one. Closing a tab over CDP can skip beforeunload entirely, and
            # beforeunload is where EmulatorJS's save-destroying exit handler
            # lives -- a reload test that closes the tab is not testing the thing
            # a person does. See STATUS.md 3a.
            if t is None:
                t = chrome.tab("about:blank")
            t.goto(url)
            return t

        tab = open_game()
        tab.set_file_input("#file", [str(a.rom.resolve())])
        for _ in range(180):
            if tab.js("window.__pfr.started === true"):
                break
            time.sleep(0.5)
        else:
            print("core never started")
            return 1
        box = (json.loads(tab.js("JSON.stringify(window.__pfr.screen())")) or {}).get("box")
        srm = lambda: (tab.js("window.__pfr.readSave()", await_promise=True, timeout=30)
                       or {}).get("sha1")

        def press(ident, n=1, gap=0.55):
            for _ in range(n):
                tab.js(f"window.__pfr.press({ident}, 120)")
                time.sleep(gap)

        def shot(name):
            p = OUT / f"{name}.png"
            tab.screenshot(p)
            print(f"    {name:<22} mean={pngstat.luma(p, box)['mean']}", flush=True)
            return p

        # ---- intro, naming screens, into the overworld -----------------------
        print(f"mashing through the intro for {a.intro_secs:.0f}s", flush=True)
        t0 = time.time()
        i = 0
        while time.time() - t0 < a.intro_secs:
            # A advances text and picks the first menu entry; START is the only
            # way off the naming screen once letters have been entered.
            press(START if i % 9 == 8 else A, 1, 1.05)
            i += 1
        shot("00-after-intro")

        base = srm()
        print(f"srm before saving: {base and base[:12]}", flush=True)

        # ---- the game's own SAVE --------------------------------------------
        # Start menu in the bedroom, before any Pokemon: BAG / <name> / SAVE /
        # OPTION / EXIT.  Two downs lands on SAVE; A opens it, A confirms the
        # "Would you like to save the game?" / overwrite prompts.
        for attempt in range(a.tries):
            print(f"save attempt {attempt + 1}", flush=True)
            press(B, 3)                      # close whatever is open
            time.sleep(1.0)
            press(START, 1); time.sleep(1.0)
            shot(f"1{attempt}-menu")
            press(DOWN, 2, 0.6)
            shot(f"2{attempt}-on-save")
            press(A, 1); time.sleep(1.8)
            shot(f"3{attempt}-save-prompt")
            press(A, 4, 1.4)                 # yes / overwrite / "saved the game"
            time.sleep(3.0)
            shot(f"4{attempt}-after-save")
            now = srm()
            print(f"    srm now {now and now[:12]}"
                  f"{'  <- CHANGED' if now != base else '  (unchanged)'}", flush=True)
            if now != base:
                ok = True
                break
            press(B, 3)

        if not ok:
            print("the game's save never wrote flash -- look at out/save/*.png")
            return 1

        tab.js("window.__pfr.save('after-in-game-save')")
        time.sleep(2.0)
        before = tab.js("window.__pfr.idbSave()", await_promise=True, timeout=30)
        print(f"in IndexedDB: {before['len']} B sha1 {before['sha1'][:12]}", flush=True)

        # ---- leave the page and come back ------------------------------------
        # navigate away in the same tab: this fires beforeunload, which is the
        # path that destroys the save on stock EmulatorJS
        tab.goto("about:blank")
        time.sleep(3.0)
        tab = open_game(tab)
        # read durable storage before any ROM is picked, so no running core can
        # have rewritten it
        after = tab.js("window.__pfr.idbSave()", await_promise=True, timeout=30)
        same = bool(after and after.get("sha1") == before["sha1"]
                    and after.get("len") == before["len"])
        print(f"after reload : {after and after.get('len')} B "
              f"sha1 {(after or {}).get('sha1', 'none')[:12]}  "
              f"{'SAME' if same else 'DIFFERENT'}", flush=True)

        # and prove the game reads it back: CONTINUE should now be on the menu
        tab.set_file_input("#file", [str(a.rom.resolve())])
        for _ in range(180):
            if tab.js("window.__pfr.started === true"):
                break
            time.sleep(0.5)
        time.sleep(14.0)
        press(A, 2, 1.2)
        time.sleep(6.0)
        press(START, 2, 1.2)
        time.sleep(4.0)
        shot("90-menu-after-reload")
        ok = same
    finally:
        if chrome:
            chrome.kill()
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()
    print("\n" + ("PASS: a save made from the game's own menu survived a reload."
                  if ok else "FAIL: see out/save/*.png"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
