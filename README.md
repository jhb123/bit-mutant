# bit-mutant

A pytest plugin that mutation-tests bitwise operators (`&`, `|`, `^`, `<<`, `>>`, `~`).

## Usage

```python
@pytest.mark.mutate(target=set_bit)
@pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (6, 2, 6)])
def test_set_bit(x, n, expected):
    assert set_bit(x, n) == expected
```

Each operator in `set_bit` is swapped (e.g. `|` → `^`) and the test reruns. A
mutant is killed if any case fails. If none do, it survived and the run fails.

Use `target=` as a keyword; a lone positional callable breaks the mark.

## Survivors

- **Missing case**: add an input where the original and mutant differ.
- **Equivalent mutant** (no input can differ): `@pytest.mark.mutate(target=f, skip={"|": ["^"]})`
- **Known-weak test**: `@pytest.mark.xfail(reason=...)`. Applies to mutants only.
