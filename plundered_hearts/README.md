# Plundered Hearts

Infocom's Plundered Hearts (1987, release 26), its one romance. You're Lord Dimsford's
daughter, sailing to the West Indies, when pirates attack: the dreaded Falcon, Captain
Nicholas Jamison, who turns out to be your father's ally against the wicked governor
Lafond. 25 points.

## Playing

    python3 ../zplay.py plundered_hearts.z5

## The walkthrough

    python3 ../zplay.py --script walkthrough.txt plundered_hearts.z5

It wins 25/25 ("Happily Ever After") in 220 commands, with any seed: nothing random gets
in its way. It was made from `../solutions/plunderedhearts.step1`, `plunderedhearts.step2`
and `plunderedhearts.txt`, checked step by step. Notes:

- In the opening, Crulley breaks in a few turns after you take the coffer, and Jamison
  hands over the missive a turn later than the guides suggest; the walkthrough's waits
  are lined up with that.
- Twice the story pauses with "Press RETURN", and the pause takes the next line of the
  walkthrough as its key press: the very first line (`get up`) goes to the title screen,
  and the extra `wait` after Davis's attack goes to the "two days later" pause.
- Leave the Lafond scene as the guides say: blow the spices at him when he gets too close.

## Files

| File | |
|------|---|
| `plundered_hearts.z5` | the game |
| `walkthrough.txt` | the full solution, 220 commands, 25/25 with any seed |
| `plundered_hearts_walkthrough.txt` | a full transcript of the walkthrough winning |
| `plundered_hearts.auto.map.pdf` | a map of the 46 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `plundered_hearts.auto.map.json` | the map data behind it |
| `plundered_hearts.txt` | the story of the game, told by the heroine |
