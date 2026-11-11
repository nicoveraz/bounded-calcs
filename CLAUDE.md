# CLAUDE.md — bounded-calcs

Clinical calculators that treat **unknown as unknown**: one YAML spec per calculator, an exact
bounding engine, a Python library and an MCP server. Companion to the paper repo
`nicoveraz/calc-bounds` (arXiv:2609.34112). Research and reference tool, not a medical device.

These instructions are written so that a small model can extend the repo safely. Follow them
literally. When they do not cover a situation, stop and ask; do not improvise.

## Start here

| Task | Read first |
|---|---|
| Add a calculator | `docs/ADDING_A_CALCULATOR.md`, then follow it step by step |
| Choose what to build | `docs/ROADMAP.md`: take the first item marked **ready**, one at a time, and read the GitHub issue it links to |
| Understand the engine | README "How it works"; docstrings of `spec.py`, `model.py`, `engine/__init__.py`, `engine/rules/__init__.py`, `testing.py` |
| Prepare a release | `docs/RELEASING.md`, and only when the user asks for a release |

## Hard rules

1. **Unknown is never absent or normal.** No defaults for missing items, in code, specs,
   tests or examples.
2. **No clinical criteria from memory.** Every item, threshold, inequality (`>` or `>=`),
   point value and category cut-off comes from a source you opened in this session. If you
   cannot open a source, stop and ask the user for it (they can attach the PDF).
3. **Say how each source was verified.** End every citation with `[P]` (primary full text
   read), `[A]` (abstract only) or `[S]` (secondary source, such as NICE or a later paper).
4. **Mark what is uncertain.** For an ambiguous or unverifiable criterion, implement the best
   reading and add an item note that starts with `TODO(physician-review):` and gives the
   reading chosen and the alternative. Only the user changes a `TODO(physician-review)` into
   `REVIEWED(physician)`. Never write `REVIEWED(physician)` yourself, unless a roadmap entry
   tells you to carry over a reading that calc-bounds already records as reviewed.
5. **Two independent implementations.** Every calculator has a `reference(v)` function in
   `tests/calculators/test_<id>.py`, written from the source and not from the YAML, and checked
   with `assert_matches_reference`. When the two disagree, re-read the source. Never copy one
   side into the other to make the test pass.
6. **Expected values come from the source, by hand.** Never run the engine and paste its
   output into a test as the expected value.
7. **Never weaken a check to get green.** Do not edit or delete existing tests, loosen the
   validation in `spec.py`, or change `testing.py` to make something pass. If a check looks
   wrong, stop and ask.
8. **Engine and format are frozen unless the user approves.** Adding a calculator touches only
   the files listed in "What a calculator consists of". Do not change `engine/`, `spec.py`,
   `model.py`, `_validate.py`, `formula.py`, `testing.py`, `mcp_server.py`, the YAML format or
   the names of output fields (they are a public API). If a calculator does not fit the
   format, stop and ask.
9. **Deterministic core.** No LLM calls, network access or randomness in `src/`.
10. **No real patient data** anywhere: specs, tests, examples, commit messages.
11. **No claims of clinical validity.** Never write that this is validated, safe for clinical
    use or a medical device.
12. **Dependencies:** `pyyaml` (runtime), `mcp>=2,<3` (optional extra), `pytest` (dev). Ask
    before adding anything else.

## When to stop and ask

- You cannot open the primary source, and the scoring table is not in an abstract or a
  secondary source you can open.
- The score exists in versions (two-tier or three-tier, original or modified) and the roadmap
  does not say which one.
- The calculator needs something the format lacks: an item used by two components,
  categories that neither the total score nor a group of components can express, a formula
  that is not monotonic or is mixed with points, or points that are not whole or half numbers.
- A test you did not write fails, or a fix seems to need a change in `src/` outside `specs/`.
- Sources disagree in a way that changes a category for some patient and you cannot tell
  which reading the roadmap intends.
- You are about to push, publish, tag a release or change repository settings.

## What a calculator consists of

Adding calculator `<id>` creates or edits exactly these files:

| File | Change |
|---|---|
| `src/bounded_calcs/specs/<id>.yaml` | new: the spec |
| `tests/calculators/test_<id>.py` | new: reference function, threshold tests, clinical examples |
| `README.md` | one row in the calculator table |
| `docs/ROADMAP.md` | move the item to the "Built" table |

Nothing else. The MCP server and the generic tests pick up new specs automatically.

## Layout

```
src/bounded_calcs/
  spec.py         the YAML format and its loader: items, categories, the top level
  model.py        the dataclasses a spec loads into (Item, Component, Category, Calculator)
  _validate.py    small checks shared by the loader and the rule parsers; SpecError
  formula.py      formula calculators: the expression language and its checks (no eval)
  engine/         the bounding engine, one job per module
    inputs.py       what a caller may send (words, numbers, ranges, units) -> the engine's state
    rules/          one module per scoring rule (present, levels, bands, any_of, count): each
                    reads its own YAML keys and computes its own points
    bounds.py       reachable scores and categories; which unknown items can change them
    formula_bounds.py  the same for formula calculators (result range from the input ranges)
    result.py       evaluate() and schema(): the output fields (public API)
    state.py        the state's type and shared helpers
  testing.py      assert_matches_reference(): spec and engine against an independent reference
  mcp_server.py   MCP tools: list_calculators, get_schema, evaluate
  _mcp_launcher.py  the bounded-calcs-mcp command (explains a missing MCP extra)
  specs/*.yaml    one calculator each (file name = id)
tests/
  calculators/    one test file per calculator (copy test_curb65.py for a new one)
  test_builtin_specs.py   rules every built-in calculator must satisfy
  test_spec.py, test_engine.py, test_formula.py, test_testing.py, test_mcp.py
docs/
  ADDING_A_CALCULATOR.md  the procedure
  ROADMAP.md              what is built, what is next, open decisions
  RELEASING.md            how a version reaches PyPI
scripts/smoke_test.py     checks a built wheel or sdist as an installed package
.github/workflows/tests.yml     runs the tests on every push to main and every pull request
.github/workflows/publish.yml   tests, builds and publishes when a version tag is pushed
```

## Commands

```sh
uv sync                                          # install (pytest and the MCP SDK included)
uv run pytest                                    # everything; must be green before a commit
uv run pytest tests/calculators/test_<id>.py -x  # one calculator while working
uv run python -c "from bounded_calcs import load_builtin; print(list(load_builtin()))"
uv run bounded-calcs-mcp                         # MCP server on stdio
grep -rn "TODO(physician-review)" src/bounded_calcs/specs/   # open review items
```

The MCP SDK is version 2: `from mcp.server import MCPServer`, tool errors via
`mcp.server.mcpserver.exceptions.ToolError`. Version 1 `FastMCP` examples do not apply. Check
an API by importing it before you use it.

## Working style

- One calculator per commit. Subject: `Add <name> (<id>)`. Body: sources with their `[P]`,
  `[A]`, `[S]` tags, each `TODO(physician-review)` note you added, and a last line
  `Closes #N` with the number of the item's issue.
- Give your report in your reply. Comment on an issue, or change its labels, only when the
  user asks.
- Do not refactor, rename or "improve" anything outside the task.
- Everything in the repository is written in English: code, specs, docs, commit messages.
- Run `uv run pytest` before every commit and read the output. A commit with a failing or
  skipped test is not done.
- Push only when the user asks. The default branch is `main`.
- End every task with this report:
  1. What you added (files).
  2. Sources and how each was verified (`[P]`, `[A]`, `[S]`), and what you could not open.
  3. The scoring table you built in step 2 of the procedure.
  4. The last line of `uv run pytest`.
  5. Every `TODO(physician-review)` note you added, quoted in full.
  6. Anything you were unsure about.
- After a roadmap item, stop. Start the next one only when the user says so.
