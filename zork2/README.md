# Zork II: The Wizard of Frobozz

Infocom's Zork II (release 63, 1986 printing), the middle part of the Zork trilogy. You
come down from a barrow into the domain of the Wizard of Frobozz, collect ten treasures,
and pay a demon to take the Wizard's wand. 400 points.

## Playing

    python3 ../zplay.py zork2.z3

## The walkthrough needs seed 1

    python3 ../zplay.py --script walkthrough.txt --seed 1 zork2.z3

Two things are random:

- The Carousel Room spins until the robot stops it, and the Low Room scrambles your
  compass, so every exit leads somewhere random. With seed 1 it takes four tries to get
  from the carousel to the Riddle Room (via the Marble Hall, Cool Room and Path Near
  Stream).
- The Wizard turns up at random and casts spells that start with F. With seed 1 he
  casts "Freeze!" at the top of the well, which takes ten waits to wear off.

It was made from `../solutions/zorkII.step1`, `zorkII.step2` and `zorkII.txt`, checked step
by step, and wins 400/400 in 366 moves. Things the guides get wrong for this release:

- This release has no "point": it's "wave wand at menhir" then `say "float"`.
- Use "enter curtain" in the bank: "enter light" is ambiguous with the lamp.
- From the narrow ledge, the balloon reaches the wide ledge in three waits, not four. One
  wait too many and it floats out of the volcano and you die.
- Take the red and blue spheres back out of the pile before putting them on their stands.

## Files

| File | |
|------|---|
| `zork2.z3` | the game |
| `walkthrough.txt` | the full solution, 328 commands, 400/400 with `--seed 1` |
| `zork2_walkthrough.txt` | a full transcript of the walkthrough winning |
| `zork2.auto.map.pdf` | a map of the 71 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `zork2.auto.map.json` | the map data behind it |
| `zork2.txt` | the story of the game, told by the adventurer |
