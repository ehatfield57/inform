# Adventure

The original Adventure (Colossal Cave), by Will Crowther (1976) and Don Woods (1977), in
Graham Nelson's Inform version (release 9, 2006), which follows the classic 350-point game.
You start at the end of a road beside a small brick well house and go down into the cave
to collect fifteen treasures, deal with dwarves, a pirate, a troll, a bear and a dragon,
and finally survive the cave closing. 350 points.

## Playing

    python3 ../zplay.py Advent.z5

## The walkthrough needs seed 1

    python3 ../zplay.py --script walkthrough.txt --seed 1 Advent.z5

It wins 350/350 ("Grandmaster Adventurer") in 281 commands, 277 moves. The dwarves and
the pirate act at random, and the walkthrough fights each dwarf where it turns up with seed
1. With other seeds the dwarves come at different times and places, and it falls short
(seed 4 still wins, with 330).

There was no solution file for this game. The walkthrough follows the route of Sean L.
Palmer's public-domain walkthrough for the 350-point game
(<https://rickadams.org/adventure/walkthroughs/walkthru.html>), worked through one move at
a time against this version. Palmer warns that his route can't be typed in blind because
of the random events. With a fixed seed the events are always the same, so this one can.
The changes:

- This version doesn't take room names as directions (`bedquilt`, `slab`, `reservoir`,
  `barren`, `fork`), so the walkthrough uses ordinary compass directions.
- The magic words don't work from the start: `xyzzy` did nothing until the note in the
  debris room had been read, and `plover` nothing until the Plover Room had been visited
  (`plugh` is heard at Y2 before it's first used). So the first trip goes in through the
  grate with the keys, and the pyramid is fetched after the emerald.
- The bottle starts empty: fill it at the spring. `turn on lamp`, not `on lamp`.
- Dwarves: pick up the axe the first dwarf throws, then `throw axe at dwarf` and
  `get axe` until each one dies.
- The pirate turns up early with seed 1 (at the rusty door) and takes the golden eggs.
  Saying `fee fie foe foo` brings the eggs back to the Giant Room, but that means walking
  back for them before you can pay the troll. Later, after giving the eggs to the troll,
  the words bring them back again.
- The bear chases the troll away for good: `release bear` when the troll blocks the bridge.
- The cave starts closing the moment you pick up the pirate's chest (all fifteen treasures
  found). After that the walkthrough leaves the magazine at Witt's End (1 point), waits six
  turns for the cave to close, and finishes in the repository with the dynamite
  (`get rod` from the southwest end, drop it at the northeast end, go back, `blast`).

## Files

| File | |
|------|---|
| `Advent.z5` | the game |
| `walkthrough.txt` | the full solution, 281 commands, 350/350 with `--seed 1` |
| `Advent_walkthrough.txt` | a full transcript of the walkthrough winning |
| `Advent.auto.map.pdf` | a map of the 68 rooms the walkthrough visits (drawn with `../tools/zplaymap.py`) |
| `Advent.auto.map.json` | the map data behind it |
| `Advent.txt` | the story of the game, told by the adventurer |
| `Advent.auto.json`, `Advent.auto.log`, `Advent_auto_transcript.txt` | an earlier run of the Ollama autoplayer (deepseek-v4.1-flash), which got as far as the snake in 77 turns |
