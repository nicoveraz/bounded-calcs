# Roadmap

Last updated 2026-11-10. Work top to bottom, one item at a time. To start a session, a prompt
like this is enough:

> Read CLAUDE.md and docs/ROADMAP.md. Do the first roadmap item marked ready, following
> docs/ADDING_A_CALCULATOR.md step by step. Stop after the commit and give me the report.

Statuses: **ready** (can be done now), **needs decision** (blocked on a question for Nicolás
below), **needs design** (not for unattended work).

Every item has a GitHub issue, linked next to it, with the same content and the full list of
sources. Decisions are answered in the issue. If an issue's label and this file disagree, the
issue is newer: update this file before starting. A commit that completes an item ends its
message with `Closes #N`.

## Built

| id | Calculator | Sources | Review | Open TODOs |
|---|---|---|---|---|
| `heart` | HEART score | [P] Six 2008; [A] Backus 2010, 2013; [P] Backus 2011, Poldervaart 2013 | reviewed 2026-09-27 (calc-bounds) | 0 |
| `wells_pe` | Wells criteria for PE, two-tier | [A] Wells 2000; [A] van Belle 2006; [S] NICE NG158 | reviewed 2026-09-27 (calc-bounds) | 0 |
| `perc` | PERC rule | [A] Kline 2004; [A] Kline 2008 | reviewed 2026-09-27 (calc-bounds) | 0 |
| `curb65` | CURB-65 | [P] Lim 2003 | reviewed 2026-09-27 (calc-bounds) | 0 |
| `qsofa` | qSOFA | [A] Seymour 2016; [P] Singer 2016 (Sepsis-3) | reviewed 2026-09-27 (calc-bounds) | 0 |
| `pecarn_head_under2` | PECARN head injury rule, under 2 years | [P] Kuppermann 2009 and 2014 erratum | open readings confirmed 2026-11-10 | 0 |
| `pecarn_head_2plus` | PECARN head injury rule, 2 years and older | [P] Kuppermann 2009 and 2014 erratum | open readings confirmed 2026-11-10 | 0 |

"Reviewed (calc-bounds)" means the readings were accepted by the author, an emergency
physician, as recorded in `docs/CALCULATOR_NOTES.md` of `nicoveraz/calc-bounds`.

## Decisions needed from Nicolás

Answer these before the matching item is started. Each has a recommendation; "go with the
recommendations" is a valid answer.

- **D1. Wells DVT version ([#3](https://github.com/nicoveraz/bounded-calcs/issues/3)).** Two-tier (likely / unlikely, Wells 2003) or three-tier (low /
  moderate / high, Wells 1997)? Recommended: two-tier, consistent with `wells_pe`.
- **D2. Sore throat score ([#4](https://github.com/nicoveraz/bounded-calcs/issues/4)).** Centor (four criteria) or McIsaac (Centor plus age)?
  Recommended: McIsaac as `mcisaac`, because its primary paper is free full text and can be
  verified as [P]. **Decided 2026-11-10: McIsaac, as `mcisaac`.**
- **D3. CHA2DS2-VASc categories ([#5](https://github.com/nicoveraz/bounded-calcs/issues/5)).** Guideline cut-offs differ and can depend on sex; this
  format only supports categories defined by the total score. Recommended: use the score-only
  categories exactly as the source paper defines them, and say in `notes` that guideline
  thresholds differ. The alternative is to wait for an engine change. **Decided 2026-11-10:
  wait for categories that can depend on an item (#12).**
- **D4. Canadian CT Head Rule encoding ([#6](https://github.com/nicoveraz/bounded-calcs/issues/6)).** It has two tiers of criteria, so it needs the
  "tiered rules" encoding of the procedure, where the score is not clinically meaningful.
  Recommended: accept the encoding, with categories `no_criteria`, `medium_risk`, `high_risk`.
  **Decided 2026-11-10: wait for an engine change that models tiers directly.** Until then
  the PECARN rules (D5) use the encoding.
- **D5. PECARN head injury rules ([#23](https://github.com/nicoveraz/bounded-calcs/issues/23)).** Decided 2026-11-10: the head injury
  rules (Kuppermann 2009), as two calculators by age, with the tiered encoding.

## Next calculators

All citations below were checked in PubMed on 2026-11-10. "Structure hints" describe the shape
of the score so you know which rules to expect. They are **not** criteria: take every item,
number and inequality from the source.

### 1. NEXUS cervical spine criteria: `nexus` — ready ([#2](https://github.com/nicoveraz/bounded-calcs/issues/2))

- Source: Hoffman JR et al. N Engl J Med 2000;343(2):94-99.
  doi:10.1056/NEJM200007133430203. PMID 10891516. The abstract lists the five criteria; the
  definitions of each criterion are in the full text.
- Structure hints: a rule-out rule like `perc.yaml`: one point per criterion that is not met,
  categories `negative` (0) and `positive` (`min: 1`). Name each item for the finding, not
  for its absence. At least one criterion is a clinician judgment.
- If you can only open the abstract, tag it [A] and add a `TODO(physician-review):` note on
  every item whose definition you could not read.
- Applies to blunt trauma patients: put the gate in `purpose` and `notes`.

### 2. Wells criteria for DVT: `wells_dvt` — needs decision D1 ([#3](https://github.com/nicoveraz/bounded-calcs/issues/3))

- Sources: Wells PS et al. Lancet 1997;350(9094):1795-1798.
  doi:10.1016/S0140-6736(97)08140-3. PMID 9428249 (three-tier). Wells PS et al. N Engl J Med
  2003;349(13):1227-1235. doi:10.1056/NEJMoa023153. PMID 14507948 (two-tier).
- Neither abstract contains the item list. You need the full text, or NICE guideline NG158
  (its DVT table) as a secondary source [S]; calc-bounds used the same guideline for `wells_pe`.
- Structure hints: one item subtracts points and is a clinician judgment; the two versions do
  not have the same item list; several examination findings carry a threshold in their
  wording (make those boolean, with the threshold in the label).

### 3. Sore throat score: `mcisaac` — ready, McIsaac decided in D2 ([#4](https://github.com/nicoveraz/bounded-calcs/issues/4))

- Sources: Centor RM et al. Med Decis Making 1981;1(3):239-246.
  doi:10.1177/0272989X8100100304. PMID 6763125 (the abstract lists the four variables).
  McIsaac WJ et al. CMAJ 1998;158(1):75-83. PMID 9475915, free full text PMC1228750.
  McIsaac WJ et al. JAMA 2004;291(13):1587-1595. doi:10.1001/jama.291.13.1587. PMID 15069046.
- Structure hints: one criterion is the absence of a symptom: use the `absent` rule on an
  item named for the symptom. The modified score adds age bands, one of them negative. The
  score has a lower age limit: gate in `purpose` and `notes`.

### 4. CHA2DS2-VASc: `cha2ds2_vasc` — needs design, waits for #12 (D3) ([#5](https://github.com/nicoveraz/bounded-calcs/issues/5))

- Source: Lip GYH et al. Chest 2010;137(2):263-272. doi:10.1378/chest.09-1584.
  PMID 19762550. The abstract does not contain the points table; you need the full text.
- Structure hints: age has two bands; one item is worth more than the others; sex is an
  ordinal item with two levels (`levels` rule).

### 5. Canadian CT Head Rule: `canadian_ct_head` — needs design, waits for engine tiers (D4) ([#6](https://github.com/nicoveraz/bounded-calcs/issues/6))

- Source: Stiell IG et al. Lancet 2001;357(9266):1391-1396.
  doi:10.1016/S0140-6736(00)04561-X. PMID 11356436.
- Structure hints: five high-risk and two medium-risk criteria (tiered encoding). The rule
  only applies to a defined group of patients with minor head injury, with exclusions: gate
  in `purpose` and `notes`.
- Known trap: the abstract writes two of the criteria with a strict inequality ("vomiting >2
  episodes", "age >65 years"). The rule is often reproduced with "2 or more" and "65 or
  older". Read the rule figure in the full text. If you cannot open it, stop and ask: this
  changes the category of a 65-year-old.

## Sources and review (needs Nicolás)

- **Full texts behind abstract-only sources ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)).** `wells_pe`, `perc` and two of the
  `heart` validation papers were read as abstracts. The issue lists, per calculator, each
  source, its identifiers and what the full text would settle. It needs the PDFs.
- **Wording changes to confirm ([#8](https://github.com/nicoveraz/bounded-calcs/issues/8)).** Labels and notes of the four specs were aligned
  with the readings calc-bounds records as accepted; the author should confirm each one.

## Engine work (needs design; ask before starting)

These change the engine or the input format, so they are not for unattended work.

1. **"Normal" for numeric items ([#9](https://github.com/nicoveraz/bounded-calcs/issues/9)).** In the paper, a note that says "heart rate normal" maps to
   an interval that does not straddle any threshold (calc-bounds `absent_means`). Here numeric
   items accept only a number or unknown, so such a note costs a question. Needs: a declared
   normal interval per item, a `normal` input value, and a check that the interval crosses no
   threshold.
2. **Plausible ranges for numeric items ([#10](https://github.com/nicoveraz/bounded-calcs/issues/10)).** Reject impossible values (age 500,
   SpO2 0.97) instead of scoring them. calc-bounds has ranges in `calculators/params.py`.
3. **Formula calculators ([#11](https://github.com/nicoveraz/bounded-calcs/issues/11))** (Cockcroft-Gault and similar). The score is continuous.
   calc-bounds bounds it exactly by evaluating the corners of the box formed by the inputs'
   allowed ranges (`bounds/__init__.py`), so this depends on item 2.
4. **Categories that depend on an item ([#12](https://github.com/nicoveraz/bounded-calcs/issues/12))**, such as sex-specific cut-offs, and items
   shared by two components.
5. **Laboratory reference ranges for "normal" ([#20](https://github.com/nicoveraz/bounded-calcs/issues/20)).**
   "Urea normal" assumes the laboratory's upper limit is at most 7 mmol/L. Proposed: interval
   inputs in the engine, normal ranges allowed to cross a threshold, and site-configurable
   reference ranges.

## Distribution ([#13](https://github.com/nicoveraz/bounded-calcs/issues/13))

Decided on 2026-11-10: publish on PyPI, and no npm package for now. An `npx` wrapper would
still need Python, and a TypeScript port is a second engine to keep in step while the engine
work above is open. The MCP SDK stays an optional extra (`bounded-calcs[mcp]`), so the library
alone depends only on PyYAML. The release procedure is in `docs/RELEASING.md`.

## Housekeeping

- Repository metadata ([#15](https://github.com/nicoveraz/bounded-calcs/issues/15)): `CITATION.cff` modelled on the one in calc-bounds, the
  GitHub "About" description (currently empty), and a link from the arXiv listing at the
  paper's next version.

## Not planned unless Nicolás asks

- A hosted HTTP API. The MCP server already supports the `streamable-http` transport, but a
  hosted service would receive patient data and raises regulatory questions.
