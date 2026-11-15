import json

from plainpairs import stats, tables
from tests.test_tables import write_export


def test_corpus_stats_on_invented_labels(tmp_path):
    root = write_export(tmp_path / "bulk")
    out = tmp_path / "t"
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    s = stats.corpus_stats(out)
    assert s["labels"] == 4
    assert s["duplicates"]["medication_guide"]["distinct_core"] == 1
    assert s["duplicates"]["medication_guide"]["shared_texts"] == 1
    assert s["medicines"]["labels_by_key_source"] == {"openfda": 1, "shared_text": 1, "none": 2}
    assert s["switch"]["text_patient"]["released:none"] == 0
    assert (
        s["switch"]["text_patient"]["released:unmarked"]
        < s["switch"]["text_patient"]["released:all"]
    )
    assert "patient.medication_guide" in s["measures"]
    assert s["alignment"]["how_to_take"]["segments"] == 2
    dumped = json.dumps(s, default=str)
    assert "made-up medicine" not in dumped and "Bottles of 30" not in dumped
    assert stats.q([]) == {"n": 0}
    assert stats.q([3])["median"] == 3
