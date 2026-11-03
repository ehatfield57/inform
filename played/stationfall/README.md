# Stationfall

Infocom's Stationfall (1987, release 107), the sequel to Planetfall. Five years later,
you're a Lieutenant First Class sent with Floyd to pick up some forms from a space
station, and find it empty: an alien pyramid has turned the station's machines against
the people. 80 points.

## Playing

    python3 ../../zplay.py stationfall.z3

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 stationfall.z3

Several things are random: when the hull welders come for you (leave the room as soon as
one appears, or it kills you), when Plato attacks with his stun ray, and the time on your
watch, which decides the spacetruck's course heading.

It was made from `../../solutions/stationfall.step` and the text guide inside
`../../solutions/stationfall.zip`, checked step by step, and wins 80/80 in 390 commands.
Notes:

- The course heading comes from a card in the game box (the Assignment Completion
  Form), which isn't in the solution files. The game keeps the right answer in a global
  variable (G92) at the moment you type, which is how the walkthrough knows to type 409.
- When the commander's log plays, the validation stamp is mentioned before the welder
  arrives: six presses of the red button is enough, then leave east.
- Leave the Barbershop right after taking the foil (a welder arrives while you break the
  mirror) and turn the detector off in the next room.
- The chapel is southwest of Level Three: from Level Five it's two `u`s, not three.
- When Plato stuns you, everything you carry falls to the floor: say "floyd, help me"
  (four times with seed 1), then `take all`.
- The headlamp is needed at the top of the station: the lights go out on the way up.

## Files

| File | |
|------|---|
| `stationfall.z3` | the game |
| `walkthrough.txt` | the full solution, 390 commands, 80/80 with `--seed 1` |
| `stationfall_walkthrough.txt` | a full transcript of the walkthrough winning |
| `stationfall.auto.map.pdf` | a map of the 71 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker) |
| `stationfall.auto.map.json` | the map data behind it |
| `stationfall.txt` | the story of the game, told by the Lieutenant |
