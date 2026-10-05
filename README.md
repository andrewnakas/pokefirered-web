# Pokemon FireRed — matching build + browser target

Builds **Pokémon FireRed (USA, Europe) (Rev 1)** from the [pret decompilation][pret] and gets a
byte-identical ROM, then runs it in the browser from a file the player picks themselves.

This repository contains **code and build tooling only**. No ROM, no sprite, no tile, no sound,
nothing extracted from a cartridge. You supply your own dump; the build runs on your machine and
the browser page reads your file in your own tab.

[pret]: https://github.com/pret/pokefirered

## What you need

A ROM you dumped yourself. The build targets this one:

| | |
|---|---|
| Pokémon FireRed (USA, Europe) (Rev 1) | sha1 `dd5945db9b930750cb39d00c84da8571feebf417` |
| | md5 `51901a6e40661b3914aa333c802e24e8`, 16 777 216 bytes |

Other dumps build from the same tree with a different make target — see `upstream/*.sha1` after
setup. Rev 1 is the default here because it is what the fleet ROM is.

Linux, no root required. Needs `gcc`, `g++`, `make`, `git`, `python3`, `libpng-dev`, `curl`,
`dpkg-deb`, and `google-chrome` for the tests.

## Build it

```sh
sh tools/setup.sh                                  # toolchain + pinned decomp, ~5 min
sh tools/build.sh ~/path/to/your/pokefirered.gba   # build + byte-compare, ~1 min
```

`setup.sh` fetches ARM binutils, builds `agbcc` from source and clones the decompilation at a
pinned revision, all inside this checkout. `build.sh` runs `make compare_firered_rev1`, which
fails if the hash is wrong, and then compares the result to your file byte for byte.

## Play it

```sh
python3 tools/fetch_emulatorjs.py    # one-time: the browser runtime, 3.7 MB
python3 tools/serve.py 8585          # then open http://localhost:8585/
```

Pick your ROM on the page. It is read with the File API, checked against the sha1 of every dump
this build knows, and handed to the emulator as an in-memory blob.

**Your ROM is not uploaded.** The page also enforces that rather than only promising it: `fetch`,
`XMLHttpRequest`, `WebSocket` and `sendBeacon` are wrapped before the emulator loads and anything
aimed at another origin is refused. That is not theoretical — EmulatorJS checks
`cdn.emulatorjs.org` for updates on every load, and this page blocks it. The test asserts that
nothing cross-origin got through.

In-game saves are kept in this browser (IndexedDB, via the core's save file). The ROM is not:
reload the page and it asks for your file again.

Stock EmulatorJS 4.2.3 **destroys the battery save every time the page is left** — its
`beforeunload` fires an `exit` handler that unmounts the save filesystem. This page refuses that
one listener and does the save-out itself. `STATUS.md` §3a has the measurements, and
`tools/save_mechanism.py` reproduces both arms in about forty seconds.

Controls: arrows move, **Z** = A, **X** = B, **A**/**S** = L/R, **Enter** = Start,
**Shift** = Select. Gamepads and touch work.

## Test it

```sh
python3 tools/browser_test.py ~/path/to/your/pokefirered.gba
python3 tools/save_test.py    ~/path/to/your/pokefirered.gba
python3 tools/deep_play.py    ~/path/to/your/pokefirered.gba --minutes 7
```

`browser_test.py` runs headless Chrome, hands the ROM to the real file input, drives the game with
scripted button presses, measures the brightness of each screenshot and checks the save round-trips
through a full page reload. Audio is muted throughout. 19 checks; exit code 0 only if all pass.

`save_test.py` is the slow one and the convincing one: it mashes through the intro and the naming
screens into Pallet Town, uses the game's **own** Start → SAVE menu, closes the tab, comes back,
and checks the main menu now offers CONTINUE. ~5 minutes.

`deep_play.py` drives for several minutes and photographs the result. It asserts nothing — it
exists so a human can look at how far the thing actually got.

## What is in here

| Path | What |
|---|---|
| `tools/setup.sh` | ARM binutils + agbcc + the pinned decomp, no root |
| `tools/build.sh` | build the Rev 1 ROM and byte-compare it to yours |
| `tools/fetch_emulatorjs.py` | fetch EmulatorJS + the mGBA core (no npm needed) |
| `tools/serve.py` | threaded local server for `web/` |
| `tools/browser_test.py` | the headless test |
| `tools/save_test.py` | play to Pallet Town, use the in-game SAVE, reload, check CONTINUE |
| `tools/save_soak.py` | N cycles of leave-and-return, both with and without the EmulatorJS bug |
| `tools/save_mechanism.py` | the deterministic version of that question (see STATUS.md §3a) |
| `tools/deep_play.py` | long scripted run, screenshots only |
| `tools/cdp.py` | Chrome DevTools Protocol client, standard library only |
| `tools/pngstat.py` | PNG brightness, standard library only |
| `web/index.html` | the page: ROM picker, same-origin lockdown, save persistence |
| `STATUS.md` | hashes, versions, what was tested and what was not |

`upstream/`, `toolchain/` and `web/data/` are fetched, not committed.

## Licensing

This repository's own code is the build tooling and the page. The decompilation is pret's; the
browser runtime is [EmulatorJS](https://github.com/EmulatorJS/EmulatorJS) (GPL-3.0) with the
libretro [mGBA](https://github.com/mgba-emu/mgba) core (MPL-2.0), fetched at setup time, not
vendored. Pokémon is a trademark of its owners; this project is not affiliated with them.
