# The Witness

Infocom's The Witness (1983, release 18), a murder mystery set in Southern California in
February 1938. You're a police detective called to the Linder house because of a threat
on Freeman Linder's life, and at 9:03 pm you watch him get shot. Witness keeps no score:
you win by arresting the right person with the evidence to convict them.

## Playing

    python3 ../../zplay.py witness.z5

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 witness.z5

Everything runs to the game clock, one minute per move, and Sergeant Duffy's lab work
takes a random amount of time, so with any other seed Monica's movements happen at
different times and the walkthrough falls out of step.

Some things the solution files don't say:

- Long waits ("wait until 9:04", "wait for monica") stop when something happens and ask
  "Do you want to keep waiting?". The `yes` and `no` lines in the walkthrough answer
  those questions.
- Drop the telegram and the note before taking the gun receipt, or you'll be carrying
  too much and drop the muddy gun.
- After Monica comes back from the movies, wait for her in her bedroom (not outside the
  toilet), ask her about Mr. Linder as soon as she sits down, then follow her to the
  office once the coroner has been.

It was made from `../../solutions/witness.step` and `../../solutions/witness.txt`, checked step
by step. The last two `yes` answers confirm the arrest and show the author's summary of
the case.

## Files

| File | |
|------|---|
| `witness.z5` | the game |
| `walkthrough.txt` | the full solution, 80 commands, with `--seed 1` |
| `witness_walkthrough.txt` | a full transcript of the walkthrough solving the case, with the author's summary at the end |
| `witness.auto.map.pdf` | a map of the 15 rooms the walkthrough visits (drawn by `zplay_auto.py`'s map maker; the house has 29) |
| `witness.auto.map.json` | the map data behind it |
| `witness.txt` | the story of the case, told by the detective |
