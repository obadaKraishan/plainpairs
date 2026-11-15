"""The release check, the switch and the rebuild, on invented labels."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from plainpairs import bulk, release, tables
from tests.test_tables import write_export


def write_structure(folder, labels, unlisted=()):
    """An invented structure folder: every label but ``unlisted`` is in the release, in its
    version, with the same words for each of its patient texts."""
    import json

    from plainpairs import structure

    folder.mkdir(parents=True, exist_ok=True)
    index, rows = [], []
    for r in labels:
        if r["set_id"] in unlisted:
            continue
        sid = r["set_id"].lower()
        index.append(
            {"set_id": sid, "version": r["version"], "version_match": True, "in_corpus": True}
        )
        for k in tables.PATIENT:
            if r[f"t_{k}_sha256"]:
                st = dict.fromkeys(f.name for f in structure.STRUCTURED)
                st.update(
                    xml_match="exact",
                    xml_dice=1.0,
                    words=50,
                    sentences=5,
                    flesch_kincaid=7.5,
                    smog=9.0,
                    blocks_heading=3,
                    blocks_item=4,
                    subsection_titles=0,
                )
                rows.append(
                    {
                        "set_id": sid,
                        "version": r["version"],
                        "section": k,
                        "side": "patient",
                        "structured": st,
                    }
                )
    pq.write_table(pa.Table.from_pylist(index, structure.INDEX_SCHEMA), folder / "index.parquet")
    pq.write_table(
        pa.Table.from_pylist(rows, structure.STRUCTURE_SCHEMA), folder / "structure.parquet"
    )
    (folder / "structure_summary.json").write_text(json.dumps({"release_date": "2026-11-13"}))
    return folder


@pytest.fixture
def built(tmp_path):
    root = write_export(tmp_path / "bulk")
    parts = tables.parts_from_manifest(root, "2026-11-13")
    bare = tmp_path / "bare"
    tables.Builder(parts, bare, "2026-11-13", log=lambda s: None).run()
    labels = pq.read_table(bare / "labels.parquet").to_pylist()
    folder = write_structure(tmp_path / "structure", labels, unlisted={labels[-1]["set_id"]})
    out = tmp_path / "tables"
    tables.Builder(parts, out, "2026-11-13", log=lambda s: None, structure_dir=folder).run()
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


def test_the_codes_table_is_checked_when_present(built):
    from plainpairs import codes

    _root, out, manifest = built
    codes.build(out, log=lambda s: None)
    problems, info = release.check(out, manifest, "unmarked")
    assert problems == [] and info["rows:codes"] > 0
    t = pq.read_table(out / "codes.parquet")
    doubled = pa.concat_tables([t, t.slice(0, 1)])
    stray = t.slice(0, 1).set_column(
        t.schema.get_field_index("set_id"), "set_id", pa.array(["set-zzzz"])
    )
    pq.write_table(pa.concat_tables([doubled, stray]), out / "codes.parquet")
    problems, _ = release.check(out, manifest, "unmarked")
    assert any("more than once" in p for p in problems)
    assert any("not in the labels table" in p for p in problems)
    pq.write_table(t.drop_columns(["doses"]), out / "codes.parquet")
    problems, _ = release.check(out, manifest, "unmarked")
    assert any("expected columns" in p for p in problems)


def _rewrite(out, name, fn):
    t = pq.read_table(out / f"{name}.parquet")
    pq.write_table(fn(t), out / f"{name}.parquet")


def test_the_two_configurations_are_set_and_kept_apart(built):
    _root, out, manifest = built
    labels = pq.read_table(out / "labels.parquet").to_pylist()
    assert {r["configuration"] for r in labels} == {"current", "unlisted"}
    un = next(r for r in labels if r["configuration"] == "unlisted")
    assert un["unlisted_reason"] == "not_in_release" and un["structure_source"] == "json"
    assert all(un[c] is None for c in release.STRUCTURED_COLUMNS)
    cur = next(r for r in labels if r["configuration"] == "current")
    assert cur["t_medication_guide_structured"]["flesch_kincaid"] == 7.5
    assert cur["t_medication_guide"]["flesch_kincaid"] is not None  # the JSON's stay
    pairs = pq.read_table(out / "section_pairs.parquet").to_pylist()
    assert {p["configuration"] for p in pairs} <= {"current", "unlisted"}
    problems, info = release.check(out, manifest, "unmarked")
    assert problems == [] and info["configuration:current"] >= 1


def test_a_build_without_configurations_fails(tmp_path):
    root = write_export(tmp_path / "bulk")
    out = tmp_path / "t"
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    manifest = bulk.read_manifest(bulk.manifest_path(root, "2026-11-13"))
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    assert any("No label has a configuration" in p for p in problems)


def test_a_current_label_without_structure_fails(built):
    _root, out, manifest = built

    def drop(t):
        rows = t.to_pylist()
        for r in rows:
            if r["configuration"] == "current" and r["t_medication_guide_sha256"]:
                r["t_medication_guide_structured"] = None
                break
        return pa.Table.from_pylist(rows, t.schema)

    _rewrite(out, "labels", drop)
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    assert any("current label without structure" in p for p in problems)


def test_a_pooled_reading_level_column_fails(built):
    _root, out, manifest = built

    def mix(t):
        rows = t.to_pylist()
        cur = next(r for r in rows if r["configuration"] == "current")
        un = next(r for r in rows if r["configuration"] == "unlisted")
        un["t_medication_guide_structured"] = cur["t_medication_guide_structured"]
        return pa.Table.from_pylist(rows, t.schema)

    _rewrite(out, "labels", mix)
    _rewrite(
        out,
        "section_pairs",
        lambda t: t.set_column(
            t.schema.get_field_index("configuration"),
            "configuration",
            pa.array([None] * t.num_rows, pa.string()),
        ),
    )
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    assert any("would be pooled in one column" in p for p in problems)
    assert any("section_pairs" in p and "pooled" in p for p in problems)


def test_an_experimental_code_in_a_release_table_fails(built):
    from plainpairs import codes

    _root, out, manifest = built
    codes.build(out, log=lambda s: None)
    x = pq.read_table(out / "codes_experimental.parquet")
    _rewrite(out, "codes", lambda t: t.append_column("vague_core", x["vague_core"]))
    problems, _ = release.check(out, manifest, "none", verify_hashes=False)
    assert any("experimental code columns vague_core" in p for p in problems)
