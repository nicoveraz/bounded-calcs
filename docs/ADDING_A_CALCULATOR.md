# Adding a calculator

Follow the steps in order. Do not skip one, and do not start a second calculator before the
first is committed. The hard rules and the stop conditions are in `CLAUDE.md`; they apply to
every step.

The goal is two implementations of the same score, written separately from the same source:
a YAML spec (what ships) and a small Python `reference` function (in the test). A test
compares them on every input. If you write one by looking at the other, the test proves
nothing.

## Step 0. Pick the task

Open `docs/ROADMAP.md` and take the first item marked **ready**. Read its whole entry and
the GitHub issue it links to: they name the id to use, the sources, and known pitfalls. If
the item needs a decision that is still open, stop and ask the user.

## Step 1. Open the sources

1. Open the primary paper. Try in this order: a PubMed tool with the PMID from the roadmap
   (or `https://pubmed.ncbi.nlm.nih.gov/<PMID>/`), the free full text on PubMed Central if
   there is a PMC id (`https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/`), the DOI page
   (`https://doi.org/<doi>`).
2. If `nicoveraz/calc-bounds` already implements the score (the roadmap says so), get a
   read-only copy with `git clone --depth 1 https://github.com/nicoveraz/calc-bounds` in a
   temporary directory outside this repo, and read `src/calc_bounds/calculators/<id>.py` and
   the matching section of `docs/CALCULATOR_NOTES.md`. Those readings were reviewed by the
   author.
3. Write down, for each source, how far you got: `[P]` full text read, `[A]` abstract only,
   `[S]` secondary source (NICE, a guideline, a later paper by the same group).
4. If the scoring table is in none of the texts you could open, stop and ask the user to
   attach the paper. Do not fill gaps from memory.

## Step 2. Write the scoring table

Before any code, write this table in your reply to the user. Every later step copies from it.

| Item | Source wording (quote) | Points | Inequality | Where in the source | Verified |
|---|---|---|---|---|---|
| ... | "..." | ... | `>=`, `>`, `<=`, `<` or none | Table 2, abstract, Figure 1... | [P] / [A] / [S] |

Then add below it:

- **Categories**: each category with its exact cut-off ("0-1 low, 2 moderate, 3 or more high").
- **Applies to**: who the score is for and who is excluded (adults only, low pretest
  probability, and so on). This is the applicability gate.
- **Disagreements**: anything two sources state differently (abstract and full text, paper and
  guideline). Each one becomes a `TODO(physician-review):` note in step 5.

Copy the inequality from the wording. "Age 65 or older" is `>=`. "More than 3 days" is `>`.
If the wording does not settle it, that is a disagreement to record, not something to guess.

## Step 3. Check that it fits

Find each line of your table in this list. If a line matches nothing, stop and ask.

| The source says | Rule to use | Example to read |
|---|---|---|
| A finding is present: n points | `present` | `wells_pe.yaml`, hemoptysis |
| A finding subtracts points | `present` with negative points | `tests/test_engine.py`, toy_negative |
| The absence of a finding earns points ("absence of cough") | `absent`, on an item named for the finding (`cough`) | `tests/test_engine.py`, toy_negative |
| One of several graded options | ordinal item + `levels` | `heart.yaml`, ECG |
| A choice with no order (for example sex) | ordinal item + `levels` | `tests/test_engine.py`, toy_reverse |
| A number falls in a range | numeric item + `bands` | `heart.yaml`, age |
| Number of risk factors: 0, 1-2, 3 or more | `count` | `heart.yaml`, risk_factors |
| "A or B" earns the point once | `any_of` | `curb65.yaml`, blood_pressure |
| Rule-out rule: negative only if every criterion is met | one point per criterion that is **not** met; categories `negative` and `positive` (`min: 1`) | `perc.yaml` |
| Tiers of criteria (any high-risk one, else any medium-risk one) | component groups: see "Groups" below | `pecarn_head_2plus.yaml` |
| A cut-off that depends on an item (different thresholds for men and women) | component groups: see "Groups" below | `tests/test_engine.py`, toy_sex |
| The source gives a score and no decision categories (a severity scale) | leave `categories` out: a score-only calculator | `tests/test_engine.py`, toy_scale |
| The result is a formula on continuous values | `formula` instead of `components`: see "Formulas" below | `tests/test_formula.py`, RATIO |

Never invent categories. If the primary paper defines no cut-off but clinicians use one,
take it from a guideline or a validation paper that you opened (decided by the author on
2026-11-11): cite it under `references` with `[S]` or `[A]` and the sentence that states the
cut-off, and write the category label so that it says what that source says the cut-off
means. Never take a cut-off from a website or from memory. If no such source can be opened,
the calculator stays score-only. In its test file the reference returns
`(score, None)`, and the sparse-note test asserts the score range instead of the categories.

Two more things fit:

- **Points of a number that depend on a category** (haemoglobin scored differently for men and
  women): rule `bands_by`, with `item` (numeric), `by` (an ordinal item) and one band table
  per level of `by`. Every level needs its table. The engine knows that an unknown `by` item
  matters only where the tables differ.

  ```
  - id: haemoglobin
    label: Haemoglobin
    rule: bands_by
    item: haemoglobin
    by: sex
    bands:
      male: [{gte: 13, points: 0}, {gte: 12, points: 1}, {gte: 10, points: 3}, {points: 6}]
      female: [{gte: 12, points: 0}, {gte: 10, points: 1}, {points: 6}]
  ```

- **A stage that is the highest any criterion gives** (not a sum): put `combine: highest` at
  the top level. Each criterion is a component whose points are the stage it gives; points
  cannot be negative; groups cannot be used. In the reference function use `max(...)`.

It does **not** fit, and you must stop, if:

- one item would feed two components (for example the same blood pressure in two criteria);
- a category depends on something that groups of components cannot express (see "Groups");
- a criterion needs arithmetic on two items (a ratio to a baseline value) inside a calculator
  with points;
- the score mixes points and a formula (a number added to a sum of points), or its formula
  does not move in one direction with some input (see "Formulas");
- points are not whole or half numbers.

### Formulas

A formula calculator has no `components`. Its spec has the items and

    formula:
      expression: (a / b) / c
      decimals: 2
      monotonic: {a: increasing, b: decreasing, c: decreasing}

- The expression uses item ids, numbers, `+ - * / **`, parentheses and `ln`, `log10`, `exp`,
  `sqrt`, `min`, `max`. A yes/no item counts 1 or 0. An ordinal item needs
  `values: {<item>: {<level>: <number>}}`.
- Every numeric item needs `accepts`, from a source: it is what bounds the result while the
  item is unknown, so a range that is too wide gives useless bounds and one that is too
  narrow rejects real patients.
- `monotonic` says, for every numeric item, whether the result rises or falls when the item
  rises. The loader checks it and refuses a spec where it does not hold. If the formula goes
  up and then down with some input, it does not fit: stop and ask.
- Limits the source puts on an input ("values below 1 are set to 1") are written with `max`
  and `min` in the expression.
- Give the parts of a long formula the names the source uses, under `where:` (see
  `meld_na.yaml`), so that the spec can be read against the paper line by line. A name may
  use items and the names above it.
- `decimals` only if the source rounds the result; cut-offs are compared after rounding.
- In the test file the reference returns `(result, category)` (`(result, None)` when there
  are no categories) and is checked with `assert_matches_reference(CALC, reference)`, as for
  every calculator. Write a test for each limit the source puts on an input and for every
  worked example it gives.

### Groups

Categories normally compare the total score with a cut-off. When the source decides the
category another way, put components in groups and let a category compare the points of one
group. A fragment (the full skeleton is in step 5):

    components:
      - {id: a, rule: present, item: a, points: 1, group: high_risk}
      - {id: b, rule: present, item: b, points: 1, group: medium_risk}
    categories:                      # lowest first; the LAST category whose condition holds applies
      - name: no_criteria
      - {name: medium_risk, group: medium_risk, min: 1}
      - {name: high_risk, group: high_risk, min: 1}

- **Tiers** ("category A if any high-risk criterion, otherwise B if any medium-risk one"):
  one group per tier, 1 point per criterion, and each category names its group with `min: 1`.
  The score is then the number of criteria present; say in `notes` that the category depends
  on the tier, not on the score.
- **A cut-off that depends on an item** (2 for men, 3 for women, where being a woman scores
  1 point): leave that item's component outside the group and put the cut-off on the group.
- A component's points always count in the total as well. The key is `group` in both places
  (never `on`: YAML reads a bare `on` as true).

In the `reference` function write the rule the way the source states it (`if any high-risk
criterion: ...`), not with groups.

## Step 4. Decide type and kind for every item

**Type**

| Type | Use when | Values a client sends |
|---|---|---|
| `boolean` | the criterion is there or not | present / absent / unknown |
| `ordinal` | one of a fixed list of options | one of `levels` / unknown |
| `numeric` | notes normally record it as a number (age, vital signs, laboratory values) | a number in `unit` / unknown |

If notes usually record the criterion as a finding ("vomited twice", "calf swelling more than
3 cm"), make it `boolean` and put the threshold in the label. If a threshold depends on a
laboratory-specific limit (troponin as a multiple of the upper reference limit), use `ordinal`
levels as `heart.yaml` does.

**Kind** (who is allowed to supply the value)

| Kind | Use when |
|---|---|
| `judgment` | the source asks for the clinician's impression or estimate: "suspicion", "more likely than", "appears", "distracting", gestalt. A note cannot settle it even if it lists every fact. Needs a `question`. |
| `measurement` | a number, or a level derived from a number (troponin band). |
| `finding` | everything else a note can document: history, symptoms, examination findings, diagnoses, ECG reading. |

When you hesitate between `finding` and `judgment`, choose `judgment` and add a
`TODO(physician-review):` note. A needless question to the clinician is cheap; a model
inventing a clinician's judgment is not.

**Wording**

- Name every boolean item for the finding itself, never for its absence. In a rule-out rule
  that lists "no midline tenderness", the item is `midline_tenderness` and present is the
  criterion that fails. If a score gives points for an absence ("absence of cough"), the item
  is `cough` and the component uses the `absent` rule. "Absent" must always mean the finding
  is not there.
- The `label` is the criterion as the source defines it, with its time window and threshold.
- The `question` is one sentence a clinician can answer in a word, and it does not suggest an
  answer. Required for `judgment` items, recommended for ordinal items.
- One unit per numeric item, the one the source uses. The caller converts; add a note with the
  conversion factor if another unit is common (see urea in `curb65.yaml`).
- Reuse an existing item id (`age`, `heart_rate`, `sbp`, `dbp`, `resp_rate`, `spo2`...) only
  when the definition and the unit are identical. List them with
  `grep -h "  - id:" src/bounded_calcs/specs/*.yaml | sort | uniq -c`. A different definition
  gets a new id (CURB-65 `confusion` and a GCS-based item are not the same thing). A reused id
  must copy the existing definition exactly: type, kind, unit, levels and `normal`. A test
  enforces this.
- **Normal range.** A numeric item that notes often describe only as "normal" (vital signs,
  routine laboratory values) may declare `normal: [lo, hi]`: the default range assumed when a
  note says "vital signs normal". A site can replace it with its own laboratory's range. When
  the item id already exists in another spec, copy its range and its note. Otherwise, add a
  range only if a source or calc-bounds (`params.py`, `absent_means`) gives one, with a
  `TODO(physician-review):` note saying where it came from. A range may cross a threshold:
  then "normal" narrows the item without deciding it, and the engine asks for the value when
  it matters. Never add a range for age, weight or other values that are never just
  "normal".
- **Other units.** If the item is commonly reported in another unit, declare it with its
  factor to the item's unit: `units: {bun_mg/dL: {divide_by: 2.8014}}` (or `multiply_by`).
  Add a `label` saying what the unit means when its name is not what a note would write
  (`label: "urea nitrogen (BUN) in mg/dL"`); the schema shows it to the model.
  The engine then converts a value sent as `{"value": x, "unit": "bun_mg/dL"}` and refuses
  any unit that is not declared. Name the unit so that it cannot be misread: when two
  analytes share a unit (urea and urea nitrogen in mg/dL), put the analyte in the name and do
  not declare the bare unit. The factor comes from a source or from calc-bounds (`units.py`),
  never from memory; say where in an item note. Only a factor fits: a conversion that adds
  an offset (degrees Fahrenheit) does not, so leave it out and stop and ask if it matters.
- **Accepted range.** A numeric item may declare `accepts: [lo, hi]`: a value outside it is
  an input error and is not scored. Use it to catch unit and transcription slips, and ages
  the score was not made for. It belongs to this calculator: do not copy it from another spec
  that uses the same item id unless the same range is right here. Add a range only if a
  source or calc-bounds (`docs/CALCULATOR_NOTES.md`, parameter modelling choices) gives one,
  with a note saying where it came from. Every threshold of the item must lie inside it.
- The applicability gate goes in `purpose` and `notes`. Do not add items for it.

## Step 5. Write the spec

Create `src/bounded_calcs/specs/<id>.yaml`. The file name must equal the `id`. Skeleton (the
content is invented; copy the structure, never the numbers):

```yaml
id: example_score              # lowercase snake_case, same as the file name
name: Example score
version: 1
purpose: What it estimates, in which patients (include the applicability gate).
citation: >-
  Author AB, Author CD. Title. Journal Year;Vol(Issue):pages. doi:10.xxxx/xxxxx. PMID 12345678. [P]
references:
  - Author EF et al. Journal Year;Vol:pages. PMID 23456789. [A]
higher_is_higher_risk: true    # false only if a LOWER score is worse
notes:
  - "Applies only to ... (gate from the source). The calculator does not check this."

items:
  - id: impression
    label: Clinician's impression of ... (exact criterion wording)
    type: boolean
    kind: judgment
    question: Is ... more likely than ...?
  - id: temperature
    label: Temperature
    type: numeric
    kind: measurement
    unit: C
    normal: [36, 37.9]         # optional: assumed when a note says only "normal"
    notes:
      - "TODO(physician-review): implemented as > 38.0 (abstract); the full text may say >= 38.0."
      - "TODO(physician-review): normal range 36 to 37.9 C, taken from <source>."
  - id: severity
    label: Severity of ...
    type: ordinal
    kind: finding
    levels: [mild, moderate, severe]

components:
  - {id: impression, label: Impression, rule: present, item: impression, points: 2}
  - id: temperature
    label: Temperature > 38
    rule: bands
    item: temperature
    bands:                     # first match wins: most extreme threshold first
      - {gt: 38, points: 1}
      - {points: 0}            # the last band has no condition
  - id: severity
    label: Severity
    rule: levels
    item: severity
    points: {mild: 0, moderate: 1, severe: 2}

categories:                    # ascending by score; the first has no bound
  - name: low
    label: Low (0-1)
  - name: high
    label: High (2 or more)
    min: 2                     # score >= 2; use "gt: 4" for "more than 4" with half points
```

YAML traps that the loader rejects with an explanation:

- A note or label containing `: ` must be wrapped in double quotes, or YAML turns it into a
  mapping. Always quote notes that start with `TODO(physician-review):`.
- Bare `yes`, `no`, `on`, `off`, `true`, `false` and numbers are not text. Do not use them as
  level names or ids.
- Unknown or misspelled keys are errors (`point` for `points`, `ge` for `gte`).

Check that it loads before going on:

```sh
uv run python -c "from bounded_calcs import load_builtin; print(load_builtin()['<id>'].name)"
```

## Step 6. Write the test file

Copy `tests/calculators/test_curb65.py` to `tests/calculators/test_<id>.py` and replace its
content part by part. Keep the structure:

1. **Docstring**: the source, and one line saying where the reference comes from.
2. **`CALC = load_builtin()["<id>"]`**
3. **`ZERO`**: a complete input that scores the minimum. Tests change one thing from it.
4. **`reference(v)`**: write it from the scoring table of step 2, in the order the source
   lists the criteria, **without looking at the YAML**. `v[item]` is `True`/`False` for
   boolean items, the level name for ordinal items, a number for numeric items. Return
   `(score, category_name)`. Do not import or read the spec inside it.
5. **`test_matches_reference`**: one line, `assert_matches_reference(CALC, reference)`. It
   compares spec and reference on every complete input (numbers are tried at each threshold
   and on both sides of it), then checks the engine's bounds and its lists of unknown items
   against brute force over the reference.
6. **Threshold tests**: for every numeric threshold in the source, one case at the threshold
   and one just past it, with the expected points taken from the source wording.
7. **Worked examples**: if the paper gives a patient with a per-item breakdown, add it.
8. **Unknown is not normal**: at least one realistic sparse note (only what a triage note
   would contain). Assert that it is not settled, the possible categories, and which unknowns
   are decisive. If the score allows it, add one case that is settled while items are still
   unknown.

Work out every expected value by hand and write the arithmetic in a comment. For a partial
input: add the points of the known items; each unknown component then contributes anything
from its lowest to its highest possible points. The score range is the known points plus the
sum of the lowest and the sum of the highest; the possible categories are those of every score
in between that can actually be formed. Never paste the engine's output as the expectation.

`assert_matches_reference` cannot catch a threshold that is wrong in the same way in the spec
and in the reference. Only the threshold tests of point 6, written from the source's own
numbers, and the physician's review protect against that.

## Step 7. Register it

- `README.md`: add a row to the "Calculators" table.
- `docs/ROADMAP.md`: move the item from "Next" to the "Built" table, with its verification
  tags and the number of open `TODO(physician-review)` notes.

## Step 8. Run everything

```sh
uv run pytest
```

All tests must pass, with none skipped that passed before. What a failure means:

| Failure | Meaning | What to do |
|---|---|---|
| `errors during collection` in every test file at once | the new spec does not load, so nothing can run | run the load command of step 5 and read its `SpecError` |
| `SpecError: ... can never apply because an earlier entry always matches first` | bands or count thresholds are in the wrong order | most extreme threshold first |
| `SpecError: ... unknown key(s)` | a key is misspelled or not part of the format | fix the key; do not extend the format |
| `SpecError: ... must be text` or `expected a mapping` | YAML did not read a value as text | wrap it in double quotes |
| `SpecError: ... already used by component` | one item in two components | the calculator does not fit: stop and ask |
| `yaml.scanner.ScannerError: mapping values are not allowed here` | a text value contains `: ` and is not quoted | wrap the whole value in double quotes |
| `SpecError: ... unknown key(s)` naming part of a label | a label with a comma inside a one-line `{...}` mapping was split | wrap the label in double quotes |
| `spec and reference disagree on a complete input` | the YAML and `reference` differ for the inputs shown | re-read the source for that item; fix the side that is wrong |
| `engine and reference disagree on a partial input` | should not happen once complete inputs agree | do not touch the engine: stop and report the message |
| `no input ever reaches [...]` | a category cut-off is impossible | check the cut-offs in the source |
| `test_has_a_reference_test` | the test file is missing or lacks `reference` | step 6 |
| `test_listed_in_readme_and_roadmap` | step 7 not done | add the rows |
| `test_cites_a_source_and_says_how_it_was_verified` | PMID/DOI or `[P]`/`[A]`/`[S]` missing | fix `citation` and `references` |
| `test_judgment_items_have_a_question` | a judgment item has no `question` | add it |
| `test_shared_item_ids_have_one_definition` | a reused item id differs from its other definition | copy the definition, or use a new id |
| `test_review_markers_are_spelled_exactly` | a marker is misspelled | `TODO(physician-review):` exactly |

If a test that existed before your change fails, your change broke something or the
calculator does not fit. Do not edit that test. Stop and ask.

## Step 9. Review your own work

Answer each line with yes before committing.

- Every number in the spec is in the scoring table of step 2, with its place in the source.
- Every inequality was copied from the source wording.
- No item is named for an absence; points for an absence use the `absent` rule.
- Judgment items have `kind: judgment` and a `question`.
- Units are stated, and conversions are noted where another unit is common.
- `citation` and each reference end with `[P]`, `[A]` or `[S]` and reflect what you really read.
- The applicability gate is in `purpose` or `notes`.
- `reference` was written from the table, not from the YAML.
- There is a threshold test for each numeric threshold and a sparse-note test.
- Each disagreement from step 2 has a `TODO(physician-review):` note, and you wrote no
  `REVIEWED(physician)` marker unless the roadmap entry told you to carry one over.
- Only the four files listed in `CLAUDE.md` changed (`git status`).
- `uv run pytest` is green.

## Step 10. Commit and report

```sh
git add src/bounded_calcs/specs/<id>.yaml tests/calculators/test_<id>.py README.md docs/ROADMAP.md
git commit    # subject: Add <name> (<id>); body: sources with tags, TODO(physician-review)
              # notes, and a last line "Closes #N" with the number of the item's issue
```

Then give the report described in `CLAUDE.md` ("Working style") and stop.
