# Ballyhoo

Infocom's Ballyhoo (1985, release 97), by Jeff O'Neill. After a disappointing evening at
The Traveling Circus That Time Forgot, you stay behind and overhear that the owner's
daughter, Chelsea, has been kidnapped. You sneak into the performers' camp, deal with
lions, a gorilla, an elephant, a fat lady and a hypnotist, and unmask the kidnappers.
200 points.

## Playing

    python3 ../../zplay.py ballyhoo.z5

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 ballyhoo.z5

It wins 200/200 in 427 commands, 414 moves. It also wins with seeds 2, 5 and 8. With other
seeds (3, 4, 6, 7) it stops at 150: Comrade Thumb turns up at a different moment, and
the suitcase scene in the Blue Room needs him to have appeared first. The guide just says
"walk around until Thumb appears", which a fixed script can't do.

It was made from `../../solutions/ballyhoo.txt`, checked step by step. Almost all of it
worked as written; the changes:

- The guide's "walk around until Thumb appears" is, with seed 1, the walk from the Blue
  Room back to the Connection (w, nw, n, w); he appears there.
- The blackjack table asks whether you want another card; the walkthrough answers `yes`
  (it loses a dollar, which doesn't matter).
- `show spreadsheet` is written out as `show spreadsheet to chuckles`, and the guide's
  "wait until ..." steps are spelled out as exact `wait`s.
- Falling off the cage after recording the tape "kills" you, but the game only jokes about
  it and carries on.

## Files

| File | |
|------|---|
| `ballyhoo.z5` | the game |
| `walkthrough.txt` | the full solution, 427 commands, 200/200 with `--seed 1` |
| `ballyhoo_walkthrough.txt` | a full transcript of the walkthrough winning |
| `ballyhoo.auto.map.pdf` | a map of the 35 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `ballyhoo.auto.map.json` | the map data behind it |
| `ballyhoo.txt` | the story of the game, told by the circus-goer |
