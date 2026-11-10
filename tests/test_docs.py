"""The instructions in docs/ must stay true: the skeleton has to load, and the messages and
examples the procedure quotes have to exist."""

import re
from pathlib import Path

import yaml

from bounded_calcs import evaluate, parse

ROOT = Path(__file__).resolve().parent.parent
PROCEDURE = (ROOT / "docs" / "ADDING_A_CALCULATOR.md").read_text(encoding="utf-8")
SRC = "\n".join(
    p.read_text(encoding="utf-8") for p in (ROOT / "src" / "bounded_calcs").glob("*.py")
)
# Join string literals that are split across lines, so whole messages can be searched for.
SRC = re.sub(r'"\s*\n\s*f?"', "", SRC)


def test_skeleton_in_the_procedure_is_a_valid_spec():
    block = re.search(r"```yaml\n(.*?)```", PROCEDURE, re.S).group(1)
    calc = parse(yaml.safe_load(block))
    assert calc.id == "example_score"
    assert evaluate(calc, {})["possible_categories"] == ["low", "high"]


def test_failure_messages_quoted_in_the_procedure_exist():
    for message in [
        "can never apply because an earlier entry always matches first",
        "unknown key(s)",
        "must be text",
        "expected a mapping",
        "already used by component",
        "spec and reference disagree on a complete input",
        "engine and reference disagree on a partial input",
        "no input ever reaches",
        "straddles a threshold",
        "crosses a threshold of the reference",
    ]:
        assert message in PROCEDURE, message
        assert message in SRC, message


def test_examples_named_in_the_procedure_exist():
    for name in re.findall(r"`(\w+\.yaml)`", PROCEDURE):
        assert (ROOT / "src" / "bounded_calcs" / "specs" / name).exists(), name
    engine_tests = (ROOT / "tests" / "test_engine.py").read_text(encoding="utf-8")
    for toy in ("toy_negative", "toy_reverse"):
        assert toy in PROCEDURE and toy in engine_tests
    assert (ROOT / "tests" / "calculators" / "test_curb65.py").exists()
    for test in re.findall(r"`(test_\w+)`", PROCEDURE):
        if test not in ("test_matches_reference",):
            assert f"def {test}(" in (ROOT / "tests" / "test_builtin_specs.py").read_text(), test
