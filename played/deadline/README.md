# Deadline

Infocom's Deadline (1982, release 22), by Marc Blank: "An INTERLOGIC Mystery", Infocom's
first detective story. Marshall Robner has been found dead in his locked library, and
everyone takes it for suicide. You're the Inspector. You arrive at the Robner estate at
8:00 in the morning and have until 8:00 in the evening to find out what really happened.
The household (Mrs. Robner, her son George, Mr. Baxter, Ms. Dunbar, the gardener McNabb
and the housekeeper Mrs. Rourke) goes about its day on a schedule whether you're watching
or not. The will is read at noon.

There's no score: you win by arresting the right people with enough evidence to convict
them.

## Playing

    python3 ../../zplay.py deadline.z5

The game came with a police dossier (interviews, the coroner's report, a floor plan) that
helps but isn't needed. `wait until 11:30`, `wait for dunbar` and `follow him` are
useful. Long waits stop when something happens and ask whether to keep waiting.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 deadline.z5

It plays 157 commands and solves the case by 1:20 pm: the jury convicts Baxter and
Dunbar. With some other seeds the fragment turns up sooner and people move at slightly
different times, so the fixed number of `y` answers below no longer lines up and the
walkthrough goes wrong (it works with seeds 3, 5, 7 and 11, but not 2 or 4).

It was made from `../../solutions/deadline.txt`, checked step by step. Changes and
additions:

- Each long wait is interrupted by events (the mailman, Baxter's car, the paperboy, the
  will reading), and each time the game asks "Do you want to keep waiting?". The
  walkthrough answers `y` the right number of times: 7 for `wait until 11:30`, 5 for
  `wait until 12:02`, 3 for `wait 10 minutes` on the balcony, 9 for `wait for baxter`.
- The mailman's envelope is opened and the letter read (not needed, but it's a clue).
- McNabb leads you to the holes with one `follow him`; a second one walks you away.
- `dig around holes` finds the fragment at random, but always by the third dig
  (`actions.zil` in Infocom's source, `github.com/historicalsource/deadline`). The
  walkthrough examines the ground and digs twice.
- `wait until 12:02` in the living room instead of plain `wait`s, so the will is read
  and Duffy brings the lab report.
- The pencil, pad, cup, envelope and letter are dropped in the library before opening the
  bookshelf. Otherwise you're carrying too much and things fall when you take the will.
- `look in safe` for the guide's "look safe", and the new will is read too.
- After `wait for dunbar`, three `follow her`s get you to the front path, where she
  drops the ticket stub.
- A final `y` shows the author's summary of the case.

## Files

| File | |
|------|---|
| `deadline.z5` | the game |
| `walkthrough.txt` | the solution, 157 commands, with `--seed 1` |
| `deadline_walkthrough.txt` | a full transcript of the walkthrough, ending with the author's summary |
| `deadline.auto.map.pdf` | a map of the 27 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `deadline.auto.map.json` | the map data behind it |
| `deadline.txt` | the story of the case, told by the Inspector |
