# Infocom game player and archive

`zplay.py` is a Z-machine interpreter. `zplay_auto.py` and `zplay_llm.py` let an Ollama model
play a game, and `tools/` has helpers (`zplaymap.py`, `zrun.py`, `zobjects.py`, `zinfo.py`,
`zdiff.py`, `zgamemap.py`, ...). Story files are in `games/`, solution guides in
`solutions/`, finished games in `played/<game>/`, and Edward's own games in `originals/`.

`zilplay.py` (terminal) and `zilserve.py` (browser, with debugger and map) play games
straight from Infocom's ZIL source in `sources/`; the interpreter is the `zil/` package
(see `zil/README.md`). A game counts as working when its walkthrough gives the same
transcript as `zplay.py` on the released story file of the same release.

## Working rules

- Commit only when asked.
- `rm` and `cp` are aliased to `-i` here and hang in scripts: use `/bin/cp` and `/bin/rm -f`.
- Edward likes to run the Ollama autoplayer himself. Don't run it unless asked.
- Don't add one-game special cases to the interpreter or tools. If a game needs that
  (or can't be won, like Bureaucracy r160), say so and offer to skip it.

## "Process a game"

When asked to process a game, make `played/<game>/` look like the other folders there
(see `played/cutthroats/` or `played/borderzone/` as examples):

1. Copy the story file from `games/` into `played/<game>/` (with `/bin/cp`).
2. **`walkthrough.txt`**: one command per line, built from `solutions/<game>.*`. The
   guides are often wrong in small ways, so check every step by replaying the whole
   script from the start:

       python3 zplay.py --script walkthrough.txt --seed 1 --no-status --width 80 <story>

   Use `--seed 1` for anything random. Saves don't keep the random state, so always
   replay from the start. Blank lines in a script count as Return for key presses. It
   helps to keep a scratch script that replays the walkthrough plus a few trial commands.
   Read random answers (codes, positions) from the game's globals with `tools/zinfo.py`
   and `tools/zdiff.py --globals-only`, or from Infocom's source at
   `github.com/historicalsource/<game>`, which also has answers that came in the box.
   If there's no guide, fetch a walkthrough from the web (use curl if WebFetch only
   summarises), check it move by move, and credit it in the README. Prefer that to
   running Ollama.
3. **`<game>_walkthrough.txt`**: the full winning transcript, made with the command above
   (`> <game>_walkthrough.txt < /dev/null`).
4. **Map**: `python3 tools/zplaymap.py played/<game>/walkthrough.txt played/<game>/<game>.z5 --seed 1 --quiet`
   writes `<game>.auto.map.pdf` and `.json`. If the player never moves (Suspended), use
   `tools/zgamemap.py <story> --pdf` instead.
5. **`<game>.txt`**: a first-person novel of the game, about 3,000 words (longer is
   fine), wrapped with `fold -s -w 100`. Check every detail against the transcript; don't
   invent events the game doesn't show.
6. **`README.md`**: what the game is, how to play it (`python3 ../../zplay.py <story>`),
   how to run the walkthrough (and that it needs `--seed 1`, if so), what was changed from
   the guide, and a table of the files.

Then tell Edward the score reached, and wait to be asked before committing. End commit
messages with the Co-Authored-By line.
