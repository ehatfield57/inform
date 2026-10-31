# Planetfall

Infocom's Planetfall (1983, release 20). You're an Ensign Seventh Class scrubbing the
deck of the S.P.S. Feinstein when it blows up. Your escape pod lands on the deserted
planet Resida, where you find Floyd, a cheerful little robot, and a whole civilization
asleep in cryo-units waiting for a cure. 80 points.

## Playing

    python3 ../zplay.py planetfall.z5

## The walkthrough needs seed 1

    python3 ../zplay.py --script walkthrough.txt --seed 1 planetfall.z5

The colored lights on the comm room's panel are picked at random (yellow, then red with
seed 1, and the panel went dark after two rounds instead of the guides' three), Floyd
wanders off and comes back at random, and the laser hits or misses at random, so with
other seeds the walkthrough falls out of step.

It was made from `../solutions/planetfall.step1`, `planetfall.step2` and
`planetfall.txt`, checked step by step, and wins 80/80 in 344 commands. Notes:

- Go west into the escape pod right after the explosion: its door shuts two turns later.
- Floyd doesn't wake the moment you turn him on; he catches up with you a few rooms later.
- Drop the computer output and the fried fromitz board before taking the mini card, or
  you'll be carrying too much.
- Inside the computer it's `e`, `n`, `n` to reach the relay with the speck.
- Fire at the microbe until the laser is "very warm", then throw it over the edge.

## Files

| File | |
|------|---|
| `planetfall.z5` | the game |
| `walkthrough.txt` | the full solution, 344 commands, 80/80 with `--seed 1` |
| `planetfall_walkthrough.txt` | a full transcript of the walkthrough winning |
| `planetfall.auto.map.pdf` | a map of the 64 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `planetfall.auto.map.json` | the map data behind it |
| `planetfall.txt` | the story of the game, told by the Ensign |
