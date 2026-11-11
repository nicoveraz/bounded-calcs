"""Canadian Syncope Risk Score: independent reference, thresholds, clinical examples.

Source: Thiruganasambandamoorthy V et al. CMAJ 2016;188(12):E289-E298, PMID 27378464, figure 2
[P]. The reference is written from figure 2: predisposition to vasovagal symptoms -1, history
of heart disease 1, any systolic pressure under 90 or over 180 mmHg 2, elevated troponin 2,
abnormal QRS axis 1, QRS duration over 130 ms 1, corrected QT over 480 ms 2, emergency
department diagnosis of vasovagal syncope -2 or cardiac syncope 2; and its risk categories
(-3, -2 very low; -1, 0 low; 1 to 3 medium; 4, 5 high; 6 to 11 very high). It is deliberately
not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["canadian_syncope"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {
    "vasovagal_predisposition": "absent",
    "history_of_heart_disease": "absent",
    "sbp_below_90_or_above_180": "absent",
    "troponin_above_99th_percentile": "absent",
    "abnormal_qrs_axis": "absent",
    "qrs_duration": 90,
    "qtc": 420,
    "ed_diagnosis": "other",
}


def reference(v):
    score = (
        -1 * v["vasovagal_predisposition"]
        + 1 * v["history_of_heart_disease"]
        + 2 * v["sbp_below_90_or_above_180"]
        + 2 * v["troponin_above_99th_percentile"]
        + 1 * v["abnormal_qrs_axis"]
        + 1 * (v["qrs_duration"] > 130)
        + 2 * (v["qtc"] > 480)
        + {"vasovagal_syncope": -2, "other": 0, "cardiac_syncope": 2}[v["ed_diagnosis"]]
    )
    if score <= -2:
        return score, "very_low"
    if score <= 0:
        return score, "low"
    if score <= 3:
        return score, "medium"
    return score, "high" if score <= 5 else "very_high"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score",
    [
        ({"qrs_duration": 130}, 0),  # "QRS duration > 130 ms"
        ({"qrs_duration": 131}, 1),
        ({"qtc": 480}, 0),  # "Corrected QT interval > 480 ms"
        ({"qtc": 481}, 2),
    ],
)
def test_thresholds(change, score):
    assert evaluate(CALC, ZERO | change)["score"] == score


@pytest.mark.parametrize(
    "change,score,category",
    [
        # Each row of the figure's lower table, built from the upper one.
        ({"vasovagal_predisposition": "present", "ed_diagnosis": "vasovagal_syncope"}, -3,
         "very_low"),
        ({"ed_diagnosis": "vasovagal_syncope"}, -2, "very_low"),
        ({"vasovagal_predisposition": "present"}, -1, "low"),
        ({}, 0, "low"),
        ({"history_of_heart_disease": "present"}, 1, "medium"),
        ({"history_of_heart_disease": "present", "troponin_above_99th_percentile": "present"}, 3,
         "medium"),
        ({"sbp_below_90_or_above_180": "present", "troponin_above_99th_percentile": "present"},
         4, "high"),
        ({"sbp_below_90_or_above_180": "present", "troponin_above_99th_percentile": "present",
          "abnormal_qrs_axis": "present"}, 5, "high"),
        ({"sbp_below_90_or_above_180": "present", "troponin_above_99th_percentile": "present",
          "qtc": 500}, 6, "very_high"),
    ],
)  # fmt: skip
def test_categories(change, score, category):
    r = evaluate(CALC, ZERO | change)
    assert (r["score"], r["category"]) == (score, category)


def test_the_highest_score_is_11():
    worst = {"vasovagal_predisposition": "absent", "history_of_heart_disease": "present",
             "sbp_below_90_or_above_180": "present", "troponin_above_99th_percentile": "present",
             "abnormal_qrs_axis": "present", "qrs_duration": 150, "qtc": 500,
             "ed_diagnosis": "cardiac_syncope"}  # fmt: skip
    r = evaluate(CALC, worst)
    assert (r["score"], r["category"]) == (11, "very_high")  # 1 + 2 + 2 + 1 + 1 + 2 + 2


def test_sparse_note_leaves_every_category_open():
    # Syncope in a patient with known coronary disease (1). Systolic pressures 104 to 132 in
    # the department (0). No trigger history, ECG not described, troponin not sent, no
    # diagnosis written. Lowest: 1 - 1 - 2 = -2. Highest: 1 + 2 + 1 + 1 + 2 + 2 = 9.
    note = {"history_of_heart_disease": "present", "sbp_below_90_or_above_180": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score_range"] == [-2, 9]
    assert r["possible_categories"] == ["very_low", "low", "medium", "high", "very_high"]
    assert "ed_diagnosis" in r["judgment_items_pending"]


def test_unknown_ecg_and_troponin_do_not_default_to_normal():
    # Everything else known and scoring 0: troponin unknown keeps 0 (low) and 2 (medium) open.
    note = {k: v for k, v in ZERO.items() if k != "troponin_above_99th_percentile"}
    r = evaluate(CALC, note)
    assert r["score_range"] == [0, 2] and r["possible_categories"] == ["low", "medium"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["troponin_above_99th_percentile"]
