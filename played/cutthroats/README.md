# Cutthroats

Infocom's Cutthroats (1984, release 23), by Michael Berlyn and Jerry Wolper. You're a diver
on Hardscrabble Island. The night your old shipmate Hevlin is murdered, he leaves you a book
of shipwrecks with two wrecks newly marked on its map, and next morning Johnny Red invites
you into a treasure hunt with Pete the Rat and the Weasel. There are four wrecks; which one
you dive for depends on what Johnny shows you.

## Playing

    python3 ../../zplay.py cutthroats.z5

You'll need the shipwreck book that came in the game box: it gives each wreck's
position, which you have to tell Johnny before the boat sails.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 cutthroats.z5

It plays 237 commands and scores 250 out of 250. The wreck is picked at random at the
start: with seed 1 Johnny shows you a dinner plate, so the wreck is the **Leviathan** (a
shallow dive in scuba gear, for a case of rare stamps). With other seeds you get a
different wreck and this walkthrough goes wrong.

It was made from `../../solutions/cutthroats.txt` (its Leviathan part), checked step by
step. Changes and additions:

- The guide doesn't give the wreck's position (it's in the box). The Leviathan is at
  latitude 25, longitude 25, taken from Infocom's source (`events.zil`); you tell Johnny
  with `johnny, latitude 25` and `johnny, longitude 25`. Don't give him 20/25: that's
  the island itself, and he kills you for the joke.
- `close door` before `lock door with key`, and `stand` before leaving The Shanty.
- The lighthouse door is locked; the meeting happens outside it, so just wait there. Wait
  one more turn after Johnny's speech, or he's in your way.
- The scuba gear is in the closet: `take all from closet` (it has no door to open).
- Johnny asks for $500; the walkthrough takes out $600, which covers the $71 share and
  the shopping.
- On the wreck, "south" in the guide is `aft` (and "north" is `fore`).
- Seal the case with `put glob on case`; `put putty on hole` picks the wrong hole.
- On board, wait in the crew's quarters. Johnny comes to ask for the position when
  everyone's aboard; after you tell him, keep waiting and the boat sails while you sleep.

## Files

| File | |
|------|---|
| `cutthroats.z5` | the game |
| `walkthrough.txt` | the Leviathan dive, 237 commands, 250/250 with `--seed 1` |
| `cutthroats_walkthrough.txt` | a full transcript of the walkthrough |
| `cutthroats.auto.map.pdf` | a map of the 47 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `cutthroats.auto.map.json` | the map data behind it |
| `cutthroats.txt` | the story of the dive, told by the diver |
