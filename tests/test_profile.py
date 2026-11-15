import copy
import json

from plainpairs import label, profile
from tests.label_samples import MISSING_SECTIONS, OLDER_WITH_INSERT, OTC_DRUG_FACTS, PLR_WITH_GUIDE


def rows():
    second = copy.deepcopy(PLR_WITH_GUIDE)
    second.update(id="doc-0005", set_id="set-eeee")
    second["openfda"] = dict(second["openfda"], manufacturer_name=["Other Maker LLC"])
    third = copy.deepcopy(PLR_WITH_GUIDE)
    third.update(id="doc-0006", set_id="set-ffff")
    third["spl_medguide"] = [PLR_WITH_GUIDE["spl_medguide"][0].upper() + " © 2026 Example"]
    records = [PLR_WITH_GUIDE, second, third, OLDER_WITH_INSERT, OTC_DRUG_FACTS, MISSING_SECTIONS]
    return [label.parse_label(r) for r in records]


def test_profile_counts_labels_and_duplicates():
    out = profile.profile(rows())
    assert out["labels"] == 6 and out["set_ids"] == 6
    assert out["paired_labels"] == 4
    mg = out["duplicates"]["medication_guide"]
    assert mg["labels"] == 3
    assert mg["distinct_texts_exact"] == 2  # the upper-case copy differs exactly...
    assert mg["texts_shared_by_2_or_more_labels"] == 1
    assert mg["shared_texts_with_2_or_more_manufacturers"] == 1
    assert mg["group_sizes"] == {1: 1, 2: 1}
    assert mg["distinct_generic_name_sets"] == 1
    assert out["duplicates"]["patient_package_insert"]["labels_without_generic_name"] == 1
    assert out["copyright_marks"]["patient"] == 1
    assert "prescriber" not in out["copyright_marks"]


def test_profile_measures_and_headings():
    out = profile.profile(rows())
    assert out["measures"]["patient.medication_guide"]["words"]["n"] == 3
    assert "prescriber.boxed_warning" in out["measures"]
    assert out["patient_above_grade_8"]["patient.medication_guide.fk_above_8"]["labels"] >= 0
    h = out["headings"]["medication_guide"]
    assert h["texts"] == 3
    assert h["with_heading"]["most_important"] == 3
    assert h["share_with_heading"]["what_is"] == 1.0
    assert h["top_templates"]["how_to_take"][0] == ("How should I take [medicine]?", 2)
    assert out["headings"]["patient_package_insert"]["with_heading"]["what_is"] == 1


def test_profile_holds_no_label_text():
    dumped = json.dumps(profile.profile(rows()))
    for phrase in ("made-up medicine", "sleepy", "Take 1 tablet", "Bottles of 30"):
        assert phrase.lower() not in dumped.lower()


def test_alignment_points_each_segment_at_a_section():
    out = profile.profile(rows())["alignment"]
    assert set(out) <= {"most_important", "what_is", "how_to_take"}
    assert sum(out["how_to_take"]["most_similar_section"].values()) == 3


def test_quantiles_and_cosine_edge_cases():
    assert profile.quantiles([]) == {"n": 0, "median": None, "p25": None, "p75": None, "p90": None}
    assert profile.quantiles([4])["median"] == 4
    assert profile.quantiles([1, 2, 3, 4])["median"] == 2.5
    assert profile.cosine({}, {"a": 1.0}) == 0.0
    assert profile.cosine({"a": 0.0}, {"a": 0.0}) == 0.0
    assert profile.tokens("The Zorvan tablets and you") == ["zorvan", "tablets"]
