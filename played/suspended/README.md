# Suspended

Infocom's Suspended (1983, release 5), often called its hardest game. You lie frozen in a
cryogenic capsule beneath the planet Contra, and an earthquake has broken the cables
between the three Filtering Computers that run the weather, farms and transit above. You
can only act through six robots, each with one sense: Iris (sight), Waldo (hands), Sensa
(magnetism and current), Auda (hearing), Poet (electrical flow) and Whiz (the computers).

There's no score: you're ranked from 1 (best) to 7 (worst) by how many people on the
surface die before you restore the balance.

## Playing

    python3 ../../zplay.py suspended.z5

Talk to a robot by name: `iris, go to main supply room`. Two robots can act together:
`both sensa and auda, move fred`.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 suspended.z5

It finishes in 70 cycles with ranking 1 (8,000 casualties out of 30,172,000), from
`../../solutions/suspended.txt`. The reset code is random: with seed 1 Poet's camera shows
BLEMUM, which is the third circle (BLE) then the second (MUM) on the reset machine. With
any other seed the code changes, so the last two commands are wrong.

Notes on the guide:

- Its #43 just says "go to gamma repair": it means Sensa.
- "Sensa and Auda, move Fred" makes them try one at a time and fail. It has to be
  "both sensa and auda, move fred".
- Sensa must replace the cable in the Primary Channel on the very next cycle after she
  arrives (the acid destroys her a cycle later): one `wait` after sending Auda off.
- Poet, Waldo and Sensa are lost to the acid in the Cavernous Room on the way. That's the
  plan, not a mistake.

## Files

| File | |
|------|---|
| `suspended.z5` | the game |
| `walkthrough.txt` | the full solution, 69 commands, ranking 1 with `--seed 1` |
| `suspended_walkthrough.txt` | a full transcript of the walkthrough winning |
| `suspended.auto.map.pdf` | a map of all 59 rooms of the complex, with what starts in each |
| `suspended.auto.map.json` | the map data behind it, built from the game's own room data with `../../tools/zgamemap.py` (the player never moves, so the usual played map would only show a few rooms) |
| `suspended.txt` | the story of the game, told by the sleeper in the capsule |
