"""How to write tests that catch bitwise mutants.

Each function has a good test and a weak one. The weak test passes on the
real code, but a mutant survives it, so it's marked xfail with the reason. The
good test adds the case that tells the original and the mutant apart.

A mutant only has to be caught by one case of a parametrized test, so the
cases work together: each one can catch different mutants.
"""

import pytest

from .examples import Flags, bistshift_divide, is_even, set_bit


@pytest.mark.mutate(target=bistshift_divide)
@pytest.mark.parametrize("x, expected", [(0, 0), (2, 1)])
def test_bitshift(x, expected):
    assert bistshift_divide(x) == expected


@pytest.mark.mutate(target=bistshift_divide)
@pytest.mark.xfail(reason="0 >> 1 == 0 << 1: zero shifts to zero either way")
@pytest.mark.parametrize("x, expected", [(0, 0)])
def test_bitshift_weak(x, expected):
    assert bistshift_divide(x) == expected


@pytest.mark.mutate(target=is_even)
@pytest.mark.parametrize("x, expected", [(3, False), (4, True)])
def test_is_even(x, expected):
    assert is_even(x) == expected


@pytest.mark.mutate(target=is_even)
@pytest.mark.xfail(
    reason="odd inputs only: x | 1 and x ^ 1 are still non-zero, so the "
    "mutants also answer 'odd'"
)
@pytest.mark.parametrize("x, expected", [(3, False), (5, False)])
def test_is_even_weak(x, expected):
    assert is_even(x) == expected


@pytest.mark.mutate(target=set_bit)
@pytest.mark.parametrize(
    "x, n, expected",
    [
        (0, 2, 4),  # catches | -> & and << -> >>
        (6, 2, 6),  # bit already set: catches | -> ^
    ],
)
def test_set_bit(x, n, expected):
    assert set_bit(x, n) == expected


@pytest.mark.mutate(target=set_bit)
@pytest.mark.xfail(
    reason="the bit is never already set, and | only differs from ^ when it is"
)
@pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (1, 3, 9)])
def test_set_bit_weak(x, n, expected):
    assert set_bit(x, n) == expected


@pytest.mark.mutate(target=Flags.set)
@pytest.mark.parametrize(
    "start, flag, expected",
    [
        (2, 4, 6),  # catches |= -> &=
        (6, 4, 6),  # flag already set: catches |= -> ^=
    ],
)
def test_flag(start, flag, expected):
    obj = Flags(start)
    obj.set(flag)
    assert obj.value == expected


@pytest.mark.mutate(target=Flags.set)
@pytest.mark.xfail(
    reason="the flag is never already set, and |= only differs from ^= when it is"
)
@pytest.mark.parametrize("start, flag, expected", [(2, 4, 6)])
def test_flag_weak(start, flag, expected):
    obj = Flags(start)
    obj.set(flag)
    assert obj.value == expected


# One test can mutation-test several functions.
@pytest.mark.mutate(target=is_even)
@pytest.mark.mutate(target=set_bit)
def test_set_bit_makes_even():
    assert set_bit(0, 2) == 4
    assert set_bit(6, 2) == 6
    assert is_even(set_bit(0, 2))
