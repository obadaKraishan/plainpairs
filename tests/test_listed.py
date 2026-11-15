"""The listed-now flags, on invented listing files only."""

import io
import json
import zipfile

import pyarrow.parquet as pq
import pytest

from plainpairs import listed, tables
from tests.test_client import FakeResponse, make
from tests.test_tables import write_export

DOWNLOAD = {
    "results": {
        "drug": {
            "ndc": {
                "export_date": "2026-11-13",
                "partitions": [
                    {
                        "file": "https://download.example.org/drug/ndc/drug-ndc-0001-of-0001.json.zip",
                        "size_mb": "1.5",
                        "records": 3,
                    }
                ],
            }
        }
    }
}


def ndc_zip(path, records):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("drug-ndc-0001-of-0001.json", json.dumps({"meta": {}, "results": records}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path


def dailymed_zip(path, lines, readme=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dm_spl_zip_files_meta_data.txt", "\n".join(lines) + "\n")
        if readme:
            z.writestr("readme.txt", "An invented note, not a list.\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path


HEADER = "SETID|ZIP_FILE_NAME|UPLOAD_DATE|SPL_VERSION|TITLE"
NDC_RECORDS = [
    {"spl_id": "doc-0001", "finished": True, "openfda": {"spl_set_id": ["set-aaaa"]}},
    {"spl_id": "doc-0002", "finished": True},  # no openfda block: matched by document id
    {"spl_id": "doc-zzzz", "finished": False, "openfda": {}},
]


def test_ndc_files_are_read_from_the_listing():
    (f,) = listed.ndc_files(DOWNLOAD)
    assert (f.filename, f.size_mb, f.records, f.export_date) == (
        "drug-ndc-0001-of-0001.json.zip",
        1.5,
        3,
        "2026-11-13",
    )
    with pytest.raises(listed.ListedError, match="drug/ndc"):
        listed.ndc_files({"results": {}})


def test_read_ndc_keeps_set_ids_and_document_ids(tmp_path):
    path = ndc_zip(tmp_path / "ndc.json.zip", NDC_RECORDS)
    set_ids, spl_ids, counts = listed.read_ndc(path)
    assert set_ids == {"set-aaaa"}
    assert spl_ids == {"doc-0001", "doc-0002", "doc-zzzz"}
    assert counts["records"] == 3 and counts["with_spl_set_id"] == 1
    assert counts["finished:False"] == 1


def test_read_dailymed_takes_the_highest_version_and_skips_other_members(tmp_path):
    lines = [
        HEADER,
        "SET-BBBB|20260101_set-bbbb.zip|01/01/2026|3|INVENTED TITLE [EXAMPLE PHARMA]",
        "set-bbbb|20260202_set-bbbb.zip|02/02/2026|4|INVENTED TITLE [EXAMPLE PHARMA]",
        "set-cccc|x.zip|01/01/2026||NO VERSION",
        "",
    ]
    path = dailymed_zip(tmp_path / "dm.zip", lines)
    versions, counts = listed.read_dailymed(path)
    assert versions == {"set-bbbb": 4, "set-cccc": 0}
    assert counts["members_read"] == 1 and counts["members_skipped"] == 1
    assert counts["rows"] == 3 and counts["rows_without_version"] == 1


def test_a_dailymed_file_of_another_shape_is_refused():
    with pytest.raises(listed.ListedError, match="SETID"):
        listed.read_dailymed_rows(io.StringIO("A|B|C|D\n1|2|3|4\n"))
    with pytest.raises(listed.ListedError):
        listed.read_dailymed_rows(io.StringIO(""))


def test_a_member_too_large_is_refused(tmp_path, monkeypatch):
    path = dailymed_zip(tmp_path / "dm.zip", [HEADER, "set-a|f|d|1|t"])
    monkeypatch.setattr(listed, "MAX_MEMBER_BYTES", 5)
    with pytest.raises(listed.ListedError, match="too large"):
        listed.read_dailymed(path)


def test_flags_say_where_each_label_is_listed(tmp_path):
    lst = listed.load(
        ndc_zip(tmp_path / "ndc" / "2026-11-13" / "n.json.zip", NDC_RECORDS),
        dailymed_zip(tmp_path / "dailymed" / "2026-11-15" / "d.zip", [HEADER, "set-aaaa|f|d|7|t"]),
    )
    assert lst.sources["ndc"]["date"] == "2026-11-13"
    assert lst.sources["dailymed"]["counts"]["distinct_set_ids"] == 1
    assert listed.flags(lst, "set-aaaa", "doc-0001", 7) == {
        "listed_in_ndc_directory": True,
        "ndc_match": "set_id",
        "served_by_dailymed": True,
        "dailymed_version": 7,
    }
    assert listed.flags(lst, "set-bbbb", "doc-0002", 2)["ndc_match"] == "spl_id"
    none = listed.flags(lst, "set-qqqq", "doc-qqqq", 1)
    assert none["listed_in_ndc_directory"] is False and none["ndc_match"] == "none"
    assert none["served_by_dailymed"] is False and none["dailymed_version"] is None


def test_without_listings_the_flags_are_null():
    assert set(listed.flags(listed.Listings(), "set-aaaa", "doc", 1).values()) == {None}


def test_fetch_ndc_refuses_a_file_over_the_limit_before_any_request(tmp_path):
    c, session, _ = make(tmp_path, [])
    with pytest.raises(listed.ListedError, match="ask the maintainer"):
        listed.fetch_ndc(c, DOWNLOAD, tmp_path / "listed", max_mb=1)
    assert session.calls == []


def test_fetch_ndc_and_dailymed_write_once_with_a_manifest(tmp_path):
    root = tmp_path / "listed"
    c, session, _ = make(tmp_path, [FakeResponse(body=b"PK-ndc"), FakeResponse(body=b"PK-dm")])
    (path,) = listed.fetch_ndc(c, DOWNLOAD, root)
    assert path == root / "ndc" / "2026-11-13" / "drug-ndc-0001-of-0001.json.zip"
    dm = listed.fetch_dailymed(c, root, "2026-11-15")
    assert dm.read_bytes() == b"PK-dm"
    # a second run downloads nothing
    assert listed.fetch_ndc(c, DOWNLOAD, root) == [path]
    assert listed.fetch_dailymed(c, root, "2026-11-15") == dm
    assert len(session.calls) == 2
    rows = (root / "manifest.csv").read_text().splitlines()
    assert rows[0].startswith("source,date,file") and len(rows) == 3
    assert listed.latest(root, "ndc") == path and listed.latest(root, "dailymed") == dm
    assert listed.latest(tmp_path / "nothing", "ndc") is None


def test_the_build_adds_the_flags_to_labels(tmp_path):
    root = write_export(tmp_path / "bulk")
    lst = listed.load(
        ndc_zip(tmp_path / "n" / "2026-11-13" / "n.json.zip", NDC_RECORDS),
        dailymed_zip(tmp_path / "d" / "2026-11-15" / "d.zip", [HEADER, "set-gggg|f|d|1|t"]),
    )
    out = tmp_path / "t"
    stats = tables.Builder(
        tables.parts_from_manifest(root, "2026-11-13"),
        out,
        "2026-11-13",
        log=lambda s: None,
        listings=lst,
    ).run()
    rows = {r["set_id"]: r for r in pq.read_table(out / "labels.parquet").to_pylist()}
    assert rows["set-aaaa"]["ndc_match"] == "set_id"
    assert rows["set-bbbb"]["ndc_match"] == "spl_id"  # matched by its document id
    assert rows["set-iiii"]["listed_in_ndc_directory"] is False
    assert rows["set-gggg"]["served_by_dailymed"] is True
    assert rows["set-aaaa"]["served_by_dailymed"] is False
    assert set(stats["listed_sources"]) == {"ndc", "dailymed"}
