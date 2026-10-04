"""The permission check from the README, with its precedence bug fixed.

The buggy version was `bool(perms & WRITE | ADMIN)`. & binds more tightly than
|, so that is `(perms & WRITE) | ADMIN`, which is never zero: everyone could
edit. Tests that only checked users who *should* be allowed couldn't tell.
"""

READ = 0b001
WRITE = 0b010
ADMIN = 0b100


def can_edit(perms: int) -> bool:
    """Editing needs WRITE or ADMIN."""
    return bool(perms & (WRITE | ADMIN))
