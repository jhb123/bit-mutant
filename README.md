# pytest-bit-mutant

[![test](https://github.com/jhb123/bit-mutant/actions/workflows/test.yml/badge.svg)](https://github.com/jhb123/bit-mutant/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/pytest-bit-mutant)](https://pypi.org/project/pytest-bit-mutant/)
[![Python versions](https://img.shields.io/pypi/pyversions/pytest-bit-mutant)](https://pypi.org/project/pytest-bit-mutant/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/jhb123/bit-mutant/blob/main/LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
![PyPI Downloads](https://img.shields.io/pypi/dm/pytest-bit-mutant)

A pytest plugin that checks whether your tests would notice if a bitwise
operator (`&`, `|`, `^`, `<<`, `>>`, `~`) in your code were wrong.

Mark a test with the function it protects. bit-mutant reruns the test once for
each small change to that function's operators (a *mutant*), such as `|`
becoming `^`. If the test still passes with the operator changed, it can't
tell the right operator from the wrong one, and bit-mutant fails the run.

```python
@pytest.mark.mutate(target=set_bit)
@pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (6, 2, 6)])
def test_set_bit(x, n, expected):
    assert set_bit(x, n) == expected
```

```console
$ pip install pytest-bit-mutant
$ pytest
```

## A bug your tests miss

Here is a permission check, and a test for it that looks reasonable.

`permissions.py`:

```python
READ = 0b001
WRITE = 0b010
ADMIN = 0b100


def can_edit(perms: int) -> bool:
    """Editing needs WRITE or ADMIN."""
    return bool(perms & WRITE | ADMIN)
```

`test_permissions.py`:

```python
import pytest

from permissions import ADMIN, READ, WRITE, can_edit


@pytest.mark.mutate(target=can_edit)
@pytest.mark.parametrize("perms", [WRITE, ADMIN, READ | WRITE])
def test_can_edit(perms):
    assert can_edit(perms)
```

Without bit-mutant, all three cases pass. With it:

```console
$ pytest
test_permissions.py .mmcm.mmcm.mmcm                                      [100%]
=============================== mutation testing ===============================

test_permissions.py::test_can_edit  1/4 caught
    survived: can_edit:8 & swapped for |
    survived: can_edit:8 & swapped for ^
    survived: can_edit:8 | swapped for ^

1/4 mutants caught
Surviving mutants: the tests passed with the operator changed. Add a
case where the original and the mutant give different answers.
==================== 3 passed, 9 missed, 3 caught in 0.02s =====================
```

The `&` could be `|` or `^` and the test wouldn't notice. Every case expects
`True`, so a version of `can_edit` that said yes to everyone would pass too.
The fix the report suggests is a case where the answer should be `False`:

```python
@pytest.mark.mutate(target=can_edit)
@pytest.mark.parametrize(
    "perms, expected",
    [(WRITE, True), (ADMIN, True), (READ | WRITE, True), (READ, False), (0, False)],
)
def test_can_edit(perms, expected):
    assert can_edit(perms) == expected
```

```console
FAILED test_permissions.py::test_can_edit[1-False] - assert True == False
FAILED test_permissions.py::test_can_edit[0-False] - assert True == False
```

That exposes the real bug. `&` binds more tightly than `|`, so the function
computes `(perms & WRITE) | ADMIN`. That is always at least `ADMIN`, so
**everyone can edit**, including users with no permissions at all. The fix:

```python
return bool(perms & (WRITE | ADMIN))
```

With the fix, one mutant still survives:

```console
test_permissions.py::test_can_edit  3/4 caught
    survived: can_edit:8 | swapped for ^
```

This is an *equivalent mutant*. `WRITE` and `ADMIN` share no bits, so
`WRITE | ADMIN` and `WRITE ^ ADMIN` are the same number, and no test could
ever tell them apart. Tell bit-mutant to leave it out:

```python
@pytest.mark.mutate(target=can_edit, skip={"|": ["^"]})
```

```console
test_permissions.py::test_can_edit  3/3 caught

3/3 mutants caught
```

The finished version is in
[`examples/`](https://github.com/jhb123/bit-mutant/tree/main/examples).

## Why test this way

Line coverage told you nothing here: the first test ran every line of
`can_edit`. What it missed was whether the *values* were checked closely
enough. Bitwise code is especially prone to this:

- **Wrong operators often give right answers.** `|`, `^` and `+` agree whenever
  the operands share no bits. `&` and `|` agree whenever the operands are
  equal. `x >> 1` and `x << 1` agree when `x` is 0. Tests built from "nice"
  inputs like 0, 1 or a single flag hit exactly these cases.
- **Precedence is easy to get wrong.** `&` binds more tightly than `|`, and
  both bind more loosely than `+` and `<<`, so `a & b | c` and `x << 1 + y`
  rarely mean what they look like.
- **The bugs matter.** Bitwise code tends to live in permission checks, flags,
  hashing, encodings and protocol parsing, where a wrong bit is a security
  hole or corrupt data rather than a cosmetic glitch.

A surviving mutant points at a specific operator on a specific line and tells
you that no test checks it. That's usually a missing case, and sometimes, as
above, a bug.

## What to test this way

Mark tests for functions where the bitwise operators are the logic:

- flags and permission masks: set, clear, test, combine
- encodings: varints, zigzag, base64, bit packing, checksums, CRCs
- binary protocols and file formats: header fields, length prefixes
- hashing and bit tricks: power-of-two checks, alignment, popcount
- hardware registers and embedded-style code

Leave out code where operators are incidental: a set union like `a | b`, a
dict merge, or a function where the bitwise part is one small step among many.
Mutants there mostly tell you what you already know.

Mutation testing reruns the test once per mutant, so put the mark on focused
unit tests, not slow end-to-end ones.

## How to test this way

### Marking a test

```python
@pytest.mark.mutate(target=func)
```

`target` is the function whose operators are mutated, passed as a keyword. It
can be a plain function, a method (`Flags.set`), a static or class method, a
property's getter (`Flags.low_byte.fget`) or a closure returned by a factory.
The test itself can call it however it likes, directly or through other code,
even from other modules. The mutant replaces the code inside the function
object, so `from module import func` sees it too.

Every operator site in `target` gets these mutants, one at a time:

| Operator | Becomes |
|---|---|
| `&` | `\|`, `^` |
| `\|` | `&`, `^` |
| `^` | `&`, `\|` |
| `<<` | `>>` |
| `>>` | `<<` |
| `&=`, `\|=`, `^=`, `<<=`, `>>=` | the same as their plain forms |
| `~x` | `x` |

A mutant is **caught** if the test fails with it in place, through a failed
assert or any other exception. It **survives** if the test passes.

### Parametrized tests work together

The cases of a parametrized test are scored as a team. A mutant only has to be
caught by one case, so each case can target different mutants:

```python
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
```

Separate test functions are scored separately, even when they share a target
(for example through a mark on a class).

### Several targets

Stack the mark to mutate several functions from one test. Each function's
mutants are run separately:

```python
@pytest.mark.mutate(target=is_even)
@pytest.mark.mutate(target=set_bit)
def test_set_bit_makes_even():
    assert is_even(set_bit(0, 2))
```

### Equivalent mutants: `skip=`

Some mutants can't be caught by any input, because in context they compute the
same thing as the original. Leave them out with `skip`, which maps an original
operator to the replacements to skip:

```python
@pytest.mark.mutate(target=encode_varint, skip={"|": ["^"]})
```

```python
@pytest.mark.mutate(target=f, skip={"|": ["^"], "&": ["|", "^"], "~": [""]})
```

- In-place operators match their plain form, so `{"|": ["^"]}` also skips
  `|=` becoming `^=`.
- `""` stands for removing the `~`.
- Skipped mutants still show up in the output as skipped, with the reason
  `skipped mutant: ...` (see them with `pytest -rs`), so they aren't hidden.

Only skip a mutant when you can explain why no input could catch it, ideally
in a comment next to the mark. Common reasons: the operands can never share
bits, so `|` and `^` agree (as in `can_edit` above), or a value is always
masked again afterwards.

### Known-weak tests: `xfail`

Sometimes a test is deliberately narrow, for example a smoke test, and you
know some mutants will get past it. Mark it `xfail` with the reason:

```python
@pytest.mark.mutate(target=set_bit)
@pytest.mark.xfail(
    reason="the bit is never already set, and | only differs from ^ when it is"
)
@pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (1, 3, 9)])
def test_set_bit_weak(x, n, expected):
    assert set_bit(x, n) == expected
```

On a mutated test, `xfail` applies to the mutants only:

- The unmutated test must still pass. If it fails, the run fails as usual.
- Its surviving mutants are reported as known weak and don't fail the run:

  ```console
  test_examples.py::test_set_bit_weak  2/3 caught  (known weak: the bit is never already set, and | only differs from ^ when it is)
      survived: set_bit:13 | swapped for ^
  ```

- If nothing survives, you're told the mark can go:
  `(marked weak, but nothing survived: remove the xfail?)`

Prefer `skip=` when the mutant can't be caught at all, and `xfail` when it
could be caught but this test doesn't try.

## Reading the output

Each mutant runs as its own test, named after the original with the mutant
appended:

```console
$ pytest -v
test_set_bit.py::test_set_bit[0-2-4] PASSED                              [ 12%]
test_set_bit.py::test_set_bit[0-2-4-set_bit:13 << swapped for >>] CAUGHT [ 25%]
test_set_bit.py::test_set_bit[0-2-4-set_bit:13 | swapped for &] CAUGHT   [ 37%]
test_set_bit.py::test_set_bit[0-2-4-set_bit:13 | swapped for ^] MISSED   [ 50%]
...
```

- In the progress line, `c` is a mutant this case caught and `m` one it
  missed. A miss by one case is fine if another case catches it.
- Under `mutation testing`, each marked test gets a score, `N/M caught`, with
  the mutants that survived every case listed beneath it as
  `function:line operator swapped for replacement`.
- After collection, `bit-mutant: added N mutant tests, M tests in total`
  explains why the test count is higher than `collected N items`.
- The run fails (exit code 1) if any mutant survives a test that isn't marked
  `xfail`.

## Running

| Command | What it does |
|---|---|
| `pytest` | runs every test plus its mutants |
| `pytest -k "not swapped"` | runs only the unmutated tests (every mutant's id contains "swapped") |
| `pytest -k "test_set_bit"` | one test and its mutants |
| `pytest --collect-only -q` | lists the mutants without running them |
| `pytest -rs` | also lists skipped mutants and why |
| `pytest -p no:bit_mutant` | turns the plugin off |

Mutants that don't run (deselected with `-k`, never reached because of `-x`,
or only collected) aren't counted as survivors.

## Limitations

- **CPython only.** Mutants are made by rewriting bytecode. Supported on
  Python 3.10 and newer, with pytest 8 or newer.
- **Only the target's own code is mutated.** Nested functions, lambdas and
  classes defined inside the target are separate code objects; target them
  directly if they matter. On Python 3.10 and 3.11 that includes the body of a
  list, set or dict comprehension. From 3.12 those are part of the function.
- **Code that runs once isn't mutated.** Default argument values, decorator
  arguments, class bodies and module-level constants like `MASK = A | B` are
  evaluated when they're defined, not when the test calls the function.
- **Bitwise operators only.** Arithmetic, comparison and boolean (`and`, `or`,
  `not`) operators are left alone.
- **One mutant at a time.** Each mutant changes exactly one operator site.
