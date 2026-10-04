"""A pytest plugin that mutation-tests bitwise operators.

Mark a test with the function it should protect:

    @pytest.mark.mutate(target=is_even)
    def test_is_even(): ...

"""

import dis
import logging
from dataclasses import dataclass

import pytest

logger = logging.getLogger("bit_mutant")


def build_instruction_table() -> dict[str, int]:
    """Map each operator symbol to the bytecode value that encodes it.

    Rather than hardcode numbers (which are a CPython implementation detail and
    can change between versions), compile a snippet using every operator and
    read the values back from the running interpreter.
    """
    probe = "\n".join([
        "a & b | c ^ d << e >> f",
        "a &= b",
        "a |= b",
        "a ^= b",
        "a <<= b",
        "a >>= b",
        "~a",
    ])
    src = compile(probe, "<probe>", "exec")
    instruction_lookup = {}
    for instruction in dis.get_instructions(src):
        if instruction.opname == "UNARY_INVERT":
            # ~ is its own instruction with no argument, so record the opcode.
            instruction_lookup["~"] = instruction.opcode
        elif instruction.opname.startswith("BINARY"):
            # All binary operators share one BINARY_OP instruction; the
            # argument (oparg) says which operator it is.
            instruction_lookup[instruction.argrepr] = instruction.oparg
    return instruction_lookup


# What each operator gets mutated into. Every entry produces one mutant per
# place the operator appears in the target function.
MUTATION_TABLE = {
    "&": ["|", "^"],
    "|": ["&", "^"],
    "^": ["&", "|"],
    "<<": [">>"],
    ">>": ["<<"],
    "&=": ["|=", "^="],
    "|=": ["&=", "^="],
    "^=": ["&=", "|="],
    "<<=": [">>="],
    ">>=": ["<<="],
    "~": [""],  # "" means drop the operator: ~x becomes x
}

# Runs once, when pytest imports this conftest at startup (before any hook).
INSTRUCTION_TABLE = build_instruction_table()

# Same size as UNARY_INVERT and leaves the stack alone, so swapping one for the
# other removes the ~ without shifting any other instruction.
NOP = dis.opmap["NOP"]

# Keys for the stash, pytest's place for plugins to keep their own data on its
# objects. Created once at module level so the hook that writes and the hook
# that reads share the same key object (stash lookups compare by identity).
#
# On a cloned item: (func, new_code), the mutant it runs.
mutant_key = pytest.StashKey[tuple]()
# On a cloned item: (test id, mutant description), which result it counts
# towards. Every case of a parametrized test shares the same test id.
group_key = pytest.StashKey[tuple[str, str]]()
# On config: {(test id, description): MutantResult}, filled in as clones run.
results_key = pytest.StashKey[dict]()


@dataclass
class MutantResult:
    target: str             # qualname of the mutated function
    weak_reason: str | None  # set if the test is marked xfail (known weak)
    killed: bool = False     # did any case catch it?


def make_mutants(func):
    """Yield (new_code, original, replacement, description) for each mutation
    of func's bytecode, where original/replacement are operator symbols.

    Each mutant changes exactly one instruction. Bytecode is "wordcode": every
    instruction is two bytes, [opcode, argument], starting at its offset.
    """
    code = func.__code__
    for instruction in dis.get_instructions(func):
        if instruction.opcode == INSTRUCTION_TABLE["~"]:
            # Replace the whole instruction (opcode byte) with a NOP. Only safe
            # if no inline cache entries follow it, since a NOP has none.
            if instruction.cache_info:
                continue
            co_code = bytearray(code.co_code)
            co_code[instruction.offset] = NOP
            co_code[instruction.offset + 1] = 0
            description = f"{func.__qualname__}:{instruction.positions.lineno} ~x->x"
            yield code.replace(co_code=bytes(co_code)), "~", "", description
            continue

        if instruction.opname != "BINARY_OP":
            continue
        for replacement in MUTATION_TABLE.get(instruction.argrepr, []):
            # Same opcode, different argument: only the second byte changes.
            new_arg = INSTRUCTION_TABLE[replacement]
            assert 0 <= new_arg < 256
            # Code objects are immutable, so edit a copy of the bytes and build
            # a new code object from it.
            co_code = bytearray(code.co_code)
            co_code[instruction.offset + 1] = new_arg
            description = (
                f"{func.__qualname__}:{instruction.positions.lineno} "
                f"{instruction.argrepr} swapped for {replacement}"
            )
            yield (
                code.replace(co_code=bytes(co_code)),
                instruction.argrepr,
                replacement,
                description,
            )


def is_skipped(skip: dict[str, list[str]], original: str, replacement: str) -> bool:
    """Whether the mark's skip table excludes this mutation.

    In-place operators are compared without their "=", so {"|": ["^"]} also
    skips "|=" -> "^=".
    """
    original = original.removesuffix("=")
    replacement = replacement.removesuffix("=")
    return any(
        op.removesuffix("=") == original
        and replacement in [r.removesuffix("=") for r in replacements]
        for op, replacements in skip.items()
    )


# --- Hooks, in the order pytest calls them ------------------------------------


# LIFECYCLE 1, startup. Called once, after command-line options and ini files
# are parsed and before collection starts. `config` holds all of that and lives
# for the whole run.
def pytest_configure(config):
    # Register the marker so pytest doesn't warn about an unknown mark.
    config.addinivalue_line(
        "markers",
        "mutate(target, skip=None): mutation-test target; skip is a dict like "
        "MUTATION_TABLE of mutations to leave out (e.g. equivalent mutants)",
    )
    # The final "N passed, M killed, ..." line colours each count using a
    # lookup table in pytest's terminal module, and anything not in it is
    # yellow. There's no public API for this, so add our categories to that
    # private table (pytest's own subtests plugin registers its categories in
    # it the same way). If a future pytest removes it, the counts just go back
    # to yellow.
    from _pytest import terminal

    colours = getattr(terminal, "_color_for_type", None)
    if isinstance(colours, dict):
        colours.setdefault(CAUGHT, "green")
        colours.setdefault(MISSED, "yellow")
    # Somewhere to collect mutant results as the clones run.
    config.stash[results_key] = {}


# LIFECYCLE 2, collection. Called once, after every test file has been imported
# and every test function turned into an item, with parametrize already
# expanded (test_x[weak] and test_x[good] are separate items by now). Nothing
# has run yet, and `items` is the exact list that will run, in that order, so
# this is the place to add, remove or reorder tests.
def pytest_collection_modifyitems(session, config, items):
    """After collection, add a copy of each marked test for every mutant."""
    new_items = []
    for item in items:
        new_items.append(item)  # the unmutated test
        # One id for the whole test, shared by all its parametrized cases, so
        # their results for a mutant can be combined.
        test_id = f"{item.parent.nodeid}::{item.originalname}"
        xfail = item.get_closest_marker("xfail")
        weak_reason = xfail.kwargs.get("reason", "marked xfail") if xfail else None
        for marker in item.iter_markers("mutate"):
            func = marker.kwargs["target"]
            skip = marker.kwargs.get("skip", {})
            logger.info("%s: mutating %s", item.nodeid, func.__qualname__)
            # Parametrized tests: keep the case's parameters with the clone, and
            # fold the case id into the name, e.g. test_x[0-2-4-<mutant>].
            callspec = getattr(item, "callspec", None)
            for new_code, original, replacement, description in make_mutants(func):
                logger.info("  mutant %s", description)
                if callspec is not None:
                    name = f"{item.originalname}[{callspec.id}-{description}]"
                else:
                    name = f"{item.name}[{description}]"
                # A new item that runs the same test function (and so gets the
                # same fixtures and parameters), under a name that says which
                # mutant it is. _fixtureinfo carries the parametrized arguments;
                # without it pytest would look for fixtures called x, n, ...
                clone = pytest.Function.from_parent(
                    item.parent,
                    name=name,
                    callobj=item.obj,
                    originalname=item.originalname,
                    callspec=callspec,
                    fixtureinfo=item._fixtureinfo,
                )
                # Remember which mutant this clone runs; read back at run time.
                clone.stash[mutant_key] = (func, new_code)
                # user_properties are copied onto every report for this item,
                # so the reporting hooks can tell mutant results apart.
                clone.user_properties.append(("bit_mutant", description))
                if is_skipped(skip, original, replacement):
                    # Still listed in the output, so ignored mutants stay visible.
                    clone.add_marker(
                        pytest.mark.skip(reason=f"skipped mutant: {description}")
                    )
                else:
                    clone.stash[group_key] = (test_id, description)
                    config.stash[results_key].setdefault(
                        (test_id, description),
                        MutantResult(func.__qualname__, weak_reason),
                    )
                    # One case missing a mutant isn't a failure by itself (another
                    # case may catch it), so a non-strict xfail keeps either
                    # outcome from failing the run: caught -> XFAIL, missed ->
                    # XPASS. Whether the mutant survived overall is decided at
                    # the end, in pytest_sessionfinish.
                    clone.add_marker(pytest.mark.xfail(strict=False))
                new_items.append(clone)
        if item.get_closest_marker("mutate"):
            # On a mutated test, xfail means "this test is known to let a
            # mutant survive". That's about the mutants only, so the unmutated
            # run drops it and must pass normally.
            item.own_markers[:] = [m for m in item.own_markers if m.name != "xfail"]
    # pytest only sees changes made to this exact list, so modify it in place.
    items[:] = new_items


# LIFECYCLE 2, end of collection. "collected N items" is printed while files
# are being collected, i.e. *before* modifyitems added the mutants, so it
# shows the original count. This hook runs after modifyitems; whatever string
# (or list of strings) it returns is printed under that line.
def pytest_report_collectionfinish(config, start_path, items):
    """Explain the item count: "collected N items" doesn't include mutants."""
    mutants = sum(mutant_key in item.stash for item in items)
    return f"bit-mutant: added {mutants} mutant tests, {len(items)} tests in total"


# LIFECYCLE 3, running, "call" phase. Called once per item, after its
# fixtures are set up. pytest's own implementation of this hook is what
# actually calls the test function.
#
# wrapper=True makes this a *hook wrapper*: it runs around all the other
# implementations. Code before `yield` runs first, `yield` runs the rest
# (i.e. the test), and code after it runs once the test is done. Whatever
# `yield` returns (or raises) is passed on, which is why it's `return (yield)`.
@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Run mutant clones with the mutated bytecode swapped in."""
    mutant = item.stash.get(mutant_key, None)
    if mutant is None:
        return (yield)  # not a mutant: run normally
    func, new_code = mutant
    # Swap the code inside the existing function object, so tests that did
    # `from module import func` see it too. MonkeyPatch restores the original
    # when the block exits, even if the test fails.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(func, "__code__", new_code)
        return (yield)  # the test runs here


# LIFECYCLE 3, running, after each phase. Called three times per item (setup,
# call, teardown) with `call` holding what happened: call.excinfo is the
# exception the phase raised, or None. As a wrapper, this sees the finished
# report after `yield`, but only reads it; the point is to record each clone's
# outcome against its mutant, combining the cases of a parametrized test.
@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    group = item.stash.get(group_key, None)
    if group is not None and call.when == "call" and call.excinfo is not None:
        # The test raised with the mutant in place: this case caught it.
        item.config.stash[results_key][group].killed = True
    return report


# Categories for mutant clones, as counted in the final summary line.
CAUGHT = "caught"
MISSED = "missed"


def is_mutant_report(report) -> bool:
    return any(key == "bit_mutant" for key, _ in report.user_properties)


# LIFECYCLE 3, running, after each phase. Called three times per item, once
# for each of the setup, call and teardown reports (hence the report.when
# check). By now xfail has been applied, so a clone's report says XFAIL
# (wasxfail + skipped) or XPASS (wasxfail + passed). This hook only changes
# how that is *shown* and *counted*.
def pytest_report_teststatus(report, config):
    """Report each clone as CAUGHT / MISSED instead of XFAIL / XPASS.

    Returns (category, short letter, verbose word). The category is what the
    final "N passed, M caught, ..." line counts.
    """
    if report.when != "call" or not is_mutant_report(report):
        return None  # let pytest decide as usual
    if hasattr(report, "wasxfail"):
        if report.skipped:
            return CAUGHT, "c", ("CAUGHT", {"green": True})
        return MISSED, "m", ("MISSED", {"yellow": True})
    return None


def survivors(results: dict, *, weak: bool) -> list:
    """Mutants no case caught, in known-weak tests (weak=True) or not."""
    return [
        group for group, result in results.items()
        if not result.killed and (result.weak_reason is not None) == weak
    ]


# LIFECYCLE 4, finishing. Called once, after every test has run, with the exit
# status pytest is about to use. Every clone has passed (XFAIL or XPASS), so
# without this a surviving mutant wouldn't fail the run. Changing
# session.exitstatus here is the supported way to change the outcome.
def pytest_sessionfinish(session, exitstatus):
    if exitstatus == pytest.ExitCode.OK and survivors(
        session.config.stash[results_key], weak=False
    ):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


# LIFECYCLE 4, finishing. Called once, just before the final "N passed, ..."
# line (after pytest_sessionfinish). Prints one line per mutated test, then
# the mutants that survived it.
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print each mutated test's score, and any surviving mutants."""
    results = config.stash[results_key]
    if not results:
        return
    tr = terminalreporter
    tr.section("mutation testing")

    by_test = {}  # test id -> {description: MutantResult}
    for (test_id, description), result in results.items():
        by_test.setdefault(test_id, {})[description] = result

    width = max(len(test_id) for test_id in by_test)
    for test_id, mutants in by_test.items():
        killed = sum(r.killed for r in mutants.values())
        weak_reason = next(iter(mutants.values())).weak_reason
        line = f"{test_id:<{width}}  {killed}/{len(mutants)} killed"
        if weak_reason is None:
            tr.write_line(line, green=killed == len(mutants), red=killed < len(mutants))
        elif killed < len(mutants):
            tr.write_line(f"{line}  (known weak: {weak_reason})", yellow=True)
        else:
            tr.write_line(
                f"{line}  (marked weak, but nothing survived: remove the xfail?)",
                yellow=True,
            )
        for description, result in mutants.items():
            if not result.killed:
                tr.write_line(f"    survived: {description}")

    total = len(results)
    killed = sum(r.killed for r in results.values())
    tr.write_line(f"\n{killed}/{total} mutants killed")
    if survivors(results, weak=False):
        tr.write_line(
            "Surviving mutants: the tests passed with the operator changed. Add a\n"
            "case where the original and the mutant give different answers.",
            red=True,
        )
