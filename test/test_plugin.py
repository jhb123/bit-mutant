"""Run the plugin on the example tests with pytester and check what it reports.

Each test copies a test file from examples/tests (or writes one) into a
throwaway directory, runs pytest on it in-process, and inspects the outcome.
bit-mutant and bit-mutant-examples are installed, so pytest loads the plugin
through its entry point and the tests import the example code, the same way a
user's run would.
"""

import pytest


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
