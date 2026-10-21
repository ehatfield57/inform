#!/usr/bin/env python3
"""
zmap_pdf.py - turn a zplay_llm map file (<story>.map.json) into a PDF.

    python3 zmap_pdf.py zork1.map.json            # writes zork1.map.pdf
    python3 zmap_pdf.py zork1.z3                  # same: finds zork1.map.json next to it
                                                  # (or zork1-r88-840726.map.json if
                                                  #  that is the one for this game)
    python3 zmap_pdf.py zork1.map.json -o mymap.pdf --title "Zork I"

Page 1 is a drawn map. Rooms are laid out by compass direction (north is up, east is
right), each box showing the room's name, a reference number, and the items seen there.
Game maps often aren't regular (going east then west doesn't always lead back), so
when a room can't sit where its directions say, it goes in the nearest free spot
and the connecting line is simply longer.

    plain line          walked both ways
    arrow               only walked this way so far (or a one-way passage)
    blue labelled line  up, down, in, out, and exits like "enter window"
    stub with ?         a direction the room's description mentions but not yet tried
    stub with x         a direction that was tried and led nowhere
    thick border        where you were when the map was last saved

The pages after it list every room (exits, blocked and untried directions, items) and
every item with where it was last seen.

Standard library only: the PDF is written directly, using the built-in Helvetica font.
"""

import argparse
import json
import os
import sys
import time
import zlib

# --------------------------------------------------------------------------- PDF writing

# Helvetica character widths (per 1000 units of font size) for ASCII 32-126, from the
# standard font metrics. Used to measure text for wrapping and centring.
_HELV = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]


def text_width(s, size, bold=False):
    w = sum(_HELV[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in s)
    return w * size / 1000 * (1.06 if bold else 1.0)


def wrap(s, size, width, bold=False):
    """Split s into lines no wider than width (a single long word is cut)."""
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if text_width(trial, size, bold) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        while text_width(word, size, bold) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size, bold) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def pdf_string(s):
    b = s.encode("cp1252", errors="replace")
    return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


class Canvas:
    """One page. Coordinates are in points with (0, 0) at the TOP left, y growing down."""

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.ops = []

    def _y(self, y):
        return self.height - y

    def _op(self, s):
        self.ops.append(s.encode("latin-1") if isinstance(s, str) else s)

    def _style(self, stroke=None, fill=None, width=None, dash=None):
        if stroke is not None:
            self._op("%.3f %.3f %.3f RG" % stroke)
        if fill is not None:
            self._op("%.3f %.3f %.3f rg" % fill)
        if width is not None:
            self._op("%.2f w" % width)
        self._op("[%s] 0 d" % " ".join("%.1f" % d for d in dash) if dash else "[] 0 d")

    def line(self, x1, y1, x2, y2, color=(0, 0, 0), width=1.0, dash=None):
        self._style(stroke=color, width=width, dash=dash)
        self._op("%.2f %.2f m %.2f %.2f l S" % (x1, self._y(y1), x2, self._y(y2)))

    def polygon(self, pts, fill=(0, 0, 0)):
        self._style(fill=fill)
        path = " ".join("%.2f %.2f %s" % (x, self._y(y), "m" if i == 0 else "l")
                        for i, (x, y) in enumerate(pts))
        self._op(path + " h f")

    def rect(self, x, y, w, h, stroke=(0, 0, 0), fill=None, width=1.0, radius=0.0, dash=None):
        self._style(stroke=stroke, fill=fill, width=width, dash=dash)
        r, k = min(radius, w / 2, h / 2), 0.5523
        X, Y = x, self._y(y + h)                      # bottom-left in PDF coordinates
        if r <= 0:
            self._op("%.2f %.2f %.2f %.2f re" % (X, Y, w, h))
        else:
            c = r * (1 - k)
            self._op(" ".join([
                "%.2f %.2f m" % (X + r, Y),
                "%.2f %.2f l" % (X + w - r, Y),
                "%.2f %.2f %.2f %.2f %.2f %.2f c" % (X + w - c, Y, X + w, Y + c, X + w, Y + r),
                "%.2f %.2f l" % (X + w, Y + h - r),
                "%.2f %.2f %.2f %.2f %.2f %.2f c" % (X + w, Y + h - c, X + w - c, Y + h, X + w - r, Y + h),
                "%.2f %.2f l" % (X + r, Y + h),
                "%.2f %.2f %.2f %.2f %.2f %.2f c" % (X + c, Y + h, X, Y + h - c, X, Y + h - r),
                "%.2f %.2f l" % (X, Y + r),
                "%.2f %.2f %.2f %.2f %.2f %.2f c h" % (X, Y + c, X + c, Y, X + r, Y)]))
        self._op("B" if fill is not None and stroke is not None else "f" if fill is not None else "S")

    def text(self, x, y, s, size=10.0, bold=False, color=(0, 0, 0), align="left"):
        """Draw s with its baseline at y. align: left, center or right of x."""
        if align != "left":
            w = text_width(s, size, bold)
            x -= w / 2 if align == "center" else w
        self._style(fill=color)
        self._op(b"BT /%s %.2f Tf %.2f %.2f Td " % (b"F2" if bold else b"F1", size, x, self._y(y))
                 + pdf_string(s) + b" Tj ET")

    def content(self):
        return b"\n".join(self.ops)


def write_pdf(path, pages, title):
    """Write the Canvas pages to path as a PDF file."""
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            5: b"<< /Title " + pdf_string(title) + b" /Producer (zmap_pdf.py) /CreationDate (D:"
               + time.strftime("%Y%m%d%H%M%S").encode() + b") >>"}
    kids, n = [], 6
    for page in pages:
        data = zlib.compress(page.content())
        objs[n] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font "
                   b"<< /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>"
                   % (round(page.width), round(page.height), n + 1))
        objs[n + 1] = (b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data)
                       + data + b"\nendstream")
        kids.append(n)
        n += 2
    objs[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), {}
    for i in range(1, n):
        offsets[i] = len(out)
        out += b"%d 0 obj\n" % i + objs[i] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % n
    for i in range(1, n):
        out += b"%010d 00000 n \n" % offsets[i]
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xref)
    with open(path, "wb") as fh:
        fh.write(out)


# --------------------------------------------------------------------------- the map data

VEC = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
       "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "northeast": "southwest", "southwest": "northeast", "northwest": "southeast",
            "southeast": "northwest", "up": "down", "down": "up", "in": "out", "out": "in"}


class GameMap:
    def __init__(self, data):
        self.rooms = data.get("rooms", {})
        self.items = data.get("items", {})
        self.here = data.get("here")
        for r in self.rooms.values():
            for key in ("exits", "guess"):
                r.setdefault(key, {})
            for key in ("blocked", "mentioned"):
                r.setdefault(key, [])
        # Only real exits between rooms we know about (and not a room to itself).
        self.edges = [(a, cmd, b) for a, r in self.rooms.items()
                      for cmd, b in r["exits"].items() if b in self.rooms and b != a]
        self.pos = {}
        self.number = {}

    def name(self, r):
        return self.rooms.get(r, {}).get("name", "?")

    def label(self, r):
        return "%s (#%d)" % (self.name(r), self.number[r]) if r in self.number else self.name(r)

    def room_items(self, r):
        return [it for it in self.items.values()
                if it.get("room") == r and not it.get("carried") and not it.get("missing")]

    def carried(self):
        return [it for it in self.items.values() if it.get("carried")]

    # ---- layout on a grid of cells
    def layout(self):
        """Try building the layout from each room in turn and keep the tidiest result."""
        nbrs = {r: [] for r in self.rooms}
        for a, cmd, b in self.edges:                 # both ends, so either can place the other
            v = VEC.get(cmd)
            nbrs[a].append((b, v))
            nbrs[b].append((a, (-v[0], -v[1]) if v else None))
        best = None
        for seed in list(self.rooms)[:60]:
            pos = self.build(seed, nbrs)
            score = self.score(pos)
            if best is None or score < best[0]:
                best = (score, pos)
        pos = best[1]
        minx = min(p[0] for p in pos.values())       # shift so the top-left cell is (0, 0)
        miny = min(p[1] for p in pos.values())
        self.pos = {r: (x - minx, y - miny) for r, (x, y) in pos.items()}
        for i, r in enumerate(sorted(self.pos, key=lambda r: (self.pos[r][1], self.pos[r][0])), 1):
            self.number[r] = i

    def build(self, seed, nbrs):
        """Place rooms outward from seed, each at the cell its direction says (or the
        nearest free one). Parts of the map not connected to the rest go to the right."""
        pos, used = {}, {}
        order = [seed] + [r for r in self.rooms if r != seed]
        for start in order:
            if start in pos:
                continue
            col = max(p[0] for p in pos.values()) + 2 if pos else 0
            self.place(start, (col, 0), pos, used)
            queue = [start]
            while queue:
                r = queue.pop(0)
                # compass neighbours first, so special exits fill in around them
                for b, v in sorted(nbrs[r], key=lambda t: t[1] is None):
                    if b in pos:
                        continue
                    x, y = pos[r]
                    target = (x + v[0], y + v[1]) if v else (x + 1, y + 1)
                    self.place(b, self.free_near(target, (x, y), used), pos, used)
                    queue.append(b)
        return pos

    def score(self, pos):
        """Lower is tidier: total line length, plus a penalty for each line that runs
        through another room's box, plus a little for the overall size."""
        total = 0.0
        cells = list(pos.items())
        for a, cmd, b in self.edges:
            (x1, y1), (x2, y2) = pos[a], pos[b]
            dx, dy = x2 - x1, y2 - y1
            total += (dx * dx + dy * dy) ** 0.5
            v = VEC.get(cmd)
            if v and (dx, dy) != v:
                total += 1.5                         # not where the direction says
            seg = dx * dx + dy * dy
            for r, (cx, cy) in cells:
                if r in (a, b) or not seg:
                    continue
                t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / seg))
                px, py = x1 + t * dx - cx, y1 + t * dy - cy
                if abs(px) < 0.45 and abs(py) < 0.4:
                    total += 6
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        return total + 0.3 * ((max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1))

    @staticmethod
    def place(r, cell, pos, used):
        pos[r] = cell
        used[cell] = r

    @staticmethod
    def free_near(target, origin, used):
        if target not in used:
            return target
        for radius in range(1, 50):
            ring = [(target[0] + dx, target[1] + dy)
                    for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)
                    if max(abs(dx), abs(dy)) == radius]
            ring = [c for c in ring if c not in used]
            if ring:
                return min(ring, key=lambda c: ((c[0] - target[0]) ** 2 + (c[1] - target[1]) ** 2,
                                                (c[0] - origin[0]) ** 2 + (c[1] - origin[1]) ** 2))
        raise RuntimeError("no room on the grid")


# --------------------------------------------------------------------------- page 1: the map

CELL_W, CELL_H = 175, 122          # grid spacing
BOX_W, BOX_H = 132, 78             # room box size
MARGIN, HEADER, FOOTER = 40, 56, 78
INK = (0.13, 0.13, 0.15)
GREY = (0.55, 0.55, 0.58)
SPECIAL = (0.12, 0.38, 0.75)       # up/down/in/out and other named exits
BLOCKED = (0.75, 0.25, 0.2)
HERE_FILL = (1.0, 0.96, 0.82)
BOX_FILL = (0.97, 0.97, 0.98)


def draw_map(gm, title):
    cols = max(p[0] for p in gm.pos.values()) + 1
    rows = max(p[1] for p in gm.pos.values()) + 1
    width = max(792, cols * CELL_W + 2 * MARGIN)
    height = max(612, rows * CELL_H + 2 * MARGIN + HEADER + FOOTER)
    c = Canvas(width, height)
    left = (width - cols * CELL_W) / 2
    top = MARGIN + HEADER + (height - 2 * MARGIN - HEADER - FOOTER - rows * CELL_H) / 2

    def center(r):
        x, y = gm.pos[r]
        return left + x * CELL_W + CELL_W / 2, top + y * CELL_H + CELL_H / 2

    def anchor(r, d):
        cx, cy = center(r)
        v = VEC[d]
        return cx + v[0] * BOX_W / 2, cy + v[1] * BOX_H / 2

    def edge_point(r, toward):
        """Where the line from r's centre toward a point leaves r's box."""
        cx, cy = center(r)
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == dy == 0:
            return cx, cy
        t = min(BOX_W / 2 / abs(dx) if dx else 1e9, BOX_H / 2 / abs(dy) if dy else 1e9)
        return cx + dx * t, cy + dy * t

    c.text(MARGIN, MARGIN + 14, title, size=18, bold=True, color=INK)
    carried = ", ".join(it["name"] for it in gm.carried()) or "nothing"
    c.text(MARGIN, MARGIN + 32, "%d rooms   ·   carrying: %s" % (len(gm.rooms), carried),
           size=9.5, color=GREY)

    # --- connections (drawn first, so boxes sit on top)
    attached = set()                                 # (room, direction) where a line meets a box
    for a, cmd, b in gm.edges:
        if cmd in VEC:
            attached.add((a, cmd))
            attached.add((b, OPPOSITE[cmd]))
    done = set()
    labels = []
    for a, cmd, b in gm.edges:
        if (a, cmd, b) in done:
            continue
        done.add((a, cmd, b))
        if cmd in VEC:
            back = OPPOSITE[cmd]
            two_way = gm.rooms[b]["exits"].get(back) == a
            if two_way:
                done.add((b, back, a))
            p1 = anchor(a, cmd)
            p2 = anchor(b, back) if back in VEC else edge_point(b, center(a))
            c.line(p1[0], p1[1], p2[0], p2[1], color=INK, width=1.3)
            if not two_way:
                arrowhead(c, p1, p2, INK)
        else:
            back = next((k for k, v in gm.rooms[b]["exits"].items()
                         if v == a and k not in VEC and (b, k, a) not in done), None)
            p1, p2 = edge_point(a, center(b)), edge_point(b, center(a))
            c.line(p1[0], p1[1], p2[0], p2[1], color=SPECIAL, width=1.2, dash=(4, 2))
            labels.append((p1, p2, cmd))
            if back:
                done.add((b, back, a))
                labels.append((p2, p1, back))
            else:
                arrowhead(c, p1, p2, SPECIAL)
    for p_from, p_to, cmd in labels:                 # labels near the end you leave from
        x = p_from[0] + (p_to[0] - p_from[0]) * 0.28
        y = p_from[1] + (p_to[1] - p_from[1]) * 0.28
        w = text_width(cmd, 7.5) + 6
        c.rect(x - w / 2, y - 6, w, 11, stroke=None, fill=(1, 1, 1))
        c.text(x, y + 2.6, cmd, size=7.5, color=SPECIAL, align="center")

    # --- stubs for blocked and not-yet-tried directions
    for r, d in gm.rooms.items():
        if r not in gm.pos:
            continue
        for dirn in VEC:
            if dirn in d["exits"] or (r, dirn) in attached:
                continue
            if dirn in d["blocked"]:
                stub(c, anchor(r, dirn), VEC[dirn], BLOCKED, "x")
            elif dirn in d["mentioned"] and dirn not in d["guess"]:
                stub(c, anchor(r, dirn), VEC[dirn], GREY, "?")

    # --- rooms
    for r in gm.pos:
        cx, cy = center(r)
        x0, y0 = cx - BOX_W / 2, cy - BOX_H / 2
        here = r == gm.here
        c.rect(x0, y0, BOX_W, BOX_H, stroke=INK, fill=HERE_FILL if here else BOX_FILL,
               width=2.6 if here else 1.0, radius=7)
        c.text(x0 + BOX_W - 5, y0 + 10, "#%d" % gm.number[r], size=6.5, color=GREY, align="right")
        if here:
            c.text(x0 + 5, y0 + 10, "you were here", size=6.5, bold=True, color=BLOCKED)
        y = y0 + 23
        for ln in wrap(gm.name(r), 9.5, BOX_W - 12, bold=True)[:2]:
            c.text(cx, y, ln, size=9.5, bold=True, color=INK, align="center")
            y += 11
        items = [it["name"] for it in gm.room_items(r)]
        room_left = int((y0 + BOX_H - 4 - y) // 8.5)
        shown = items if len(items) <= room_left else items[:max(room_left - 1, 0)]
        for name in shown:
            c.text(cx, y + 1, "· " + wrap(name, 7, BOX_W - 16)[0], size=7, color=GREY, align="center")
            y += 8.5
        if len(shown) < len(items):
            c.text(cx, y + 1, "+ %d more (see list)" % (len(items) - len(shown)), size=7,
                   color=GREY, align="center")

    draw_legend(c, MARGIN, height - MARGIN - FOOTER + 30)
    return c


def arrowhead(c, p1, p2, color, size=7.0):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    bx, by = p2[0] - ux * size, p2[1] - uy * size
    c.polygon([p2, (bx - uy * size * 0.45, by + ux * size * 0.45),
               (bx + uy * size * 0.45, by - ux * size * 0.45)], fill=color)


def stub(c, p, v, color, mark):
    n = (v[0] ** 2 + v[1] ** 2) ** 0.5
    ex, ey = p[0] + v[0] / n * 14, p[1] + v[1] / n * 14
    c.line(p[0], p[1], ex, ey, color=color, width=1.1, dash=(2, 1.5))
    c.text(ex + v[0] / n * 5, ey + v[1] / n * 5 + 2.5, mark, size=7.5, bold=True, color=color,
           align="center")


def draw_legend(c, x, y):
    c.text(x, y - 14, "Key", size=8.5, bold=True, color=INK)
    entries = [
        ("line", "walked both ways"),
        ("arrow", "only walked this way (or one-way)"),
        ("special", "up / down / in / out / named exit"),
        ("tried", "mentioned, not tried"),
        ("blocked", "tried, led nowhere"),
        ("here", "where you were last"),
    ]
    cx = x
    for kind, text in entries:
        if cx + 32 + text_width(text, 8) > c.width - x:     # wrap onto a second row
            cx, y = x, y + 20
        if kind == "line":
            c.line(cx, y, cx + 26, y, color=INK, width=1.3)
        elif kind == "arrow":
            c.line(cx, y, cx + 26, y, color=INK, width=1.3)
            arrowhead(c, (cx, y), (cx + 26, y), INK)
        elif kind == "special":
            c.line(cx, y, cx + 26, y, color=SPECIAL, width=1.2, dash=(4, 2))
        elif kind == "tried":
            stub(c, (cx + 4, y), (1, 0), GREY, "?")
        elif kind == "blocked":
            stub(c, (cx + 4, y), (1, 0), BLOCKED, "x")
        else:
            c.rect(cx, y - 6, 26, 12, stroke=INK, fill=HERE_FILL, width=2.2, radius=3)
        c.text(cx + 32, y + 3, text, size=8, color=INK)
        cx += 32 + text_width(text, 8) + 22


# --------------------------------------------------------------------------- the list pages

class Pages:
    """Flowing text over as many portrait pages as needed."""

    W, H, M = 612, 792, 54

    def __init__(self, title):
        self.title = title
        self.pages = []
        self.new_page()

    def new_page(self):
        self.c = Canvas(self.W, self.H)
        self.pages.append(self.c)
        self.y = self.M
        self.c.text(self.W - self.M, self.H - 30, "%s  ·  page %d" % (self.title, len(self.pages) + 1),
                    size=7.5, color=GREY, align="right")

    def need(self, h):
        if self.y + h > self.H - self.M:
            self.new_page()

    def heading(self, s, size=14.0):
        self.need(size + 30)
        self.y += size + 6
        self.c.text(self.M, self.y, s, size=size, bold=True, color=INK)
        self.y += 8

    def para(self, s, size=9.5, indent=0, bold=False, color=INK, gap=2.5, label=None):
        """Wrapped text; label (bold, in its own column) goes before the first line."""
        lab_w = 78 if label else 0
        lines = wrap(s, size, self.W - 2 * self.M - indent - lab_w, bold)
        for i, ln in enumerate(lines):
            self.need(size + gap)
            self.y += size + gap
            if label and i == 0:
                self.c.text(self.M + indent, self.y, label, size=size - 0.5, bold=True, color=GREY)
            self.c.text(self.M + indent + lab_w, self.y, ln, size=size, bold=bold, color=color)

    def space(self, h=6):
        self.y += h


def list_pages(gm, title):
    pg = Pages(title)
    pg.heading("Rooms", 16)
    carried = gm.carried()
    pg.para("%d rooms visited, %d items seen. Rooms are numbered as on the map, top to bottom."
            % (len(gm.rooms), len(gm.items)), color=GREY)
    pg.para(", ".join(it["name"] for it in carried) or "nothing", label="Carrying")
    if gm.here in gm.rooms:
        pg.para(gm.label(gm.here), label="Last seen in")
    pg.space(4)
    for r in sorted(gm.rooms, key=lambda r: gm.number.get(r, 999)):
        d = gm.rooms[r]
        pg.need(40)
        pg.space(8)
        pg.para("#%d  %s%s" % (gm.number.get(r, 0), d["name"],
                               "   (you were here)" if r == gm.here else ""), size=11, bold=True)
        exits = []
        for cmd, b in sorted(d["exits"].items(), key=lambda kv: (kv[0] not in VEC, kv[0])):
            exits.append("%s -> %s" % (cmd, "the same room" if b == r else gm.label(b)))
        if exits:
            pg.para("; ".join(exits), indent=12, label="Exits")
        guesses = ["%s -> %s" % (cmd, gm.label(b)) for cmd, b in d["guess"].items()
                   if cmd not in d["exits"] and b in gm.rooms]
        if guesses:
            pg.para("; ".join(guesses), indent=12, label="Way back?", color=GREY)
        if d["blocked"]:
            pg.para(", ".join(d["blocked"]), indent=12, label="Led nowhere")
        untried = [m for m in d["mentioned"]
                   if m not in d["exits"] and m not in d["blocked"] and m not in d["guess"]]
        if untried:
            pg.para(", ".join(untried), indent=12, label="Not yet tried")
        items = gm.room_items(r)
        if items:
            pg.para("; ".join(it["name"] + ("" if it.get("where") in ("here", None)
                                            else " (%s)" % it["where"]) for it in items),
                    indent=12, label="Items")
        gone = [it["name"] for it in gm.items.values() if it.get("room") == r and it.get("missing")]
        if gone:
            pg.para(", ".join(gone), indent=12, label="Gone from here", color=GREY)

    pg.space(10)
    pg.heading("Items", 16)
    if not gm.items:
        pg.para("No items seen yet.", color=GREY)
    for it in sorted(gm.items.values(), key=lambda it: it["name"].lower()):
        if it.get("carried"):
            where = "carried"
        else:
            where = gm.label(it.get("room"))
            if it.get("where") not in ("here", None):
                where += ", " + it["where"]
        pg.para("%s  —  %s" % (it["name"], where))
    return pg.pages


# --------------------------------------------------------------------------- main

def story_key(path):
    """The game's release, serial and checksum, as the map file records them; None if the
    story file can't be read."""
    try:
        import zplay
        mem = zplay.load_story(path)
        return [int.from_bytes(mem[2:4], "big"), bytes(mem[0x12:0x18]).decode("latin-1"),
                int.from_bytes(mem[0x1C:0x1E], "big")]
    except Exception:
        return None


def find_map(path):
    """The map file to draw. Given a story file, that is <story>.map.json, or the longer
    <story>-r<release>-<serial>.map.json the players use when the plain name already
    holds a different game's map."""
    if path.endswith(".json"):
        return path
    stem = os.path.splitext(path)[0]
    key = story_key(path)
    if key:
        alt = "%s-r%s-%s.map.json" % (stem, key[0], key[1])
        if os.path.exists(alt):
            return alt
    return stem + ".map.json"


def main():
    ap = argparse.ArgumentParser(description="Make a PDF of a zplay_llm map file.")
    ap.add_argument("map", help="the map file (e.g. zork1.map.json), or the story file next to it")
    ap.add_argument("-o", "--output", help="PDF to write (default: <story>.map.pdf)")
    ap.add_argument("--title", help="title for the PDF (default: from the file name)")
    args = ap.parse_args()

    path = find_map(args.map)
    try:
        with open(path) as fh:
            data = json.load(fh)
    except OSError as e:
        sys.exit("Can't read %s: %s" % (path, e.strerror))
    except ValueError as e:
        sys.exit("%s isn't a valid map file: %s" % (path, e))
    if not data.get("rooms"):
        sys.exit("%s has no rooms in it yet; play a little first." % path)

    stem = os.path.basename(path)
    stem = stem[: -len(".map.json")] if stem.endswith(".map.json") else os.path.splitext(stem)[0]
    title = args.title or "%s map" % stem
    out = args.output or os.path.join(os.path.dirname(path), stem + ".map.pdf")

    gm = GameMap(data)
    gm.layout()
    pages = [draw_map(gm, title)] + list_pages(gm, title)
    write_pdf(out, pages, title)
    print("Wrote %s: %d rooms, %d items, %d pages." % (out, len(gm.rooms), len(gm.items), len(pages)))


if __name__ == "__main__":
    main()
