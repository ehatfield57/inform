# Tools for looking inside Z-machine games

These are the tools used to work out puzzles and test the autoplayer hints for Starcross,
The Lurking Horror, A Mind Forever Voyaging and Wishbringer. They work on any Z-machine
story file (best on Infocom's version 3-5 games). Every tool has `--help`.

They need `zplay.py`, so keep this folder next to it. Run them from the project folder:

    python3 tools/zrun.py --help

| Tool | What it's for |
|------|---------------|
| `zrun.py` | Play commands (from a fresh game or a save), save the result, see the room after each move, watch variables, trace what the game checks. The main tool. |
| `zobjects.py` | The object tree, one object in detail, every room with its exits, and the shortest walk between two rooms. Works on save files too. |
| `zdiff.py` | Compare two saves: which objects moved, which flags and variables changed. |
| `zstrings.py` | Dump or search all the game's text, with addresses. |
| `zdis.py` | Disassemble game code, and find where a routine or table is used. |
| `zwords.py` | List the game's dictionary or check commands against it (the autoplayer rejects unknown words). |
| `zgamemap.py` | Map a whole game from the rooms and exits stored in the story file, without playing; `--pdf` draws it with `zmap_pdf.py`. Used for Suspended, where the player never moves. |
| `amfv_codes.py` | A Mind Forever Voyaging's 512 security codes (`amfv_codes.json`). |
| `zinfo.py` | Shared library used by the others (not a command). |

## Save files

Three kinds of file all work wherever a tool takes a save:

- a save made by typing `save` while playing with `zplay.py`
- the autoplayer's `<story>.auto.sav`
- a file written by `zrun.py --save`

## How hints were tested

1. Play the first few commands and save:

       python3 tools/zrun.py wishbringer/wishbringer.z5 south wait "take envelope" --save /tmp/1.sav

2. Carry on from there, a few commands at a time, saving as you go:

       python3 tools/zrun.py wishbringer/wishbringer.z5 --from /tmp/1.sav north west west yes --save /tmp/2.sav

3. When stuck, look inside: search the text, check where things are, see what an action
   changes, read the code:

       python3 tools/zstrings.py wishbringer/wishbringer.z5 --grep troll
       python3 tools/zobjects.py wishbringer/wishbringer.z5 --save /tmp/2.sav --where "gold coin"
       python3 tools/zdiff.py wishbringer/wishbringer.z5 /tmp/1.sav /tmp/2.sav
       python3 tools/zrun.py amfv/amfv.z4 --from x.sav --trace 1234 1234

4. When the whole route works, put it in a file, one command per line, and check it in one go.
   `--moves` lists each command with the room it reached, which is what the hints quote:

       python3 tools/zrun.py wishbringer/wishbringer.z5 --script wishbringer/walkthrough.txt --quiet --moves
       python3 tools/zwords.py wishbringer/wishbringer.z5 --check wishbringer/walkthrough.txt

Use the same `--seed` throughout (the default is 1): with the same seed and the same commands
the game plays out exactly the same way, which is what makes saving and retrying reliable.

## Maps without playing

The autoplayer draws a map of the rooms it walks through. `zgamemap.py` maps every room the
story file knows about instead, straight from the game's data, with the things that start
in each room:

    python3 tools/zgamemap.py suspended/suspended.z5 --pdf     # suspended/suspended.game.map.pdf
    python3 tools/zgamemap.py zork1/zork1.z3 --no-items --pdf  # just the 111 rooms and exits

It writes `<story>.game.map.json` by default, so it never overwrites a played
`<story>.auto.map.json`. Exits that a routine decides while playing (passwords, mazes that
change) can't be read from the file, so a few connections may be missing.
