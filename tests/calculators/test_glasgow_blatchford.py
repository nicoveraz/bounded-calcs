"""Glasgow-Blatchford bleeding score: independent reference, thresholds, clinical examples.

Source: Blatchford O, Murray WR, Blatchford M. Lancet 2000;356:1318-1321, PMID 11073021,
Table 1 [P], read from the page image. The reference is written from that table: blood urea
(mmol/L) >= 6.5 < 8.0 scores 2, >= 8.0 < 10.0 scores 3, >= 10.0 < 25.0 scores 4, >= 25 scores 6;
haemoglobin (g/L) for men >= 120 < 130 scores 1, >= 100 < 120 scores 3, below 100 scores 6 (the
table prints '< 10.0' for that row); for women >= 100 < 120 scores 1, < 100 scores 6; systolic
blood pressure (mmHg) 100-109 scores 1, 90-99 scores 2, < 90 scores 3; pulse >= 100 per minute
1; presentation with melaena 1; presentation with syncope 2; hepatic disease 2; cardiac failure
2. The paper gives no cut-off on the score, so the calculator is score-only. The reference is
deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import InputError, evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["glasgow_blatchford"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {
    "urea": 5.0,
    "haemoglobin": 145,
    "sex": "male",
    "sbp": 125,
    "heart_rate": 80,
    "melaena": "absent",
    "syncope": "absent",
    "hepatic_disease": "absent",
    "cardiac_failure": "absent",
}


def reference(v):
    urea, hb, sbp = v["urea"], v["haemoglobin"], v["sbp"]
    score = 0
    if urea >= 25:
        score += 6
    elif urea >= 10:
        score += 4
    elif urea >= 8:
        score += 3
    elif urea >= 6.5:
        score += 2
    if v["sex"] == "male":
        if hb < 100:
            score += 6
        elif hb < 120:
            score += 3
        elif hb < 130:
            score += 1
    else:
        if hb < 100:
            score += 6
        elif hb < 120:
            score += 1
    if sbp < 90:
        score += 3
    elif sbp < 100:
        score += 2
    elif sbp < 110:
        score += 1
    score += 1 * (v["heart_rate"] >= 100)
    score += 1 * v["melaena"] + 2 * v["syncope"] + 2 * v["hepatic_disease"]
    score += 2 * v["cardiac_failure"]
    return score, None


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score",
    [
        ({"urea": 6.4}, 0),  # ">= 6.5 < 8.0": 2
        ({"urea": 6.5}, 2),
        ({"urea": 7.9}, 2),
        ({"urea": 8.0}, 3),  # ">= 8.0 < 10.0": 3
        ({"urea": 9.9}, 3),
        ({"urea": 10.0}, 4),  # ">= 10.0 < 25.0": 4
        ({"urea": 24.9}, 4),
        ({"urea": 25}, 6),  # ">= 25": 6
        ({"haemoglobin": 130}, 0),  # men ">= 120 < 130": 1
        ({"haemoglobin": 129}, 1),
        ({"haemoglobin": 120}, 1),
        ({"haemoglobin": 119}, 3),  # men ">= 100 < 120": 3
        ({"haemoglobin": 100}, 3),
        ({"haemoglobin": 99}, 6),  # men, lowest band: 6
        ({"sex": "female", "haemoglobin": 120}, 0),  # women ">= 100 < 120": 1
        ({"sex": "female", "haemoglobin": 119}, 1),
        ({"sex": "female", "haemoglobin": 100}, 1),
        ({"sex": "female", "haemoglobin": 99}, 6),  # women "< 100": 6
        ({"sbp": 110}, 0),  # "100-109": 1
        ({"sbp": 109}, 1),
        ({"sbp": 100}, 1),
        ({"sbp": 99}, 2),  # "90-99": 2
        ({"sbp": 90}, 2),
        ({"sbp": 89}, 3),  # "< 90": 3
        ({"heart_rate": 99}, 0),  # "Pulse >= 100 (per min)": 1
        ({"heart_rate": 100}, 1),
        ({"melaena": "present"}, 1),
        ({"syncope": "present"}, 2),
        ({"hepatic_disease": "present"}, 2),
        ({"cardiac_failure": "present"}, 2),
    ],
)
def test_thresholds(change, score):
    r = evaluate(CALC, ZERO | change)
    assert r["settled"] and r["score"] == score and r["category"] is None


def test_the_highest_score_is_23():
    worst = {"urea": 30, "haemoglobin": 80, "sex": "male", "sbp": 80, "heart_rate": 120,
             "melaena": "present", "syncope": "present", "hepatic_disease": "present",
             "cardiac_failure": "present"}  # fmt: skip
    assert evaluate(CALC, worst)["score"] == 23  # 6 + 6 + 3 + 1 + 1 + 2 + 2 + 2


def test_units_are_converted():
    # Haemoglobin 12.5 g/dL is 125 g/L: 1 point for a man. BUN 28 mg/dL is 9.99 mmol/L: 3.
    r = evaluate(CALC, ZERO | {"haemoglobin": {"value": 12.5, "unit": "g/dL"}})
    assert r["score"] == 1
    r = evaluate(CALC, ZERO | {"urea": {"value": 28, "unit": "bun_mg/dL"}})
    assert r["score"] == 3
    with pytest.raises(InputError):  # 13.5 sent as g/L is outside what the item accepts
        evaluate(CALC, ZERO | {"haemoglobin": 13.5})


def test_sex_is_asked_only_where_the_tables_differ():
    # Haemoglobin 125 g/L: 1 point for a man, 0 for a woman. Everything else scores 0.
    note = {k: v for k, v in ZERO.items() if k != "sex"} | {"haemoglobin": 125}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score_range"] == [0, 1]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["sex"]
    # Haemoglobin 145 g/L scores 0 for both, and 95 g/L scores 6 for both.
    for hb, score in ((145, 0), (95, 6)):
        r = evaluate(CALC, note | {"haemoglobin": hb})
        assert r["settled"] and r["score"] == score and r["irrelevant_unknowns"] == ["sex"]


def test_sparse_note_keeps_the_score_open():
    # Haematemesis in a man, pulse 112 (1), systolic pressure 96 (2), "no melaena". Bloods
    # pending, nothing on syncope, liver or heart. Lowest: 1 + 2 = 3. Highest: 3 + 6 (urea)
    # + 6 (haemoglobin) + 2 + 2 + 2 = 21.
    note = {"sex": "male", "heart_rate": 112, "sbp": 96, "melaena": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score"] is None and r["score_range"] == [3, 21]
    asked = {d["item"] for d in r["decisive_unknowns"]}
    assert asked == {"urea", "haemoglobin", "syncope", "hepatic_disease", "cardiac_failure"}


def test_values_reported_as_normal_are_not_scored_as_zero():
    # "Urea normal" is read as 2.5 to 8 mmol/L: 0 points below 6.5, 2 from 6.5, 3 at 8.0.
    r = evaluate(CALC, ZERO | {"urea": "normal"})
    assert not r["settled"] and r["score_range"] == [0, 3]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["urea"]
    # "Blood pressure normal" is read as 101 to 139 mmHg: 1 point under 110, none from 110.
    r = evaluate(CALC, ZERO | {"sbp": "normal"})
    assert not r["settled"] and r["score_range"] == [0, 1]
