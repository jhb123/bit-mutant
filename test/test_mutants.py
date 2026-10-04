"""Unit tests for the mutation engine: the opcode table and make_mutants.

These call the plugin's functions directly, without running pytest inside
pytest. test_plugin.py covers the hooks.
"""

import operator
import sys
import types

import bit_mutant_examples as ex
import pytest
from bit_mutant_examples import encoding

from pytest_bit_mutant import (
    INSTRUCTION_TABLE,
    MUTATION_TABLE,
    MutantResult,
    is_skipped,
    make_mutants,
    survivors,
)

# What each operator computes, to check a mutant against its replacement.
COMPUTES = {
    "&": operator.and_,
    "|": operator.or_,
    "^": operator.xor,
    "<<": operator.lshift,
    ">>": operator.rshift,
}
BINARY = list(COMPUTES)
IN_PLACE = [op + "=" for op in BINARY]


# One function per operator, each using it exactly once.
def and_(a, b):
    return a & b


def or_(a, b):
    return a | b


def xor(a, b):
    return a ^ b


def lshift(a, b):
    return a << b


def rshift(a, b):
    return a >> b


def iand(a, b):
    a &= b
    return a


def ior(a, b):
    a |= b
    return a


def ixor(a, b):
    a ^= b
    return a


def ilshift(a, b):
    a <<= b
    return a


def irshift(a, b):
    a >>= b
    return a


USES = {
    "&": and_,
    "|": or_,
    "^": xor,
    "<<": lshift,
    ">>": rshift,
    "&=": iand,
    "|=": ior,
    "^=": ixor,
    "<<=": ilshift,
    ">>=": irshift,
}

# Between them, these pairs tell every operator apart from its replacements, so
# a mutant that computed the wrong thing would be noticed.
OPERANDS = [(6, 3), (5, 1), (12, 2)]


def run(new_code, func, *args):
    """Call func's code with new_code swapped in, without touching func."""
    mutant = types.FunctionType(
        new_code, func.__globals__, func.__name__, func.__defaults__, func.__closure__
    )
    return mutant(*args)


# --- The tables ----------------------------------------------------------------


def test_instruction_table_has_every_operator():
    symbols = set(MUTATION_TABLE) | {
        r for rs in MUTATION_TABLE.values() for r in rs if r
    }
    assert symbols <= set(INSTRUCTION_TABLE)


def test_instruction_table_values_are_distinct():
    # Within one family (binary, in-place) every operator must be told apart.
    binary = [INSTRUCTION_TABLE[op] for op in BINARY]
    in_place = [INSTRUCTION_TABLE[op] for op in IN_PLACE]
    assert len(set(binary)) == len(binary)
    assert len(set(in_place)) == len(in_place)


def test_instruction_table_values_fit_in_a_byte():
    assert all(0 <= value < 256 for value in INSTRUCTION_TABLE.values())


def test_mutation_table_replacements_stay_in_their_family():
    for original, replacements in MUTATION_TABLE.items():
        for replacement in replacements:
            if original == "~":
                assert replacement == ""
            else:
                assert replacement in MUTATION_TABLE
                assert replacement != original
                assert original.endswith("=") == replacement.endswith("=")


# --- Mutants behave like the replacement operator -------------------------------


@pytest.mark.parametrize("op", BINARY + IN_PLACE)
def test_mutants_compute_the_replacement(op):
    func = USES[op]
    mutants = list(make_mutants(func))
    assert [replacement for _, _, replacement, _ in mutants] == MUTATION_TABLE[op]
    for new_code, original, replacement, _ in mutants:
        assert original == op
        expected = COMPUTES[replacement.removesuffix("=")]
        for a, b in OPERANDS:
            assert run(new_code, func, a, b) == expected(a, b)


def test_invert_mutant_drops_the_operator():
    func = lambda x: ~x
    [(new_code, original, replacement, description)] = make_mutants(func)
    assert (original, replacement) == ("~", "")
    assert description.endswith("~x->x")
    assert [run(new_code, func, x) for x in [0, 5, -3]] == [0, 5, -3]


def test_double_invert_gives_one_mutant_per_operator():
    mutants = list(make_mutants(ex.double_invert))
    assert len(mutants) == 2
    # Dropping either ~ leaves one, so both mutants compute ~x.
    assert [run(code, ex.double_invert, 5) for code, *_ in mutants] == [~5, ~5]


def test_each_mutant_changes_one_site():
    # a | b | c: two | sites, two replacements each, four mutants.
    func = lambda a, b, c: a | b | c
    results = sorted(run(code, func, 6, 3, 1) for code, *_ in make_mutants(func))
    # (6 & 3) | 1, (6 ^ 3) | 1, (6 | 3) & 1, (6 | 3) ^ 1
    assert results == sorted([3, 5, 1, 6])


def test_original_function_is_untouched():
    code = ex.set_bit.__code__
    list(make_mutants(ex.set_bit))
    assert ex.set_bit.__code__ is code
    assert ex.set_bit(0, 2) == 4


def test_closures_keep_working():
    masker = ex.make_masker(0b0110)
    [(and_to_or, *_), (and_to_xor, *_)] = make_mutants(masker)
    assert run(and_to_or, masker, 0b1010) == 0b1110
    assert run(and_to_xor, masker, 0b1010) == 0b1100


# --- Which operators are found --------------------------------------------------


def sites(ops: list[str]) -> list[str]:
    """The originals make_mutants yields for these operator sites, sorted."""
    return sorted(op for op in ops for _ in MUTATION_TABLE[op])


# Before 3.12 a comprehension is a separate code object, so its operators
# belong to that, not to the enclosing function (PEP 709 inlined them).
INLINED_COMPREHENSIONS = sys.version_info >= (3, 12)


@pytest.mark.parametrize(
    "func, ops",
    [
        (ex.bistshift_divide, [">>"]),
        (ex.is_even, ["&"]),
        (ex.set_bit, ["|", "<<"]),
        (ex.chained, ["|", "&", "^", "<<"]),
        (ex.augmented_all, ["<<=", ">>=", "&=", "|=", "^="]),
        (ex.double_invert, ["~", "~"]),
        (ex.set_ops, ["|", "&", "|", "^"]),
        (ex.dict_merge, ["|"]),
        (ex.bool_xor, ["^"]),
        (ex.in_fstring, ["^"]),
        (ex.in_ternary, ["<<", ">>"]),
        (ex.in_match, ["&"]),
        (ex.async_mask, ["&"]),
        (ex.Flags.set, ["|="]),
        (ex.Flags.clear, ["&=", "~"]),
        (ex.Flags.has, ["&"]),
        (ex.Flags.combine, ["|"]),
        (ex.Flags.from_bits, ["|=", "<<"]),
        (ex.Flags.low_byte.fget, ["&"]),
        (ex.Flags.Inner.swap_nibbles, ["&", "<<", "&", ">>", "|"]),
        (ex.method_factory().shift, [">>"]),
        (ex.make_masker(1), ["&"]),
        # Nested functions and lambdas are separate code objects: only the
        # function's own operators count.
        (ex.outer, [">>"]),
        (ex.only_inner_has_ops, []),
        (ex.deeply_nested, []),
        (ex.in_lambda, []),
        # Evaluated when the def runs, not when the function is called.
        (ex.default_arg, []),
        (ex.decorated, []),
        (ex.in_comprehension, [">>", "&"] if INLINED_COMPREHENSIONS else []),
        (ex.in_walrus, ["&"] if INLINED_COMPREHENSIONS else []),
        # Encodings
        (encoding.encode_varint, ["&", ">>=", "|"]),
        (encoding.decode_varint, ["|=", "&", "<<", "&"]),
        (encoding.zigzag_encode, ["<<", ">>", "^"]),
        (encoding.zigzag_decode, [">>", "&", "^"]),
        (encoding.align_down, ["~", "&"]),
    ],
    ids=lambda value: getattr(value, "__qualname__", None),
)
def test_operators_found(func, ops):
    found = sorted(original for _, original, _, _ in make_mutants(func))
    assert found == sites(ops)


@pytest.mark.parametrize(
    "func",
    [
        ex.no_ops,
        ex.arithmetic,
        ex.boolean_logic,
        ex.comparisons,
        ex.unary_non_invert,
        ex.matmul,
        ex.bitwise_in_strings_and_comments,
    ],
    ids=lambda func: func.__qualname__,
)
def test_no_bitwise_operators_no_mutants(func):
    assert list(make_mutants(func)) == []


# --- Descriptions ---------------------------------------------------------------


def test_description_names_function_line_and_swap():
    line = ex.set_bit.__code__.co_firstlineno + 1
    descriptions = [d for *_, d in make_mutants(ex.set_bit)]
    assert descriptions == [
        f"set_bit:{line} << swapped for >>",
        f"set_bit:{line} | swapped for &",
        f"set_bit:{line} | swapped for ^",
    ]


def test_description_line_numbers_follow_the_source():
    # One operator per line, starting on the line after the def.
    first = ex.augmented_all.__code__.co_firstlineno
    lines = sorted(
        {int(d.split(":")[1].split()[0]) for *_, d in make_mutants(ex.augmented_all)}
    )
    assert lines == [first + 1, first + 2, first + 3, first + 4, first + 5]


def test_description_uses_qualname():
    descriptions = [d for *_, d in make_mutants(ex.Flags.Inner.swap_nibbles)]
    assert all(d.startswith("Flags.Inner.swap_nibbles:") for d in descriptions)


# --- skip= and survivors ---------------------------------------------------------


@pytest.mark.parametrize(
    "skip, original, replacement, expected",
    [
        ({}, "|", "^", False),
        ({"|": ["^"]}, "|", "^", True),
        ({"|": ["^"]}, "|", "&", False),
        ({"|": ["^"]}, "&", "^", False),
        # In-place operators match their plain form, either way round.
        ({"|": ["^"]}, "|=", "^=", True),
        ({"|=": ["^="]}, "|", "^", True),
        ({"|": ["&", "^"]}, "|", "&", True),
        ({"~": [""]}, "~", "", True),
    ],
)
def test_is_skipped(skip, original, replacement, expected):
    assert is_skipped(skip, original, replacement) is expected


def test_survivors_split_by_weak():
    results = {
        ("t1", "caught"): MutantResult("f", None, caught=True, ran=True),
        ("t1", "survived"): MutantResult("f", None, ran=True),
        ("t1", "never ran"): MutantResult("f", None),
        ("t2", "weak survived"): MutantResult("f", "known weak", ran=True),
        ("t2", "weak caught"): MutantResult("f", "known weak", caught=True, ran=True),
    }
    assert survivors(results, weak=False) == [("t1", "survived")]
    assert survivors(results, weak=True) == [("t2", "weak survived")]
