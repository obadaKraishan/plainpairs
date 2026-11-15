"""The release check, the switch and the rebuild, on invented labels."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from plainpairs import bulk, release, tables
from tests.test_tables import write_export


@pytest.fixture
def built(tmp_path):
    root = write_export(tmp_path / "bulk")
    out = tmp_path / "tables"
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    manifest = bulk.read_manifest(bulk.manifest_path(root, "2026-11-13"))
    return root, out, manifest


def test_a_clean_build_passes_with_the_unmarked_and_none_settings(built):
    _, out, manifest = built
    problems, info = release.check(out, manifest, "unmarked")
    assert problems == []
    assert info["release:text_patient"] < info["rows:text_patient"]  # the marked label is held back
    problems, info = release.check(out, manifest, "none")
    assert problems == [] and info["release:text_prescriber"] == 0


def test_all_refuses_marked_texts_unless_allowed(built):
    _, out, manifest = built
    problems, _ = release.check(out, manifest, "all")
    assert any("would release marked texts" in p for p in problems)
    problems, info = release.check(out, manifest, "all", allow_marked=True)
    assert problems == [] and info["release:text_patient"] == info["rows:text_patient"]
    with pytest.raises(ValueError, match="Unknown switch"):
        release.select(pq.read_table(out / "text_patient.parquet"), "some")


def rewrite(out, name, fn):
    t = pq.read_table(out / f"{name}.parquet")
    pq.write_table(fn(t), out / f"{name}.parquet")


def test_the_check_fails_loudly(built):
    _, out, manifest = built
    rewrite(out, "labels", lambda t: pa.concat_tables([t, t.slice(0, 1)]))
    rewrite(
        out,
        "text_patient",
        lambda t: t.set_column(
            t.schema.get_field_index("has_copyright_mark"),
            "has_copyright_mark",
            pa.array([None] * t.num_rows, pa.bool_()),
        ),
    )
    bad_manifest = {k: {**v, "listed_records": "99"} for k, v in manifest.items()}
    problems, _ = release.check(out, bad_manifest, "unmarked")
    text = " ".join(problems)
    assert "the manifest lists" in text
    assert "appear more than once" in text
    assert "have no has_copyright_mark" in text
    assert "rows; the build summary says" in text


def test_a_text_column_or_an_out_of_scope_label_in_the_record_layer_fails(built):
    _, out, manifest = built
    rewrite(
        out, "patient_texts", lambda t: t.append_column("text", pa.array(["x" * 400] * t.num_rows))
    )
    rewrite(
        out,
        "labels",
        lambda t: t.set_column(
            t.schema.get_field_index("label_format"),
            "label_format",
            pa.array(["otc_drug_facts"] * t.num_rows),
        ),
    )
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    text = " ".join(problems)
    assert "has a text column" in text
    assert "out of scope" in text
    assert "holds strings of 400 characters" in text


def test_a_changed_text_is_caught_by_its_hash(built):
    _, out, manifest = built
    rewrite(
        out,
        "text_prescriber",
        lambda t: t.set_column(
            t.schema.get_field_index("text"), "text", pa.array(["changed"] * t.num_rows)
        ),
    )
    problems, _ = release.check(out, manifest, "none")
    assert any("does not match its SHA-256" in p for p in problems)


def test_rebuild_makes_the_same_text_layer_and_confirms_it(built, tmp_path):
    root, out, _ = built
    again = tmp_path / "rebuilt"
    report = release.rebuild_text(out / "labels.parquet", root, again, log=lambda s: None)
    assert report == {
        "export_date": "2026-11-13",
        "labels": 4,
        "rebuilt": 4,
        "missing": 0,
        "hash_mismatches": 0,
    }
    for name in tables.TEXT_TABLES:
        a = pq.read_table(out / f"{name}.parquet").sort_by(
            [("set_id", "ascending"), ("section", "ascending"), ("part_index", "ascending")]
        )
        b = pq.read_table(again / f"{name}.parquet").sort_by(
            [("set_id", "ascending"), ("section", "ascending"), ("part_index", "ascending")]
        )
        assert a.equals(b)


def test_rebuild_reports_a_label_whose_text_changed(built, tmp_path):
    root, out, _ = built
    rewrite(
        out,
        "labels",
        lambda t: t.set_column(
            t.schema.get_field_index("p_boxed_warning_sha256"),
            "p_boxed_warning_sha256",
            pa.array(["0" * 64] * t.num_rows),
        ),
    )
    report = release.rebuild_text(out / "labels.parquet", root, tmp_path / "r", log=lambda s: None)
    assert report["hash_mismatches"] == 4


def test_long_names_from_the_openfda_block_are_allowed_but_not_without_limit(built):
    _, out, manifest = built
    rewrite(
        out,
        "labels",
        lambda t: t.set_column(
            t.schema.get_field_index("medicine_key"),
            "medicine_key",
            pa.array(["a|" * 400] * t.num_rows),
        ),
    )
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    assert problems == []
    rewrite(
        out,
        "labels",
        lambda t: t.set_column(
            t.schema.get_field_index("medicine_key"),
            "medicine_key",
            pa.array(["a" * 2500] * t.num_rows),
        ),
    )
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    assert any("2500 characters in medicine_key" in p for p in problems)
