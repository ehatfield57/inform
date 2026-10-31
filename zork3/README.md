# Zork III: The Dungeon Master

Infocom's Zork III (release 15), the last part of the Zork trilogy. At the bottom of the
endless stair you face the Dungeon Master's tests. Zork III doesn't keep an ordinary
score: it measures your "potential", one point for each of 7 key deeds, and you win by
reaching the Treasury of Zork and taking the Dungeon Master's place.

## Playing

    python3 ../zplay.py zork3.z5

## The walkthrough needs seed 1

    python3 ../zplay.py --script walkthrough.txt --seed 1 zork3.z5

Zork III is full of chance: whether you find the amulet on the lake bottom, when the old
man is asleep in the Engravings Room, when the earthquake strikes and the Viking ship
sails past, when the cloaked figure appears in the Land of Shadow, and how the fight goes.
With seed 1 the old man is there on the first visit, the amulet comes up first time, the
ship passes on the first wait (with the earthquake), the figure appears on the third wait,
and four blows leave it "badly hurt and defenseless".

It was made from `../solutions/zorkIII.step` and `../solutions/zorkIII.txt`, checked step
by step, and reaches potential 7 of 7 in 293 moves. Notes:

- The Scenic Vista indicator steps every two turns. Touch the table at "II" for Room 8
  (the grue repellent) and at "III" for the Damp Passage (drop the torch there).
- In the Technology Museum, say "gold machine": there are three machines there.
- The walls in the Royal Puzzle are pushed with "push", not "press".

## Files

| File | |
|------|---|
| `zork3.z5` | the game |
| `walkthrough.txt` | the full solution, 248 commands, potential 7/7 with `--seed 1` |
| `zork3_walkthrough.txt` | a full transcript of the walkthrough winning |
| `zork3.auto.map.pdf` | a map of the 55 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `zork3.auto.map.json` | the map data behind it |
| `zork3.txt` | the story of the game, the last of the adventurer's three |
