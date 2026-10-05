#!/usr/bin/env python3
"""Drive the web build for several minutes and photograph what happens.

browser_test.py proves the thing boots, draws and keeps a save.  This goes
further: it mashes through Oak's speech and the naming screens and tries to
reach the overworld, taking a screenshot every few seconds so a human can see
how far it actually got.  It asserts nothing on its own -- "playable" is a claim
you make after looking at the pictures, not after reading an exit code.

    python3 tools/deep_play.py /path/to/pokefirered.gba --minutes 6

Audio stays muted.  Screenshots land in out/deep/.
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
OUT = ROOT / "out" / "deep"
B, SELECT, START, UP, DOWN, LEFT, RIGHT, A = 0, 2, 3, 4, 5, 6, 7, 8


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=pathlib.Path)
    ap.add_argument("--minutes", type=float, default=6.0)
    ap.add_argument("--port", type=int, default=8586)
    ap.add_argument("--cdp-port", type=int, default=9586)
    ap.add_argument("--shot-every", type=float, default=10.0)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    srv = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "serve.py"), str(a.port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    chrome = None
    log = []
    try:
        chrome = cdp.Chrome(port=a.cdp_port, headless=True)
        tab = chrome.tab("about:blank")
        tab.call("Page.navigate",
                 url=f"http://localhost:{a.port}/index.html?mute=1&autostart=1")
        for _ in range(40):
            if tab.js("!!(window.__pfr && window.__pfr.version)"):
                break
            time.sleep(0.5)
        tab.set_file_input("#file", [str(a.rom.resolve())])
        for _ in range(180):
            if tab.js("window.__pfr.started === true"):
                break
            time.sleep(0.5)
        else:
            print("core never started")
            return 1
        box = (json.loads(tab.js("JSON.stringify(window.__pfr.screen())")) or {}).get("box")
        print("core started; driving for %.1f min" % a.minutes, flush=True)

        t0 = time.time()
        end = t0 + a.minutes * 60
        next_shot = t0
        n = 0
        last_srm = None
        i = 0
        while time.time() < end:
            t = time.time() - t0
            # A advances every text box and picks the first menu entry.
            # START confirms a name on the naming screen (the one place A alone
            # will not get you out of), so sprinkle it in.
            # Once the overworld should be up (~4 min), open the menu and try
            # to find SAVE by walking down it.
            if t > 240 and i % 11 == 0:
                tab.js(f"window.__pfr.press({START}, 120)")
            elif t > 240 and i % 11 in (1, 2, 3, 4, 5):
                tab.js(f"window.__pfr.press({DOWN}, 120)")
            elif i % 9 == 8:
                tab.js(f"window.__pfr.press({START}, 120)")
            else:
                tab.js(f"window.__pfr.press({A}, 120)")
            i += 1
            time.sleep(1.1)

            if time.time() >= next_shot:
                next_shot = time.time() + a.shot_every
                p = OUT / f"{n:03d}-t{int(t):04d}s.png"
                tab.screenshot(p)
                st = pngstat.luma(p, box)
                srm = tab.js("window.__pfr.readSave()", await_promise=True, timeout=30)
                sig = (srm or {}).get("sha1")
                changed = sig != last_srm
                last_srm = sig
                row = {"t": round(t), "shot": p.name, "mean": st["mean"],
                       "srm": (sig or "")[:12], "srm_changed": changed}
                log.append(row)
                print(f"  t={int(t):4}s mean={st['mean']:<7} srm={row['srm']}"
                      f"{'  <- changed' if changed else ''}", flush=True)
                n += 1
    finally:
        if chrome:
            chrome.kill()
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            srv.kill()
    (OUT / "log.json").write_text(json.dumps(log, indent=2))
    print(f"\n{len(log)} screenshots in {OUT} -- look at them before claiming anything")
    return 0


if __name__ == "__main__":
    sys.exit(main())
