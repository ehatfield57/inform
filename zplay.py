#!/usr/bin/env python3
"""
zplay.py - a Z-machine interpreter in pure Python (standard library only).

Plays Infocom and Inform story files: versions 3, 4, 5, 7 and 8
(.z3 .z4 .z5 .z7 .z8, plus .zblorb wrappers). Version 6 (graphical) is not supported.

    python3 zplay.py zork1.z5
    python3 zplay.py game.z5 --script walkthrough.txt   # type commands from a file
    python3 zplay.py game.z5 --no-status                 # hide the status line
    python3 zplay.py game.z5 --debug                     # show the room's object tree each turn

While playing, two commands are handled by zplay itself instead of the game:
    /debug    turn the debug view on or off. Before each prompt it shows the location's
              object number and name, and every object in it (number, name, attributes,
              contents). It reveals hidden objects, so it is for checking how a game and
              this interpreter behave, not for normal play.
    /help     list these.
For playing in plain English (and a map of where things are), see zplay_llm.py.

Save/restore use a small JSON file (not Quetzal). Undo works in games that support it.
"""

import argparse
import base64
import json
import os
import random
import shutil
import struct
import sys
import zlib

A0 = "abcdefghijklmnopqrstuvwxyz"
A1 = A0.upper()
A2 = "0123456789.,!?_#'\"/\\-:()"
DEFAULT_EXTRA = ("äöüÄÖÜß»«ëïÿËÏáéíóúýÁÉÍÓÚÝàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛåÅøØãñõÃÑÕæÆçÇþðÞÐ£œŒ¡¿")


class ZError(Exception):
    pass


class Quit(Exception):
    pass


class Restart(Exception):
    pass


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


class Frame:
    __slots__ = ("ret_pc", "locals", "store", "stack", "argc")

    def __init__(self, ret_pc, locals_, store, argc, stack=None):
        self.ret_pc = ret_pc
        self.locals = locals_
        self.store = store
        self.argc = argc
        self.stack = stack if stack is not None else []

    def copy(self):
        return Frame(self.ret_pc, list(self.locals), self.store, self.argc, list(self.stack))


# --------------------------------------------------------------------------- screen

class Screen:
    """Lower window = scrolling, word-wrapped stdout. Upper window = a character grid
    (status line, quote boxes) that is printed above the prompt whenever input is read."""

    def __init__(self, width, height, show_status=True, script=None):
        self.width = width
        self.height = height
        self.show_status = show_status
        self.ansi = sys.stdout.isatty()
        self.pending = ""
        self.col = 0
        self.upper_lines = 0
        self.grid = []
        self.cur_row = 1
        self.cur_col = 1
        self.last_shown = None
        self.script = list(script) if script else []

    # lower window
    def write(self, s):
        out = sys.stdout
        for ch in s:
            if ch == "\n":
                out.write(self.pending + "\n")
                self.pending = ""
                self.col = 0
                continue
            self.pending += ch
            if self.col + len(self.pending) >= self.width:
                sp = self.pending.rfind(" ")
                if sp >= 0:
                    out.write(self.pending[:sp] + "\n")
                    self.pending = self.pending[sp + 1:]
                elif self.col > 0:
                    out.write("\n")
                else:
                    out.write(self.pending + "\n")
                    self.pending = ""
                self.col = 0

    def flush(self):
        if self.pending:
            sys.stdout.write(self.pending)
            self.col += len(self.pending)
            self.pending = ""
        sys.stdout.flush()

    # upper window
    def split(self, n):
        self.upper_lines = n
        while len(self.grid) < n:
            self.grid.append([" "] * self.width)
        if self.cur_row > max(n, 1):
            self.cur_row, self.cur_col = 1, 1

    def erase_upper(self):
        self.grid = [[" "] * self.width for _ in range(self.upper_lines)]
        self.cur_row, self.cur_col = 1, 1

    def upper_write(self, s):
        for ch in s:
            if ch == "\n":
                self.cur_row += 1
                self.cur_col = 1
                continue
            r, c = self.cur_row - 1, self.cur_col - 1
            if 0 <= r < len(self.grid) and 0 <= c < self.width:
                self.grid[r][c] = ch
            self.cur_col += 1

    def erase_line(self):
        r = self.cur_row - 1
        if 0 <= r < len(self.grid):
            for c in range(max(self.cur_col - 1, 0), self.width):
                self.grid[r][c] = " "

    def status_row(self, text, reverse=True):
        if self.col > 0:            # keep the pending prompt for after the status line
            sys.stdout.write("\n")
            self.col = 0
        if self.ansi and reverse:
            sys.stdout.write("\x1b[7m" + text[: self.width - 1].ljust(self.width - 1) + "\x1b[0m\n")
        else:
            sys.stdout.write(text.rstrip() + "\n")

    def show_upper(self):
        if not self.show_status or self.upper_lines == 0:
            return
        rows = ["".join(r).rstrip() for r in self.grid[: self.upper_lines]]
        if rows == self.last_shown:
            return
        self.last_shown = rows
        for i, row in enumerate(rows):
            if row.strip():
                self.status_row(row, reverse=(i == 0))

    # input
    def read_line(self):
        if self.script:
            self.flush()
            line = self.script.pop(0)
            sys.stdout.write(line + "\n")
            self.col = 0
            return line
        # Hand the unprinted prompt to input() so readline can redraw it while editing.
        prompt, self.pending = self.pending, ""
        sys.stdout.flush()
        try:
            line = input(prompt)
        except EOFError:
            sys.stdout.write("\n")
            raise Quit()
        self.col = 0
        return line

    def key_ready(self, timeout):
        """For timed key reads (real-time games like Border Zone): True if the player
        presses a key within `timeout` seconds. Scripts and piped input never "press" a
        key during a timed wait, so the game's timer routine runs instead."""
        if self.script or not sys.stdin.isatty():
            return False
        self.flush()
        sys.stdout.flush()
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ready, _, _ = select.select([fd], [], [], timeout)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return bool(ready)

    def read_char(self):
        self.flush()
        if self.script:
            line = self.script.pop(0)
            sys.stdout.write("\n")
            self.col = 0
            return line[0] if line else "\n"
        if not sys.stdin.isatty():
            line = sys.stdin.readline()
            if not line:
                raise Quit()
            return line[0]
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                ch = {"[A": "\x81", "[B": "\x82", "[D": "\x83", "[C": "\x84"}.get(seq, "\x1b")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x04":
            raise Quit()
        return ch


# --------------------------------------------------------------------------- machine

class ZMachine:
    def __init__(self, story, screen, story_path="story", seed=None, debug=False):
        self.debug = debug
        self.story = bytes(story)
        self.screen = screen
        self.story_path = story_path
        self.rng = random.Random(seed)
        self.undo_stack = []
        self.transcript = None
        self.reset()

    # ---- setup
    def reset(self, keep_flags2=0):
        self.mem = bytearray(self.story)
        m = self.mem
        v = self.version = m[0]
        if v not in (3, 4, 5, 7, 8):
            raise ZError("Unsupported Z-machine version %d" % v)
        self.static_base = self.rw(0x0E)
        self.globals = self.rw(0x0C)
        self.obj_table = self.rw(0x0A)
        self.dict_addr = self.rw(0x08)
        self.abbrevs = self.rw(0x18)
        self.pscale = 2 if v <= 3 else (4 if v <= 7 else 8)
        self.routine_off = self.rw(0x28) * 8 if v == 7 else 0
        self.string_off = self.rw(0x2A) * 8 if v == 7 else 0
        if v <= 3:
            self.obj_entry, self.obj_base = 9, self.obj_table + 62
        else:
            self.obj_entry, self.obj_base = 14, self.obj_table + 126
        self.setup_alphabets()
        self.setup_unicode()
        m[0x11] = (m[0x11] & 0xFC) | (keep_flags2 & 3)
        self.write_header()
        self.frames = [Frame(0, [], None, 0)]
        self.pc = self.rw(0x06)
        self.mem_streams = []
        self.stream1 = True
        self.window = 0
        self.font = 1
        self.dict_cache = {}
        self.screen.split(0)
        self.build_tables()

    def write_header(self):
        m, v, sc = self.mem, self.version, self.screen
        if v <= 3:
            m[1] = (m[1] & ~0x70 & 0xFF) | 0x20      # status line available, split screen available
        else:
            m[1] = 0x1C                               # bold, italic, fixed-pitch "available"
        m[0x11] &= ~(0x08 | 0x20 | 0x80) & 0xFF       # no pictures, mouse or sound
        m[0x1E] = 6
        m[0x1F] = ord("A")
        if v >= 4:
            m[0x20] = min(sc.height, 255)
            m[0x21] = min(sc.width, 255)
        if v >= 5:
            self.ww(0x22, sc.width)
            self.ww(0x24, sc.height)
            m[0x26] = 1
            m[0x27] = 1
            m[0x2C] = 2
            m[0x2D] = 9
        m[0x32] = 1
        m[0x33] = 0

    def setup_alphabets(self):
        addr = self.rw(0x34) if self.version >= 5 else 0
        if addr:
            self.alpha = [list(self.mem[addr + 26 * i: addr + 26 * i + 26]) for i in range(3)]
        else:
            self.alpha = [[ord(c) for c in A0], [ord(c) for c in A1], [0, 13] + [ord(c) for c in A2]]
        self.alpha_rev = {}
        for a in (2, 1, 0):
            for i, z in enumerate(self.alpha[a]):
                if a == 2 and i < 2:
                    continue
                self.alpha_rev[z] = (a, i + 6)

    def setup_unicode(self):
        table = None
        if self.version >= 5:
            ext = self.rw(0x36)
            if ext and self.rw(ext) >= 3:
                t = self.rw(ext + 6)
                if t:
                    table = [chr(self.rw(t + 1 + 2 * i)) for i in range(self.mem[t])]
        self.extra = table if table is not None else list(DEFAULT_EXTRA)
        self.uni_rev = {c: 155 + i for i, c in enumerate(self.extra)}

    def build_tables(self):
        v = self.version
        self.op2 = {
            1: self.op_je, 2: self.op_jl, 3: self.op_jg, 4: self.op_dec_chk, 5: self.op_inc_chk,
            6: self.op_jin, 7: self.op_test, 8: self.op_or, 9: self.op_and, 10: self.op_test_attr,
            11: self.op_set_attr, 12: self.op_clear_attr, 13: self.op_store, 14: self.op_insert_obj,
            15: self.op_loadw, 16: self.op_loadb, 17: self.op_get_prop, 18: self.op_get_prop_addr,
            19: self.op_get_next_prop, 20: self.op_add, 21: self.op_sub, 22: self.op_mul,
            23: self.op_div, 24: self.op_mod, 25: self.op_call_2s, 26: self.op_call_2n,
            27: self.op_nop, 28: self.op_throw,
        }
        self.op1 = {
            0: self.op_jz, 1: self.op_get_sibling, 2: self.op_get_child, 3: self.op_get_parent,
            4: self.op_get_prop_len, 5: self.op_inc, 6: self.op_dec, 7: self.op_print_addr,
            8: self.op_call_1s, 9: self.op_remove_obj, 10: self.op_print_obj, 11: self.ret,
            12: self.op_jump, 13: self.op_print_paddr, 14: self.op_load,
            15: self.op_not if v <= 4 else self.op_call_1n,
        }
        self.op0 = {
            0: self.op_rtrue, 1: self.op_rfalse, 2: self.op_print, 3: self.op_print_ret,
            4: self.op_nop, 5: self.op_save, 6: self.op_restore, 7: self.op_restart,
            8: self.op_ret_popped, 9: self.op_pop if v <= 4 else self.op_catch, 10: self.op_quit,
            11: self.op_new_line, 12: self.op_show_status, 13: self.op_verify, 15: self.op_piracy,
        }
        self.opvar = {
            0: self.op_call_vs, 1: self.op_storew, 2: self.op_storeb, 3: self.op_put_prop,
            4: self.op_read, 5: self.op_print_char, 6: self.op_print_num, 7: self.op_random,
            8: self.op_push, 9: self.op_pull, 10: self.op_split_window, 11: self.op_set_window,
            12: self.op_call_vs, 13: self.op_erase_window, 14: self.op_erase_line,
            15: self.op_set_cursor, 16: self.op_get_cursor, 17: self.op_nop, 18: self.op_nop,
            19: self.op_output_stream, 20: self.op_nop, 21: self.op_nop, 22: self.op_read_char,
            23: self.op_scan_table, 24: self.op_not, 25: self.op_call_vn, 26: self.op_call_vn,
            27: self.op_tokenise, 28: self.op_encode_text, 29: self.op_copy_table,
            30: self.op_print_table, 31: self.op_check_arg_count,
        }
        self.opext = {
            0: self.op_save, 1: self.op_restore, 2: self.op_log_shift, 3: self.op_art_shift,
            4: self.op_set_font, 9: self.op_save_undo, 10: self.op_restore_undo,
            11: self.op_print_unicode, 12: self.op_check_unicode, 13: self.op_nop,
        }

    # ---- memory
    def rw(self, a):
        return (self.mem[a] << 8) | self.mem[a + 1]

    def ww(self, a, v):
        self.mem[a] = (v >> 8) & 0xFF
        self.mem[a + 1] = v & 0xFF

    # ---- variables
    def read_var(self, v):
        if v == 0:
            st = self.frames[-1].stack
            if not st:
                # A few games pop more than they pushed (Seastalker does it on "go to
                # SCIMITAR" inside the Aquadome). Frotz and Infocom's interpreters keep a
                # routine's locals just below its stack, so the extra pop reads the last
                # local; do the same instead of stopping the game.
                locs = self.frames[-1].locals
                return locs[-1] if locs else 0
            return st.pop()
        if v < 16:
            return self.frames[-1].locals[v - 1]
        return self.rw(self.globals + 2 * (v - 16))

    def write_var(self, v, x):
        x &= 0xFFFF
        if v == 0:
            self.frames[-1].stack.append(x)
        elif v < 16:
            self.frames[-1].locals[v - 1] = x
        else:
            self.ww(self.globals + 2 * (v - 16), x)

    def peek_var(self, v):          # "indirect" variable reads don't pop the stack
        if v == 0:
            return self.frames[-1].stack[-1]
        return self.read_var(v)

    def poke_var(self, v, x):
        if v == 0:
            self.frames[-1].stack[-1] = x & 0xFFFF
        else:
            self.write_var(v, x)

    # ---- execution
    def run(self):
        while True:
            try:
                while True:
                    self.step()
            except Restart:
                self.screen.flush()
                self.reset(self.mem[0x11])
            except Quit:
                self.screen.flush()
                return
            finally:
                if self.transcript:
                    self.transcript.flush()

    def var_operands(self, pc, typebytes):
        m = self.mem
        ops = []
        for tb in typebytes:
            for shift in (6, 4, 2, 0):
                t = (tb >> shift) & 3
                if t == 3:
                    return ops, pc
                if t == 0:
                    ops.append((m[pc] << 8) | m[pc + 1])
                    pc += 2
                elif t == 1:
                    ops.append(m[pc])
                    pc += 1
                else:
                    ops.append(self.read_var(m[pc]))
                    pc += 1
        return ops, pc

    def step(self):
        m = self.mem
        start = pc = self.pc
        op = m[pc]
        pc += 1
        if op < 0x80:                                   # long form, 2OP
            a, b = m[pc], m[pc + 1]
            pc += 2
            if op & 0x40:
                a = self.read_var(a)
            if op & 0x20:
                b = self.read_var(b)
            args = (a, b)
            h = self.op2.get(op & 0x1F)
        elif op < 0xC0:
            if op == 0xBE and self.version >= 5:        # extended form
                num, tb = m[pc], m[pc + 1]
                pc += 2
                args, pc = self.var_operands(pc, (tb,))
                h = self.opext.get(num)
            else:                                       # short form
                t = (op >> 4) & 3
                if t == 3:
                    args = ()
                    h = self.op0.get(op & 0x0F)
                else:
                    if t == 0:
                        x = (m[pc] << 8) | m[pc + 1]
                        pc += 2
                    elif t == 1:
                        x = m[pc]
                        pc += 1
                    else:
                        x = self.read_var(m[pc])
                        pc += 1
                    args = (x,)
                    h = self.op1.get(op & 0x0F)
        else:                                           # variable form
            if op == 0xEC or op == 0xFA:
                tbs = (m[pc], m[pc + 1])
                pc += 2
            else:
                tbs = (m[pc],)
                pc += 1
            args, pc = self.var_operands(pc, tbs)
            h = (self.op2 if op < 0xE0 else self.opvar).get(op & 0x1F)
        if h is None:
            raise ZError("Illegal opcode 0x%02x at 0x%05x" % (op, start))
        self.pc = pc
        h(*args)

    def store(self, value):
        var = self.mem[self.pc]
        self.pc += 1
        self.write_var(var, value)

    def branch(self, cond):
        m = self.mem
        b = m[self.pc]
        self.pc += 1
        if b & 0x40:
            off = b & 0x3F
        else:
            off = ((b & 0x3F) << 8) | m[self.pc]
            self.pc += 1
            if off & 0x2000:
                off -= 0x4000
        if bool(cond) == bool(b & 0x80):
            if off == 0:
                self.ret(0)
            elif off == 1:
                self.ret(1)
            else:
                self.pc += off - 2

    def call(self, paddr, args, store):
        if paddr == 0:
            if store is not None:
                self.write_var(store, 0)
            return
        addr = paddr * self.pscale + self.routine_off
        n = self.mem[addr]
        addr += 1
        if self.version <= 4:
            locs = [self.rw(addr + 2 * i) for i in range(n)]
            addr += 2 * n
        else:
            locs = [0] * n
        for i, a in enumerate(args[:n]):
            locs[i] = a
        self.frames.append(Frame(self.pc, locs, store, len(args)))
        self.pc = addr

    def call_now(self, paddr):
        """Run a routine to completion right away (an input timer) and return its value."""
        if paddr == 0:
            return 0
        depth = len(self.frames)
        self.call(paddr, [], None)
        while len(self.frames) > depth:
            self.step()
        return self.last_ret

    def ret(self, value):
        self.last_ret = value
        f = self.frames.pop()
        self.pc = f.ret_pc
        if f.store is not None:
            self.write_var(f.store, value)

    def read_store_var(self):
        v = self.mem[self.pc]
        self.pc += 1
        return v

    # ---- text
    def zscii_char(self, z):
        if z == 13 or z == 10:
            return "\n"
        if 32 <= z <= 126:
            return chr(z)
        if 155 <= z < 155 + len(self.extra):
            return self.extra[z - 155]
        return ""

    def to_zscii(self, ch):
        if ch == "\n":
            return 13
        o = ord(ch)
        if 32 <= o <= 126:
            return o
        return self.uni_rev.get(ch, ord("?"))

    def decode(self, addr):
        """Decode the Z-string at addr; returns (text, address after the string)."""
        zc = []
        while True:
            w = self.rw(addr)
            addr += 2
            zc += ((w >> 10) & 31, (w >> 5) & 31, w & 31)
            if w & 0x8000 or addr >= len(self.mem):
                break
        return self.zchars_to_str(zc), addr

    def zchars_to_str(self, zc):
        out = []
        alpha = 0
        i, n = 0, len(zc)
        while i < n:
            c = zc[i]
            i += 1
            if c == 0:
                out.append(" ")
            elif c <= 3:
                if i < n:
                    idx = 32 * (c - 1) + zc[i]
                    i += 1
                    out.append(self.decode(self.rw(self.abbrevs + 2 * idx) * 2)[0])
            elif c == 4:
                alpha = 1
                continue
            elif c == 5:
                alpha = 2
                continue
            elif alpha == 2 and c == 6:
                if i + 1 < n:
                    out.append(self.zscii_char((zc[i] << 5) | zc[i + 1]))
                i += 2
            elif alpha == 2 and c == 7:
                out.append("\n")
            else:
                out.append(self.zscii_char(self.alpha[alpha][c - 6]))
            alpha = 0
        return "".join(out)

    def encode_word(self, zs):
        nz = 6 if self.version <= 3 else 9
        out = []
        for z in zs:
            if z in self.alpha_rev:
                a, c = self.alpha_rev[z]
                if a:
                    out.append(3 + a)
                out.append(c)
            else:
                out += [5, 6, (z >> 5) & 31, z & 31]
            if len(out) >= nz:
                break
        out = (out + [5] * nz)[:nz]
        words = [(out[i] << 10) | (out[i + 1] << 5) | out[i + 2] for i in range(0, nz, 3)]
        words[-1] |= 0x8000
        return struct.pack(">%dH" % len(words), *words)

    def out(self, s):
        if not s:
            return
        if self.mem_streams:
            t = self.mem_streams[-1]
            for ch in s:
                self.mem[t[0] + 2 + t[1]] = self.to_zscii(ch)
                t[1] += 1
            return
        if self.window == 1:
            self.screen.upper_write(s)
            return
        if self.stream1:
            self.screen.write(s)
        self.sync_transcript()
        if self.transcript:
            self.transcript.write(s)

    def sync_transcript(self):
        """Open or close the transcript to match header bit Flags2.0. Older games
        (e.g. Infocom v3) turn scripting on by setting this bit directly."""
        want = self.mem[0x11] & 1
        if want and not self.transcript:
            path = os.path.splitext(self.story_path)[0] + ".transcript.txt"
            try:
                self.transcript = open(path, "a", encoding="utf-8")
            except OSError as e:
                self.mem[0x11] &= 0xFE
                self.screen.write("[Could not open transcript: %s]\n" % e)
        elif not want and self.transcript:
            self.transcript.close()
            self.transcript = None

    # ---- objects
    def oaddr(self, o):
        return self.obj_base + (o - 1) * self.obj_entry

    def orel(self, o, which):               # 0 parent, 1 sibling, 2 child
        if o == 0:
            return 0
        a = self.oaddr(o)
        return self.mem[a + 4 + which] if self.version <= 3 else self.rw(a + 6 + 2 * which)

    def set_orel(self, o, which, val):
        a = self.oaddr(o)
        if self.version <= 3:
            self.mem[a + 4 + which] = val
        else:
            self.ww(a + 6 + 2 * which, val)

    def prop_table(self, o):
        a = self.oaddr(o)
        return self.rw(a + 7) if self.version <= 3 else self.rw(a + 12)

    def obj_name(self, o):
        if o == 0:
            return ""
        p = self.prop_table(o)
        return self.decode(p + 1)[0] if self.mem[p] else ""

    def props(self, o):
        """Yield (number, data address, length) for each property of object o."""
        m = self.mem
        a = self.prop_table(o)
        a += 1 + 2 * m[a]
        while True:
            b = m[a]
            if b == 0:
                return
            if self.version <= 3:
                num, ln = b & 31, (b >> 5) + 1
                a += 1
            else:
                num = b & 63
                if b & 0x80:
                    ln = (m[a + 1] & 63) or 64
                    a += 2
                else:
                    ln = 2 if b & 0x40 else 1
                    a += 1
            yield num, a, ln
            a += ln

    def find_prop(self, o, prop):
        if o == 0:
            return 0, 0
        for num, a, ln in self.props(o):
            if num == prop:
                return a, ln
            if num < prop:
                break
        return 0, 0

    def remove_obj(self, o):
        p = self.orel(o, 0)
        if p == 0:
            return
        s = self.orel(o, 1)
        c = self.orel(p, 2)
        if c == o:
            self.set_orel(p, 2, s)
        else:
            while c:
                nxt = self.orel(c, 1)
                if nxt == o:
                    self.set_orel(c, 1, s)
                    break
                c = nxt
        self.set_orel(o, 0, 0)
        self.set_orel(o, 1, 0)

    # ---- 2OP
    def op_je(self, a, *rest):
        self.branch(a in rest)

    def op_jl(self, a, b):
        self.branch(s16(a) < s16(b))

    def op_jg(self, a, b):
        self.branch(s16(a) > s16(b))

    def op_dec_chk(self, var, val):
        x = (self.peek_var(var) - 1) & 0xFFFF
        self.poke_var(var, x)
        self.branch(s16(x) < s16(val))

    def op_inc_chk(self, var, val):
        x = (self.peek_var(var) + 1) & 0xFFFF
        self.poke_var(var, x)
        self.branch(s16(x) > s16(val))

    def op_jin(self, a, b):
        self.branch(self.orel(a, 0) == b)

    def op_test(self, a, b):
        self.branch(a & b == b)

    def op_or(self, a, b):
        self.store(a | b)

    def op_and(self, a, b):
        self.store(a & b)

    def op_test_attr(self, o, attr):
        if o == 0:
            return self.branch(False)
        self.branch(self.mem[self.oaddr(o) + attr // 8] & (0x80 >> (attr & 7)))

    def op_set_attr(self, o, attr):
        if o:
            self.mem[self.oaddr(o) + attr // 8] |= 0x80 >> (attr & 7)

    def op_clear_attr(self, o, attr):
        if o:
            self.mem[self.oaddr(o) + attr // 8] &= ~(0x80 >> (attr & 7)) & 0xFF

    def op_store(self, var, val):
        self.poke_var(var, val)

    def op_insert_obj(self, o, dest):
        if o == 0 or dest == 0:
            return
        self.remove_obj(o)
        self.set_orel(o, 1, self.orel(dest, 2))
        self.set_orel(dest, 2, o)
        self.set_orel(o, 0, dest)

    def op_loadw(self, a, i):
        self.store(self.rw((a + 2 * i) & 0xFFFF))

    def op_loadb(self, a, i):
        self.store(self.mem[(a + i) & 0xFFFF])

    def op_get_prop(self, o, prop):
        a, ln = self.find_prop(o, prop)
        if a == 0:
            self.store(self.rw(self.obj_table + 2 * (prop - 1)))
        elif ln == 1:
            self.store(self.mem[a])
        else:
            self.store(self.rw(a))

    def op_get_prop_addr(self, o, prop):
        self.store(self.find_prop(o, prop)[0])

    def op_get_next_prop(self, o, prop):
        if o == 0:
            return self.store(0)
        it = self.props(o)
        if prop == 0:
            nxt = next(it, None)
            return self.store(nxt[0] if nxt else 0)
        for num, a, ln in it:
            if num == prop:
                nxt = next(it, None)
                return self.store(nxt[0] if nxt else 0)
        self.store(0)

    def op_add(self, a, b):
        self.store(s16(a) + s16(b))

    def op_sub(self, a, b):
        self.store(s16(a) - s16(b))

    def op_mul(self, a, b):
        self.store(s16(a) * s16(b))

    def op_div(self, a, b):
        a, b = s16(a), s16(b)
        if b == 0:
            raise ZError("Division by zero")
        q = abs(a) // abs(b)
        self.store(q if (a < 0) == (b < 0) else -q)

    def op_mod(self, a, b):
        a, b = s16(a), s16(b)
        if b == 0:
            raise ZError("Division by zero")
        r = abs(a) % abs(b)
        self.store(-r if a < 0 else r)

    def op_call_2s(self, r, a):
        self.call(r, [a], self.read_store_var())

    def op_call_2n(self, r, a):
        self.call(r, [a], None)

    def op_throw(self, value, frame_id):
        del self.frames[frame_id:]
        self.ret(value)

    # ---- 1OP
    def op_jz(self, a):
        self.branch(a == 0)

    def op_get_sibling(self, o):
        s = self.orel(o, 1)
        self.store(s)
        self.branch(s)

    def op_get_child(self, o):
        c = self.orel(o, 2)
        self.store(c)
        self.branch(c)

    def op_get_parent(self, o):
        self.store(self.orel(o, 0))

    def op_get_prop_len(self, addr):
        if addr == 0:
            return self.store(0)
        b = self.mem[addr - 1]
        if self.version <= 3:
            self.store((b >> 5) + 1)
        elif b & 0x80:
            self.store((b & 63) or 64)
        else:
            self.store(2 if b & 0x40 else 1)

    def op_inc(self, var):
        self.poke_var(var, self.peek_var(var) + 1)

    def op_dec(self, var):
        self.poke_var(var, self.peek_var(var) - 1)

    def op_print_addr(self, a):
        self.out(self.decode(a)[0])

    def op_call_1s(self, r):
        self.call(r, [], self.read_store_var())

    def op_call_1n(self, r):
        self.call(r, [], None)

    def op_remove_obj(self, o):
        if o:
            self.remove_obj(o)

    def op_print_obj(self, o):
        self.out(self.obj_name(o))

    def op_jump(self, off):
        self.pc += s16(off) - 2

    def op_print_paddr(self, p):
        self.out(self.decode(p * self.pscale + self.string_off)[0])

    def op_load(self, var):
        self.store(self.peek_var(var))

    def op_not(self, a):
        self.store(~a & 0xFFFF)

    # ---- 0OP
    def op_rtrue(self):
        self.ret(1)

    def op_rfalse(self):
        self.ret(0)

    def op_print(self):
        s, self.pc = self.decode(self.pc)
        self.out(s)

    def op_print_ret(self):
        self.op_print()
        self.out("\n")
        self.ret(1)

    def op_nop(self, *args):
        pass

    def op_restart(self):
        raise Restart()

    def op_ret_popped(self):
        self.ret(self.read_var(0))

    def op_pop(self):
        self.read_var(0)

    def op_catch(self):
        self.store(len(self.frames))

    def op_quit(self):
        raise Quit()

    def op_new_line(self):
        self.out("\n")

    def op_show_status(self):
        if self.version <= 3:
            self.show_status_line()

    def op_verify(self):
        flen = self.rw(0x1A) * self.pscale
        if flen == 0:
            return self.branch(True)
        self.branch(sum(self.story[0x40:flen]) & 0xFFFF == self.rw(0x1C))

    def op_piracy(self):
        self.branch(True)

    def show_status_line(self):
        if not self.screen.show_status:
            return
        g = lambda n: self.rw(self.globals + 2 * n)
        left = " " + self.obj_name(g(0))
        a, b = s16(g(1)), s16(g(2))
        if self.mem[1] & 0x02:
            right = "Time: %d:%02d %s " % ((a % 12) or 12, b, "pm" if a >= 12 else "am")
        else:
            right = "Score: %d  Moves: %d " % (a, b)
        w = self.screen.width - 1
        self.screen.status_row(left[: w - len(right) - 1].ljust(w - len(right)) + right)

    # ---- VAR
    def op_call_vs(self, r, *args):
        self.call(r, list(args), self.read_store_var())

    def op_call_vn(self, r, *args):
        self.call(r, list(args), None)

    def op_storew(self, a, i, v):
        self.ww((a + 2 * i) & 0xFFFF, v)

    def op_storeb(self, a, i, v):
        self.mem[(a + i) & 0xFFFF] = v & 0xFF

    def op_put_prop(self, o, prop, val):
        a, ln = self.find_prop(o, prop)
        if a == 0:
            return
        if ln == 1:
            self.mem[a] = val & 0xFF
        else:
            self.ww(a, val)

    def op_read(self, text, parse=0, time=0, routine=0):
        v = self.version
        if v <= 3:
            self.show_status_line()
        self.screen.show_upper()
        if self.debug:
            self.show_debug()
        while True:
            line = self.screen.read_line()
            cmd = line.strip().lower()
            if cmd == "/help":                  # commands for zplay itself, not the game
                self.debug_lines(["/debug  show the location's object tree before each prompt"
                                  " (reveals hidden objects)", "/help   show this"],
                                 prefix="[zplay] ")
            elif cmd == "/debug":
                self.debug = not self.debug
                self.debug_lines(["debug view " + ("on" if self.debug else "off")])
                if self.debug:
                    self.show_debug()
            else:
                break
            sys.stdout.write(">")
        self.finish_read(text, parse, line)

    def finish_read(self, text, parse, line):
        """The second half of read: hand the typed line to the game."""
        v = self.version
        self.sync_transcript()
        if self.transcript:
            self.transcript.write(line + "\n")
        zs = [self.to_zscii(c) for c in line.lower()]
        m = self.mem
        if v <= 4:
            zs = zs[: max(m[text] - 1, 0)]
            for i, z in enumerate(zs):
                m[text + 1 + i] = z
            m[text + 1 + len(zs)] = 0
        else:
            existing = m[text + 1]
            zs = zs[: max(m[text] - existing, 0)]
            for i, z in enumerate(zs):
                m[text + 2 + existing + i] = z
            m[text + 1] = existing + len(zs)
        if parse:
            self.tokenise(text, parse)
        if v >= 5:
            self.store(13)

    def op_print_char(self, z):
        self.out(self.zscii_char(z))

    def op_print_num(self, v):
        self.out(str(s16(v)))

    def op_random(self, r):
        r = s16(r)
        if r > 0:
            self.store(self.rng.randint(1, r))
        else:
            self.rng.seed(-r if r < 0 else None)
            self.store(0)

    def op_push(self, v):
        self.write_var(0, v)

    def op_pull(self, var):
        value = self.read_var(0)
        self.poke_var(var, value)

    def op_split_window(self, n):
        self.screen.split(n)

    def op_set_window(self, w):
        self.window = w
        if w == 1:
            self.screen.cur_row, self.screen.cur_col = 1, 1

    def op_erase_window(self, w):
        w = s16(w)
        if w == -1:
            self.screen.split(0)
            self.screen.erase_upper()
            self.window = 0
        elif w in (-2, 1):
            self.screen.erase_upper()

    def op_erase_line(self, val=1):
        if self.window == 1 and val == 1:
            self.screen.erase_line()

    def op_set_cursor(self, line, col=1, *rest):
        if self.window == 1 and s16(line) > 0:
            self.screen.cur_row, self.screen.cur_col = line, col

    def op_get_cursor(self, arr):
        if self.window == 1:
            self.ww(arr, self.screen.cur_row)
            self.ww(arr + 2, self.screen.cur_col)
        else:
            self.ww(arr, self.screen.height)
            self.ww(arr + 2, self.screen.col + len(self.screen.pending) + 1)

    def op_output_stream(self, n, table=0, width=0):
        n = s16(n)
        if n == 1:
            self.stream1 = True
        elif n == -1:
            self.stream1 = False
        elif n == 2:
            self.mem[0x11] |= 1
            self.sync_transcript()
        elif n == -2:
            self.mem[0x11] &= 0xFE
            self.sync_transcript()
        elif n == 3:
            if len(self.mem_streams) >= 16:
                raise ZError("Too many nested output streams")
            self.mem_streams.append([table, 0])
        elif n == -3:
            if self.mem_streams:
                t, count = self.mem_streams.pop()
                self.ww(t, count)

    def op_read_char(self, dev=1, time=0, routine=0, *rest):
        self.screen.show_upper()
        if time and routine:
            # Timed key read: every time/10 seconds with no key pressed, call the timer
            # routine; if it returns true, stop waiting and return 0. (Border Zone moves you
            # along this way while you run across the border zone.) The cap stops a game
            # whose routine never says "stop" from waiting forever on a script.
            for _ in range(2000):
                if self.screen.key_ready(time / 10):
                    break
                if self.call_now(routine):
                    self.store(0)
                    return
        ch = self.screen.read_char()
        if ch in ("\r", "\n"):
            z = 13
        elif ch in ("\x7f", "\x08"):
            z = 8
        elif ch == "\x1b":
            z = 27
        elif "\x81" <= ch <= "\x84":
            z = 129 + ord(ch) - 0x81
        else:
            z = self.to_zscii(ch)
        self.store(z)

    def op_scan_table(self, x, table, length, form=0x82):
        size, word = form & 0x7F, form & 0x80
        a = table
        for _ in range(length):
            if (self.rw(a) if word else self.mem[a]) == x:
                self.store(a)
                return self.branch(True)
            a += size
        self.store(0)
        self.branch(False)

    def tokenise(self, text, parse, dictionary=0, flag=0):
        m = self.mem
        if self.version >= 5:
            start = text + 2
            chars = list(m[start: start + m[text + 1]])
        else:
            start = text + 1
            chars = []
            i = start
            while m[i] != 0:
                chars.append(m[i])
                i += 1
        seps, lookup = self.load_dict(dictionary or self.dict_addr)
        words = []
        i, n = 0, len(chars)
        while i < n:
            c = chars[i]
            if c == 32:
                i += 1
            elif c in seps:
                words.append((i, 1))
                i += 1
            else:
                j = i
                while j < n and chars[j] != 32 and chars[j] not in seps:
                    j += 1
                words.append((i, j - i))
                i = j
        words = words[: m[parse]]
        m[parse + 1] = len(words)
        for k, (off, ln) in enumerate(words):
            addr = lookup.get(self.encode_word(chars[off: off + ln]), 0)
            if flag and addr == 0:
                continue
            e = parse + 2 + 4 * k
            self.ww(e, addr)
            m[e + 2] = ln
            m[e + 3] = off + (start - text)

    def load_dict(self, addr):
        if addr in self.dict_cache:
            return self.dict_cache[addr]
        m = self.mem
        n = m[addr]
        seps = set(m[addr + 1: addr + 1 + n])
        a = addr + 1 + n
        elen = m[a]
        count = abs(s16(self.rw(a + 1)))
        a += 3
        keylen = 4 if self.version <= 3 else 6
        lookup = {}
        for i in range(count):
            e = a + i * elen
            lookup.setdefault(bytes(m[e: e + keylen]), e)
        # A dictionary in dynamic memory can be changed by the game (Beyond Zork adds
        # its magic words to one as they're learned), so only cache those in static memory.
        if addr >= self.static_base:
            self.dict_cache[addr] = (seps, lookup)
        return seps, lookup

    def op_tokenise(self, text, parse, dictionary=0, flag=0):
        self.tokenise(text, parse, dictionary, flag)

    def op_encode_text(self, ztext, length, frm, coded):
        enc = self.encode_word(list(self.mem[ztext + frm: ztext + frm + length]))
        self.mem[coded: coded + len(enc)] = enc

    def op_copy_table(self, first, second, size):
        size = s16(size)
        m = self.mem
        if second == 0:
            m[first: first + abs(size)] = bytes(abs(size))
        elif size < 0:
            for i in range(-size):
                m[second + i] = m[first + i]
        else:
            m[second: second + size] = bytes(m[first: first + size])

    def op_print_table(self, text, width, height=1, skip=0):
        sc = self.screen
        col = sc.cur_col
        for r in range(height):
            row = "".join(self.zscii_char(z) for z in self.mem[text: text + width])
            text += width + skip
            if self.window == 1:
                sc.upper_write(row)
                if r < height - 1:          # next line under the first; the cursor
                    sc.cur_row += 1         # stays after the text on the last one
                    sc.cur_col = col
            else:
                self.out(row + ("\n" if r < height - 1 else ""))

    def op_check_arg_count(self, n):
        self.branch(n <= self.frames[-1].argc)

    # ---- EXT
    def op_log_shift(self, n, places):
        p = s16(places)
        self.store(n << p if p >= 0 else n >> -p)

    def op_art_shift(self, n, places):
        p = s16(places)
        self.store(s16(n) << p if p >= 0 else s16(n) >> -p)

    def op_set_font(self, f):
        if f == 0:
            self.store(self.font)
        elif f in (1, 4):
            prev, self.font = self.font, f
            self.store(prev)
        else:
            self.store(0)

    def op_print_unicode(self, c):
        self.out(chr(c))

    def op_check_unicode(self, c):
        self.store(3 if c >= 32 else 0)

    # ---- debug view
    def debug_lines(self, lines, prefix="[debug] "):
        """Print lines straight to the terminal (not to the game's output or transcript)."""
        sc = self.screen
        if sc.col > 0:
            sys.stdout.write("\n")
            sc.col = 0
        for ln in lines:
            ln = prefix + ln
            sys.stdout.write("\x1b[2;33m%s\x1b[0m\n" % ln if sc.ansi else ln + "\n")
        sys.stdout.flush()

    def attrs(self, o):
        a, n = self.oaddr(o), 32 if self.version <= 3 else 48
        return [i for i in range(n) if self.mem[a + i // 8] & (0x80 >> (i & 7))]

    def debug_tree(self, o, depth=0, out=None, limit=60):
        """Lines describing object o's children, recursively."""
        out = [] if out is None else out
        c = self.orel(o, 2)
        while c and len(out) < limit:
            out.append("%s%d %r  attrs %s" % ("  " * (depth + 1), c, self.obj_name(c),
                                             ",".join(map(str, self.attrs(c))) or "-"))
            if depth < 4:
                self.debug_tree(c, depth + 1, out, limit)
            c = self.orel(c, 1)
        return out

    def debug_info(self):
        """Lines for the debug view. Global 0 is the location in v3; in v4+ it often is too."""
        try:
            loc = self.rw(self.globals)
            name = self.obj_name(loc) if 0 < loc < 2000 else ""
            if not name:
                return ["global 0 = %d (not an object, so the location isn't known)" % loc]
            label = "location" if self.version <= 3 else "global 0 (usually the location)"
            lines = ["%s: %d %r  parent %d  attrs %s" % (
                label, loc, name, self.orel(loc, 0), ",".join(map(str, self.attrs(loc))) or "-")]
            return lines + (self.debug_tree(loc) or ["  (nothing in it)"])
        except (IndexError, ZError) as e:
            return ["couldn't read the object tree: %s" % e]

    def show_debug(self):
        self.debug_lines(self.debug_info())

    # ---- undo / save / restore
    def snapshot(self):
        return (bytes(self.mem[: self.static_base]), [f.copy() for f in self.frames], self.pc)

    def restore_snapshot(self, dyn, frames, pc):
        keep = self.mem[0x11] & 3
        self.mem[: len(dyn)] = dyn
        self.mem[0x11] = (self.mem[0x11] & 0xFC) | keep
        self.write_header()
        self.frames = frames
        self.pc = pc

    def op_save_undo(self):
        self.undo_stack.append(self.snapshot())
        del self.undo_stack[:-20]
        self.store(1)

    def op_restore_undo(self):
        if not self.undo_stack:
            return self.store(0)
        dyn, frames, pc = self.undo_stack.pop()
        self.restore_snapshot(dyn, [f.copy() for f in frames], pc)
        self.store(2)

    def result(self, value):
        """Finish a save/restore: v1-3 branch, v4+ store."""
        if self.version <= 3:
            self.branch(value)
        else:
            self.store(value)

    def ask_filename(self, verb):
        default = os.path.splitext(self.story_path)[0] + ".sav"
        self.screen.write("%s file name [%s]: " % (verb, default))
        return self.screen.read_line().strip() or default

    def story_id(self):
        return [self.rw(2), bytes(self.mem[0x12:0x18]).decode("latin-1"), self.rw(0x1C)]

    def op_save(self, *aux):
        if aux:                                   # auxiliary-table saves: unsupported
            return self.store(0)
        name = self.ask_filename("Save")
        dyn, frames, pc = self.snapshot()
        state = {
            "format": "zplay-1",
            "story": self.story_id(),
            "dynamic": base64.b64encode(zlib.compress(dyn)).decode(),
            "frames": [[f.ret_pc, f.locals, f.store, f.stack, f.argc] for f in frames],
            "pc": pc,
        }
        try:
            with open(name, "w") as fh:
                json.dump(state, fh)
            ok = True
        except OSError as e:
            self.screen.write("[%s]\n" % e)
            ok = False
        self.result(1 if ok else 0)

    def op_restore(self, *aux):
        if aux:
            return self.store(0)
        name = self.ask_filename("Restore")
        try:
            with open(name) as fh:
                state = json.load(fh)
            if state.get("format") != "zplay-1" or state["story"] != self.story_id():
                raise ValueError("that save file is from a different game")
            dyn = zlib.decompress(base64.b64decode(state["dynamic"]))
            frames = [Frame(r, l, s, a, st) for r, l, s, st, a in state["frames"]]
        except (OSError, ValueError, KeyError, TypeError, IndexError, zlib.error) as e:
            self.screen.write("[Could not restore: %s]\n" % e)
            return self.result(0)
        self.restore_snapshot(dyn, frames, state["pc"])
        self.result(2 if self.version >= 4 else 1)


# --------------------------------------------------------------------------- main

def load_story(path):
    data = open(path, "rb").read()
    if data[:4] == b"FORM" and data[8:12] == b"IFRS":     # Blorb: pull out the ZCOD chunk
        i = 12
        while i + 8 <= len(data):
            cid, ln = data[i:i + 4], struct.unpack(">I", data[i + 4:i + 8])[0]
            if cid == b"ZCOD":
                return data[i + 8: i + 8 + ln]
            i += 8 + ln + (ln & 1)
        raise ZError("No Z-code found in Blorb file")
    return data


def main():
    ap = argparse.ArgumentParser(
        description="Play Z-machine (Infocom/Inform) story files.",
        epilog="While playing, type /debug to toggle the debug view, or /help.")
    ap.add_argument("story", help="story file (.z3, .z5, .z8, .zblorb ...)")
    ap.add_argument("--script", help="text file of commands to type, one per line")
    ap.add_argument("--no-status", action="store_true", help="don't print the status line")
    ap.add_argument("--width", type=int, help="screen width (default: terminal width)")
    ap.add_argument("--seed", type=int, help="random seed, for reproducible runs")
    ap.add_argument("--debug", action="store_true",
                    help="show the location's object tree before each prompt (also: type /debug)")
    args = ap.parse_args()

    size = shutil.get_terminal_size((80, 24))
    script = None
    if args.script:
        with open(args.script) as fh:
            script = [l.rstrip("\n") for l in fh]
    if sys.stdin.isatty():
        try:
            import readline  # noqa: F401  (gives input() line editing and history)
        except ImportError:
            pass
    screen = Screen(args.width or size.columns, size.lines, not args.no_status, script)
    zm = None
    try:
        zm = ZMachine(load_story(args.story), screen, args.story, args.seed, args.debug)
        zm.run()
    except ZError as e:
        screen.flush()
        print("\n[Z-machine error: %s]" % e)
        sys.exit(1)
    except KeyboardInterrupt:
        screen.flush()
        print()
    except OSError as e:
        screen.flush()
        print("\n[Error: %s]" % e)
        sys.exit(1)
    except Exception as e:
        # A bug in the interpreter or a malformed story: report it without a traceback.
        screen.flush()
        where = " at pc 0x%05x" % zm.pc if zm else ""
        print("\n[Interpreter error%s: %s: %s]" % (where, type(e).__name__, e))
        sys.exit(1)
    finally:
        if zm and zm.transcript:
            zm.transcript.close()


if __name__ == "__main__":
    main()