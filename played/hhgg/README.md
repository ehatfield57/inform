# The Hitchhiker's Guide to the Galaxy

Infocom's The Hitchhiker's Guide to the Galaxy (1984, release 59), by Douglas Adams and
Steve Meretzky. You're Arthur Dent, it's the worst day of your life, and the Earth is
about to be demolished to make way for a hyperspace bypass. Escape with Ford Prefect onto
a Vogon ship, get a babel fish into your ear, survive the poetry, and end up on the Heart
of Gold, where the Infinite Improbability Drive sends you off as Ford, Zaphod and
Trillian, among other places. The game is famously unfair, and lies to you at least once.

## Playing

    python3 ../../zplay.py hhgg.z5

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 hhgg.z5

It plays 481 commands and scores 400 out of 400 in 540 turns. A lot is random: which
scenario the Improbability Drive picks each time (and the bounces back into finished
ones), which of your senses comes back first in the dark, the Captain's poem (here the
case's word is "morphousite"), and which tool the Tree of Foreknowledge shows Marvin
asking for. With seed 2 it goes wrong early.

It was made from `../../solutions/hitchhiker.step` and `hitchhiker.txt`, checked step by
step against the game and against Infocom's source (`github.com/historicalsource/hitchhikersguide`).
Changes and additions:

- The walkthrough goes through the dark parts with whichever sense comes back (`smell`
  then `look at shadow`; `examine darkness` then `examine light`; `touch darkness` then
  `drink liquid`; `listen`), and waits where nothing works yet. Each time you hear the
  ship's star drive, `aft` (not port) leads back to the Heart of Gold.
- In the engine room, keep going `aft` past the warnings, and `look` a few times before
  the spare Improbability Generator shows up. You can't carry it with everything else:
  the walkthrough leaves the screwdriver, toothbrush, Sub-Etha device, gown and thing
  there, takes the generator to the bridge first, then fetches the tea substitute.
- The small plug goes into the plotter (`plug small plug into plotter`) after the
  dangly bit is in the tea substitute; plugging it in before you walk off with the
  plotter undoes it. The drive switch is the `generator switch`.
- The Vl'Hurg/G'Gugvunt scenario only happens after a careless remark: a command of more
  than three words that the game can't understand, once the Earth is gone. The
  walkthrough says `foozle the blue frob` on the bridge. Then: `take awl`, wait for the
  fleet to see the dog, and in the maze walk until the black particle appears (the
  third successful move) and `take particle`.
- Zaphod: `guards, don't shoot` and `trillian, shoot rifles`.
- Ford's fluff: the guide puts it on the satchel, but there it ends up inside Ford's
  satchel, which Arthur isn't allowed to open. Instead, on a later visit as Ford,
  `give fluff to arthur` after the house is demolished; it then turns up in Arthur's
  gown pocket.
- With real tea in the plotter, each idle turn in the dark moves you to the next
  destination in a fixed list, so the walkthrough waits to get the scenario it needs
  (the whale for the flowerpot, and Ford again for the fluff).
- Eat the fruit straight after leaving the sauna: then Marvin asks for the molecular
  hyperwave pincer, which lies on the bridge.
- The screening door opens when you hold both `tea` and `no tea` (take the tea, then
  `take no tea`). Drink the tea before entering the pantry: its 100 points take you
  over the 300 needed to survive Marvin's depression.
- `marvin, fix the hatch`, then wait in the access space, `give pincer to marvin`,
  `port`, `down`.

## Files

| File | |
|------|---|
| `hhgg.z5` | the game |
| `walkthrough.txt` | the whole game, 481 commands, 400/400 with `--seed 1` |
| `hhgg_walkthrough.txt` | a full transcript of the walkthrough |
| `hhgg.auto.map.pdf` | a map of the 27 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `hhgg.auto.map.json` | the map data behind it |
| `hhgg.txt` | the story, told by Arthur Dent |
