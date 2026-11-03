#!/usr/bin/env python3
"""zdis.py - disassemble Z-machine code, to see how a puzzle really works.

Game logic is compiled to Z-machine instructions. Reading them answers questions no
walkthrough does: which flag a door checks, what number a code is compared with, what an
action adds to a score. It's slow reading, so use the other tools to find the right spot:

  1. Find a message with zstrings.py; its address is inside (or near) the code that prints
     it. Or trace a command with zrun.py --trace-compare to see the addresses it runs.
  2. Disassemble around that address with this tool.

Disassembly starts wherever you tell it. If that's the middle of an instruction, the first
lines come out as nonsense ("???") until it falls back into step; start a little earlier,
or use --routine with the routine's address when you know it.

Output, one instruction per line:
  address  opcode operands [-> store variable] [?branch target]  [notes]
Operands: #12 is a constant, L0..L14 are the routine's local variables, G0.. are globals
(G0 is variable 16), sp is the stack. Object numbers are followed by the object's name in
[brackets]; printed text is shown in quotes.

Examples:
  python3 tools/zdis.py played/wishbringer/wishbringer.z5 1da67 1da94
  python3 tools/zdis.py played/amfv/amfv.z4 --routine 2b444
  python3 tools/zdis.py played/amfv/amfv.z4 --refs 7af3        # where is this address used?
  python3 tools/zdis.py played/amfv/amfv.z4 --refs-routine 2b444   # who calls this routine?
"""

import argparse
import re
import sys

import zinfo

# (name, stores a result, branches) for each opcode.  "None" entries are unused numbers.
OP2 = {1: ("je", 0, 1), 2: ("jl", 0, 1), 3: ("jg", 0, 1), 4: ("dec_chk", 0, 1),
       5: ("inc_chk", 0, 1), 6: ("jin", 0, 1), 7: ("test", 0, 1), 8: ("or", 1, 0),
       9: ("and", 1, 0), 10: ("test_attr", 0, 1), 11: ("set_attr", 0, 0),
       12: ("clear_attr", 0, 0), 13: ("store", 0, 0), 14: ("insert_obj", 0, 0),
       15: ("loadw", 1, 0), 16: ("loadb", 1, 0), 17: ("get_prop", 1, 0),
       18: ("get_prop_addr", 1, 0), 19: ("get_next_prop", 1, 0), 20: ("add", 1, 0),
       21: ("sub", 1, 0), 22: ("mul", 1, 0), 23: ("div", 1, 0), 24: ("mod", 1, 0),
       25: ("call_2s", 1, 0), 26: ("call_2n", 0, 0), 27: ("set_colour", 0, 0),
       28: ("throw", 0, 0)}
OP1 = {0: ("jz", 0, 1), 1: ("get_sibling", 1, 1), 2: ("get_child", 1, 1),
       3: ("get_parent", 1, 0), 4: ("get_prop_len", 1, 0), 5: ("inc", 0, 0), 6: ("dec", 0, 0),
       7: ("print_addr", 0, 0), 8: ("call_1s", 1, 0), 9: ("remove_obj", 0, 0),
       10: ("print_obj", 0, 0), 11: ("ret", 0, 0), 12: ("jump", 0, 0),
       13: ("print_paddr", 0, 0), 14: ("load", 1, 0), 15: ("not", 1, 0)}
OP0 = {0: ("rtrue", 0, 0), 1: ("rfalse", 0, 0), 2: ("print", 0, 0), 3: ("print_ret", 0, 0),
       4: ("nop", 0, 0), 5: ("save", 0, 1), 6: ("restore", 0, 1), 7: ("restart", 0, 0),
       8: ("ret_popped", 0, 0), 9: ("pop", 0, 0), 10: ("quit", 0, 0), 11: ("new_line", 0, 0),
       12: ("show_status", 0, 0), 13: ("verify", 0, 1), 15: ("piracy", 0, 1)}
VAR = {0: ("call", 1, 0), 1: ("storew", 0, 0), 2: ("storeb", 0, 0), 3: ("put_prop", 0, 0),
       4: ("sread", 0, 0), 5: ("print_char", 0, 0), 6: ("print_num", 0, 0),
       7: ("random", 1, 0), 8: ("push", 0, 0), 9: ("pull", 0, 0), 10: ("split_window", 0, 0),
       11: ("set_window", 0, 0), 12: ("call_vs2", 1, 0), 13: ("erase_window", 0, 0),
       14: ("erase_line", 0, 0), 15: ("set_cursor", 0, 0), 16: ("get_cursor", 0, 0),
       17: ("set_text_style", 0, 0), 18: ("buffer_mode", 0, 0), 19: ("output_stream", 0, 0),
       20: ("input_stream", 0, 0), 21: ("sound_effect", 0, 0), 22: ("read_char", 1, 0),
       23: ("scan_table", 1, 1), 24: ("not", 1, 0), 25: ("call_vn", 0, 0),
       26: ("call_vn2", 0, 0), 27: ("tokenise", 0, 0), 28: ("encode_text", 0, 0),
       29: ("copy_table", 0, 0), 30: ("print_table", 0, 0), 31: ("check_arg_count", 0, 1)}
EXT = {0: ("save", 1, 0), 1: ("restore", 1, 0), 2: ("log_shift", 1, 0),
       3: ("art_shift", 1, 0), 4: ("set_font", 1, 0), 9: ("save_undo", 1, 0),
       10: ("restore_undo", 1, 0), 11: ("print_unicode", 0, 0), 12: ("check_unicode", 1, 0)}

OBJ_FIRST = {"jin", "test_attr", "set_attr", "clear_attr", "insert_obj", "get_prop",
             "get_prop_addr", "get_next_prop", "get_sibling", "get_child", "get_parent",
             "remove_obj", "print_obj", "put_prop"}
CALLS = {"call", "call_1s", "call_2s", "call_2n", "call_vs2", "call_vn", "call_vn2", "call_1n"}


def info(story, table, num):
    """Opcode info, adjusted for the story's version."""
    v = story.version
    if table is OP1 and num == 15 and v >= 5:
        return ("call_1n", 0, 0)
    if table is OP0 and num in (5, 6) and v >= 4:
        return (table[num][0], 1, 0) if v == 4 else None   # v4 stores; v5 moved to EXT
    if table is OP0 and num == 9 and v >= 5:
        return ("catch", 1, 0)
    if table is VAR and num == 4 and v >= 5:
        return ("aread", 1, 0)
    return table.get(num)


class Disassembler:
    def __init__(self, story):
        self.s = story
        self.nobj = story.count()

    def var(self, v):
        return "sp" if v == 0 else "L%d" % (v - 1) if v < 16 else "G%d" % (v - 16)

    def objname(self, n):
        if 0 < n <= self.nobj:
            nm = self.s.name(n)
            return "[%s]" % nm if nm else ""
        return ""

    def one(self, a):
        """Disassemble the instruction at a. Returns (text, address of the next one)."""
        s, m = self.s, self.s.mem
        start, op = a, m[a]
        a += 1
        types, ops = [], []
        if op == 0xBE and s.version >= 5:                     # extended
            num = m[a]
            a += 1
            entry = EXT.get(num)
            tb = m[a]
            a += 1
            types = [(tb >> sh) & 3 for sh in (6, 4, 2, 0)]
        elif op < 0x80:                                       # long form 2OP
            entry = info(s, OP2, op & 31)
            types = [2 if op & 0x40 else 1, 2 if op & 0x20 else 1]
        elif op < 0xB0:                                       # short form 1OP
            entry = info(s, OP1, op & 15)
            types = [(op >> 4) & 3]
        elif op < 0xC0:                                       # short form 0OP
            entry = info(s, OP0, op & 15)
        else:                                                 # variable form
            entry = info(s, OP2 if op < 0xE0 else VAR, op & 31)
            name = entry[0] if entry else ""
            tb = m[a]
            a += 1
            types = [(tb >> sh) & 3 for sh in (6, 4, 2, 0)]
            if name in ("call_vs2", "call_vn2"):              # these take a second type byte
                tb2 = m[a]
                a += 1
                types += [(tb2 >> sh) & 3 for sh in (6, 4, 2, 0)]
        for t in types:
            if t == 3:
                break
            if t == 0:
                ops.append(("#", s.rw(a)))
                a += 2
            elif t == 1:
                ops.append(("#", m[a]))
                a += 1
            else:
                ops.append(("v", m[a]))
                a += 1
        if entry is None:
            return "%05x ??? %02x" % (start, op), start + 1
        name, stores, branches = entry
        texts = [("#%d" % v) if k == "#" else self.var(v) for k, v in ops]
        notes = ""
        if name in ("print", "print_ret"):
            t, a = s.decode(a)
            notes += ' "%s"' % t.replace("\n", "\\n")[:90]
        tail = ""
        if stores:
            tail += " -> " + self.var(m[a])
            a += 1
        if branches:
            b = m[a]
            a += 1
            off = b & 63
            if not b & 0x40:
                off = (off << 8) | m[a]
                a += 1
                if off & 0x2000:
                    off -= 0x4000
            target = {0: "rfalse", 1: "rtrue"}.get(off, "%05x" % (a + off - 2))
            tail += " ?%s%s" % ("" if b & 0x80 else "~", target)
        if name == "jump" and ops:
            off = ops[0][1] if ops[0][0] == "#" else 0
            off = off - 0x10000 if off & 0x8000 else off
            notes += "  (to %05x)" % (a + off - 2)
        if name in CALLS and ops and ops[0][0] == "#":
            notes += "  (routine %05x)" % s.unpack(ops[0][1])
        if name == "print_paddr" and ops and ops[0][0] == "#":
            try:
                notes += ' "%s"' % s.decode(s.unpack(ops[0][1]))[0][:70]
            except Exception:
                pass
        if name in OBJ_FIRST and ops and ops[0][0] == "#":
            notes += "  " + self.objname(ops[0][1])
        if name in ("jin", "insert_obj") and len(ops) > 1 and ops[1][0] == "#":
            notes += " in " + self.objname(ops[1][1])
        if name == "je":
            names = [self.objname(v) for k, v in ops[1:] if k == "#" and v <= self.nobj]
            if any(names):
                notes += "  (objects? %s)" % " ".join(n for n in names if n)
        return "%05x %s %s%s%s" % (start, name, " ".join(texts), tail, notes), a

    def range(self, a, end):
        while a < end:
            text, a = self.one(a)
            print(text)


def main():
    ap = argparse.ArgumentParser(
        description="Disassemble Z-machine code (versions 3-5).",
        epilog="Addresses are hexadecimal, as printed by zstrings.py and the other tools.")
    ap.add_argument("story", help="story file")
    ap.add_argument("start", nargs="?", help="first address to disassemble (hex)")
    ap.add_argument("end", nargs="?", help="stop before this address (hex; default start+0x60)")
    ap.add_argument("--routine", metavar="ADDR",
                    help="disassemble the routine starting at ADDR (hex byte address): reads "
                         "its local-variable header, then decodes until the routine seems to end")
    ap.add_argument("--packed", action="store_true",
                    help="treat --routine ADDR as a packed address (as seen in call operands)")
    ap.add_argument("--refs", metavar="VALUE",
                    help="list every place in the file holding this 16-bit value (hex), e.g. a "
                         "table address or a packed routine/string address")
    ap.add_argument("--refs-routine", metavar="ADDR",
                    help="list places that may call the routine at byte address ADDR (hex): "
                         "searches for its packed address")
    args = ap.parse_args()

    s = zinfo.Story(args.story)
    d = Disassembler(s)
    if args.refs or args.refs_routine:
        if args.refs:
            value = int(args.refs, 16)
        else:
            a = int(args.refs_routine, 16)
            value = a // (2 if s.version <= 3 else 4 if s.version <= 5 else 8)
        pat = re.escape(bytes([value >> 8, value & 255]))
        hits = [mm.start() for mm in re.finditer(pat, bytes(s.mem))]
        print("value %04x found at %d places:" % (value, len(hits)))
        for h in hits:
            print("  %05x" % h)
        return 0
    if args.routine:
        a = int(args.routine, 16)
        if args.packed:
            a = s.unpack(a)
        nloc = s.mem[a]
        print("routine %05x: %d local variable(s)" % (a, nloc))
        a += 1 + (2 * nloc if s.version <= 4 else 0)
        # Keep going until an instruction that never falls through (a return, quit or
        # jump) is past every branch target seen so far: that's the end of the routine.
        furthest = a
        for _ in range(2000):
            text, nxt = d.one(a)
            print(text)
            for t in re.findall(r"\?~?([0-9a-f]{5})|\(to ([0-9a-f]{5})\)", text):
                furthest = max(furthest, int(t[0] or t[1], 16))
            name = text.split()[1] if len(text.split()) > 1 else ""
            a = nxt
            if name in ("rtrue", "rfalse", "ret", "ret_popped", "print_ret", "quit", "jump") \
                    and a > furthest:
                break
        return 0
    if not args.start:
        ap.error("give a start address, or --routine, --refs or --refs-routine")
    start = int(args.start, 16)
    end = int(args.end, 16) if args.end else start + 0x60
    d.range(start, end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
