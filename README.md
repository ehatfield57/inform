# Inform: playing, studying and running Infocom's games

A workshop for the classic text adventures of the 1980s, mostly Infocom's. Everything is
written in plain Python 3 (standard library only):

- **`zplay.py`**, a Z-machine interpreter that plays the original story files.
- **Language-model players** that let a local model (through Ollama) translate plain English into commands, or play a whole game by itself.
- **Tools** for looking inside a story file: objects, rooms, text, code, dictionaries and maps.
- **A finished-game archive**: almost thirty games played to the end, each with a checked walkthrough, a full transcript, a map, a short novel of the game and notes.
- **A ZIL interpreter**: a new way to play the games, straight from Infocom's original source code. It comes with a browser debugger, so you can watch the game's code and variables while you play.

The project was built together with Claude (Anthropic's AI) in Claude Code.

---

## What's in this folder

| Path | What it is |
|---|---|
| `zplay.py` | The Z-machine interpreter: plays `.z3` `.z4` `.z5` `.z7` `.z8` and `.zblorb` story files. |
| `zplay_llm.py` | Play in plain English: a local model turns what you type into game commands, and keeps a map. |
| `zplay_auto.py` | Let a local model play a whole game by itself, with notes, hints and a map. |
| `zmap_pdf.py` | Turns a map file into a printable PDF. |
| `tools/` | Tools for looking inside story files (see `tools/README.md`), plus `zilcheck.py` for the ZIL interpreter. |
| `games/` | Story files. |
| `solutions/` | Solution guides used to build the walkthroughs. |
| `played/<game>/` | One folder per finished game (see below). |
| `originals/` | Two original games written in Inform for Edward and Donald. |
| `sources/` | Infocom's original ZIL source code, one zip per game release. |
| `zil/` | The ZIL interpreter and its browser windows (see `zil/README.md`). |
| `zilplay.py` | Play a game from its ZIL source in the terminal. |
| `zilserve.py` | Play a game from its ZIL source in the browser, with a debugger and a live map. |

Nothing needs installing beyond Python 3. Ollama (https://ollama.com) is needed only for
the two language-model players.

---

## Playing story files: `zplay.py`

    python3 zplay.py games/zork1.z3
    python3 zplay.py games/zork1.z3 --script played/zork1/walkthrough.txt --seed 1
    python3 zplay.py --help

- **Versions:** plays versions 3, 4, 5, 7 and 8. Version 6, the graphical one, isn't supported.
- **Saves:** save and restore use a small JSON file, and undo works in games that support it.
- **Scripts:** `--script` types commands from a file, and `--seed` makes random events repeat exactly. Every walkthrough here is checked that way.
- **Debug view:** while playing, `/debug` shows the current room's object tree before each prompt.

## Playing in plain English: `zplay_llm.py` and `zplay_auto.py`

    python3 zplay_llm.py games/zork1.z3          # you type English, the model types commands
    python3 zplay_auto.py games/zork1.z3         # the model plays by itself

`zplay_llm.py` sends what you type through a local model, which turns it into a command
the game's parser understands. It also draws a map of where you've been.

`zplay_auto.py` lets the model play by itself. It keeps notes, follows hints you can
edit, builds a map, and can be paused at any time so you can type commands yourself.
Several Ollama cloud models have been tried (DeepSeek, GLM, Mistral and others).

## Looking inside a game: `tools/`

| Tool | What it's for |
|---|---|
| `zrun.py` | Play commands from a fresh game or a save; watch variables; trace what the game checks. |
| `zobjects.py` | The object tree, one object in detail, every room and its exits, and the shortest route between rooms. |
| `zdiff.py` | Compare two saves: what moved, which flags and variables changed. |
| `zstrings.py` | Dump or search all the game's text. |
| `zdis.py` | Disassemble game code, and find where a routine or table is used. |
| `zwords.py` | List a game's dictionary, or check commands against it. |
| `zgamemap.py` | Map a whole game from its stored rooms and exits, without playing. |
| `zplaymap.py` | Draw a map by playing a walkthrough through the autoplayer's mapper. |
| `zilcheck.py` | Check the ZIL interpreter against a played game (see below). |

Each tool has `--help`. More in `tools/README.md`.

---

## The finished games: `played/`

Each folder in `played/` holds one game played to the end:

| File | What it is |
|---|---|
| `<story file>` | The game itself. |
| `walkthrough.txt` | One command per line, checked by replaying the whole game from the start with `--seed 1`. |
| `<game>_walkthrough.txt` | The full winning transcript. |
| `<game>.auto.map.json`, `.pdf` | A map of every room and exit on the way, and the same map as a printable PDF. |
| `<game>.txt` | A first-person novel of the game, about 3,000 words, checked against the transcript. |
| `README.md` | What the game is, how to play it, how to run the walkthrough, and what had to change from the published solution. |

Games played so far: Zork I, II and III, Deadline, Starcross, Suspended, The Witness,
Planetfall, Enchanter, Infidel, Sorcerer, Seastalker, Cutthroats, The Hitchhiker's Guide
to the Galaxy, Suspect, Wishbringer, A Mind Forever Voyaging, Spellbreaker, Ballyhoo,
Trinity, Leather Goddesses of Phobos, Moonmist, Hollywood Hijinx, Stationfall, The
Lurking Horror, Plundered Hearts, Border Zone and Sherlock, plus Colossal Cave Adventure.

## Original games: `originals/`

Two new text adventures in the Infocom style, written in Inform for Edward and Donald:

- **Edward's Quest.** Wicked Sir Morvane, the Raven Knight, has stolen good King Hal's crown.
- **Get Home Alive.** You are Jack Swigert, Command Module Pilot of Apollo 13, April 1970.

Each comes with its Inform source, the compiled game, a walkthrough and a novel.

---

## Playing from Infocom's source code: the ZIL interpreter

Infocom wrote its games in **ZIL** (Zork Implementation Language), a language based on
MDL (an MIT Lisp dialect). A compiler called ZILCH turned them into the story files
everyone played. That compiler was never released, but much of Infocom's source code now
survives (the zips in `sources/` come from the historicalsource collection on GitHub).

This project's interpreter **runs the games straight from that source**. It reads the
ZIL, runs the macros and load-time code, lays out the game's data in memory exactly as
ZILCH did, and then runs the routines as they're written. Every step it takes is tied to
a file and line of the original source, so you can watch the code run.

### Running it

In the browser, with the debugger and map:

    python3 zilserve.py sources/zork1-r119.zip --seed 1

In the terminal, like `zplay.py`:

    python3 zilplay.py sources/zork1-r119.zip

The browser version opens a page on your own computer (`http://127.0.0.1:8765/`). The page
is the game itself; a side panel switches the other windows on and off:

| Window | What it shows |
|---|---|
| **Game** (the main page) | Play as usual, with a status line and command history. |
| **Source** | The ZIL source in side-by-side panes. Click a line number to set a breakpoint, or stop whenever a routine starts. Pause, Continue, Step over, Step into and Step out (F6, F5, F10, F11, Shift+F11), with a clickable call stack. |
| **State** | The local variables of every routine on the call stack, all the globals (changes since your last move highlighted, objects shown by name), the object tree, and any object's flags, properties and contents. |
| **Map** | The rooms you've visited, laid out by compass direction and drawn as you play, with unexplored exits, doors and locked ways marked. "Show all rooms" reveals the rest. |

All the windows show the same running game, so they can be spread over several screens.
You can also pick any story in `sources/` and a random seed from the side panel.

### How well it works

A game counts as working when its walkthrough, played from the source, gives **exactly**
the same transcript as `zplay.py` playing the released story file of the same release,
character for character, including every random event with `--seed 1`.
`tools/zilcheck.py <game>` runs that comparison.

**Identical to the released game (12 games):**

| Game | Source release | Ending reached |
|---|---|---|
| Zork I | r119 | 350/350 |
| Zork II | r63 | 400/400 |
| Zork III | r15 | 7/7 |
| Infidel | r22 | master adventurer |
| Suspect | r14 | solved |
| Spellbreaker | r63 | 600/600 |
| Hollywood Hijinx | r37 | 150/150 |
| Stationfall | r107 | HyperAdmiral |
| The Lurking Horror | r203 | 100/100 |
| Plundered Hearts | r26 | 25/25 (only the serial number line differs) |
| Trinity (version 4) | r15 | 100/100 |
| A Mind Forever Voyaging (version 4) | r77 | finished |

Other games:

- **Cutthroats** matches all but one line.
- **The walkthrough still wins from a different source release:** Starcross, Suspended, Enchanter, The Hitchhiker's Guide to the Galaxy, Wishbringer and Ballyhoo.
- **Run, but can't be checked:** Deadline, The Witness, Planetfall, Sorcerer, Seastalker and Leather Goddesses. The surviving source is a different release whose text, timing or puzzles changed.
- **Version 4 games work** (Trinity and A Mind Forever Voyaging), including the top window they draw themselves.
- **Not yet supported:** the version 5 games (Border Zone, Sherlock, Beyond Zork). That's the next step.

### What we learned about Infocom's compiler

Getting identical transcripts meant working out how ZILCH really behaved. The source zips
often include the compiler's own assembly output (`.zap` files), which settled each
question. Some of the findings:

- **Two compiler generations.** ZILCH changed in the mid-1980s. The two generations set up a room's starting contents in a different order, and number objects differently. The interpreter works out which one built a game from that game's own compiler output.
- **Rules that held across all the games:**
  - A verb's syntax lines are stored last-defined first.
  - Two spaces typed after a full stop print as one.
  - A name that's never defined becomes 0, as the assembler did.
  - Version 3 games always get `HERE`, `SCORE` and `MOVES` as their first globals.
- **The later compiler's additions:** a built-in `TELL` configured by `TELL-TOKENS`; the loops `DO`, `MAP-CONTENTS` and `MAP-DIRECTIONS`; `NAME:TYPE` declarations; and constants like `LAST-OBJECT` that the compiler fills in itself.
- **Source bugs ZILCH tolerated.** Infocom's sources contain mismatched brackets, stray statements and leftover routines from other games. ZILCH compiled them anyway, and the interpreter copies how it coped.

The full list, with the evidence for each rule, is in `zil/README.md`.

### How the code is organised

| Module | Job |
|---|---|
| `zil/reader.py` | Reads ZIL/MDL text; every form remembers its file and line. |
| `zil/mdl.py` | A small MDL evaluator for the code that runs while a game loads. |
| `zil/loader.py` | Runs a game's files and records its declarations; works out the compiler generation. |
| `zil/image.py` | Lays out objects, properties, globals, tables, the dictionary and the parser's syntax tables in memory. |
| `zil/compiler.py` | Turns routines into trees of nodes the interpreter runs. |
| `zil/runtime.py` | The interpreter and its built-in operations. |
| `zil/session.py` | A game on its own thread, with breakpoints, stepping and snapshots, for the browser. |
| `zil/web/` | The browser pages. |

---

## Notes

- **Copyright.** Infocom's games, source code and documentation remain the property of their owners. They're here for study and preservation, as in the historicalsource collection.
- **Building the archive.** `CLAUDE.md` describes the working rules and the steps for adding a finished game to `played/`.
