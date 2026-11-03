# Sorcerer

Infocom's Sorcerer (1984, release 4), the second part of the Enchanter trilogy. Belboz,
head of the Circle of Enchanters, has vanished, and something has taken hold of him. 400
points.

## Playing

    python3 ../../zplay.py sorcerer.z5

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 sorcerer.z5

Two puzzles use numbers the game picks at random:

- The trunk in the cellar: Belboz's journal names a creature ("Current code: dorn" with
  seed 1), and the five buttons must be pressed in that creature's colors from the
  Infotater that came in the game box. For dorn: gray, purple, black, gray, white.
- The dial door in the coal mine: your older self tells you the combination (623 with
  seed 1 and this walkthrough).

The walkthrough was made from `../../solutions/sorcerer.step1` to `.step3` and
`../../solutions/sorcerer.txt`, checked step by step. With any other seed the code and the
combination change, so it stops working partway. The Infotater isn't in the solution
files; the button order came from the game's own table of them.

## Files

| File | |
|------|---|
| `sorcerer.z5` | the game |
| `walkthrough.txt` | the full solution, 240 commands, 400/400 with `--seed 1` |
| `sorcerer_walkthrough.txt` | a full transcript of the walkthrough winning |
| `sorcerer.auto.map.pdf` | a map of all 63 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `sorcerer.auto.map.json` | the map data behind it |
| `sorcerer.txt` | the story of the game, as told by the young Enchanter |
