# Spellbreaker

Infocom's Spellbreaker (1985, release 63), the last part of the Enchanter trilogy. Magic
is failing all over the land, every guildmaster at the council is turned into a newt or
a frog, and a cloaked figure slips away. 600 points.

## Playing

    python3 ../zplay.py spellbreaker.z5

## The walkthrough needs seed 1

    python3 ../zplay.py --script walkthrough.txt --seed 1 spellbreaker.z5

Spellbreaker has more randomness than any of the other games here:

- Spells sometimes fail ("The casting feels wrong"). The walkthrough casts lesoch and
  throck twice where they fail with seed 1, and skips the optional yomin spell.
- The game of tag with the brown rock depends on where it moves. With seed 1:
  rock, west / rock, ne / rock, east / rock, south / rock, south / rock, east. (Use
  "rock, ne": "rock, go northeast" wastes a turn.)
- Belboz asks one of six questions. With seed 1 it's the fireworks one: Dimithio.
- In the outer vault, three jindak spells weigh the twelve cubes against each other.
  With seed 1 the powerful cube is x5.

It was made from `../solutions/spellbreaker.step` and `../solutions/spellbreaker.txt`,
checked step by step, and wins 600/600 in 489 moves. The guides leave out a few things:
you can't cast blorple while standing in one of the cube rooms (step outside first),
don't cast spells inside the carpet shop, and in the last scene the right moves after
girgol are "take 12" and "put knife in tesseract".

## Files

| File | |
|------|---|
| `spellbreaker.z5` | the game |
| `walkthrough.txt` | the full solution, 379 commands, 600/600 with `--seed 1` |
| `spellbreaker_walkthrough.txt` | a full transcript of the walkthrough winning |
| `spellbreaker.auto.map.pdf` | a map of all 67 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `spellbreaker.auto.map.json` | the map data behind it |
| `spellbreaker.txt` | the story of the game, the last of the young Enchanter's three |
