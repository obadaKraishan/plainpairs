import io
import json
import zipfile

import pytest

from plainpairs import bulk
from tests.test_client import FakeResponse, make

DOWNLOAD = {
    "meta": {"last_updated": "2026-11-13"},
    "results": {
        "drug": {
            "label": {
                "export_date": "2026-11-13",
                "total_records": 25,
                "partitions": [
                    {
                        "display_name": "/drug/label (part 2 of 2)",
                        "file": "https://download.example.org/drug/label/drug-label-0002-of-0002.json.zip",
                        "size_mb": "0.5",
                        "records": 5,
                    },
                    {
                        "display_name": "/drug/label (part 1 of 2)",
                        "file": "https://download.example.org/drug/label/drug-label-0001-of-0002.json.zip",
                        "size_mb": "9.1",
                        "records": 20,
                    },
                ],
            }
        }
    },
}


def test_label_parts_are_read_and_ordered():
    date, parts = bulk.label_parts(DOWNLOAD)
    assert date == "2026-11-13"
    assert [p.number for p in parts] == [1, 2]
    assert parts[1].filename == "drug-label-0002-of-0002.json.zip"
    assert bulk.smallest(parts).number == 2


def test_label_parts_refuse_an_unknown_shape():
    with pytest.raises(bulk.BulkError, match=r"results\.drug\.label"):
        bulk.label_parts({"results": {}})
    bad = json.loads(json.dumps(DOWNLOAD))
    bad["results"]["drug"]["label"]["partitions"][0]["display_name"] = "odd"
    with pytest.raises(bulk.BulkError, match="part number"):
        bulk.label_parts(bad)


def test_fetch_part_refuses_a_part_over_the_limit(tmp_path):
    _, parts = bulk.label_parts(DOWNLOAD)
    c, session, _ = make(tmp_path, [])
    with pytest.raises(bulk.BulkError, match="approval"):
        bulk.fetch_part(c, parts[0], tmp_path, "2026-11-13", max_mb=1)
    assert session.calls == []


def test_fetch_part_downloads_into_a_folder_named_by_the_export_date(tmp_path):
    _, parts = bulk.label_parts(DOWNLOAD)
    c, _, _ = make(tmp_path, [FakeResponse(body=b"PK-zip-bytes")])
    dest = bulk.fetch_part(c, parts[1], tmp_path / "bulk", "2026-11-13", max_mb=1)
    assert dest == tmp_path / "bulk" / "2026-11-13" / "drug-label-0002-of-0002.json.zip"
    assert dest.read_bytes() == b"PK-zip-bytes"


def labels_json(n, meta=None):
    meta = meta or {"last_updated": "2026-11-13", "results": {"skip": 0, "limit": n, "total": n}}
    rows = [{"id": f"id-{i}", "set_id": f"set-{i}", "text": ["a [x] {y}, " * i]} for i in range(n)]
    return json.dumps({"meta": meta, "results": rows}, indent=1)


def test_iter_results_reads_records_across_small_chunks():
    text = labels_json(7)
    got = list(bulk.iter_results(io.StringIO(text), chunk_size=13))
    assert [r["id"] for r in got] == [f"id-{i}" for i in range(7)]
    assert got[3]["text"] == ["a [x] {y}, " * 3]


def test_iter_results_of_an_empty_array():
    assert list(bulk.iter_results(io.StringIO('{"meta": {}, "results": []}'))) == []


def test_iter_results_refuses_broken_files():
    with pytest.raises(bulk.BulkError, match="No results array"):
        list(bulk.iter_results(io.StringIO('{"meta": {}}')))
    with pytest.raises(bulk.BulkError, match="inside a label record"):
        list(bulk.iter_results(io.StringIO('{"results": [{"id": "a"'), chunk_size=4))
    with pytest.raises(bulk.BulkError, match="inside the results array"):
        list(bulk.iter_results(io.StringIO('{"results": [{"id": "a"},  '), chunk_size=4))
    with pytest.raises(bulk.BulkError, match="not a JSON object"):
        list(bulk.iter_results(io.StringIO('{"results": [3]}')))


def make_zip(path, members):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def test_iter_labels_and_meta_read_a_part_without_unpacking(tmp_path):
    z = make_zip(tmp_path / "p.json.zip", {"drug-label-0001-of-0001.json": labels_json(3)})
    assert [r["set_id"] for r in bulk.iter_labels(z)] == ["set-0", "set-1", "set-2"]
    assert bulk.read_meta(z)["last_updated"] == "2026-11-13"
    assert list(tmp_path.iterdir()) == [z]


def test_read_meta_of_a_part_without_one(tmp_path):
    z = make_zip(tmp_path / "p.zip", {"a.json": '{"results": []}'})
    assert bulk.read_meta(z) == {}


def test_untrusted_archives_are_checked(tmp_path):
    two = make_zip(tmp_path / "two.zip", {"a.json": "{}", "b.json": "{}"})
    with pytest.raises(bulk.BulkError, match="one file"):
        list(bulk.iter_labels(two))
    sneaky = make_zip(tmp_path / "s.zip", {"../evil.json": "{}"})
    with pytest.raises(bulk.BulkError, match="Unexpected file name"):
        list(bulk.iter_labels(sneaky))
    odd = make_zip(tmp_path / "o.zip", {"a.txt": "{}"})
    with pytest.raises(bulk.BulkError, match="Unexpected file name"):
        list(bulk.iter_labels(odd))


def test_a_member_that_unpacks_too_large_is_refused(tmp_path, monkeypatch):
    z = make_zip(tmp_path / "p.zip", {"a.json": labels_json(1)})
    monkeypatch.setattr(bulk, "MAX_UNPACKED", 10)
    with pytest.raises(bulk.BulkError, match="unpacks to"):
        list(bulk.iter_labels(z))
