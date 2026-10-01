"""Integer encodings used by formats like Protocol Buffers.

- varint: unsigned ints in 7-bit groups, low group first, with the top bit of
  each byte set when more bytes follow (LEB128).
- zigzag: maps signed ints onto unsigned ones so small negatives stay small
  (0, -1, 1, -2, 2, ... -> 0, 1, 2, 3, 4, ...), which keeps their varints short.
"""

MAX_VARINT_BYTES = 10  # enough for any 64-bit value


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varints are unsigned; zigzag-encode negatives first")
    out = bytearray()
    # A bounded loop rather than `while value:` so a mutant like `>>=` -> `<<=`
    # produces wrong output instead of looping forever.
    for _ in range(MAX_VARINT_BYTES):
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)
    raise ValueError("value too large for a varint")


def decode_varint(data: bytes) -> tuple[int, int]:
    """Return (value, number of bytes consumed)."""
    result = 0
    for i, byte in enumerate(data[:MAX_VARINT_BYTES]):
        result |= (byte & 0x7F) << (7 * i)
        if not byte & 0x80:
            return result, i + 1
    raise ValueError("truncated or overlong varint")


def zigzag_encode(n: int) -> int:
    # n >> 63 is 0 for non-negative n and -1 (all ones) for negative n.
    return (n << 1) ^ (n >> 63)


def zigzag_decode(z: int) -> int:
    return (z >> 1) ^ -(z & 1)


def align_down(x: int, alignment: int) -> int:
    """Round x down to a multiple of alignment (which must be a power of two)."""
    return x & ~(alignment - 1)
