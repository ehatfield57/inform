# Leather Goddesses of Phobos

Infocom's Leather Goddesses of Phobos (1986), by Steve Meretzky: "a racy space-age spoof".
It's 1936, and you're drinking a nickel beer in Joe's Bar in Upper Sandusky, Ohio, when
tentacled aliens carry you off to a cell on Phobos. The Leather Goddesses are about to
invade Earth. With Trent, a fellow prisoner from Alaska who is strong as an ox and keeps
getting killed (and coming back), you jump through black circles to Venus, Mars, a
spaceship off Saturn and Cleveland, gathering the parts for Trent's Super-Duper
Anti-Leather Goddesses of Phobos Attack Machine: a blender, a rubber hose, cotton balls,
an eighty-two degree angle, a headlight, a mouse, a photo of Jean Harlow and a Cleveland
phone book.

Which bathroom you use at the start sets whether you play a man (Gents, northwest) or a
woman (Ladies, northeast). The game starts in "suggestive" mode; `lewd` and `tame`
change it. This walkthrough plays a man in suggestive mode.

This story file is a version 3 game, even though it's named `.z5`, and its header says
release 0.

## Playing

    python3 ../../zplay.py leather_goddesses_of_phobos.z5

The game came with a scratch 'n' sniff card. When it says "Scratch 'n' sniff spot number
N", just press Return and it tells you what you smelled.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 leather_goddesses_of_phobos.z5

It plays 381 commands (plus blank lines for the key presses) and scores 350 out of 350,
rank Interplanetary Emperor, in 396 turns. Two things are random: the sword fight with
Thorbast, and the number of the Sultan's wife you have to ask for. With other seeds the
fight goes differently (with seed 2 you die in it) and the wife's number changes.

It was made from `../../solutions/lgop.step1` (by Erik Futtrup and Twan Lintermans),
checked step by step, with help from the other `lgop.*` files. Changes:

- A blank line at the start (the game asks you to press Return) and one after every
  `smell`, which waits for a key press.
- Thorbast fight: with seed 1 it takes `hit thorbast with sword` and three `again`s
  before his sword drifts toward you. Then `give his sword to thorbast` (the guide's
  "throw his sword to thorbast" just floats back to you) and `hit monster with my sword`
  (the guide's version asks which sword).
- `wait` instead of `examine frog` while falling over Mars (the frog isn't there yet).
- At the Oasis the circle turns white: `paint circle` turns it black again (the guide's
  `put black stain on circle` can't find it).
- In the Cleveland bedroom Trent asks how much you weigh. Answer `say 200` (more than he
  weighs) and he goes for the headlight; the guide just waits, and Trent gives up.
- The coded message is a shift of 3, read backwards. With seed 1 it decodes to "wife
  number 6889" (the guide's 7313 is from its own game), so the walkthrough says `6889`.
- `search dust` twice in the Exit Shop: the first time finds nothing.
- A blank line at the end for the last key press.

## Files

| File | |
|------|---|
| `leather_goddesses_of_phobos.z5` | the game |
| `walkthrough.txt` | the whole game, 381 commands, 350/350 with `--seed 1` |
| `leather_goddesses_of_phobos_walkthrough.txt` | a full transcript of the walkthrough |
| `leather_goddesses_of_phobos.auto.map.pdf` | a map of the 72 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `leather_goddesses_of_phobos.auto.map.json` | the map data behind it |
| `leather_goddesses_of_phobos.txt` | the story, told by the man from Joe's Bar |
