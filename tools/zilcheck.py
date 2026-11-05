#!/usr/bin/env python3
"""zilcheck.py - check the ZIL interpreter against a game we've already played.

Plays played/<game>/walkthrough.txt twice with --seed 1: once with zplay.py on the
story file in played/<game>/, once with zilplay.py on the game's ZIL source from
sources/. Then it compares the two transcripts.

If a source of the same release as the story file exists, the transcripts should be
identical. If only other releases exist, text can differ a little, so it also
reports whether the ZIL run reaches the same ending (its last score line).

Examples:
  python3 tools/zilcheck.py zork1
  python3 tools/zilcheck.py deadline
  python3 tools/zilcheck.py deadline --source sources/deadline-r28.zip
  python3 tools/zilcheck.py hhgg --show 40        # show more of the first difference
  python3 tools/zilcheck.py --list                # every played game and its sources

The two transcripts are left in /tmp (or --out) as <game>.zplay.txt and <game>.zil.txt.
"""

import argparse
import difflib
import glob
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# played/ folder name -> name used for its zips in sources/, where they differ
SOURCE_NAMES = {"hhgg": "hitchhiker", "leather_goddesses_of_phobos": "leathergoddesses",
                "lurking": "lurkinghorror", "plundered_hearts": "plunderedhearts"}


def story_file(game):
    for ext in ("z3", "z4", "z5", "z8", "zblorb"):
        hits = glob.glob(os.path.join(ROOT, "played", game, "*." + ext))
        if hits:
            return hits[0]
    return None


def story_release(path):
    d = open(path, "rb").read(0x20)
    serial = d[0x12:0x18].decode("latin-1")
    return d[2] * 256 + d[3], serial if serial.isdigit() else None


def sources_for(game):
    name = SOURCE_NAMES.get(game, game)
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "sources", name + "-*.zip"))):
        m = re.search(r"-r(\d+)", os.path.basename(p))
        out.append((p, int(m.group(1)) if m else None))
    return out


def ranked_sources(game, release):
    """Sources in order of preference: same release first, then the nearest numbered
    releases (ties: newer), then the rest. InvisiClues builds go last."""
    srcs = sources_for(game)

    def key(pr):
        p, r = pr
        return ("invclues" in p, r != release, "mac" in p and r == release,
                abs(r - release) if r is not None else 999, -(r or 0))
    return [(p, r == release) for p, r in sorted(srcs, key=key)]


def loads(src):
    """True if zilplay.py can load this source (some zips are incomplete or damaged)."""
    r = subprocess.run([sys.executable, "zilplay.py", src, "--no-status"], cwd=ROOT,
                       input="", capture_output=True, text=True, timeout=300)
    return "[Could not load" not in r.stdout


def pick_source(game, release, check=False):
    ranked = ranked_sources(game, release)
    if not ranked:
        return None, False
    if check:
        for p, same in ranked:
            if loads(p):
                return p, same
    return ranked[0]


def run(cmd, out_path):
    with open(out_path, "w") as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                       cwd=ROOT, timeout=600)
    with open(out_path, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


SCORE = re.compile(r"(score|potential|rank|points)", re.I)


def ending(lines):
    hits = [l for l in lines if SCORE.search(l)]
    return hits[-1].strip() if hits else "(no score line)"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game", nargs="?", help="folder name in played/, e.g. deadline")
    ap.add_argument("--source", help="ZIL source to use (default: same or nearest release)")
    ap.add_argument("--zilch", choices=["old", "new"], help="passed on to zilplay.py")
    ap.add_argument("--show", type=int, default=12, help="lines of difference to show")
    ap.add_argument("--out", default=tempfile.gettempdir(), help="where to leave transcripts")
    ap.add_argument("--list", action="store_true", help="list played games and their sources")
    args = ap.parse_args()

    if args.list:
        for d in sorted(os.listdir(os.path.join(ROOT, "played"))):
            story = story_file(d)
            if not story:
                continue
            rel, serial = story_release(story)
            src, same = pick_source(d, rel)
            print("%-30s r%-4d %-8s %s%s" % (d, rel, serial or "?",
                                            os.path.basename(src) if src else "(no source)",
                                            "  (same release)" if same else ""))
        return
    if not args.game:
        ap.error("name a game, or use --list")
    game = args.game
    story = story_file(game)
    walk = os.path.join(ROOT, "played", game, "walkthrough.txt")
    if not story or not os.path.exists(walk):
        sys.exit("no story file or walkthrough in played/%s" % game)
    rel, serial = story_release(story)
    src, same = (args.source, None) if args.source else pick_source(game, rel, check=True)
    if not src:
        sys.exit("no source for %s in sources/" % game)
    print("story  %s (release %d, serial %s)" % (os.path.relpath(story, ROOT), rel, serial or "?"))
    print("source %s%s" % (os.path.relpath(src, ROOT),
                           "  (same release)" if same else "  (different release)" if same is False else ""))

    common = ["--script", walk, "--seed", "1", "--no-status", "--width", "80"]
    zp = run([sys.executable, "zplay.py", story] + common,
             os.path.join(args.out, game + ".zplay.txt"))
    zcmd = [sys.executable, "zilplay.py", src] + common
    if serial:
        zcmd += ["--serial", serial]
    out_path = os.path.join(args.out, game + ".zil.txt")
    if args.zilch:
        zl = run(zcmd + ["--zilch", args.zilch], out_path)
    else:
        # The compiler generation is sometimes only a guess (see zil/loader.py), so if
        # the result isn't identical, also try the other one and keep the closer match.
        zl = run(zcmd, out_path)
        if zl != zp:
            tried = {}
            for gen in ("old", "new"):
                tried[gen] = run(zcmd + ["--zilch", gen], out_path + "." + gen)
            best = max(tried, key=lambda g: difflib.SequenceMatcher(None, zp, tried[g],
                                                                    autojunk=False).ratio())
            if tried[best] != zl and similarity(zp, tried[best]) > similarity(zp, zl):
                print("zilch  closer with --zilch %s (the automatic choice was a guess)" % best)
                zl = tried[best]
                with open(out_path, "w") as fh:
                    fh.write("\n".join(zl) + "\n")

    print("lines  zplay %d, zil %d" % (len(zp), len(zl)))
    print("ending zplay: %s" % ending(zp))
    print("       zil:   %s" % ending(zl))
    if zp == zl:
        print("RESULT identical")
        return
    sm = difflib.SequenceMatcher(None, zp, zl, autojunk=False)
    first = next(op for op in sm.get_opcodes() if op[0] != "equal")
    _, i1, i2, j1, j2 = first
    same_lines = sum(b - a for t, a, b, _, _ in sm.get_opcodes() if t == "equal")
    print("RESULT differs: %d%% of lines the same; first difference at line %d"
          % (100 * same_lines // max(len(zp), 1), i1 + 1))
    for line in difflib.unified_diff(zp, zl, "zplay", "zil", n=2, lineterm=""):
        if args.show <= 0:
            break
        print("  " + line)
        args.show -= 1
    err = [l for l in zl if l.startswith("[ZIL error") or l.startswith("[Could not load")]
    if err:
        print("ZIL stopped: " + err[0])


if __name__ == "__main__":
    main()
