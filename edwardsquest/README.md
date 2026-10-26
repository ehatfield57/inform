# Edward's Quest

An original text adventure in the style of the old Infocom games, written for Edward
and Donald.

Wicked Sir Morvane, the Raven Knight, has stolen good King Hal's crown and carried it off
to his black tower beyond the river. Every knight in the kingdom has gone after it, and not
one has come back. Nobody thinks of asking Edward the stable lad.

Donald, the king's absent-minded wizard, pops up now and then in a puff of purple smoke.
He has lost his spectacles, so his spells don't always go where he points them.

- 24 locations: the stable, a village with a tavern, smithy and chapel, a crypt, the
  Darkwood, a river ford, the Raven Knight's tower, and the castle
- A chain of puzzles worth 100 points, with characters to talk to and ask about things
- Moderately hard: you can be turned to stone, but UNDO always works

## Playing

    python3 ../zplay.py edwardsquest.z5

Or open `edwardsquest.z5` in any Z-machine player (Frotz, Gargoyle, Lectrote...).
Type `help` for how to play. If you're stuck, ask Donald about anything when he's around.

## Files

| File | |
|------|---|
| `edwardsquest.z5` | the game |
| `edwardsquest.inf` | the source, in Inform 6 |
| `build.sh` | rebuilds the game (needs `brew install inform6`) |
| `walkthrough.txt` | the full solution: no peeking! `python3 ../zplay.py edwardsquest.z5 --script walkthrough.txt --seed 1` plays it (Donald's timing is random, so it only lines up with seed 1) |
| `edwardsquest.txt` | the story of the game, as told by Edward |
