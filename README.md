# bounded-calcs

[![Tests](https://github.com/nicoveraz/bounded-calcs/actions/workflows/tests.yml/badge.svg)](https://github.com/nicoveraz/bounded-calcs/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/bounded-calcs)](https://pypi.org/project/bounded-calcs/)

Clinical calculators that treat **unknown as unknown**.

Most calculator tools, and the LLM benchmarks built on them, take a complete input. When a
note doesn't mention a finding, someone fills it in as absent or normal, and the calculator
returns a confident number. `bounded-calcs` instead accepts **present / absent / unknown** for
every item and returns:

- whether the decision category is **settled** by what is known,
- every category still **possible**, and the **worst case**,
- the exact **score range**,
- the **decisive unknowns**: the only items worth asking the clinician about, with what the
  category would be for each possible answer.

It packages the approach from *Unknown is not normal: separating language-model extraction
from rule-based decision logic for clinical risk scores*
([arXiv:2609.34112](https://arxiv.org/abs/2609.34112); experiment code:
[calc-bounds](https://github.com/nicoveraz/calc-bounds)): the LLM only reads the note;
deterministic code decides whether the missing items matter.

> **Research and reference use only.** Not a medical device. The built-in definitions were
> reviewed by one emergency physician (the author); several sources were read only as
> abstracts or through secondary sources, as each spec states.

## Install

```bash
pip install bounded-calcs            # the library
pip install "bounded-calcs[mcp]"     # the library and the MCP server
```

Python 3.11 or later. The MCP server can also run without installing anything first: see
[MCP server](#mcp-server).

## Calculators

| id | Calculator | Source | Verified |
|---|---|---|---|
| `heart` | HEART score (low / moderate / high) | Six et al., Neth Heart J 2008. PMID 18665203 | [P] |
| `wells_pe` | Wells criteria for PE, two-tier (unlikely / likely) | Wells et al., Thromb Haemost 2000. PMID 10744147 | [A], [S] |
| `perc` | PERC rule (negative / positive) | Kline et al., J Thromb Haemost 2004. PMID 15304025 | [A] |
| `curb65` | CURB-65 (low / moderate / high) | Lim et al., Thorax 2003. PMID 12728155 | [P] |
| `qsofa` | qSOFA (negative / positive) | Seymour et al., JAMA 2016. PMID 26903335; Sepsis-3 criteria | [A], [P] |
| `pecarn_head_under2` | PECARN head injury rule, under 2 years (CT not recommended / observation versus CT / CT recommended) | Kuppermann et al., Lancet 2009. PMID 19758692 | [P] |
| `pecarn_head_2plus` | PECARN head injury rule, 2 years and older (CT not recommended / observation versus CT / CT recommended) | Kuppermann et al., Lancet 2009. PMID 19758692 | [P] |
| `wells_dvt` | Wells criteria for DVT, two-tier (unlikely / likely) | Wells et al., N Engl J Med 2003. PMID 14507948; NICE NG158 table 1 | [P], [S] |
| `mcisaac` | McIsaac sore throat score (no culture or antibiotic / culture, treat if positive / culture, treat on clinical grounds) | McIsaac et al., CMAJ 1998. PMID 9475915 | [P] |
| `nexus` | NEXUS cervical spine criteria (negative / positive) | Hoffman et al., N Engl J Med 2000. PMID 10891516 | [P] |

Verified: **[P]** primary full text read, **[A]** abstract only, **[S]** secondary source
(guideline or later paper). All four are ported from calc-bounds, whose readings the author
reviewed and accepted (`docs/CALCULATOR_NOTES.md` there). Item notes in each spec record the
reading implemented and the alternatives: `REVIEWED(physician)` marks a reading a physician
accepted, `TODO(physician-review)` one that is still open.

Every calculator is checked against an independent reference function on all complete
inputs, including each numeric threshold, and on partial inputs by brute force.

## Example

A note documents heart rate 110, no haemoptysis, no malignancy, and says nothing else:

```python
from bounded_calcs import load_builtin, evaluate

wells = load_builtin()["wells_pe"]
r = evaluate(wells, {"heart_rate": 110, "hemoptysis": "absent", "malignancy": "absent"})
```

```json
{
  "settled": false,
  "possible_categories": ["pe_unlikely", "pe_likely"],
  "worst_case_category": "pe_likely",
  "score_range": [1.5, 10.5],
  "decisive_unknowns": [
    {"item": "dvt_signs", "kind": "finding", "settles_decision_in": "1 of 2 answers", "...": "..."},
    {"item": "pe_most_likely", "kind": "judgment", "settles_decision_in": "1 of 2 answers", "...": "..."}
  ],
  "jointly_relevant_unknowns": ["immobilization_or_surgery", "prior_vte"],
  "judgment_items_pending": ["pe_most_likely"]
}
```

Filling the silence with "absent" would have returned *PE unlikely*. The honest answer is
that it depends on two things the note doesn't say, one of which only the clinician can judge.

## Inputs

- **boolean** items: `"present"`, `"absent"` (or `true` / `false`)
- **ordinal** items: one of the listed levels
- **numeric** items: a number in the item's unit; a range `{"min": x, "max": y}` when the
  source gives only bounds ("heart rate over 100": `{"min": 100}`); or `"normal"` when the
  source says only that the value is normal and the item has a normal range (`get_schema`
  lists it). A range on one side of every threshold settles the item; one that crosses a
  threshold leaves it as a question when it matters. The result names any range assumed for
  "normal" under `normal_assumed`, with its source
- anything omitted, `null`, or `"unknown"` is unknown, **never** normal
- a numeric item without a normal range (such as age) that the source only calls "normal" is
  also unknown; never invent a number

Each item also has a **kind**: `finding` (readable from a note), `measurement` (vitals, labs,
age) or `judgment` (clinician only, e.g. HEART history, Wells "alternative diagnosis less
likely"). Clients should never infer judgment items from text.

### Unknown categories in the output

| field | meaning |
|---|---|
| `decisive_unknowns` | knowing this item alone could narrow the possible categories; ask these, in order |
| `jointly_relevant_unknowns` | knowing it alone cannot rule out a category, but for some values of the other unknowns it changes the category; ask these when no decisive unknown is left |
| `irrelevant_unknowns` | cannot change the category, whatever the other unknowns turn out to be (every unknown, once the result is settled) |

## MCP server

Runs over stdio by default, so notes stay on the machine. With
[uv](https://docs.astral.sh/uv/) installed, one command fetches and starts it:

```bash
uvx --from "bounded-calcs[mcp]" bounded-calcs-mcp
```

Claude Desktop / Claude Code config:

```json
{
  "mcpServers": {
    "bounded-calcs": {
      "command": "uvx",
      "args": ["--from", "bounded-calcs[mcp]", "bounded-calcs-mcp"]
    }
  }
}
```

**Site normal ranges.** "Normal" for a laboratory value depends on the laboratory. The
default urea range (2.5 to 8 mmol/L) crosses the CURB-65 threshold of 7 on purpose, so "urea
normal" is asked about when it matters. A site whose laboratory's upper limit is at most 7 can
say so once, in a YAML or JSON file, and pass it to the server:

```yaml
# ranges.yaml: item id -> [lo, hi] in the item's unit
urea: [2.5, 7.0]
```

```bash
uvx --from "bounded-calcs[mcp]" bounded-calcs-mcp --normal-ranges ranges.yaml
```

In Python: `evaluate(calc, findings, normal_ranges={"urea": [2.5, 7.0]})`.

From a clone of this repository, use `"command": "uv"` with
`"args": ["--directory", "/path/to/bounded-calcs", "run", "bounded-calcs-mcp"]`.

Tools: `list_calculators`, `get_schema(calculator_id)`, `evaluate(calculator_id, findings)`.
The server's instructions tell the model to send only documented findings, ask about
decisive unknowns, and never fill judgment items itself.

## Adding a calculator

Each calculator is one YAML file in `src/bounded_calcs/specs/`: items (type, kind, levels or
unit, a question to ask), components (how items become points), and categories. Component
rules: `present`, `absent`, `levels`, `bands` (numeric thresholds), `count` (number of present
items, with an optional override item), and `any_of` (points if any of several conditions is
met, such as CURB-65's "SBP < 90 or DBP <= 60"). Points may be negative. Every item belongs to
exactly one component; that is what makes the bounds exact rather than approximate. The
loader is strict: misspelled keys, bands that can never match and text that YAML misread are
errors.

The procedure is in [`docs/ADDING_A_CALCULATOR.md`](https://github.com/nicoveraz/bounded-calcs/blob/main/docs/ADDING_A_CALCULATOR.md), the
queue in [`docs/ROADMAP.md`](https://github.com/nicoveraz/bounded-calcs/blob/main/docs/ROADMAP.md), and the rules for AI coding agents in
[`CLAUDE.md`](https://github.com/nicoveraz/bounded-calcs/blob/main/CLAUDE.md). In short: take every criterion from the primary source, write the
spec and an independent reference function, and let `assert_matches_reference` compare them:

```python
from bounded_calcs import load_file
from bounded_calcs.testing import assert_matches_reference

def reference(v):   # written from the paper, not from the YAML
    score = v["confusion"] + (v["urea"] > 7) + (v["resp_rate"] >= 30) \
        + (v["sbp"] < 90 or v["dbp"] <= 60) + (v["age"] >= 65)
    return score, "low" if score <= 1 else "moderate" if score == 2 else "high"

assert_matches_reference(load_file("curb65.yaml"), reference)
```

## How it works

Components are independent, so the reachable scores are exactly the sumset of each
component's reachable points; there is no sampling and no LLM in the loop. Categories compare
the total with cut-offs or, for rules a total cannot express (tiers of criteria, a cut-off
that differs by sex), the points of a group of components; the bounds stay exact. An unknown item is
decisive if some value of it removes at least one category from the possible set, and
jointly relevant if it is not decisive but, for some values of the other unknowns, changing it
changes the category. Whenever the result is not settled, at least one unknown is decisive or
jointly relevant, so there is always something to ask. Decisive
items are ordered by how often an answer settles the decision, then by how much it narrows on
average, with data items before judgments when otherwise equal.

## Development

```bash
uv sync
uv run pytest
```

Releases are published to PyPI by a GitHub Actions workflow when a version tag is pushed:
[`docs/RELEASING.md`](https://github.com/nicoveraz/bounded-calcs/blob/main/docs/RELEASING.md).

Each calculator has its own test file with an independent reference function, threshold
cases taken from the source, and sparse-note examples. Other tests cover the spec loader's
validation, input handling, every rule type, an end-to-end MCP session, and that the
reference check itself fails on a wrong spec.

## License

MIT
