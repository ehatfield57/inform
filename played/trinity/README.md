# Trinity

Infocom's Trinity (1986, release 15), by Brian Moriarty. A tourist on the last day of a
London holiday steps through a white door as a missile falls on Kensington Gardens, and
finds a strange land of giant toadstools whose doors open onto the sites of nuclear
explosions, ending at the first one: the Trinity test in New Mexico, 1945. 100 points.

## Playing

    python3 ../../zplay.py trinity.z4

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 trinity.z4

It wins 100/100 (rank "Tourist") in 446 commands, 442 moves. Some answers are chosen at
random when the game starts, so with another seed it goes wrong near the end. With seed 1:

- the jeep radio's dial reads **73**, so the walkie-talkie is set with `set slider to 73`
  (with other seeds it reads something else: 66, 55, 64 ...);
- the diagram on the back of the bookmark says `RD=GND`, and the line that drops out when
  you flip the breaker is the ground line, so the wire to cut is the **red** one.

To play with another seed, read the dial (`examine dial`) and the diagram (`read diagram`)
and change those two lines.

It was made from `../../solutions/trinity.step` (which matches this release, with its brass
ring on the sundial), checked step by step, with `../../solutions/trinity.txt` for background.
Notes:

- The game stops twice for "press any key": at the very start, and on the title screen
  after you step through the first white door. Each pause takes the next line of the
  walkthrough, so those two lines are just `begin`. The `wait` at the very end answers a
  last pause before the final score.
- The magpie's clues in the cottage are only hints, so the walkthrough doesn't wait for them.
- Cut the wire the turn after the countdown says "Zero minus fifteen seconds. Fourteen.
  Thirteen. Twelve. Eleven." (ten `wait`s after looking into the panel).

## Files

| File | |
|------|---|
| `trinity.z4` | the game |
| `walkthrough.txt` | the full solution, 446 commands, 100/100 with `--seed 1` |
| `trinity_walkthrough.txt` | a full transcript of the walkthrough winning |
| `trinity.auto.map.pdf` | a map of the 99 rooms the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `trinity.auto.map.json` | the map data behind it |
| `trinity.txt` | the story of the game, told by the tourist |
