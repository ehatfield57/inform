# Zork I

Infocom's Zork I: The Great Underground Empire (release 119, 1988 build of the 1980 game).
You start west of a white house, get in through a window, go down through a trap door, and
bring nineteen treasures back to the trophy case in the living room, past a troll, a
thief, a cyclops and the spirits at the gates of Hades. 350 points; the game ends when you
follow the map to the Stone Barrow.

## Playing

    python3 ../zplay.py zork1.z3

## The walkthrough needs seed 1

    python3 ../zplay.py --script walkthrough.txt --seed 1 zork1.z3

It wins 350/350 ("Master Adventurer") and enters the Stone Barrow in 374 commands, 399
moves. The fights with the troll and the thief are random, and so are the thief's
wanderings, so the walkthrough is built around what seed 1 does. It also wins with seed 3;
with seeds 2, 4 and 5 you die early.

It was made from `../solutions/zorkI.step2` (with `zorkI.step1` for the temple and rainbow),
checked step by step. Changes:

- The step2 guide's `TEMPLE` shortcut doesn't exist. Instead, `pray` at the altar takes
  you up to the forest, which the walkthrough uses twice to get heavy treasures home.
- `ulysses` scares the cyclops away without feeding him, so the bottle and lunch stay in
  the kitchen; only the garlic is taken (it keeps the bat away later).
- After the troll fight you're wounded; the walkthrough waits ten turns in the cyclops room
  until you're healed, before going up to the thief. Then it gives him the egg (he opens
  it) and kills him with the knife.
- Loads are heavy: the egg is fetched on a second trip, the lantern and garlic wait in the
  temple while you carry the coffin, and the trident is picked up on the last trip.
- The canary has to be taken out of the egg and put in the case separately (10 points).
- At the Entrance to Hades, the candles drop when you ring the bell: `get candles` before
  lighting them.
- On the river, grab the buoy as soon as it appears (four waits after launching) and land
  on the east beach, or the boat goes over Aragain Falls.

## Files

| File | |
|------|---|
| `zork1.z3` | the game |
| `walkthrough.txt` | the full solution, 374 commands, 350/350 with `--seed 1` |
| `zork1_walkthrough.txt` | a full transcript of the walkthrough winning |
| `zork1.auto.map.pdf` | a map of the 85 rooms the walkthrough visits (drawn with `../tools/zplaymap.py`) |
| `zork1.auto.map.json` | the map data behind it |
| `zork1.txt` | the story of the game, told by the adventurer |
| `zork1.map.json`, `zork1.map.pdf`, `zork1.sav` | a hand-drawn map and a save from earlier play |
| `zork1.auto.json`, `zork1.auto.log`, `zork1_auto_transcript.txt` | an earlier run of the Ollama autoplayer |
