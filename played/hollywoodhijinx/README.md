# Hollywood Hijinx

Infocom's Hollywood Hijinx (1986, release 37), by Dave Anderson and Liz Cyr-Jones. Your
Aunt Hildegarde has died, and her will leaves you the whole estate (the Malibu house and
Uncle Buddy's movie studio) if you can find ten "treasures" hidden around the house and
grounds in one night. The puzzles are built out of Uncle Buddy's B-movie props: a scale
model of Tokyo with an Atomic Chihuahua, a closet that works as an elevator, a hedge maze,
a cannon, and two safes.

## Playing

    python3 ../../zplay.py hollywoodhijinx.z3

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 hollywoodhijinx.z3

It plays 446 commands and scores 150 out of 150. Two things are random:

- The song the film projector tells you to play on the piano is picked from ten. With
  seed 1 it's "Feelings" (`play feelings`).
- In the final fight, Herman grabs a random prop each turn, so which props are still
  lying around for you to throw depends on the seed.

It was made from `../../solutions/hollywood.step1` (Erik Futtrup and Twan Lintermans),
checked step by step. Changes and additions:

- The guide leaves the song as a blank; seed 1 gives "Feelings".
- Fixed a typo, `turn dail right 5`.
- Added `read plaque` at the bomb-shelter safe ("Levy, Regan, Lebling": left 4, right 5,
  left 7), so the transcript shows where the combination comes from.
- The guide's ending (`put peg in hole`, then `untie Hildegarde`) doesn't work: Herman
  pushes you away. Every prop is fake except that the third thing you hit him with knocks
  him down, whatever it is (`elevator.zil` in Infocom's source). The walkthrough throws
  the sword, the stick and the mop (Herman has taken the bag, club and clippers by then),
  then unties Hildegarde.

## Files

| File | |
|------|---|
| `hollywoodhijinx.z3` | the game |
| `walkthrough.txt` | the whole game, 446 commands, 150/150 with `--seed 1` |
| `hollywoodhijinx_walkthrough.txt` | a full transcript of the walkthrough |
| `hollywoodhijinx.auto.map.pdf` | a map of the 56 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `hollywoodhijinx.auto.map.json` | the map data behind it |
| `hollywoodhijinx.txt` | the story of the night, told by the heir |
