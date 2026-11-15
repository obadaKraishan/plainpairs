from collections import Counter

from plainpairs import align
from plainpairs import text as tx
from tests.test_text_readability import GUIDE


def test_every_standard_heading_is_mapped():
    assert set(align.MAPPING) == set(tx.HEADING_KEYS)


def test_label_counts_drop_words_common_to_the_label():
    sections = {"contraindications": "Zorvan allergy hives", "description": "Zorvan tablet core"}
    segments = [("who_should_not", "Zorvan allergy"), ("ingredients", "Zorvan tablet")]
    sec, seg = align.label_counts(sections, segments)
    assert "zorvan" not in sec["contraindications"]
    assert seg[0][1] == Counter({"allergy": 1})


def test_score_prefers_the_section_sharing_rare_words():
    df = Counter()
    sections = {
        "contraindications": Counter({"allergy": 2, "hives": 1}),
        "description": Counter({"tablet": 3, "core": 1}),
        "patient_counseling_information": Counter({"advise": 2}),
    }
    n = align.update_df(df, list(sections.values()) + [Counter({"allergy": 1})])
    idf = align.idf_table(df, n)
    out = align.score("who_should_not", Counter({"allergy": 1}), sections, idf, 1.0)
    assert out["best_section"] == "contraindications"
    assert out["best_is_mapped"] is True
    assert out["mapped_present"] == ["contraindications"]
    assert out["section17_similarity"] == 0.0
    nothing = align.score("storage", Counter({"unseen": 1}), sections, idf, 1.0)
    assert nothing["best_section"] is None
    assert nothing["best_is_mapped"] is False
    assert nothing["mapped_best_similarity"] is None


def test_segment_spans_match_the_segments():
    spans = tx.segment_spans(GUIDE)
    segs = tx.segment_patient_text(GUIDE)
    assert [s[0] for s in spans] == [s.key for s in segs]
    key, start, head_end, end = spans[1]
    assert GUIDE[start:head_end] == segs[1].heading
    assert GUIDE[head_end:end].strip() == segs[1].body
    assert tx.segment_spans("") == []
