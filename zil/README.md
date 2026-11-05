# ZIL interpreter

Plays Infocom's games straight from their original ZIL source code (the zips in
`sources/`), in the terminal or in the browser. The browser version lets you
watch the game's insides as you play: the source code with breakpoints and
single-stepping, every variable, the object tree, and a map that draws itself.

## Running it

**In the browser** (game, debugger and map):

    python3 zilserve.py sources/zork1-r119.zip --seed 1

This opens `http://127.0.0.1:8765/`. The main page is the game. The panel on
the right (hide it with the "panel" button) has:

- **Windows**: switches that open and close the other windows. If nothing
  opens, allow pop-ups for `127.0.0.1:8765` in the browser.
- **Now**: whether the game is waiting for you, running or paused.
- **Game**: pick any story in `sources/` and a seed, then **Start again**.

Stop the server with Ctrl-C. Use `--port` for a different port and
`--no-browser` to open the page yourself.

**In the terminal**, like `zplay.py`:

    python3 zilplay.py sources/zork1-r119.zip
    python3 zilplay.py sources/zork1-r119.zip --script played/zork1/walkthrough.txt --seed 1

`python3 zilplay.py --help` and `python3 zilserve.py --help` list every option.

## The windows

| Window | What it shows |
|---|---|
| Game (main page) | Play as usual. Up/down arrows recall earlier commands. |
| Source | The ZIL files in up to three panes. Click a line number to set a breakpoint. The left side has the call stack, the breakpoints and a routine finder (the dot next to a routine stops whenever it starts). |
| State | Locals of each routine on the call stack, all globals (changes since your last move are highlighted; ones holding objects show the object's name), the object tree, and one object's flags, properties and contents. |
| Map | Rooms you've visited, laid out by compass direction. "?" stubs are exits you haven't tried, red dashes are closed doors or locked ways, blue lines are up/down/in/out. "show all rooms" reveals the whole map. Click a room to see it in State. |

Debugger keys (Source window): **F5** continue, **F6** pause, **F10** step over,
**F11** step into, **Shift+F11** step out. Pausing while the game waits for a
command stops at the start of the next command you type.

Windows talk to each other: click a stack frame in Source to see its locals in
State; click "show in source" in State, or an object's definition, to jump
there in Source.

## Options

| Option | What it does |
|---|---|
| `--seed N` | Same random events every time. The walkthroughs in `played/` use `--seed 1`; the random numbers match `zplay.py`'s, so fights go the same way. |
| `--serial NNNNNN` | Serial number the game reports (the source doesn't record it). |
| `--zilch old\|new` | Which compiler generation to copy (see below). Normally worked out automatically. |
| `--warnings` | (zilplay) Show what the loader noticed, and which compiler generation it chose. |
| `--script FILE`, `--width`, `--no-status` | (zilplay) As in `zplay.py`. |

Saves go in `saves/` (browser) or wherever you name them (terminal). A save keeps
the game's memory, not the call stack, which is fine for Infocom games because
they save and restore from their main loop.

## Which games work

Each game we've played was checked with `python3 tools/zilcheck.py <game>`, which
plays `played/<game>/walkthrough.txt` with `--seed 1` through both `zplay.py` (on
the released story file) and `zilplay.py` (on the closest source release), then
compares the transcripts. `python3 tools/zilcheck.py --list` shows the pairings.

**Identical** (same release as our story file):

| Game | Source | Ending |
|---|---|---|
| Zork I | `zork1-r119` | 350/350 |
| Zork II | `zork2-r63` | 400/400 |
| Zork III | `zork3-mac-r15` | 7/7 |
| Infidel | `infidel-r22-s830916` | master adventurer |
| Suspect | `suspect-r14` | solved |
| Spellbreaker | `spellbreaker-r63` (needs `--zilch old`) | 600/600 |
| Hollywood Hijinx | `hollywoodhijinx-r37` | 150/150 |
| Stationfall | `stationfall-r107` | HyperAdmiral |
| The Lurking Horror | `lurkinghorror-r203` | 100/100 |
| Plundered Hearts | `plunderedhearts-r26` | 25/25 (only the serial line differs: the story file's is unreadable) |
| Trinity (version 4) | `trinity-r15` | 100/100 |
| A Mind Forever Voyaging (version 4) | `amfv-r77` | finished |

**Same release, nearly identical:** Cutthroats wins with the same rank, but one line
differs (the real game describes a loose mine ours doesn't; cause not found yet).

**Different release, the walkthrough still wins** (differences are Infocom's own
changes between releases): Starcross, Suspended, Enchanter, Hitchhiker's Guide,
Wishbringer, Ballyhoo.

**Run, but can't be checked** (the source is a different release whose timing,
puzzles or text changed, so the walkthrough drifts): Deadline, The Witness,
Planetfall, Sorcerer, Seastalker, Leather Goddesses (our story file is an early
"Release 0" build).

**Version 4** works: the game's version comes from `<VERSION EZIP>`, or from the build
(`.NEW` in the main `.zap`, as for A Mind Forever Voyaging). Version 4 brings 48 flags,
bigger objects and properties, 9-letter dictionary words with no adjective numbers,
word-sized exits, the upper window the game draws itself (shown above the text in the
terminal and in the browser's status bar), output into tables, and timed key input.

**Not yet:** version 5 games (Border Zone, Sherlock, Beyond Zork).

## How it works

The game's **data** is laid out in memory exactly as Infocom's compiler (ZILCH)
did: objects, properties, globals, tables, the dictionary and the parser's syntax
tables. That matters because Infocom's parser reads those as raw bytes. The
**routines** are not compiled: they run as trees straight from the source, and
every step keeps its file and line, which is what makes breakpoints and stepping
possible.

| File | Job |
|---|---|
| `reader.py` | Reads ZIL/MDL text into forms, lists and atoms. |
| `mdl.py` | Runs the MDL code met while loading: macros (`DEFMAC`), `DEFINE`, `%<...>`. |
| `loader.py` | Runs a game's files and records its declarations; works out the compiler generation. |
| `image.py` | Lays out the data in memory. |
| `compiler.py` | Turns routines into trees of nodes. |
| `runtime.py` | The interpreter and its built-in operations. |
| `session.py` | A game on its own thread, with the debugger, for the browser. |
| `web/` | The browser pages (`index.html` is the main page). |

### Compiler generations

ZILCH changed over the years, and a few of its habits change what a game does.
The earlier compiler (Zork III r15, 1983) and the later one (Zork I r119,
Zork II r63) differ in the order objects start in a room. The earlier one keeps
the first object defined in a container first, then the rest newest first; the
later one puts them all newest first. The loader works out which compiler built
a game from the object tree in the compiler's data assembly (`*dat.zap`) when the
zip has one, or from a `.record` file naming the compiler. Otherwise it guesses: an
older-style main file (MDL memory set-up with `<BLOAT ...>`) means the older
compiler, anything else the later one. The guess can be wrong (Spellbreaker is
older-compiler without `BLOAT`), so `--zilch` overrides it, and `zilcheck.py` tries
both when a game isn't identical. `--warnings` shows the choice and the reason.

Both generations number objects roughly in reverse order of definition (exactly, for
the older one). That matters: a direction's property number (20-31) can be mistaken
for an object number, so objects defined early, like `NOT-HERE-OBJECT`, must not get
those numbers.

Habits both generations share, all checked against the `.zap` files that come with
many sources:

- A verb's syntax lines are stored last-defined first.
- `<SET var constant>` inside a condition always counts as true.
- Two spaces typed after a full stop print as one; ". " at the end of a source
  line still prints two.
- A property written like an exit, such as `(ENTER PER MIRIN)`, is stored as an
  exit even if it isn't a direction.
- `<ITABLE BYTE n>` (old style) is n words, with n in the first byte.
- A bare `(...)` where a statement belongs runs its items in order.
- `.X` for something that isn't a local means `,X`, and `,X` for something that is
  only a local means `.X`; extra call arguments are dropped.
- A name that is never defined becomes 0 (the assembler warned "global undefined"
  and carried on); an object only named as a location, `(IN X)`, is made empty.
- Version 3 games always have the globals `HERE`, `SCORE` and `MOVES`, first.
- `W?.` is the "." word only if the dictionary has one; `A?word` is a word's
  adjective number.
- MDL code that runs while loading (macros, `DEFINE`d functions called from
  properties, `%<...>`) behaves as MDL does, including lists that share tails, and
  `.X`/`,X` that compare equal by atom.
- The later compiler's additions: a built-in `TELL` configured by `TELL-TOKENS`;
  the loops `DO`, `MAP-CONTENTS` and `MAP-DIRECTIONS` (with `(END ...)`);
  `NAME:TYPE` declarations; `VERB-SYNONYM` and friends (one part of speech only);
  `<SYNTAX GO (DUCK) ...>` (DUCK becomes a verb synonym); `<BYTE a b>` (one byte, the
  bits together); `(LENGTH STRING)` tables; `CRLF-CHARACTER`; `LAST-OBJECT` (the
  compiler fills it in); `BIT-SYNONYM`s sharing one flag.
- When a word has more meanings than its two value slots, the object meaning gives
  up its slot (its value is never used).
- Reader leniency the original MDL reader had: a `)` closes open `<...>` forms up to
  its list; a `!` ending a name is dropped.

A routine that can't be compiled (leftover code naming things the game doesn't
have, like Zork III's `I-CANDLES`) is reported as a warning and only stops the
game if it's called.
