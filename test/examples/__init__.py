def bistshift_divide(x: int) -> int:
    return x >> 1


def is_even(x: int) -> bool:
    return (x & 1) == 0


def set_bit(x: int, n: int) -> int:
    return x | (1 << n)


def no_ops():
    pass


def arithmetic(x: int, y: int) -> int:
    return (x + y) * (x - y) // 2 % 7 ** 2


def boolean_logic(a: bool, b: bool) -> bool:
    # `and` / `or` / `not` are ast.BoolOp / ast.Not, not bitwise.
    return (a and b) or not a


def comparisons(x: int) -> bool:
    return 0 < x <= 10 and x != 5 and x is not None


def unary_non_invert(x: int) -> int:
    return -x + +x


def matmul(a, b):
    return a @ b


def bitwise_in_strings_and_comments() -> str:
    # x >> 1, x & 1, ~x
    return "x << 1 | y ^ z & ~w"


FLAG_A = 1 << 0  # <module>
FLAG_B = 1 << 1  # <module>
MASK = FLAG_A | FLAG_B  # <module>
INVERTED = ~MASK  # <module>


class Flags:
    READ = 1 << 2  # Flags
    WRITE = 1 << 3  # Flags
    ALL = READ | WRITE  # Flags

    def __init__(self, value: int = 0):
        self.value = value

    def set(self, flag: int) -> None:  # Flags.set: 1 (AugAssign)
        self.value |= flag

    def clear(self, flag: int) -> None:  # Flags.clear: 2 (&= and ~)
        self.value &= ~flag

    def has(self, flag: int) -> bool:  # Flags.has: 1
        return bool(self.value & flag)

    @staticmethod
    def combine(a: int, b: int) -> int:  # Flags.combine: 1
        return a | b

    @classmethod
    def from_bits(cls, *bits: int) -> "Flags":  # Flags.from_bits: 2
        value = 0
        for bit in bits:
            value |= 1 << bit
        return cls(value)

    @property
    def low_byte(self) -> int:  # Flags.low_byte: 1
        return self.value & 0xFF

    class Inner:
        def swap_nibbles(self, x: int) -> int:  # Flags.Inner.swap_nibbles: 5
            return ((x & 0x0F) << 4) | ((x & 0xF0) >> 4)


# --- Nested functions ----------------------------------------------------------


def outer(x: int) -> int:  # outer: 1
    def inner(y: int) -> int:  # outer.<locals>.inner: 1
        return y << 2

    return inner(x) >> 1


def only_inner_has_ops(x: int) -> int:  # not reported
    def helper(y: int) -> int:  # only_inner_has_ops.<locals>.helper: 1
        return y ^ 0b1010

    return helper(x)


def deeply_nested(x: int) -> int:  # not reported
    def level1(a: int) -> int:  # not reported
        def level2(b: int) -> int:  # deeply_nested.<locals>.level1.<locals>.level2: 1
            return b & 0xF

        return level2(a)

    return level1(x)


def make_masker(mask: int):  # not reported
    def masker(x: int) -> int:  # make_masker.<locals>.masker: 1 (closure)
        return x & mask

    return masker


def method_factory():  # not reported
    class Local:
        SHIFT = 1 << 1  # method_factory.<locals>.Local

        def shift(self, x: int) -> int:  # method_factory.<locals>.Local.shift: 1
            return x >> self.SHIFT

    return Local


async def async_mask(x: int) -> int:  # async_mask: 1
    return x & 0xFFFF



def chained(a: int, b: int, c: int, d: int) -> int:  # chained: 4
    return a | b & c ^ d << 1


def augmented_all(x: int) -> int:  # augmented_all: 5
    x <<= 1
    x >>= 1
    x &= 0xFF
    x |= 0x01
    x ^= 0x10
    return x


def double_invert(x: int) -> int:  # double_invert: 2
    return ~~x


def in_lambda(xs: list[int]) -> list[int]:  # in_lambda: 1 (lambda has its own code object)
    return sorted(xs, key=lambda v: v & 0xF)


def in_comprehension(xs: list[int]) -> list[int]:  # in_comprehension: 2
    return [x >> 1 for x in xs if x & 1]


def in_fstring(x: int) -> str:  # in_fstring: 1
    return f"{x ^ 0xFF:08b}"


def in_walrus(xs: list[int]) -> list[int]:  # in_walrus: 1
    return [y for x in xs if (y := x & 3)]


def in_ternary(x: int, flag: bool) -> int:  # in_ternary: 2 (only one runs per call)
    return x << 1 if flag else x >> 1


def in_match(x: int) -> str:  # in_match: 1 (patterns can't contain operators)
    match x & 0b11:
        case 0:
            return "zero"
        case _:
            return "other"


def default_arg(x: int = 1 << 4) -> int:  # default_arg: 1 (actually runs at def time)
    return x


def decorator_arg(mask: int):  # not reported
    def deco(func):
        return func

    return deco


@decorator_arg(0xF0 | 0x0F)  # credited to decorated: 1 (actually runs at <module>)
def decorated(x: int) -> int:
    return x


def set_ops(a: set, b: set) -> set:  # set_ops: 4
    return (a | b) - (a & b) | (a ^ b)


def dict_merge(a: dict, b: dict) -> dict:  # dict_merge: 1
    return a | b


def bool_xor(a: bool, b: bool) -> bool:  # bool_xor: 1
    return a ^ b
