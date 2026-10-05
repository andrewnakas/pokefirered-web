# pokefirered — status

_2026-10-05. Linux, no root. Everything below was run on this box._

**Done: the build is byte-identical to the staged ROM; the browser target passes 19/19 headless
checks with audio muted; and a save made from the game's own SAVE menu survives a page reload, with
the game showing CONTINUE afterwards.** What shipped for the browser is a built ROM on an emscripten
GBA core, **not** an emscripten build of the decomp — the reasons are in "The native route" below
and they are not "I ran out of time".

LeafGreen was not downloaded, so nothing here is tested against it. The same tree builds it
(`make compare_leafgreen_rev1`) and the page recognises its hashes, but **that is unverified.**

---

## 1. The matching build

| | |
|---|---|
| Upstream | `https://github.com/pret/pokefirered` |
| **Pinned revision** | **`037335f4c725d7c9aecdac87066f2002b4bd7e14`** (2026-09-26, "Audio improvements (#774)") |
| Make target | `compare_firered_rev1` (= `GAME_VERSION=FIRERED GAME_REVISION=1 COMPARE=1`) |
| Build time | ~60 s at `-j6` after the tools are built |

### Hashes

| | sha1 | md5 | bytes |
|---|---|---|---|
| Staged ROM `~/decompfleet/roms/pokefirered.gba` | `dd5945db9b930750cb39d00c84da8571feebf417` | `51901a6e40661b3914aa333c802e24e8` | 16777216 |
| Built `upstream/pokefirered_rev1.gba` | `dd5945db9b930750cb39d00c84da8571feebf417` | `51901a6e40661b3914aa333c802e24e8` | 16777216 |

`cmp` reports no differences. **Byte-identical, not merely same-hash.**

### Verified against upstream's documented hashes first, as asked

The staged ROM's sha1 is exactly the one in upstream's own `firered_rev1.sha1` at the pinned
revision. **No mismatch, nothing patched around.** For the record, all six targets upstream
documents, and which one the fleet ROM is:

```
dd5945db9b930750cb39d00c84da8571feebf417  pokefirered_rev1.gba    <- the staged ROM
41cb23d8dccc8ebd7c649cd8fbb58eeace6e2fdc  pokefirered.gba          (rev 0)
baa452d0b24629dd7782cfc07a8984085dde1311  pokefirered_switch.gba   (REVISION=10)
7862c67bdecbe21d1d69ce082ce34327e1c6ed5e  pokeleafgreen_rev1.gba
574fa542ffebb14be69902d1d36f1ec0a4afd71e  pokeleafgreen.gba
62b9fc77549dbc67032eb6cbd0ea6ad3b825690f  pokeleafgreen_switch.gba
```

So the matching target is the rev1 one, as the task said — the default `make` target would have
produced the rev-0 ROM and compared against the wrong hash.

### Toolchain

| Piece | Version | Where it came from |
|---|---|---|
| agbcc | `da598c1d918402c42c0c0d7128ba14567f3175e9` (pret/agbcc, 2026-01-20) | built from source here |
| host compiler for agbcc | gcc (Ubuntu 15.2.0-16ubuntu1) **15.2.0** | system |
| ARM binutils | **2.45.50.20251209-1ubuntu1+23build1** | `apt-get download binutils-arm-none-eabi` + `dpkg-deb -x` (no root) |
| make | GNU Make 4.4.1 | system |
| libpng | 1.6.57-1 (`libpng-dev`) | system, for `gbagfx`/`rsfont` |
| python | 3.14.4 | system |

agbcc binaries as installed (`~/decompfleet/shared/agbcc-install`, shared with the pokeruby agent):

```
2879a669aa0059ccf9ff672a856d1e84061ec20c  bin/agbcc
bf57ac04c2ab11324c4c967d52dd1a07fdf94ca6  bin/agbcc_arm
73d003e6de3f8f4f0a5b8f63b6bf70f580388491  bin/old_agbcc
b3969bb1ffbe48071073e9c1b58d7807c63ebd41  lib/libc.a
c61ad82531caa6e661ba0aadafc898b86e128793  lib/libgcc.a
```

### agbcc: what actually happened

Written up in full at `~/decompfleet/shared/agbcc-notes.md` for the pokeruby agent. The short
version, because it is the opposite of what the Windows notes predicted:

- **`sh build.sh` worked on the first try, unmodified, against gcc 15.2.0.** Zero errors, no
  patches, no CFLAGS overrides, no `-fcommon`, no sanitizer flags, ~2 minutes. Upstream's own
  `BASE_CFLAGS` already carries `-std=gnu11 -Werror-implicit-function-declaration
  -Wno-error=incompatible-pointer-types`, which is exactly what a modern gcc needs to compile
  GCC-2.95-era sources. The `gcc_arm` `./configure --target=arm-elf --host=i386-linux-gnu` step
  also worked unchanged.
- **None of the pain in `/mnt/d/n64work/pokeemerald-cleanroom/docs/PLATFORM_GAME_BOY_ADVANCE.md`
  applies on Linux** — the zig-cc UBSan trip on `obstack.c`, the `-j2` race on `genrtl.h`, the
  `CPP='clang -E'` for libc `.s`, the `.exe`/no-extension collision, building libpng and zlib from
  source. All of it is Windows/zig-specific. I read that document early as instructed and the
  correct conclusion from it was "do not do any of this here."
- **`agbcc_arm` IS needed.** The Windows notes say the pret GBA games do not use it and skip it;
  pokefirered's Makefile line 287 compiles `src/librfu_intr.c` with it. Skipping it fails the link.
- The prebuilt agbcc at `/mnt/d/n64work/pokeemerald/agbcc` is a **Windows** build (`.exe`) and was
  not used, as instructed.
- There is **no sudo** on this box and **no `arm-none-eabi-*` anything** preinstalled. The
  `apt-get download` + `dpkg-deb -x` route needs no root. Note that package ships **no
  `arm-none-eabi-gcc` and no `arm-none-eabi-cpp`**, so `make modern` is not available from it —
  irrelevant here, since the matching build is the agbcc one.

### Reproducing

```sh
sh tools/setup.sh
sh tools/build.sh ~/decompfleet/roms/pokefirered.gba
```

---

## 2. The browser target

**Shipped: the matching ROM running on an emscripten build of mGBA (libretro core, via EmulatorJS
4.2.3), with the player supplying their own ROM.** `web/index.html`, served by `tools/serve.py`.

- The player picks their file with a real `<input type="file">` (or drops it on the page). It is
  read with the File API into an `ArrayBuffer`, sha1'd in the page with Web Crypto, identified
  against the six dumps upstream documents, and handed to the core as a `blob:` URL.
- **Never uploaded, and the page enforces it.** `fetch`, `XMLHttpRequest.open`, `WebSocket` and
  `navigator.sendBeacon` are wrapped before the emulator loads; anything aimed at another origin is
  refused and recorded in `window.__pfr.blocked`. This caught a real one: **EmulatorJS fetches
  `https://cdn.emulatorjs.org/stable/data/version.json`** (`src/emulator.js:181`). Correcting my
  own first description of this: it is **not** unconditional. `emulator.js:207` gates it on
  `this.debug || hostname in (localhost, 127.0.0.1)` — so it fires in a local test and not on a
  deployed page, which is the worse way round, because it is invisible in production and noisy in
  the thing you are grading. (Thanks to `pokegold` for catching that.) It carries no
  ROM, but a page holding someone's cartridge dump has no business talking to a CDN, and now it
  cannot. The test asserts at the network layer — CDP
  `Network.requestWillBeSent`, not the page's own say-so — that nothing cross-origin got through.
  `EJS_CacheLimit = 0` also stops EmulatorJS copying the ROM into IndexedDB; the ROM lives in tab
  memory for the session and nowhere else.
- **Saves persist** — see §3a, which corrects an earlier false pass on exactly this point. The
  core's save file is on emscripten's IDBFS at `/data/saves/mGBA/pokefirered.srm` (131072 B = the
  cartridge's 128 KB flash). Two traps, both of which this page now works around:
  - EmulatorJS names the save after `EJS_gameName`, falling back to the ROM's filename — and a
    `blob:` URL's "filename" is a fresh UUID on every load, so without an explicit `EJS_gameName`
    the save lands under a new name each time and looks lost. Fixed to `"pokefirered"`.
  - **Stock EmulatorJS 4.2.3 destroys the save when the page is left.** `emulator.js:1092`
    registers a `beforeunload` listener that fires its `exit` event, and that handler ends in
    `FS.unmount("/data/saves")`, after which the IndexedDB store behind that mount is empty. The
    page now refuses that one registration and does the save-out itself. §3a has the measurements.
- Keyboard, gamepad and EmulatorJS's touch pad all work (keyboard and the headless gamepad path are
  what the test drives; touch is **unverified**, no touch device here).
- Runtime is fetched by `tools/fetch_emulatorjs.py` straight off `registry.npmjs.org` over HTTPS —
  this box has no node and no npm. 3.7 MB into `web/data/`, which is gitignored: EmulatorJS 4.2.3
  (GPL-3.0) + the mGBA core 4.2.3 (MPL-2.0, core built 2025-06-14). The non-threaded cores only, so
  no SharedArrayBuffer and therefore no COOP/COEP headers needed — the page works from a plain
  static server and inside an iframe.

```
1e1897dc019879e1749457d985006b57672289db  web/data/cores/mgba-legacy-wasm.data   (the one actually loaded)
c865339bf2be61fb74ebc31c3f839c04a7585114  web/data/cores/mgba-wasm.data
```

(EmulatorJS picks the `-legacy` WebGL1 core here because the mGBA core report ships an empty
`options` object, so `options.defaultWebGL2` is undefined and its `legacy` flag goes true. Both are
fetched so a future core report flipping that does not 404.)

### The native route — why this is not an emscripten build of the decomp

I was asked to try that first. I did, and it does not exist for FireRed. Three independent reasons,
any one of which is enough:

1. **There is no native or wasm target upstream, and no mature fork.** `pret/pokefirered` at the
   pinned revision has zero mentions of emscripten, emcc, wasm or SDL in its Makefile, `*.mk`,
   `INSTALL.md`, `README.md` or `docs/`. Its only targets are GBA ROMs. The sibling game is much
   further along — `pokeemerald` has `pokeemerald-native`, `pokeemerald-sdl2pc`,
   `pokeemerald-multiplatform` and `pokeemerald-wasm` — but FireRed has exactly one rehost,
   [`xinpw8/pokefirered-native`](https://github.com/xinpw8/pokefirered-native) (0 stars, last pushed
   2026-04-02). By its own HANDOFF.md it reaches the title screen and Oak's speech and then **stops
   early in overworld initialisation**, with **no audio (m4a unimplemented), no save/flash, and
   incomplete rendering**. That is behind what the emulator route already does, and shipping it
   would be shipping something that cannot be played.
2. **It would not survive the port to wasm anyway.** That rehost maps the GBA address space with
   `mmap()` at fixed addresses (EWRAM, IWRAM, I/O, palette, VRAM, OAM). wasm has no `mmap` and no
   fixed-address memory, so the whole memory model would have to be rewritten. The game itself
   touches **463 distinct `REG_*` hardware registers**, 16 distinct BIOS SWI calls
   (`LZ77UnCompVram`, `CpuFastSet`, `BgAffineSet`, `ArcTan2`, `SoftReset`, …), raw addresses at
   `0x4000000`/`0x5000000`/`0x6000000`/`0xE000000`, and one translation unit that must be compiled
   as ARM rather than Thumb (`src/librfu_intr.c`, via `agbcc_arm`). Standing that up means writing
   a GBA PPU, DMA engine, interrupt controller, BIOS and flash emulator — i.e. most of a GBA
   emulator, which is what mGBA already is.
3. **It would break the fleet's own rule.** The deliverable is a page where the user supplies their
   own ROM. A wasm build of the decomp has every sprite, tilemap and string baked into the binary,
   because the pret clone is itself a dirty tree. That is redistributing the game, which is exactly
   what "the user supplies their own ROM, read into memory, never uploaded" exists to avoid. The
   emulator route is not a compromise on this point; it is the only route that satisfies it.

So: **ROM on a wasm GBA core, deliberately.** The wasm here is a real emscripten build — of mGBA,
not of the decomp. I am using the precise words on purpose.

---

## 3. What I actually tested

`python3 tools/browser_test.py ~/decompfleet/roms/pokefirered.gba` — headless Chrome
151.0.7922.108, software GL (ANGLE/SwiftShader), **audio muted two ways** (`EJS_volume = 0` and
Chrome's `--mute-audio`). **19 of 19 checks passed.** Screenshots and `report.json` in `out/`.

| Check | Result |
|---|---|
| page loads | PASS |
| ROM read in the browser via the real `<input type=file>`; page-computed sha1 == on-disk sha1 | PASS |
| mGBA core booted the ROM | PASS |
| audio muted for the whole test | PASS |
| ROM never leaves the page (22 requests, all same-origin/blob, 0 POST/PUT, 1 cross-origin attempt blocked) | PASS |
| emulator canvas laid out (960x596) | PASS |
| the emulator screen is drawing, not black (6/6 frames mean luma > 3) | PASS |
| picture changes between steps (6 distinct screenshots) | PASS |
| ran past the intro into the game's own screens (luma means 25, 76, 84, 92, 174, 186) | PASS |
| core save file written and flushed to IndexedDB | PASS |
| save is in IndexedDB before the reload | PASS |
| **save survives a full page reload** (`7e6591cd465c`, 131072 B, identical before and after) | PASS |
| the core picks that save file back up | PASS |
| the save store is not empty after leaving the page | PASS |
| still running after the reload | PASS |
| Play button appears when `autostart` is off (the path a person actually takes) | PASS |
| clicking Play starts the game | PASS |
| manual start draws a picture (mean luma 60) | PASS |
| no uncaught JavaScript exception | PASS |

**Played, not just booted.** I looked at the screenshots. The run goes Game Freak logo → intro →
title → main menu (the CONTROLS help screen is legible: "The various buttons will be explained in
the order of their importance.") → NEW GAME → Professor Oak on screen saying **"Hello, there! Glad
to meet you!"**. That is past the intro and inside the game's own scripted opening, driven by
simulated button presses.

## 3a. Correction: the first save result was a false pass

**The "save survives a full page reload — PASS" in an earlier version of this file was not
trustworthy, and I am recording that rather than quietly replacing it.** The `pokegold` agent
found that stock EmulatorJS 4.2.3 destroys the battery save whenever the page is left
(`emulator.js:1092` registers a `beforeunload` that fires `exit`; `GameManager`'s exit handler
ends in `FS.unmount("/data/saves")`, and the IndexedDB store behind that mount comes back empty).
The coordinator asked me to re-check. I was exposed, on two counts.

**Count one: my test never exercised the path that breaks.** It ended the first session with
`chrome.close_tab()` — a CDP `/json/close` — which can tear the target down without running
`beforeunload` at all. So the listener that does the damage never fired in my test. The claim was
about what happens when a person leaves the page; the test measured something else.

**Count two, and this is the part worth passing on: fixing count one is not enough.** I rebuilt
the test to navigate away in the same tab, which does fire `beforeunload`, and ran the controlled
experiment 8 times per arm. The broken page passed all eight:

| how the question is asked | stock EmulatorJS (`?ejsunload=keep`) | this page |
|---|---|---|
| navigate away, come back, read IndexedDB — 8 cycles | **kept 8/8** | kept 8/8 |
| `dispatchEvent(new Event("beforeunload"))`, then read | **DESTROYED** | intact |

Eight clean runs of the realistic experiment, on a page I can prove is broken. The real unload is
a race the page usually wins in headless Chrome — the tab dies before the unmount's IndexedDB
writes land. `pokegold` saw 3 failures in 5; I saw 0 in 8. **Same bug, and the user-visible
experiment is a bad detector of it.** Had I only run that, I would have concluded trap 10 did not
apply to mGBA and shipped the bug with a green test above it.

What settles it is dispatching the event instead of navigating, so nothing races
(`tools/save_mechanism.py`, ~40 s, deterministic). On the stock arm:

```
after boot          files={'/data/saves/mGBA/pokefirered.srm': 131072}   mount={mounted:True, autoPersist:True}
dispatch beforeunload
after beforeunload  files={}                                            mount={mounted:True, autoPersist:False}
-> save destroyed by beforeunload: YES
```

On this page, same script, same browser:

```
after beforeunload  files={'/data/saves/mGBA/pokefirered.srm': 131072}   mount={mounted:True, autoPersist:True}
-> save destroyed by beforeunload: no
```

`autoPersist` flipping to `false` is the fingerprint: the IDBFS mount has been torn down and the
store behind it emptied. Calling `EJS_emulator.callEvent("exit")` by hand empties the store on
**both** arms — so the fix is not "make exit safe", it is "never let `beforeunload` reach `exit`".

**The fix**, in `web/index.html`: wrap `window.addEventListener` before `data/loader.js` is
injected and refuse any `beforeunload` registration not marked `__keep`, then register our own,
which writes the core's SRAM to the FS and `syncfs`es it to IndexedDB and **never unmounts**.
Two supporting changes came out of the same review:

- `getSaveFile()` with no argument calls `saveSaveFiles()` first, writing the core's *current*
  SRAM over the file. Called after a reload, before the core has loaded the restored save, it
  overwrites a good save with blanks and then reports the blanks. Every read now passes `false`.
- Every flush is gated on `savesAlive()`, because `syncfs` on a path that is no longer an IDBFS
  mount makes emscripten's reconcile *delete* the remote entries — a "flush" that wipes the save.

**Two controls, because a two-arm comparison is worthless if the arms are the same.** The arms here
are one query parameter apart, so `save_mechanism.py` asserts the fixed arm logs that it dropped
the listener and the stock arm does not — it does. And `tools/cdp.py` grew a `goto()` that waits
for the new document: after `Page.navigate`, `Runtime.evaluate` still answers from the **old**
document for a moment, so "poll until `window.__pfr` exists" returned true against the page I was
trying to leave. That cost a debugging cycle before I spotted it.

Reproduce:

```sh
python3 tools/save_mechanism.py ROM --keep-ejs-unload   # the bug, deterministically
python3 tools/save_mechanism.py ROM                     # the shipped page
python3 tools/save_soak.py ROM --cycles 8 --both        # the weak test, both arms
```

Everything in §3 below was re-run after the fix: **19/19** (the new check is "the save store is not
empty after leaving the page"), and the in-game save round trip was re-run end to end.

### An in-game save, made and reloaded

`python3 tools/save_test.py ~/decompfleet/roms/pokefirered.gba --intro-secs 150` — **PASS**, first
attempt. Screenshots in `out/save/`. Re-run after the §3a fix, and re-run again after changing the
test to **navigate away in the same tab** rather than close it, so the `beforeunload` that destroys
the save on stock EmulatorJS actually fires. Numbers below are from that last run:

1. Scripted A-mashing (with START to clear the two naming screens) reaches the **overworld** —
   the bedroom in Pallet Town, player sprite on the rug, 113 s in by the `deep_play.py` log.
2. Start → down → down → **SAVE** → YES. The screenshots show the game's own save panel
   (PALLET TOWN / PLAYER AAAAA / BADGES 0 / TIME 0:00) over **"Would you like to save the game?"**,
   then **"AAAAA saved the game."** (the player name is A-repeated because A-mashing typed it.)
3. The core's `.srm` changed `7e6591cd465c` → `3262ce2eb6ba` at exactly that moment, and nowhere
   else in the run — so it is the game writing flash, not the emulator churning.
4. Flushed to IndexedDB as `78badf6bbb5f`, 131072 B. **Navigated away** (firing `beforeunload`),
   came back: IndexedDB still holds `78badf6bbb5f`, 131072 B, **identical**.
5. ROM picked again, and the game's own main menu now reads **CONTINUE / PLAYER AAAAA /
   TIME 0:00 / BADGES 0** above NEW GAME.

Step 5 is the claim that matters: the game read its own save back after a reload. Not inferred
from a file hash — photographed.

Two measurement traps found and fixed, worth keeping:

- **The page cannot read its own canvas.** A first version measured brightness with `drawImage` on
  the emulator's canvas and reported a perfect black screen — mean luma 0.00 on every frame — while
  the game was plainly running. The WebGL context has no `preserveDrawingBuffer`, so the buffer is
  empty by the time JS looks. The screenshot Chrome takes is the ground truth. `tools/pngstat.py`
  decodes it with nothing but the standard library (validated pixel-for-pixel against PIL), and the
  test crops to the canvas rect so page chrome is not scored as "picture".
- **The save comparison was a race.** Comparing the live FS copy before and after a reload failed
  (same length, different sha1) because the core rewrites the flash image within seconds of boot.
  The test now reads emscripten's IDBFS IndexedDB database directly, **before the ROM is picked on
  the second load**, so nothing can have touched it in between.

### What I did NOT test

- **Battles, and anything past the first room.** Verified as far as the bedroom in Pallet Town and
  the game's save menu. I have not walked outside, caught anything, or fought anything. **Not
  play-tested as a game**, only driven far enough to prove the pieces work.
- **That the save is *correct*, as opposed to persistent.** The game reloads it and shows CONTINUE
  with the right name and badge count, which is strong; I did not continue from it and compare the
  world state.
- **Sound.** Deliberately never enabled, per the fleet rules. Whether audio is correct is unknown.
- **Touch input and real mobile devices.** EmulatorJS's virtual pad is enabled; nothing here has a
  touchscreen.
- **LeafGreen.** Not downloaded. Not built, not run, not hashed.
- **The rev-0 and Switch FireRed targets.** Not built. The page recognises their hashes and would
  boot them; the *build* side is untested for them.
- **Other browsers.** Chrome only. No Firefox or Safari here.
- **A fresh machine.** `tools/setup.sh` is the recipe I actually ran, but reassembled into a script
  afterwards; it has not been run end-to-end from an empty directory.

---

## 4. Proposed catalog entry

Fragment only — **I have not touched `src/data/games.json`**, per the rules. Note `mode`/`kind`
differ from the cleanroom entries: this one needs the player's own ROM.

```json
{
  "id": "pokemon-firered",
  "title": "Pokémon FireRed",
  "aliases": ["pokefirered", "pokemon firered", "firered", "fire red"],
  "year": 2004,
  "genre": "RPG",
  "kind": "Decompilation",
  "mode": "embed",
  "engine": "the pret/pokefirered decompilation, built to a matching ROM and run on EmulatorJS (mGBA, WebAssembly)",
  "description": "Return to Kanto: catch, train and battle through the original 151.",
  "overview": "Pokémon FireRed built from the pret/pokefirered decompilation. The build is byte-identical to a retail (USA, Europe) (Rev 1) cartridge dump — sha1 dd5945db9b930750cb39d00c84da8571feebf417 — and runs in the browser on an emscripten build of mGBA. You supply your own ROM: it is read in your browser with the File API, checked against the hashes the decompilation documents, and handed straight to the emulator. The page blocks every cross-origin request before the emulator loads, so your file cannot leave the tab.",
  "source": "https://github.com/andrewnakas/pokefirered-web",
  "engineLicense": "pret/pokefirered; EmulatorJS GPL-3.0; mGBA core MPL-2.0",
  "assetLicense": "None distributed — the player supplies their own ROM",
  "assetRequirements": "Your own Pokémon FireRed ROM (USA, Europe) (Rev 1), sha1 dd5945db9b930750cb39d00c84da8571feebf417. Nothing is uploaded.",
  "controls": [
    "Arrow keys — D-pad",
    "Z — A",
    "X — B",
    "A / S — L / R",
    "Enter — Start",
    "Shift — Select",
    "Gamepad — any standard controller, detected automatically",
    "Touch — on-screen Game Boy Advance pad on phones and tablets"
  ],
  "saveInstructions": "Save from the in-game menu (Start, SAVE). The save is kept in this browser's storage; clearing site data removes it. Your ROM is not kept — the page asks for it again after a reload.",
  "limitations": [
    "You must supply your own ROM; none is distributed.",
    "Link cable, wireless trading and battles are not available in the browser.",
    "LeafGreen is untested.",
    "Verified as far as the first room and the in-game save menu; battles and the wider overworld have not been play-tested."
  ],
  "inputs": ["Gamepad", "Keyboard", "Touch"],
  "downloadMB": 4,
  "complete": false,
  "color": "#d2492f",
  "shelf": "decomp",
  "platform": "Game Boy Advance",
  "launch": "embed",
  "touch": true,
  "embedUrl": "https://andrewnakas.github.io/pokefirered-web/",
  "verification": {
    "status": "smoke-tested",
    "date": "2026-10-05",
    "browsers": ["Chrome 151 (headless, software GL)"],
    "scope": "19/19 headless checks plus a scripted playthrough, audio muted throughout: ROM read in-page (sha1 match), no cross-origin request, core boots, screen draws, scripted input reaches the title screen, main menu, NEW GAME, Oak's opening and the overworld, and a save made from the game's own SAVE menu survives a page reload (the game shows CONTINUE on return).",
    "playthrough": false
  },
  "image": "/images/pokemon-firered.png"
}
```

`source` and `embedUrl` are guesses — nothing has been pushed anywhere. There is no `image` yet
either; the rules forbid generating art, and a screenshot of the running build is retail pixels, so
that one is for you.

---

## 5. Notes for the next agent

- `~/decompfleet/shared/agbcc-install` is built, verified and shared. `~/decompfleet/shared/arm-bin`
  has the ARM binutils. Recipe and hashes in `~/decompfleet/shared/agbcc-notes.md`. **Do not build
  agbcc again.**
- `tools/cdp.py` is a dependency-free Chrome DevTools Protocol client (RFC 6455 by hand) — this box
  has no websocket-client, playwright or node. Reusable by any agent that needs a browser test.
  One gotcha already paid for: **`/json/new` has been PUT-only since Chrome 111**; a GET gets a 405.
- `tools/pngstat.py` is a stdlib PNG brightness reader, validated against PIL. Also reusable.
- `tools/save_mechanism.py` and `tools/save_soak.py` are the two ways to ask "did the save
  survive?", and §3a is the argument for preferring the first. If you ship a game with a battery
  save on EmulatorJS, run the mechanism test before you believe any green.
- **Three harness bugs from this session, all of which produced confident wrong answers.** Worth
  checking for in your own:
  1. `chrome.close_tab()` over CDP can skip `beforeunload` entirely, so a reload test that closes
     a tab never exercises what happens when a person leaves the page.
  2. After `Page.navigate`, `Runtime.evaluate` still answers from the **old** document for a
     moment, so "poll until my global exists" returns true against the page you are leaving.
     `cdp.Tab.goto()` puts a nonce in the URL and waits for it.
  3. `pgrep -f save_test.py` in a waiter loop **matches the waiter's own command line**, so the
     loop waits on itself forever and whatever was chained after it silently never runs. Match on
     `python3 .*save_test\.py`, or hold the PID.
- **The fleet `.gitignore` list excludes `*.md` (Mega Drive ROMs) — which would also hide STATUS.md
  and README.md.** This repo's `.gitignore` re-includes them explicitly. Check yours.
- Disk went from 22 G to 14 G free while ten agents worked. This project is 420 MB with the upstream
  clone and a full build; the committed repo is ~70 KB.

---

## 6. Shared with the other agents

- `~/decompfleet/shared/agbcc-notes.md` — the agbcc recipe, hashes, and the correction that
  someone has since added a full `arm-none-eabi-gcc` 14.2.1 to `shared/arm-bin`.
- `~/decompfleet/shared/emulatorjs-notes.md` — appended seven corrections to the orchestrator's
  section, for the NES/GBC/GBA/Genesis agents. The two that cost me time:
  `EJS_disableDatabases = true` (which that note recommends) **turns off saves**, and a `blob:`
  ROM URL **requires** an explicit `EJS_gameName` or the save file is renamed on every load and
  looks lost. Also: ship the `-legacy` core, it is the one that actually loads.
