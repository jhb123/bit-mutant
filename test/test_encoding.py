import pytest

from .examples.encoding import (
    align_down,
    decode_varint,
    encode_varint,
    zigzag_decode,
    zigzag_encode,
)

# Known encodings, including the example from the Protocol Buffers docs (300).
VARINTS = [
    (0, b"\x00"),
    (1, b"\x01"),
    (127, b"\x7f"),
    (128, b"\x80\x01"),
    (300, b"\xac\x02"),
    (16384, b"\x80\x80\x01"),
    (2**64 - 1, b"\xff" * 9 + b"\x01"),
]

ZIGZAGS = [
    (0, 0),
    (-1, 1),
    (1, 2),
    (-2, 3),
    (2, 4),
    (2**31 - 1, 2**32 - 2),
    (-(2**31), 2**32 - 1),
]


# `byte` is at most 0x7F, so `byte | 0x80` == `byte ^ 0x80`: an equivalent mutant.
@pytest.mark.mutate(target=encode_varint, skip={"|": ["^"]})
def test_encode_varint():
    for value, encoded in VARINTS:
        assert encode_varint(value) == encoded


# Each 7-bit group lands on bits of `result` that are still zero, so
# `result |= ...` == `result ^= ...`: an equivalent mutant.
@pytest.mark.mutate(target=decode_varint, skip={"|": ["^"]})
def test_decode_varint():
    for value, encoded in VARINTS:
        # Trailing bytes must be left alone.
        assert decode_varint(encoded + b"\xff") == (value, len(encoded))


@pytest.mark.mutate(target=zigzag_encode)
@pytest.mark.mutate(target=zigzag_decode)
def test_zigzag():
    for n, z in ZIGZAGS:
        assert zigzag_encode(n) == z
        assert zigzag_decode(z) == n


@pytest.mark.mutate(target=align_down)
def test_align_down():
    assert align_down(0, 8) == 0
    assert align_down(7, 8) == 0
    assert align_down(8, 8) == 8
    assert align_down(13, 4) == 12
    assert align_down(4096 + 100, 4096) == 4096
