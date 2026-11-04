# Suspect

Infocom's Suspect (1984, release 14), by Dave Lebling: "An Interactive Mystery". It's
Halloween night at Veronica Ashcroft's costume party at Ashcroft Farm, and you're a
reporter in a cowboy suit. Veronica is found strangled in the office with your own lariat,
and the police soon come looking for you. You have to find out who really did it, and
convince the detective, before he arrests you.

There's no score: you win by having the detective arrest the right people.

## Playing

    python3 ../../zplay.py suspect.z5

Everyone at the party moves around on a schedule, and every command takes time. Ask
people about each other (`ask michael about ostmann`), `listen` to conversations,
`hide behind` things and `wait for` people.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 suspect.z5

It plays 173 commands and solves the case at 12:09 a.m.: Michael and Alicia are convicted
and your story wins the Pulitzer Prize. Timing is tight (see below), and with other
seeds the walkthrough doesn't win (seeds 2 to 5 all fail).

It was made from `../../solutions/suspect.step` (by Erik Futtrup and Twan Lintermans),
checked step by step. Changes:

- **Reaching the detective in time.** Once the detective has seen the body and your
  lariat and gone back to the ballroom, he and Sergeant Duffy come to arrest you unless
  you've already shown him enough evidence (more than four clues: `I-START-ARREST` and
  `PLAYER-ARRESTED?` in `people.zil`, Infocom's source at
  `github.com/historicalsource/suspect`). Following the guide, you're arrested before
  you can show him anything. The walkthrough leaves out three optional steps (`look`,
  the trip to show the manila folder to Ostmann, and `inventory`), then does
  `wait for detective` (with three `y` answers) in the front hall instead of chasing him.
- `wait for duffy` needs six `y` answers before Duffy brings back the fingerprint
  analysis; then `detective, arrest michael and alicia`.

The rest of the guide works as written, including its many `ask about` questions (they
aren't needed, but they tell the story).

## Files

| File | |
|------|---|
| `suspect.z5` | the game |
| `walkthrough.txt` | the solution, 173 commands, with `--seed 1` |
| `suspect_walkthrough.txt` | a full transcript of the walkthrough, ending with the explanation of the case |
| `suspect.auto.map.pdf` | a map of the 26 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `suspect.auto.map.json` | the map data behind it |
| `suspect.txt` | the story of the party, told by the reporter |
