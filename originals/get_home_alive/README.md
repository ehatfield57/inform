# Get Home Alive

An original text adventure in the style of the old Infocom games, written for Edward
and Donald. It's based on the true story of Apollo 13, April 1970.

You are Jack Swigert, Command Module Pilot. Two hundred thousand miles from Earth,
Houston asks for a routine stir of the oxygen tanks, and then: BANG. With the command
module *Odyssey* dying, you, Jim Lovell and Fred Haise must use the lunar module
*Aquarius* as a lifeboat, and get home alive.

- Follows the real flight: "Houston, we've had a problem", copying the guidance
  alignment into Aquarius by hand, the free-return and PC+2 burns, the duct-tape
  "mailbox" that fits Odyssey's square CO2 canisters to Aquarius's round sockets, the
  14-second burn steered by the edge of the Earth and timed with an Omega watch, the
  freezing power-up of Odyssey, the wrecked service module, "Farewell, Aquarius", and
  the reentry blackout
- 8 locations in two spacecraft. A spacecraft is tiny, so the challenge comes from
  timers instead of mapping: Odyssey's oxygen running out, carbon dioxide building up,
  a burn you must stop at exactly the right second, and batteries with no amps to spare
- A chain of puzzles worth 100 points. Moderately hard: you can lose in several ways,
  but UNDO always works

## Playing

    python3 ../../zplay.py get_home_alive.z5

Or open `get_home_alive.z5` in any Z-machine player (Frotz, Gargoyle, Lectrote...).
Type `help` for how to play. Houston is on the radio everywhere. If you're stuck,
ask Jim or Fred about anything.

## Files

| File | |
|------|---|
| `get_home_alive.z5` | the game |
| `get_home_alive.inf` | the source, in Inform 6 |
| `build.sh` | rebuilds the game (needs `brew install inform6`) |
| `walkthrough.txt` | the full solution: no peeking! `python3 ../../zplay.py get_home_alive.z5 --script walkthrough.txt` plays it (the game has no randomness, so any seed works) |
| `get_home_alive.txt` | the story of the game, as told by Jack Swigert |
