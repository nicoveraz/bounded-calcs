# Roadmap

Last updated 2026-11-11. Work top to bottom, one item at a time. To start a session, a prompt
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
| `heart` | HEART score | [P] Six 2008; [A] Backus 2010, 2013; [P] Backus 2011, Poldervaart 2013 | reviewed 2026-09-27 (calc-bounds) | 1 |
| `wells_pe` | Wells criteria for PE, two-tier | [A] Wells 2000; [A] van Belle 2006; [S] NICE NG158 | reviewed 2026-09-27 (calc-bounds) | 0 |
| `perc` | PERC rule | [A] Kline 2004; [A] Kline 2008 | reviewed 2026-09-27 (calc-bounds) | 1 |
| `curb65` | CURB-65 | [P] Lim 2003 | reviewed 2026-09-27 (calc-bounds) | 1 |
| `qsofa` | qSOFA | [A] Seymour 2016; [P] Singer 2016 (Sepsis-3) | reviewed 2026-09-27 (calc-bounds) | 0 |
| `pecarn_head_under2` | PECARN head injury rule, under 2 years | [P] Kuppermann 2009 and 2014 erratum | open readings confirmed 2026-11-10 | 0 |
| `pecarn_head_2plus` | PECARN head injury rule, 2 years and older | [P] Kuppermann 2009 and 2014 erratum | open readings confirmed 2026-11-10 | 0 |
| `wells_dvt` | Wells criteria for DVT, two-tier | [P] Wells 2003; [S] NICE NG158 table 1 | not yet reviewed | 0 |
| `mcisaac` | McIsaac sore throat score | [P] McIsaac 1998 | not yet reviewed | 1 |
| `nexus` | NEXUS cervical spine criteria | [P] Hoffman 2000 and its correction | not yet reviewed | 2 |
| `canadian_syncope` | Canadian Syncope Risk Score | [P] Thiruganasambandamoorthy 2016 (figure 2 and legend) | not yet reviewed | 1 |
| `spesi` | Simplified PESI | [P] Jiménez 2010 (table 1 and methods) | not yet reviewed | 3 |
| `bisap` | BISAP (score only) | [P] Wu 2008 (methods and scoring sentence) | not yet reviewed | 3 |
| `meld_na` | MELD-Na, 2008 formula (formula, score only) | [P] Kim 2008 | not yet reviewed | 6 |
| `canadian_ct_head` | Canadian CT Head Rule | [P] Stiell 2001 (panel 1 and methods) | not yet reviewed | 1 |
| `has_bled` | HAS-BLED (score only) | [P] Pisters 2010 (methods and table 2) | not yet reviewed | 4 |
| `cha2ds2_vasc` | CHA2DS2-VASc | [P] Lip 2010 (table 2 and methods) | not yet reviewed | 2 |
| `sf_syncope` | San Francisco Syncope Rule | [P] Quinn 2004 (abstract and results) | not yet reviewed | 1 |

"Reviewed (calc-bounds)" means the readings were accepted by the author, an emergency
physician, as recorded in `docs/CALCULATOR_NOTES.md` of `nicoveraz/calc-bounds`.

## Decisions needed from Nicolás

Answer these before the matching item is started. Each has a recommendation; "go with the
recommendations" is a valid answer.

- **D1. Wells DVT version ([#3](https://github.com/nicoveraz/bounded-calcs/issues/3)).** Decided 2026-11-10: two-tier.
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
  **Decided 2026-11-10: wait for an engine change that models tiers directly.** Done:
  component groups; the PECARN rules (D5) use them since their version 2.
- **D5. PECARN head injury rules ([#23](https://github.com/nicoveraz/bounded-calcs/issues/23)).** Decided 2026-11-10: the head injury
  rules (Kuppermann 2009), as two calculators by age (tiers as component groups).

## Next calculators

All citations below were checked in PubMed on 2026-11-10. "Structure hints" describe the shape
of the score so you know which rules to expect. They are **not** criteria: take every item,
number and inequality from the source.

### 1. CHA2DS2-VASc: `cha2ds2_vasc` — needs the source and a category decision (D3) ([#5](https://github.com/nicoveraz/bounded-calcs/issues/5))

- Source: Lip GYH et al. Chest 2010;137(2):263-272. doi:10.1378/chest.09-1584.
  PMID 19762550. The abstract does not contain the points table; you need the full text.
- Structure hints: age has two bands; one item is worth more than the others; sex is an
  ordinal item with two levels (`levels` rule). Sex-dependent cut-offs fit the format now
  (component groups); which categories to ship, and from which source, is still to decide.

### 2. Canadian CT Head Rule: `canadian_ct_head` — ready once the full text is open (D4) ([#6](https://github.com/nicoveraz/bounded-calcs/issues/6))

- Source: Stiell IG et al. Lancet 2001;357(9266):1391-1396.
  doi:10.1016/S0140-6736(00)04561-X. PMID 11356436.
- Structure hints: five high-risk and two medium-risk criteria (one group per tier). The rule
  only applies to a defined group of patients with minor head injury, with exclusions: gate
  in `purpose` and `notes`.
- Known trap: the abstract writes two of the criteria with a strict inequality ("vomiting >2
  episodes", "age >65 years"). The rule is often reproduced with "2 or more" and "65 or
  older". Read the rule figure in the full text. If you cannot open it, stop and ask: this
  changes the category of a 65-year-old.

### Requested on 2026-11-10 and 2026-11-11

Each has an issue with the request, a first reading of the score's shape and the paper it
needs. "Fits" is that first reading, not checked against the source. "Source" says whether the
primary paper can be opened without Nicolás: **PMC** means a free full text exists in PubMed
Central; **readable on the publisher's site** means the full article opened in the browser on
2026-11-11; **needs PDF** means neither. Details are under Papers below.

| Issue | Calculator | Fits the format? | Source |
|---|---|---|---|
| [#47](https://github.com/nicoveraz/bounded-calcs/issues/47) | Modified Glasgow (Imrie) score | yes (expected) | PMC copy is a scan without text: needs a PDF or reading page images |
| [#47](https://github.com/nicoveraz/bounded-calcs/issues/47) | Ranson's criteria | partly: criteria that are a change between two times; cut-offs by aetiology | needs PDF; version to choose |
| [#37](https://github.com/nicoveraz/bounded-calcs/issues/37) | PESI | no: age is added as points (a formula inside a sum) | PMC |
| [#45](https://github.com/nicoveraz/bounded-calcs/issues/45) | San Francisco Syncope Rule | yes (expected) | needs PDF |
| [#29](https://github.com/nicoveraz/bounded-calcs/issues/29) | HAS-BLED | yes (expected) | needs PDF |
| [#30](https://github.com/nicoveraz/bounded-calcs/issues/30) | Cincinnati Prehospital Stroke Scale | yes; can be built from the abstract as [A] | needs PDF for [P] |
| [#31](https://github.com/nicoveraz/bounded-calcs/issues/31) | NIH Stroke Scale | score-only (done); version to choose | original 1989 scale readable on the publisher's site; current form to locate |
| [#40](https://github.com/nicoveraz/bounded-calcs/issues/40) | Killip classification | probably, with groups | needs PDF |
| [#43](https://github.com/nicoveraz/bounded-calcs/issues/43) | West Haven criteria | probably, with groups; version to choose | 2014 guideline readable on the publisher's site; 1977 original needs PDF |
| [#36](https://github.com/nicoveraz/bounded-calcs/issues/36) | Glasgow-Blatchford | no if points depend on sex and haemoglobin together | needs PDF |
| [#41](https://github.com/nicoveraz/bounded-calcs/issues/41) | ROX index | formula (done) | needs PDF |
| [#44](https://github.com/nicoveraz/bounded-calcs/issues/44) | AKIN staging | no: highest of several criteria, from ratios | PMC |
| [#38](https://github.com/nicoveraz/bounded-calcs/issues/38) | KDIGO AKI staging | no: the same | guideline free on kdigo.org |
| [#48](https://github.com/nicoveraz/bounded-calcs/issues/48) | Rule of nines, Lund and Browder, Parkland | Parkland is a formula (done); burn size feeds it (not supported); output is a volume to infuse, which needs Nicolás's explicit decision | needs PDFs |

Built on 2026-11-11 from this list: Canadian Syncope, sPESI, BISAP and MELD-Na (2008
formula; the version is still Nicolás's to confirm).
The four papers now readable for #7 (van Belle 2006, Kline 2004 and 2008, Backus 2013) can
turn those `[A]` tags into `[P]`.

## Papers

Checked in PubMed on 2026-11-11 (citation matched to a PMID, title read, PMC id looked up).
A paper with no PMC id has to be attached to its issue as a PDF, or read through the
browser where the user has access.

**Free full text (can be opened now)**

| For | Paper | Identifiers |
|---|---|---|
| PESI | Aujesky D et al. Am J Respir Crit Care Med 2005;172(8):1041-1046 | PMID 16020800 · PMC2718410 · doi:10.1164/rccm.200506-862OC |
| MELD-Na | Kim WR et al. N Engl J Med 2008;359(10):1018-1026 | PMID 18768945 · PMC4374557 · doi:10.1056/NEJMoa0801209 |
| AKIN | Mehta RL et al. Crit Care 2007;11(2):R31 | PMID 17331245 · PMC2206446 · doi:10.1186/cc5713 |
| Canadian Syncope | Thiruganasambandamoorthy V et al. CMAJ 2016;188(12):E289-E298 | PMID 27378464 · PMC5008955 · doi:10.1503/cmaj.151469 |
| Modified Glasgow (Imrie) | Blamey SL et al. Gut 1984;25(12):1340-1346 | PMID 6510766 · PMC1420197 · doi:10.1136/gut.25.12.1340 |

**Readable on the publisher's site (opened in the browser on 2026-11-11, no PMC copy)**

Each DOI was opened in Chrome and the page checked for the full article (methods, tables,
references), not only the abstract. Nothing was downloaded.

| For | Paper | Identifiers | Where |
|---|---|---|---|
| sPESI | Jiménez D et al. Arch Intern Med 2010;170(15):1383-1389 | PMID 20696966 · doi:10.1001/archinternmed.2010.199 | jamanetwork.com, full text |
| BISAP | Wu BU et al. Gut 2008;57(12):1698-1703 | PMID 18519429 · doi:10.1136/gut.2008.152702 | gut.bmj.com, full text |
| West Haven (as used in guidelines) | Vilstrup H et al. Hepatology 2014;60(2):715-735 | PMID 25042402 · doi:10.1002/hep.27210 | journals.lww.com, full text |
| NIHSS (original 15-item scale) | Brott T et al. Stroke 1989;20(7):864-870 | PMID 2749846 · doi:10.1161/01.str.20.7.864 | ahajournals.org, free access (page reader) |
| KDIGO AKI staging | KDIGO Clinical Practice Guideline for Acute Kidney Injury, 2012 | kdigo.org/guidelines/acute-kidney-injury | free PDF linked from that page |
| Wells PE ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)) | van Belle A et al. JAMA 2006;295(2):172-179 | PMID 16403929 · doi:10.1001/jama.295.2.172 | jamanetwork.com, full text |
| PERC ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)) | Kline JA et al. J Thromb Haemost 2004;2(8):1247-1255 | PMID 15304025 · doi:10.1111/j.1538-7836.2004.00790.x | jthjournal.org, open archive |
| PERC ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)) | Kline JA et al. J Thromb Haemost 2008;6(5):772-780 | PMID 18318689 · doi:10.1111/j.1538-7836.2008.02944.x | jthjournal.org, open archive |
| HEART ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)) | Backus BE et al. Int J Cardiol 2013;168(3):2153-2158 | PMID 23465250 · doi:10.1016/j.ijcard.2013.01.255 | internationaljournalofcardiology.com, open access |

**Needed from Nicolás as a PDF (the publisher asked for access, or could not be read)**

| For | Paper | Identifiers | What the browser showed |
|---|---|---|---|
| Glasgow-Blatchford | Blatchford O et al. Lancet 2000;356(9238):1318-1321 | PMID 11073021 · doi:10.1016/S0140-6736(00)02816-6 | abstract; "Get Access" |
| Canadian CT Head | Stiell IG et al. Lancet 2001;357(9266):1391-1396 | PMID 11356436 · doi:10.1016/S0140-6736(00)04561-X | abstract; "Get Access" |
| HAS-BLED | Pisters R et al. Chest 2010;138(5):1093-1100 | PMID 20299623 · doi:10.1378/chest.10-0134 | abstract; "Get Access" |
| CHA2DS2-VASc | Lip GYH et al. Chest 2010;137(2):263-272 | PMID 19762550 · doi:10.1378/chest.09-1584 | abstract; "Get Access" |
| Killip | Killip T, Kimball JT. Am J Cardiol 1967;20(4):457-464 | PMID 6059183 · doi:10.1016/0002-9149(67)90023-9 | abstract; "Get Access" |
| San Francisco Syncope | Quinn JV et al. Ann Emerg Med 2004;43(2):224-232 | PMID 14747812 · doi:10.1016/s0196-0644(03)00823-0 | abstract; "Get Access" |
| Cincinnati | Kothari RU et al. Ann Emerg Med 1999;33(4):373-378 | PMID 10092713 · doi:10.1016/s0196-0644(99)70299-4 | abstract; "Get Access" |
| ROX | Roca O et al. Am J Respir Crit Care Med 2019;199(11):1368-1376 | PMID 30576221 · doi:10.1164/rccm.201803-0589OC | abstract; purchase (academic.oup.com) |
| ROX | Roca O et al. J Crit Care 2016;35:200-205 | PMID 27481760 · doi:10.1016/j.jcrc.2016.05.022 | ScienceDirect asked for a captcha; not attempted |
| Parkland | Baxter CR, Shires T. Ann N Y Acad Sci 1968;150(3):874-894 | PMID 4973463 · doi:10.1111/j.1749-6632.1968.tb14738.x | first page only (Wiley) |
| Rule of nines | Wallace AB. Lancet 1951;1(6653):501-504 | PMID 14805109 · doi:10.1016/s0140-6736(51)91975-7 | marked open access, but the page carries almost no text (probably a scanned PDF); to check by hand |
| HEART ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)) | Backus BE et al. Crit Pathw Cardiol 2010;9(3):164-169 | PMID 20802272 · doi:10.1097/HPC.0b013e3181ec36d8 | abstract only (Ovid) |
| MELD (only if plain MELD is wanted) | Kamath PS et al. Hepatology 2001;33(2):464-470 | PMID 11172350 · doi:10.1053/jhep.2001.22172 | abstract only |

**No readable copy found (tried from the PubMed record on 2026-11-11)**

| For | Paper | Identifiers / what was found |
|---|---|---|
| Ranson | Ranson JH et al. Surg Gynecol Obstet 1974;139(1):69-81 | PMID 4834279 · PubMed lists no full-text link |
| West Haven (original) | Conn HO et al. Gastroenterology 1977;72(4 Pt 1):573-583 | PMID 14049 · gastrojournal.org marks it open access, but the page carries no article text (a scan) |
| Wells PE ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)) | Wells PS et al. Thromb Haemost 2000;83(3):416-420 | PMID 10744147 · PubMed lists no full-text link |
| Modified Glasgow (Imrie) | Blamey SL et al. Gut 1984;25(12):1340-1346 | PMID 6510766 · PMC1420197 is a scan with no text; it has to be read as page images or from a PDF |
| Lund and Browder chart | Lund CC, Browder NC (1944) | not in PubMed search yet |
| NIHSS, current form | the scale as published by NINDS, if that version is chosen ([#31](https://github.com/nicoveraz/bounded-calcs/issues/31)) | to locate |

Volumes, issues and pages above are as PubMed gives them for the matched PMID; check them
against the paper when it is opened.

## Sources and review (needs Nicolás)

- **Full texts behind abstract-only sources ([#7](https://github.com/nicoveraz/bounded-calcs/issues/7)).** `wells_pe`, `perc` and two of the
  `heart` validation papers were read as abstracts. The issue lists, per calculator, each
  source, its identifiers and what the full text would settle. It needs the PDFs.
- **Wording changes to confirm ([#8](https://github.com/nicoveraz/bounded-calcs/issues/8)).** Labels and notes of the four specs were aligned
  with the readings calc-bounds records as accepted; the author should confirm each one.

## Engine work (needs design; ask before starting)

These change the engine or the input format, so they are not for unattended work.

1. ~~"Normal" for numeric items~~ ([#9](https://github.com/nicoveraz/bounded-calcs/issues/9)): done (PR #18).
2. ~~Plausible ranges for numeric items~~ ([#10](https://github.com/nicoveraz/bounded-calcs/issues/10)): done. A numeric item can declare
   `accepts: [lo, hi]`; a value outside it is an input error. The adult calculators use the
   ranges of calc-bounds. `gcs` and the McIsaac `age` have none yet (no source for a range).
3. ~~Formula calculators~~ ([#11](https://github.com/nicoveraz/bounded-calcs/issues/11)): done as a separate kind of calculator (`formula` instead of `components`), for formulas that move in one direction with each input. Not covered: a formula inside a sum of points (PESI's age), and non-monotonic formulas. Earlier note: the score is continuous.
   calc-bounds bounds it exactly by evaluating the corners of the box formed by the inputs'
   allowed ranges (`bounds/__init__.py`), so this depends on item 2.
4. ~~Categories that depend on an item, and tiers~~ ([#12](https://github.com/nicoveraz/bounded-calcs/issues/12)): done with component
   groups (a category can compare the points of one group). The PECARN rules use them. Still
   open in #12: an item shared by two components.
5. ~~Laboratory reference ranges for "normal"~~ ([#20](https://github.com/nicoveraz/bounded-calcs/issues/20)):
   done. Numeric items accept ranges, normal ranges may cross a threshold, and sites can set
   their own ranges (`--normal-ranges`). The urea default (2.5 to 8 mmol/L) crosses 7 on
   purpose, as decided on 2026-11-10.

6. ~~Unit conversion by the engine~~: done. A numeric item can declare other units with a
   factor (`units`); a value sent with a unit is converted, an undeclared unit is an error.
   CURB-65 urea takes `bun_mg/dL` and `urea_mg/dL`. Not covered: conversions with an offset.
   A site states its units once (`--units`); without that, the server refuses a plain
   number for an item with more than one unit.
7. ~~Score-only calculators~~: done. A spec without `categories` returns the score and its
   range; needed for scales such as NIHSS ([#31](https://github.com/nicoveraz/bounded-calcs/issues/31)).

8. **Points that depend on another item** (open part of [#12](https://github.com/nicoveraz/bounded-calcs/issues/12)): Glasgow-Blatchford, Lund
   and Browder, Ranson by aetiology. Not started.
9. **Highest of several criteria** as the result (KDIGO, AKIN). Not started.
10. **A formula inside a sum of points** (PESI's age) and **one calculator feeding another**
    (burn size into fluid volume). Not started.

The engine is now a package, `engine/`, with one module per job and one per scoring rule
(see CLAUDE.md, Layout), so each of these is an addition and not an edit of one large file.
`spec.py` is not split the same way yet.

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
