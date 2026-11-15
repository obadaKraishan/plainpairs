"""The two-layer build, on invented labels only."""

import copy
import io
import json
import zipfile

import pyarrow.parquet as pq
import pytest

from plainpairs import bulk, tables
from tests.label_samples import MISSING_SECTIONS, OLDER_WITH_INSERT, OTC_DRUG_FACTS, PLR_WITH_GUIDE


def records():
    generic_copy = copy.deepcopy(PLR_WITH_GUIDE)
    generic_copy.update(id="doc-0010", set_id="set-gggg", openfda={})  # same guide, no openfda
    otc_with_guide = copy.deepcopy(OTC_DRUG_FACTS)
    otc_with_guide.update(id="doc-0011", set_id="set-hhhh")
    otc_with_guide["spl_medguide"] = ["MEDICATION GUIDE What is EXAMPLA? A made-up gel."]
    marked = copy.deepcopy(OLDER_WITH_INSERT)
    marked.update(id="doc-0012", set_id="set-iiii")
    marked["package_label_principal_display_panel"] = ["\u00a9 2026 Example Pharma"]
    return [
        [PLR_WITH_GUIDE, OLDER_WITH_INSERT, OTC_DRUG_FACTS],
        [generic_copy, otc_with_guide, marked, MISSING_SECTIONS],
    ]


def write_export(root, date="2026-11-13", parts=None):
    parts = parts or records()
    total = sum(len(p) for p in parts)
    folder = root / date
    folder.mkdir(parents=True)
    rows = []
    skip = 0
    for i, recs in enumerate(parts, start=1):
        buf = io.BytesIO()
        meta = {"last_updated": date, "results": {"skip": skip, "limit": len(recs), "total": total}}
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("drug-label.json", json.dumps({"meta": meta, "results": recs}))
        name = f"drug-label-000{i}-of-000{len(parts)}.json.zip"
        (folder / name).write_bytes(buf.getvalue())
        rows.append((i, name, len(recs)))
        skip += len(recs)
    import csv
    import hashlib

    with (folder / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=bulk.MANIFEST_FIELDS)
        w.writeheader()
        for i, name, n in rows:
            data = (folder / name).read_bytes()
            w.writerow(
                {
                    "export_date": date,
                    "part": i,
                    "of": len(parts),
                    "file": name,
                    "listed_mib": 0,
                    "listed_records": n,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "meta_last_updated": date,
                    "meta_skip": 0,
                    "meta_total": total,
                    "added": "T",
                    "how": "test",
                }
            )
    return root


@pytest.fixture
def built(tmp_path):
    root = write_export(tmp_path / "bulk")
    parts = tables.parts_from_manifest(root, "2026-11-13")
    out = tmp_path / "tables"
    stats = tables.Builder(parts, out, "2026-11-13", log=lambda s: None).run()
    return out, stats


def test_scope_and_counts(built):
    out, stats = built
    c = stats["counts"]
    assert c["labels_read"] == 7
    assert c["in_scope"] == 4  # the guide label, its copy, the two older labels with inserts
    assert c["format:otc_drug_facts"] == 2
    labels = pq.read_table(out / "labels.parquet").to_pylist()
    assert sorted(r["set_id"] for r in labels) == ["set-aaaa", "set-bbbb", "set-gggg", "set-iiii"]
    excluded = pq.read_table(out / "excluded_otc.parquet").to_pylist()
    assert [r["set_id"] for r in excluded] == ["set-hhhh"]


def test_record_layer_holds_no_text(built):
    out, _ = built
    for name in tables.RECORD_TABLES:
        cols = pq.read_schema(out / f"{name}.parquet").names
        assert "text" not in cols, name
    dumped = json.dumps(pq.read_table(out / "labels.parquet").to_pylist(), default=str)
    assert "made-up medicine" not in dumped and "Bottles of 30" not in dumped


def test_medicine_key_comes_from_openfda_or_a_shared_text(built):
    out, _ = built
    rows = {r["set_id"]: r for r in pq.read_table(out / "labels.parquet").to_pylist()}
    assert (rows["set-aaaa"]["medicine_key"], rows["set-aaaa"]["medicine_key_source"]) == (
        "zorvanide",
        "openfda",
    )
    assert (rows["set-gggg"]["medicine_key"], rows["set-gggg"]["medicine_key_source"]) == (
        "zorvanide",
        "shared_text",
    )
    assert rows["set-iiii"]["medicine_key_source"] == "none"
    assert (rows["set-aaaa"]["product_name"], rows["set-aaaa"]["product_name_source"]) == (
        "ZORVAN",
        "spl_product_data_elements",
    )
    assert rows["set-bbbb"]["product_name_source"] == "none"
    assert rows["set-aaaa"]["medicine_key"] == "zorvanide"  # never merged with the name
    assert rows["set-iiii"]["has_copyright_mark"] is True
    assert rows["set-aaaa"]["p_boxed_warning"]["words"] > 0
    assert rows["set-iiii"]["p_use_in_specific_populations"] is None


def test_patient_texts_group_shared_guides(built):
    out, _ = built
    b = pq.read_table(out / "patient_texts.parquet").to_pylist()
    guide = next(r for r in b if r["kind"] == "medication_guide")
    assert guide["n_labels"] == 2 and guide["set_ids"] == ["set-aaaa", "set-gggg"]
    assert guide["crosses_makers"] is False and guide["n_labels_without_manufacturer"] == 1
    assert guide["headings_found"] == ["how_to_take", "most_important", "what_is"]
    assert {r["kind"] for r in b} == {"medication_guide", "patient_package_insert"}


def test_text_layer_rows_carry_the_mark_and_a_hash(built):
    out, _ = built
    tp = pq.read_table(out / "text_prescriber.parquet").to_pylist()
    pt = pq.read_table(out / "text_patient.parquet").to_pylist()
    assert all(r["has_copyright_mark"] is not None for r in tp + pt)
    assert {r["set_id"] for r in pt} == {"set-aaaa", "set-bbbb", "set-gggg", "set-iiii"}
    assert any(r["part"] == "table" for r in tp)
    marked = [r for r in tp + pt if r["set_id"] == "set-iiii"]
    assert marked and all(r["has_copyright_mark"] for r in marked)
    labels = {r["set_id"]: r for r in pq.read_table(out / "labels.parquet").to_pylist()}
    row = next(r for r in pt if r["set_id"] == "set-aaaa" and r["section"] == "medication_guide")
    assert row["sha256"] == labels["set-aaaa"]["t_medication_guide_sha256"]


def test_section_pairs_map_and_score_segments(built):
    out, _ = built
    c = pq.read_table(out / "section_pairs.parquet").to_pylist()
    keys = [(r["set_id"], r["heading_key"]) for r in c if r["kind"] == "medication_guide"]
    assert ("set-aaaa", "what_is") in keys and ("set-gggg", "how_to_take") in keys
    r = next(x for x in c if x["set_id"] == "set-aaaa" and x["heading_key"] == "how_to_take")
    assert r["mapped_sections"] == ["dosage_and_administration"]
    assert r["heading_template"] == "How should I take [medicine]?"
    assert r["seg_start"] < r["heading_end"] <= r["seg_end"]
    assert r["rule_status"] == "pending_hand_check"


def test_parts_from_manifest_refuses_a_changed_or_missing_part(tmp_path):
    root = write_export(tmp_path / "bulk")
    part = root / "2026-11-13" / "drug-label-0001-of-0002.json.zip"
    part.write_bytes(part.read_bytes()[:-1] + b"X")
    with pytest.raises(bulk.BulkError, match="SHA-256"):
        tables.parts_from_manifest(root, "2026-11-13")
    part.unlink()
    with pytest.raises(bulk.BulkError, match="missing"):
        tables.parts_from_manifest(root, "2026-11-13")
    with pytest.raises(bulk.BulkError, match="No manifest"):
        tables.parts_from_manifest(root, "2026-11-20")


def test_a_parallel_build_gives_the_same_tables(tmp_path, built):
    out, stats = built
    root = write_export(tmp_path / "bulk2")
    out2 = tmp_path / "tables2"
    stats2 = tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"),
        out2,
        "2026-11-13",
        log=lambda s: None,
        workers=2,
    ).run()
    assert stats2["counts"] == stats["counts"] and stats2["rows"] == stats["rows"]
    for name in tables.SCHEMAS:
        a = pq.read_table(out / f"{name}.parquet").drop_columns(["source"])
        b = pq.read_table(out2 / f"{name}.parquet").drop_columns(["source"])
        assert a.equals(b), name
    assert not (out2 / "_parts").exists()


def test_a_label_typed_over_the_counter_is_listed_apart_even_in_a_prescription_format(tmp_path):
    otc_plr = copy.deepcopy(PLR_WITH_GUIDE)
    otc_plr.update(id="doc-0099", set_id="set-otcp")
    otc_plr["openfda"] = dict(otc_plr["openfda"], product_type=["HUMAN OTC DRUG"])
    root = tmp_path / "bulk"
    import csv
    import hashlib

    folder = root / "2026-11-13"
    folder.mkdir(parents=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        meta = {"last_updated": "2026-11-13", "results": {"skip": 0, "limit": 1, "total": 1}}
        z.writestr("drug-label.json", json.dumps({"meta": meta, "results": [otc_plr]}))
    name = "drug-label-0001-of-0001.json.zip"
    (folder / name).write_bytes(buf.getvalue())
    with (folder / "manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=bulk.MANIFEST_FIELDS)
        w.writeheader()
        w.writerow(
            {
                "export_date": "2026-11-13",
                "part": 1,
                "of": 1,
                "file": name,
                "listed_mib": 0,
                "listed_records": 1,
                "bytes": len(buf.getvalue()),
                "sha256": hashlib.sha256(buf.getvalue()).hexdigest(),
                "meta_last_updated": "x",
                "meta_skip": 0,
                "meta_total": 1,
                "added": "T",
                "how": "test",
            }
        )
    out = tmp_path / "t"
    tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    assert pq.read_table(out / "labels.parquet").num_rows == 0
    assert [r["label_format"] for r in pq.read_table(out / "excluded_otc.parquet").to_pylist()] == [
        "plr"
    ]


def test_the_build_counts_restated_headings_and_pairs_them_once(tmp_path):
    guide = copy.deepcopy(PLR_WITH_GUIDE)
    guide["spl_medguide"] = [
        "MEDICATION GUIDE ZORVAN What should I tell my healthcare provider before taking "
        "ZORVAN? Before taking ZORVAN, tell your healthcare provider about your conditions. "
        "How should I take ZORVAN? Take 1 tablet each day."
    ]
    root = write_export(tmp_path / "bulk", parts=[[guide]])
    out = tmp_path / "t"
    stats = tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"), out, "2026-11-13", log=lambda s: None
    ).run()
    assert stats["counts"]["restated_headings:medication_guide"] == 1
    pairs = pq.read_table(out / "section_pairs.parquet").to_pylist()
    assert [r["heading_key"] for r in pairs] == ["before", "how_to_take"]
    assert pairs[0]["measures"]["words"] > 5
