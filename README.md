# bit-mutant

[![test](https://github.com/jhb123/bit-mutant/actions/workflows/test.yml/badge.svg)](https://github.com/jhb123/bit-mutant/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/bit-mutant)](https://pypi.org/project/bit-mutant/)
[![Python versions](https://img.shields.io/pypi/pyversions/bit-mutant)](https://pypi.org/project/bit-mutant/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/jhb123/bit-mutant/blob/main/LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

A pytest plugin that mutation-tests bitwise operators (`&`, `|`, `^`, `<<`, `>>`, `~`).

## Usage

```python
@pytest.mark.mutate(target=set_bit)
@pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (6, 2, 6)])
def test_set_bit(x, n, expected):
    assert set_bit(x, n) == expected
```

Each operator in `set_bit` is swapped (e.g. `|` → `^`) and the test reruns. A
mutant is caught if any case fails. If none do, it survived and the run fails.

Use `target=` as a keyword; a lone positional callable breaks the mark.

## Survivors

- **Missing case**: add an input where the original and mutant differ.
- **Equivalent mutant** (no input can differ): `@pytest.mark.mutate(target=f, skip={"|": ["^"]})`
- **Known-weak test**: `@pytest.mark.xfail(reason=...)`. Applies to mutants only.
