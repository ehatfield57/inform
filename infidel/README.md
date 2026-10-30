# Infidel

Infocom's Infidel (1983, release 22). Your workers have drugged you and deserted you in
the desert, and you set out alone to find a lost queen's pyramid. 400 points.

## Playing

    python3 ../zplay.py infidel.z5

## The walkthrough

    python3 ../zplay.py --script walkthrough.txt infidel.z5

It wins 400/400 with any seed: the game has no random events that matter. It was made
from `../solutions/infidel.step` and `../solutions/infidel.txt`, checked step by step.
Two things the solutions only hint at: the torch starts to sputter in the Annex (re-oil it:
put it out, dip it in the jar, strike a match, light it), and the last command, opening
the sarcophagus, ends the game (as Infocom intended).

## Files

| File | |
|------|---|
| `infidel.z5` | the game |
| `walkthrough.txt` | the full solution, 246 commands |
| `infidel_walkthrough.txt` | a full transcript of the walkthrough winning |
| `infidel.auto.map.pdf` | a map of all 58 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `infidel.auto.map.json` | the map data behind it |
| `infidel.txt` | the story of the game, as told by the treasure hunter |
