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
    # a build without a structure table has one group, never a pooled number
    assert set(s["measures"]["patient.medication_guide"]) == {"no_configuration"}
    assert "json" in s["measures"]["patient.medication_guide"]["no_configuration"]
    assert s["configurations"]["labels"] == {"no_configuration": s["labels"]}
    assert s["alignment"]["how_to_take"]["segments"] == 2
    dumped = json.dumps(s, default=str)
    assert "made-up medicine" not in dumped and "Bottles of 30" not in dumped
    assert stats.q([]) == {"n": 0}
    assert stats.q([3])["median"] == 3


def test_stats_of_names_listings_and_codes(tmp_path):
    from plainpairs import codes, listed
    from tests.test_listed import HEADER, NDC_RECORDS, dailymed_zip, ndc_zip

    root = write_export(tmp_path / "bulk")
    out = tmp_path / "t"
    bare = tmp_path / "bare"
    parts = tables.parts_from_manifest(root, "2026-11-13")
    tables.Builder(parts, bare, "2026-11-13", log=lambda s: None).run()
    assert stats.corpus_stats(bare)["listed"] == {"sources": {}}
    assert stats.corpus_stats(bare)["codes"] == {}
    lst = listed.load(
        ndc_zip(tmp_path / "n" / "2026-11-13" / "n.json.zip", NDC_RECORDS),
        dailymed_zip(tmp_path / "d" / "2026-11-15" / "d.zip", [HEADER, "set-aaaa|f|d|7|t"]),
    )
    tables.Builder(parts, out, "2026-11-13", log=lambda s: None, listings=lst).run()
    codes.build(out, log=lambda s: None)
    s = stats.corpus_stats(out)
    names = s["product_names"]
    assert names["labels_named"] == 2 and names["agreement_share"] == 1.0
    assert names["halves"]["without_openfda"]["named"] == 1  # the copy without the block
    assert names["distinct_product_names"] == 1
    li = s["listed"]
    assert li["corpus"]["in_ndc_directory"] == 2  # by set id and by document id
    assert li["corpus"]["dailymed_same_version"] == 1
    assert li["with_openfda"]["labels"] + li["without_openfda"]["labels"] == 4
    assert li["distinct_patient_texts"]["medication_guide"] == 1
    assert s["codes"]["patient.medication_guide"]["texts"] == 1  # two labels, one text
    assert s["codes"]["prescriber.boxed_warning"]["texts"] == 2  # counted per label
    assert stats.code_summary(codes.SCHEMA.empty_table(), "patient") == {"texts": 0}
    assert s["section_pairs_empty"] == 0
    assert json.dumps(s, default=str)
