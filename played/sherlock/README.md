# Sherlock

Infocom's Sherlock: The Riddle of the Crown Jewels (1987, release 26), by Bob Bates. You
are Doctor Watson. It's the weekend of Queen Victoria's Golden Jubilee, the Crown Jewels
have been stolen from the Tower of London, and they must be back at Buckingham Palace by
nine o'clock on Monday morning. The thief has left a verse of riddles. Holmes lets you lead
the investigation, and the trail goes through Westminster Abbey, the British Museum,
Madame Tussaud's, Big Ben, the Bank of England and the Tower, gathering five gems with
messages scratched into them, and ends in Professor Moriarty's lair.

## Playing

    python3 ../../zplay.py sherlock.z5

The clock matters. Walking one street takes five minutes, and some things only happen at
certain times: the Abbey opens at 7 am, Big Ben's clapper only swings within reach while it
strikes the hour, and the moss under London Bridge can only be reached at high tide. Signs
and plaques are shown in a pop-up window that `zplay.py` doesn't print in script mode
(`--no-status`), so `read sign` prints nothing there.

## The walkthrough needs seed 1

    python3 ../../zplay.py --script walkthrough.txt --seed 1 sherlock.z5

It plays 363 commands and scores 100 out of 100 (Consulting Detective). Two things are
random: the girl's heartbeat in Covent Garden (fast with seed 1) and the Tower password
Mycroft gives you (`Howard` with seed 1). With other seeds the walkthrough goes wrong.

It was made mostly from `../../solutions/sherlock.step1` (Erik Futtrup and Twan
Lintermans), with `../../solutions/sherlock.step2` (Jacob Gunness) for some steps, checked
move by move. The tide times, street map and bank dial come from Infocom's source at
`github.com/historicalsource/sherlock`. Changes:

- The first line is blank: it's the key press for the title screen. Another blank line
  follows the first time Big Ben strikes, for the one-time note about `$SOUND`.
- `wait` and `wait until` stop to ask "Do you want to continue waiting?"; the walkthrough
  answers `n` or `y` on the next line.
- The first guide gets the pills the wrong way round. A fast heartbeat needs the digitalis
  (the blue bottle's orange pill), not the belladonna.
- Many of the first guide's directions are garbled. The walkthrough's routes are worked out
  from the game's map: the oar is in the Black Museum under Scotland Yard (Whitehall, `e`,
  `d`), Sherman's shop is south of Cheapside (`s`, `w`), the Tower is east of Lower Thames
  Street, and the Byward Tower is two `e` past the Tower entrance.
- The Black Museum is dark, so keep the lamp lit until you've taken the oar. The papers,
  crayon and clue are left there, since your hands are full.
- Look at Nelson's statue through the telescope before showing the ruby to the pigeon.
- The sapphire needs two grabs while the bell swings towards you. 1 pm only strikes once,
  so the walkthrough tugs once at 1 pm and pulls it free at 2 pm.
- High tide (when the moss can be reached) is 8:32 to 8:48 am or 8:38 to 8:54 pm on
  Saturday. The walkthrough is too late for the morning one, so after Big Ben and the bank
  key it waits on the Embankment for the evening. In the boat: `row east` twice to get
  under London Bridge, `drop anchor` at once (or you drift out to sea), and `take clump of
  moss` at 8:40.
- Show Holmes the ruby (he gives you his signet ring) before going to the bank. Holmes is
  kidnapped as you leave the bank, and Mycroft won't see you without the ring.
- The vault dial is always right, right, left, right, right. The box is 600 (the Great Fire,
  1666, minus the Conquest, 1066).
- The guard at the Byward Tower takes `guard, howard`.
- At Swan Lane, `wait until 2 am` only reaches Sunday 2 am; then `wait` and `wait until 2 am`
  again for Monday. `proprietor, swordfish` brings Akbar.
- In the lair, `untie holmes` keeps the rope, so you don't need the jackknife. Blow the
  whistle twice for a cab. The cab reaches the palace at 8:54, six minutes before the
  deadline.

### Tool fixes

Two small fixes were needed to draw the map; neither is specific to Sherlock.

- `tools/zplaymap.py` dropped blank lines from the walkthrough, but `zplay.py --script`
  uses them as key presses, so the map run fell out of step after the first one. It now
  keeps them. It also stops when the game asks for a key after the script has run out
  (Sherlock's end-of-game menu), instead of pressing Return forever.
- `zplay.py`'s `print_table` moved the cursor down a line after the last row of a table.
  Sherlock clears its status line by printing blanks with `print_table` in a few chunks, so
  the chunks went to the wrong line, old room names showed through ("Entry Hallr Street"),
  and the map got 129 rooms instead of 79. The cursor now stays after the last row. The
  `--no-status` transcript is the same as before.

## Files

| File | |
|------|---|
| `sherlock.z5` | the game |
| `walkthrough.txt` | the whole case, 363 commands, 100/100 with `--seed 1` |
| `sherlock_walkthrough.txt` | a full transcript of the walkthrough |
| `sherlock.auto.map.pdf` | a map of the 79 places the walkthrough visits (drawn with `../../tools/zplaymap.py`) |
| `sherlock.auto.map.json` | the map data behind it |
| `sherlock.txt` | the story of the case, told by Watson |
