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

> **Research and reference use only.** Not a medical device. The earlier built-in definitions
> were reviewed by one emergency physician (the author); the calculators added since version
> 0.2.0 have not been reviewed yet (`docs/ROADMAP.md` lists the state of each). Some sources
> were read only in part, as abstracts or through secondary sources: each spec says exactly
> what was read, and marks every open question with `TODO(physician-review)`.

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
| `wells_pe` | Wells criteria for PE, two-tier (unlikely / likely) | Wells et al., Thromb Haemost 2000. PMID 10744147; cut-off and item table from van Belle et al. 2006 | [A], [P], [S] |
| `perc` | PERC rule (negative / positive) | Kline et al., J Thromb Haemost 2004. PMID 15304025 | [P] |
| `curb65` | CURB-65 (low / moderate / high) | Lim et al., Thorax 2003. PMID 12728155 | [P] |
| `qsofa` | qSOFA (negative / positive) | Seymour et al., JAMA 2016. PMID 26903335; Sepsis-3 criteria | [A], [P] |
| `pecarn_head_under2` | PECARN head injury rule, under 2 years (CT not recommended / observation versus CT / CT recommended) | Kuppermann et al., Lancet 2009. PMID 19758692 | [P] |
| `pecarn_head_2plus` | PECARN head injury rule, 2 years and older (CT not recommended / observation versus CT / CT recommended) | Kuppermann et al., Lancet 2009. PMID 19758692 | [P] |
| `wells_dvt` | Wells criteria for DVT, two-tier (unlikely / likely) | Wells et al., N Engl J Med 2003. PMID 14507948; NICE NG158 table 1 | [P], [S] |
| `mcisaac` | McIsaac sore throat score (no culture or antibiotic / culture, treat if positive / culture, treat on clinical grounds) | McIsaac et al., CMAJ 1998. PMID 9475915 | [P] |
| `nexus` | NEXUS cervical spine criteria (negative / positive) | Hoffman et al., N Engl J Med 2000. PMID 10891516 | [P] |
| `canadian_syncope` | Canadian Syncope Risk Score (very low / low / medium / high / very high) | Thiruganasambandamoorthy et al., CMAJ 2016. PMID 27378464 | [P] |
| `spesi` | Simplified PESI (low risk / high risk) | Jiménez et al., Arch Intern Med 2010. PMID 20696966 | [P] |
| `bisap` | BISAP (below 3 / 3 or more) | Wu et al., Gut 2008. PMID 18519429; cut-off from Singh et al. 2009 | [P], [A] |
| `meld_na` | MELD-Na, 2008 formula (score 6 to 40, no categories) | Kim et al., N Engl J Med 2008. PMID 18768945 | [P] |
| `canadian_ct_head` | Canadian CT Head Rule (no criterion / medium risk / high risk) | Stiell et al., Lancet 2001. PMID 11356436 | [P] |
| `has_bled` | HAS-BLED (not high risk / high risk) | Pisters et al., Chest 2010. PMID 20299623; cut-off from the 2010 ESC guideline | [P], [S] |
| `cha2ds2_va` | CHA2DS2-VA (score 0 / 1 / 2 or more) | 2024 ESC atrial fibrillation guideline, Eur Heart J 2024. doi:10.1093/eurheartj/ehae176 | [P] |
| `sf_syncope` | San Francisco Syncope Rule (negative / positive) | Quinn et al., Ann Emerg Med 2004. PMID 14747812 | [P] |
| `cincinnati_stroke` | Cincinnati Prehospital Stroke Scale (all normal / any abnormal) | Kothari et al., Ann Emerg Med 1999. PMID 10092713 | [P] |
| `rox` | ROX index (formula, no categories) | Roca et al., J Crit Care 2016, PMID 27481760; Am J Respir Crit Care Med 2019, PMID 30576221 | [P] |
| `killip` | Killip classification (A to D) | Killip and Kimball, Am J Cardiol 1967. PMID 6059183 | [P] |
| `parkland` | Parkland formula (a volume, no categories) | Baxter and Shires, Ann N Y Acad Sci 1968. PMID 4973463 | [P] |
| `glasgow_blatchford` | Glasgow-Blatchford bleeding score (score only) | Blatchford et al., Lancet 2000. PMID 11073021 | [P] |

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
- a numeric item that lists other units takes `{"value": x, "unit": u}`, and the engine
  converts it; a value outside the range the calculator accepts is an error, not a score (see
  Units, Site units and Accepted ranges below)
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

**Accepted ranges.** A numeric item can declare the values its calculator accepts. A value
outside that range (an oxygen saturation of 0.97, an age of 16 in an adult score) is an error
with an explanation, not a score.

**Score-only calculators.** A scale whose source gives a score and no decision categories
has no `categories` in its spec. The result is then the score: `settled` means the score is
exact, `score_range` bounds it otherwise, and each unknown item that can change it is listed
with the range the score would have for each answer. `meld_na` is score-only.

**Formula calculators.** A spec can have a `formula` instead of point components: an
expression on the items, such as `(a / b) / c`. A known input is used as it is; an unknown one
is bounded by the range the calculator accepts, and a value known only as a range by that
range. The spec declares whether the result rises or falls with each numeric input, and the
loader checks it, so the result's lowest and highest values are at the ends of those ranges:
`score_range` is exact, and every category it touches is listed as possible. For which unknown
inputs matter, formulas are conservative: an input is called irrelevant only if it cannot move
the result at all or the category is already settled. `meld_na` is the first built-in formula
calculator.

**Units.** Every numeric item has one unit, and a number sent alone is read in it. An item
can also declare other units with their conversion factor: CURB-65 urea is in mmol/L and
takes `{"value": 25, "unit": "bun_mg/dL"}` or `{"value": 54, "unit": "urea_mg/dL"}`. The
engine converts, and the result says so under `converted`. A unit the item does not declare
(a bare `mg/dL`, which does not say whether the laboratory reports urea or urea nitrogen) is
an error: the engine never guesses a conversion. The accepted range is checked after
conversion, so an unconverted BUN of 150 sent as mmol/L is refused too.

**Site units.** Which unit a laboratory reports is a fact about the site, so the site states
it once: `bounded-calcs-mcp --units units.yaml`, with lines such as `urea: bun_mg/dL`. A
value whose source gives no unit is then read in the site's unit and converted (`read_as` in
the result). Through the server, an item that declares more than one unit never takes a
number alone: the caller sends the unit the source gives, or `"unit": "not stated"`. Saying
it every time keeps a value in another unit (a report from another laboratory) from being
taken for the site's by omission. "Not stated" is accepted only when the site has set a unit;
otherwise the caller has to ask. In the library the same behaviour is
`evaluate(..., units={...}, require_units=True)`; by default the library reads a plain number
in the site's unit if one is given, and otherwise in the item's own unit. Normal ranges and
accepted ranges are always in the item's own unit. A note that quotes a value in another
unit without saying so cannot be caught by any of this, except by the accepted range.

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

The units a site's laboratory reports are set the same way, with `--units units.yaml`
(`urea: bun_mg/dL`); see Site units above.

From a clone of this repository, use `"command": "uv"` with
`"args": ["--directory", "/path/to/bounded-calcs", "run", "bounded-calcs-mcp"]`.

Tools: `list_calculators`, `get_schema(calculator_id, detail)`,
`evaluate(calculator_id, findings, detail)`. Both answer in a brief form by default, to keep a
model's context small: the schema without citations, provenance and review notes, the result
without the per-component breakdown. `detail="full"` returns everything. The Python functions
`schema()` and `evaluate()` always return everything.
The server's instructions tell the model to send only documented findings, ask about
decisive unknowns, and never fill judgment items itself.

## Adding a calculator

Each calculator is one YAML file in `src/bounded_calcs/specs/`: items (type, kind, levels or
unit, a question to ask), components (how items become points) or a formula, and categories
(left out for a score-only calculator). Component
rules: `present`, `absent`, `levels`, `bands` (numeric thresholds), `bands_by` (thresholds that depend on
another item, such as haemoglobin by sex), `count` (number of present
items, with an optional override item), and `any_of` (points if any of several conditions is
met, such as CURB-65's "SBP < 90 or DBP <= 60"). Points may be negative. The score is the
sum of the components, or with `combine: highest` the highest of them (staging systems). Every item belongs to
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

For a formula calculator the result range comes from the ends of the input ranges, which is
exact because the spec declares, and the loader checks, the direction of the result in each
input.

The engine is a small package with one module per job (`engine/inputs.py`, `engine/rules/`
with one module per scoring rule, `engine/bounds.py`, `engine/formula_bounds.py`,
`engine/result.py`). Each rule module also reads its own part of the YAML, so a new rule is
one new module and not an edit to the others.

## Development

```bash
uv sync
uv run pytest
```

Releases are published to PyPI by a GitHub Actions workflow when a version tag is pushed:
[`docs/RELEASING.md`](https://github.com/nicoveraz/bounded-calcs/blob/main/docs/RELEASING.md).

Each calculator has its own test file with an independent reference function, threshold
cases taken from the source, and sparse-note examples. Other tests cover the spec loader's
validation, input handling, units, every rule type, formula calculators, an end-to-end MCP
session, and that the reference check itself fails on a wrong spec.

## License

MIT
