"""Z-machine text: encode and decode Z-strings (no abbreviations).

Object names and dictionary words live in memory as real Z-strings, so the
parser and PRINTB/PRINTD see the same bytes a compiled game would have.
"""

A0 = "abcdefghijklmnopqrstuvwxyz"
A1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
A2_V1 = " 0123456789.,!?_#'\"/\\<-:()"
A2 = " \n0123456789.,!?_#'\"/\\-:()"   # index 0 is the escape marker


def zchars(text, version=3):
    """Text -> list of 5-bit Z-characters."""
    out = []
    for ch in text:
        if ch == " ":
            out.append(0)
        elif ch in A0:
            out.append(A0.index(ch) + 6)
        elif ch in A1:
            out += [4, A1.index(ch) + 6]
        elif ch != " " and ch in A2[1:]:
            out += [5, A2.index(ch) + 6]
        else:
            z = ord(ch) if ch != "\n" else 13
            out += [5, 6, z >> 5, z & 31]
    return out


def pack(zs):
    """5-bit chars -> bytes, padding with 5s, last word's top bit set."""
    zs = list(zs)
    while len(zs) % 3 or not zs:
        zs.append(5)
    out = bytearray()
    for i in range(0, len(zs), 3):
        w = (zs[i] << 10) | (zs[i + 1] << 5) | zs[i + 2]
        if i + 3 >= len(zs):
            w |= 0x8000
        out += bytes([w >> 8, w & 0xFF])
    return bytes(out)


def encode(text, version=3):
    return pack(zchars(text, version))


def encode_word(text, version=3):
    """Dictionary key: lower case, truncated to 6 (v3) or 9 (v4+) Z-chars."""
    n = 6 if version <= 3 else 9
    zs = zchars(text.lower(), version)[:n]
    zs += [5] * (n - len(zs))
    return pack(zs)


def decode(mem, addr):
    """Decode the Z-string at addr. Returns (text, address after it)."""
    zs = []
    while True:
        w = (mem[addr] << 8) | mem[addr + 1]
        addr += 2
        zs += [(w >> 10) & 31, (w >> 5) & 31, w & 31]
        if w & 0x8000:
            break
    return decode_zchars(zs), addr


def decode_zchars(zs):
    out = []
    alpha = 0
    i = 0
    while i < len(zs):
        z = zs[i]
        i += 1
        if z == 0:
            out.append(" ")
        elif z in (1, 2, 3):
            i += 1  # abbreviation: we never write these
        elif z == 4:
            alpha = 1
            continue
        elif z == 5:
            alpha = 2
            continue
        elif alpha == 2 and z == 6:
            if i + 1 < len(zs):
                out.append(chr((zs[i] << 5) | zs[i + 1]))
            i += 2
        elif alpha == 2 and z == 7:
            out.append("\n")
        else:
            out.append((A0, A1, A2)[alpha][z - 6])
        alpha = 0
    return "".join(out)
