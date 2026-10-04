import pytest
from bit_mutant_examples.permissions import ADMIN, READ, WRITE, can_edit


# WRITE and ADMIN share no bits, so WRITE | ADMIN == WRITE ^ ADMIN: the
# | -> ^ mutant is equivalent and no input could catch it.
@pytest.mark.mutate(target=can_edit, skip={"|": ["^"]})
@pytest.mark.parametrize(
    "perms, expected",
    [
        (WRITE, True),
        (ADMIN, True),
        (READ | WRITE, True),
        # The cases that found the bug: users who must be refused.
        (READ, False),
        (0, False),
    ],
)
def test_can_edit(perms, expected):
    assert can_edit(perms) == expected
