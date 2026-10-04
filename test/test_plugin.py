"""Run the plugin on the example tests with pytester and check what it reports.

Each test copies a test file from examples/tests (or writes one) into a
throwaway directory, runs pytest on it in-process, and inspects the outcome.
bit-mutant and bit-mutant-examples are installed, so pytest loads the plugin
through its entry point and the tests import the example code, the same way a
user's run would.
"""

from glob import escape

import pytest
from bit_mutant_examples import set_bit

# The line in bit_mutant_examples that set_bit's operators are on.
SET_BIT_LINE = set_bit.__code__.co_firstlineno + 1


def mutant_id(case: str, swap: str) -> str:
    """An fnmatch pattern for a set_bit clone's id, e.g. "0-2-4", "| swapped for &".

    The id contains [ and ], which fnmatch would read as a character class.
    """
    return "*::" + escape(f"test_set_bit[{case}-set_bit:{SET_BIT_LINE} {swap}]")


def test_marker_is_registered(pytester: pytest.Pytester):
    result = pytester.runpytest("--markers")
    result.stdout.fnmatch_lines(["@pytest.mark.mutate(target, skip=None):*"])


def test_examples(pytester: pytest.Pytester):
    pytester.copy_example("test_examples.py")
    result = pytester.runpytest()
    # Every survivor is in a test marked xfail, so the run passes.
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 15, "caught": 20, "missed": 14}
    result.stdout.fnmatch_lines(
        [
            "bit-mutant: added 34 mutant tests, 49 tests in total",
            "*::test_bitshift *1/1 caught",
            "*::test_bitshift_weak *0/1 caught  (known weak: *)",
            "    survived: bistshift_divide:* >> swapped for <<",
            "*::test_set_bit_weak *2/3 caught  (known weak: *)",
            "    survived: set_bit:* | swapped for ^",
            "*::test_set_bit_makes_even *5/5 caught",
            "16/21 mutants caught",
        ]
    )
    result.stdout.no_fnmatch_line("Surviving mutants: *")


def test_encoding(pytester: pytest.Pytester):
    pytester.copy_example("test_encoding.py")
    result = pytester.runpytest("-rs")
    # Two equivalent mutants are left out with skip=, the rest are caught.
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 4, "skipped": 2, "caught": 22}
    result.stdout.fnmatch_lines(
        [
            "22/22 mutants caught",
            "SKIPPED *skipped mutant: encode_varint:* | swapped for ^",
            "SKIPPED *skipped mutant: decode_varint:* |= swapped for ^=",
        ]
    )


def test_surviving_mutant_fails_the_run(pytester: pytest.Pytester):
    # test_set_bit_weak from the examples, without its xfail.
    pytester.makepyfile(
        test_weak="""
        import pytest

        from bit_mutant_examples import set_bit


        @pytest.mark.mutate(target=set_bit)
        @pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (1, 3, 9)])
        def test_set_bit(x, n, expected):
            assert set_bit(x, n) == expected
        """
    )
    result = pytester.runpytest()
    # Every test passed, but the | -> ^ mutant survived, so the run fails.
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes() == {"passed": 2, "caught": 4, "missed": 2}
    result.stdout.fnmatch_lines(
        [
            "*::test_set_bit  2/3 caught",
            "    survived: set_bit:* | swapped for ^",
            "2/3 mutants caught",
            "Surviving mutants: *",
        ]
    )


def test_xfail_without_survivors_is_flagged(pytester: pytest.Pytester):
    # test_set_bit from the examples, wrongly marked xfail.
    pytester.makepyfile(
        test_not_weak="""
        import pytest

        from bit_mutant_examples import set_bit


        @pytest.mark.mutate(target=set_bit)
        @pytest.mark.xfail(reason="not actually weak")
        @pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (6, 2, 6)])
        def test_set_bit(x, n, expected):
            assert set_bit(x, n) == expected
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(["*marked weak, but nothing survived*"])


def test_failing_unmutated_test_still_fails(pytester: pytest.Pytester):
    pytester.makepyfile(
        test_wrong="""
        import pytest

        from bit_mutant_examples import set_bit


        @pytest.mark.mutate(target=set_bit)
        def test_set_bit():
            assert set_bit(0, 2) == 5
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes()["failed"] == 1


# A test that catches all three set_bit mutants, used by several tests below.
GOOD_SET_BIT_TEST = """
import pytest

from bit_mutant_examples import set_bit


@pytest.mark.mutate(target=set_bit)
@pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (6, 2, 6)])
def test_set_bit(x, n, expected):
    assert set_bit(x, n) == expected
"""


def test_plugin_can_be_disabled(pytester: pytest.Pytester):
    pytester.makepyfile(GOOD_SET_BIT_TEST)
    result = pytester.runpytest(
        "-p", "no:bit_mutant", "-W", "ignore::pytest.PytestUnknownMarkWarning"
    )
    assert result.ret == pytest.ExitCode.OK
    result.assert_outcomes(passed=2)
    result.stdout.no_fnmatch_line("bit-mutant: *")
    result.stdout.no_fnmatch_line("*mutation testing*")


def test_no_tests_exit_code_is_unchanged(pytester: pytest.Pytester):
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED


def test_collect_only_lists_each_mutant(pytester: pytest.Pytester):
    pytester.makepyfile(GOOD_SET_BIT_TEST)
    result = pytester.runpytest("--collect-only", "-q")
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [
            "*::" + escape("test_set_bit[0-2-4]"),
            mutant_id("0-2-4", "<< swapped for >>"),
            mutant_id("0-2-4", "| swapped for &"),
            mutant_id("0-2-4", "| swapped for ^"),
            "*::" + escape("test_set_bit[6-2-6]"),
            mutant_id("6-2-6", "<< swapped for >>"),
            mutant_id("6-2-6", "| swapped for &"),
            mutant_id("6-2-6", "| swapped for ^"),
        ]
    )
    # Nothing ran, so there's nothing to score.
    result.stdout.no_fnmatch_line("*mutation testing*")
    result.stdout.no_fnmatch_line("Surviving mutants: *")


def test_parametrize_ids_are_kept(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import is_even


        @pytest.mark.mutate(target=is_even)
        @pytest.mark.parametrize("x, expected", [(3, False), (4, True)], ids=["odd", "even"])
        def test_is_even(x, expected):
            assert is_even(x) == expected
        """
    )
    result = pytester.runpytest("--collect-only", "-q")
    result.stdout.fnmatch_lines(
        [
            "*::" + escape("test_is_even[odd]"),
            "*::"
            + escape("test_is_even[odd-is_even:")
            + "* & swapped for |"
            + escape("]"),
            "*::" + escape("test_is_even[even]"),
        ]
    )


def test_verbose_shows_caught_and_missed(pytester: pytest.Pytester):
    pytester.makepyfile(GOOD_SET_BIT_TEST)
    result = pytester.runpytest("-v")
    result.stdout.fnmatch_lines(
        [
            "*::" + escape("test_set_bit[0-2-4]") + " PASSED*",
            mutant_id("0-2-4", "<< swapped for >>") + " CAUGHT*",
            mutant_id("0-2-4", "| swapped for &") + " CAUGHT*",
            mutant_id("0-2-4", "| swapped for ^") + " MISSED*",
            "*::" + escape("test_set_bit[6-2-6]") + " PASSED*",
            mutant_id("6-2-6", "<< swapped for >>") + " MISSED*",
            mutant_id("6-2-6", "| swapped for &") + " CAUGHT*",
            mutant_id("6-2-6", "| swapped for ^") + " CAUGHT*",
        ]
    )


def test_unmarked_tests_get_no_mutants(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        from bit_mutant_examples import set_bit


        def test_set_bit():
            assert set_bit(0, 2) == 4
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["bit-mutant: added 0 mutant tests, 1 tests in total"])
    result.stdout.no_fnmatch_line("*mutation testing*")


def test_mutation_is_undone_after_each_test(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import set_bit

        ORIGINAL = set_bit.__code__


        @pytest.mark.mutate(target=set_bit)
        def test_weak():
            assert set_bit(0, 2) == 4


        def test_runs_after_the_mutants():
            assert set_bit.__code__ is ORIGINAL
            assert set_bit(6, 2) == 6
        """
    )
    result = pytester.runpytest("-p", "no:randomly")
    assert result.parseoutcomes() == {"passed": 2, "caught": 2, "missed": 1}
    result.stdout.no_fnmatch_line("*test_runs_after_the_mutants FAILED*")


def test_mutant_is_seen_through_other_modules(pytester: pytest.Pytester):
    # The mutant replaces the code inside the function object, so callers in
    # other modules, and names imported with `from ... import`, see it too.
    pytester.makepyfile(
        mylib="""
        from bit_mutant_examples import is_even


        def count_even(xs):
            return sum(is_even(x) for x in xs)
        """,
        test_mylib="""
        import pytest

        import mylib
        from bit_mutant_examples import is_even


        @pytest.mark.mutate(target=is_even)
        def test_count_even():
            assert mylib.count_even([1, 2, 3, 4]) == 2
        """,
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 1, "caught": 2}


def test_exception_counts_as_caught(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import is_even


        @pytest.mark.mutate(target=is_even)
        def test_index():
            # The mutants return a value that isn't a bool, so indexing fails.
            assert [10, 20][is_even(3) + 0] == 10
            assert {False: "odd", True: "even"}[is_even(4)] == "even"
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 1, "caught": 2}


def test_mutants_get_fixtures(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import set_bit


        @pytest.fixture
        def start():
            return 6


        @pytest.mark.mutate(target=set_bit)
        def test_set_bit(start, tmp_path):
            assert tmp_path.is_dir()
            assert set_bit(start, 2) == 6
            assert set_bit(0, 2) == 4
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 1, "caught": 3}


def test_class_based_tests(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import set_bit


        class TestSetBit:
            @pytest.mark.mutate(target=set_bit)
            @pytest.mark.parametrize("x, n, expected", [(0, 2, 4), (6, 2, 6)])
            def test_set_bit(self, x, n, expected):
                assert set_bit(x, n) == expected
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 2, "caught": 4, "missed": 2}
    result.stdout.fnmatch_lines(["*::TestSetBit::test_set_bit  3/3 caught"])


def test_marker_on_class_applies_to_its_tests(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import is_even


        @pytest.mark.mutate(target=is_even)
        class TestIsEven:
            def test_odd(self):
                assert is_even(3) is False

            def test_even(self):
                assert is_even(4) is True
        """
    )
    result = pytester.runpytest()
    # Each test is scored on its own: odd inputs alone can't catch | or ^
    # (both still give a non-zero result), so test_odd lets them survive.
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        [
            "*::TestIsEven::test_odd *0/2 caught",
            "*::TestIsEven::test_even *2/2 caught",
        ]
    )


def test_several_targets_on_one_test(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import is_even, set_bit


        @pytest.mark.mutate(target=is_even)
        @pytest.mark.mutate(target=set_bit)
        def test_both():
            assert is_even(set_bit(0, 2))
            assert not is_even(set_bit(0, 0))
            assert set_bit(0, 2) == 4
            assert set_bit(6, 2) == 6
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [
            "bit-mutant: added 5 mutant tests, 6 tests in total",
            "*::test_both  5/5 caught",
        ]
    )


def test_methods_closures_and_properties(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import Flags, make_masker

        low_nibble = make_masker(0x0F)


        @pytest.mark.mutate(target=Flags.clear)
        def test_clear():
            flags = Flags(0b1110)
            flags.clear(0b0100)
            assert flags.value == 0b1010


        @pytest.mark.mutate(target=Flags.low_byte.fget)
        def test_low_byte():
            assert Flags(0x1FF).low_byte == 0xFF
            assert Flags(0x100).low_byte == 0


        @pytest.mark.mutate(target=low_nibble)
        def test_closure():
            assert low_nibble(0xAB) == 0x0B
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [
            "*::test_clear *3/3 caught",
            "*::test_low_byte *2/2 caught",
            "*::test_closure *2/2 caught",
        ]
    )


def test_invert_mutant(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples.encoding import align_down


        @pytest.mark.mutate(target=align_down)
        def test_align_down():
            # 0 & anything is 0, so dropping the ~ makes no difference.
            assert align_down(0, 8) == 0
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        ["*::test_align_down  2/3 caught", "    survived: align_down:* ~x->x"]
    )


def test_skip_also_matches_in_place_operators(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import Flags


        @pytest.mark.mutate(target=Flags.set, skip={"|": ["^"]})
        def test_set():
            flags = Flags(2)
            flags.set(4)
            assert flags.value == 6
        """
    )
    result = pytester.runpytest("-rs")
    # |= -> ^= would survive, but skip={"|": ["^"]} leaves it out.
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 1, "skipped": 1, "caught": 1}
    result.stdout.fnmatch_lines(
        ["SKIPPED *skipped mutant: Flags.set:* |= swapped for ^="]
    )


def test_weak_test_must_still_pass_unmutated(pytester: pytest.Pytester):
    # xfail on a mutated test is about its mutants. A real failure of the
    # unmutated test still fails the run, rather than counting as XFAIL.
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import set_bit


        @pytest.mark.mutate(target=set_bit)
        @pytest.mark.xfail(reason="known weak")
        def test_set_bit():
            assert set_bit(0, 2) == 5
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes()["failed"] == 1


def test_failures_and_survivors_together(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import set_bit


        @pytest.mark.mutate(target=set_bit)
        def test_weak():
            assert set_bit(0, 2) == 4


        def test_broken():
            assert False
        """
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes() == {
        "failed": 1,
        "passed": 1,
        "caught": 2,
        "missed": 1,
    }
    result.stdout.fnmatch_lines(["    survived: set_bit:* | swapped for ^"])


def test_summary_counts_across_files(pytester: pytest.Pytester):
    pytester.makepyfile(
        test_a=GOOD_SET_BIT_TEST,
        test_b="""
        import pytest

        from bit_mutant_examples import is_even


        @pytest.mark.mutate(target=is_even)
        @pytest.mark.parametrize("x, expected", [(3, False), (4, True)])
        def test_is_even(x, expected):
            assert is_even(x) == expected
        """,
    )
    result = pytester.runpytest()
    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(
        [
            "test_a.py::test_set_bit  *3/3 caught",
            "test_b.py::test_is_even  *2/2 caught",
            "5/5 mutants caught",
        ]
    )


def test_deselected_mutants_are_not_survivors(pytester: pytest.Pytester):
    pytester.makepyfile(GOOD_SET_BIT_TEST)
    # Every clone's id contains "swapped", so this runs only the originals.
    result = pytester.runpytest("-k", "not swapped")
    assert result.ret == pytest.ExitCode.OK
    assert result.parseoutcomes() == {"passed": 2, "deselected": 6}
    result.stdout.no_fnmatch_line("*mutation testing*")


def test_mutants_never_reached_are_not_survivors(pytester: pytest.Pytester):
    pytester.makepyfile(
        """
        import pytest

        from bit_mutant_examples import set_bit


        def test_broken():
            assert False


        @pytest.mark.mutate(target=set_bit)
        def test_weak():
            assert set_bit(0, 2) == 4
        """
    )
    # -x stops at the first failure, before any mutant runs.
    result = pytester.runpytest("-x")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    assert result.parseoutcomes() == {"failed": 1}
    result.stdout.no_fnmatch_line("*mutation testing*")
