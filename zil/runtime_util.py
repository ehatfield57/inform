"""Small helpers shared by the compiler and the runtime."""


def s16(x):
    """A 16-bit value as a signed number."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x
