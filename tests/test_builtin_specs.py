"""Rules every built-in calculator must satisfy. If one of these fails after you add a
calculator, the message says what is missing; see docs/ADDING_A_CALCULATOR.md."""

import re
from pathlib import Path

import pytest

from bounded_calcs import evaluate, load_builtin

ROOT = Path(__file__).resolve().parent.parent
CALCS = load_builtin()
each = pytest.mark.parametrize("calc", list(CALCS.values()), ids=lambda c: c.id)


@each
def test_has_a_reference_test(calc):
    path = ROOT / "tests" / "calculators" / f"test_{calc.id}.py"
    assert path.exists(), f"add {path.relative_to(ROOT)} (copy tests/calculators/test_curb65.py)"
    text = path.read_text(encoding="utf-8")
    assert "def reference(" in text and "assert_matches_reference(CALC, reference" in text, (
        f"{path.name} must define reference(v) and call assert_matches_reference(CALC, reference)"
    )
    assert f'load_builtin()["{calc.id}"]' in text, f"{path.name} must test '{calc.id}'"


@each
def test_listed_in_readme_and_roadmap(calc):
    row = f"| `{calc.id}` |"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert row in readme, f"add a row for `{calc.id}` to the calculator table in README.md"
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    built = roadmap.split("## Built", 1)[1].split("\n## ", 1)[0]
    assert row in built, f"move `{calc.id}` to the 'Built' table in docs/ROADMAP.md"


@each
def test_cites_a_source_and_says_how_it_was_verified(calc):
    assert re.search(r"PMID \d+|doi:\S+", calc.citation), (
        f"{calc.id}: citation needs a PMID or DOI of the primary source"
    )
    for ref in (calc.citation, *calc.references):
        assert re.search(r"\[[PAS]\]\s*$", ref), (
            f"{calc.id}: end each citation/reference with [P] (full text read), [A] (abstract "
            f"only) or [S] (secondary source): {ref[:60]!r}..."
        )


@each
def test_judgment_items_have_a_question(calc):
    for item in calc.items.values():
        if item.kind == "judgment":
            assert item.question, f"{calc.id}.{item.id}: judgment items need a 'question'"


@each
def test_review_markers_are_spelled_exactly(calc):
    notes = [*calc.notes, *(n for i in calc.items.values() for n in i.notes)]
    for note in notes:
        for word in re.findall(r"\b(?:TODO|REVIEWED)\b[^:]*", note):
            assert word in ("TODO(physician-review)", "REVIEWED(physician)"), (
                f"{calc.id}: write the marker exactly as 'TODO(physician-review):' or "
                f"'REVIEWED(physician):', got {word!r}"
            )


@each
def test_every_category_is_possible_when_nothing_is_known(calc):
    r = evaluate(calc, {})
    assert r["possible_categories"] == calc.by_risk({c.name for c in calc.categories})
