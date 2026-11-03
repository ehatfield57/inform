# Border Zone

Infocom's Border Zone: A Game of Intrigue (1987, release 9), by Marc Blank. A Cold War
spy story in three chapters, each with a different hero: an American businessman on the
train to the border, the wounded American agent Topaz escaping across it, and Viper, the
KGB man (and secret double agent) trying to stop an assassination in the town of Ostnitz.
It runs in real time. There's no score: each chapter is won or lost.

## Playing

    python3 ../../zplay.py borderzone.z5

At the start, press 1, 2 or 3 to pick a chapter. In `zplay.py` the game clock moves on only
when you enter a command, not while you sit thinking at the prompt (it doesn't time line
input), so you have as long as you like to decide. Timed scenes, such as the run across the
border zone, do play out in real time.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 borderzone.z5

It plays all three chapters in a row (choosing chapter 1, then `continue` after each
chapter), 188 commands, and wins all three. The searchlights, the guards' patrols and the
people on the station platform are random, so with other seeds it goes wrong.

It was made from `../../solutions/borderzone.txt`, checked step by step. Changes:

- Chapter 1: putting the document in the toilet gets you caught (a shred is found).
  Instead, `tear document` and `eat shreds`. The contact is the boy who bumps into you and
  says "Hartzi dazi" (forgive me); reply `say "popka izim"` and give him the film.
- Chapter 2: the timings are written out as exact waits for seed 1. Wait three turns at
  the edge of the border zone before `run north`, three more before cutting the fence. Set
  the pen bomb to one minute, not two: commands from a script take less game time than a
  person typing, and with two minutes the guards reach you first.
- Chapter 3: the chapter starts at the northwest corner of the square, not where the
  guide starts. Riznik's shop has a policeman in it at first; wait outside until a man
  with a walkie-talkie leaves. The vendor's cart to topple is one block north of the
  cafe. The sniper's room is the free room with an open window, which with seed 1 is
  5D: the eastern door halfway down the fifth-floor hall. Hit Topaz after he shoots the
  sniper, before he turns round.

### Interpreter fixes

Border Zone waits for single key presses with a timer while things happen around you
(running across the border zone, for instance). `zplay.py` used to ignore input timers, so
the run never started and the game sat waiting for a key. It now calls the game's timer
routine when no key comes in time, and stops waiting when the routine says so, as other
interpreters do. With a script, the timer always runs, since nobody is typing.

## Files

| File | |
|------|---|
| `borderzone.z5` | the game |
| `walkthrough.txt` | all three chapters, 188 commands, with `--seed 1` |
| `borderzone_walkthrough.txt` | a full transcript of the walkthrough winning all three |
| `borderzone.auto.map.pdf` | a map of the 50 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `borderzone.auto.map.json` | the map data behind it |
| `borderzone.txt` | the story of the game, told in turn by the businessman, Topaz and Viper |
