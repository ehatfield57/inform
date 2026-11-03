# Enchanter

Infocom's Enchanter (1983, release 10). You are a novice Enchanter sent by Belboz and the
Circle to defeat the warlock Krill. 400 points.

## Playing

    python3 ../../zplay.py enchanter.z5

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 enchanter.z5

The game has random events (when the adventurer appears in the Hall of Mirrors, where he
wanders), and the walkthrough's waits are timed for seed 1. Without `--seed 1` each run
uses a different seed and the walkthrough misses the adventurer.

## Files

| File | |
|------|---|
| `enchanter.z5` | the game |
| `walkthrough.txt` | the full solution, 232 commands, 400/400 with `--seed 1` |
| `enchanter_walkthrough.txt` | a full transcript of the walkthrough winning |
| `enchanter.auto.json` | hints (and notes) for the autoplayer, `zplay_auto.py` |
| `enchanter.auto.log`, `.map.json`, `.map.pdf`, `.sav` | the autoplayer's log, map and saved game |
| `enchanter.txt` | the story of the game, as told by the young Enchanter |
