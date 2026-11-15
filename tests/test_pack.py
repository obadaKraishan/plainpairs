"""The release pack: built from an invented build, checked on its own, and broken on purpose."""

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from plainpairs import codes, pack
from tests.test_release import _nci_tables, built  # noqa: F401  (the fixture)


@pytest.fixture
def made(built, tmp_path):  # noqa: F811
    _root, out, _manifest = built
    _nci_tables(out, tmp_path)
    codes.build(out, log=lambda s: None)
    take = tmp_path / "takedown.csv"
    take.write_text("kind,id,received,reason\n", encoding="utf-8")
    p = tmp_path / "pack"
    m = pack.build_pack(out, p, "0.1.0", take, today=lambda: "2026-11-15")
    return out, p, m


def test_a_clean_pack_passes(made):
    _out, p, m = made
    assert pack.check_pack(p) == []
    configs = [f["config"] for f in m["files"]]
    assert configs[:6] == [f"current_{t}" for t in pack.LABEL_TABLES]
    assert "unlisted_labels" in configs and "nci_text" in configs and "excluded_otc" in configs
    assert m["switch"] == {"labels": "unmarked", "nci": "kept_text_with_credit"}
    card = (p / "README.md").read_text(encoding="utf-8")
    body = card.split("\n---\n", 1)[1]
    assert "Not medical information" in body[:800] and "$" not in card
    assert "config_name: current_labels" in card and "default: true" not in card
    lic = (p / "LICENSES.md").read_text(encoding="utf-8")
    assert "CC0" in lic and "cancer.gov" in lic and "$" not in lic
    unl = pq.read_table(p / "data/unlisted/labels.parquet")
    assert not [c for c in unl.column_names if c.endswith("_structured")]
    assert set(unl["configuration"].to_pylist()) <= {"unlisted"}


def test_the_switch_holds_back_marked_text_and_takedowns(built, tmp_path):  # noqa: F811
    _root, out, _manifest = built
    _nci_tables(out, tmp_path)
    codes.build(out, log=lambda s: None)
    labels = pq.read_table(out / "labels.parquet").to_pylist()
    sid = next(r["set_id"] for r in labels if r["configuration"] == "current")
    nci_url = pq.read_table(out / "nci_summaries.parquet")["url"].to_pylist()[0]
    take = tmp_path / "takedown.csv"
    take.write_text(
        f"kind,id,received,reason\nset_id,{sid},2026-11-15,invented\nurl,{nci_url},2026-11-15,x\n",
        encoding="utf-8",
    )
    m = pack.build_pack(out, tmp_path / "p", "0.1.0", take, today=lambda: "2026-11-15")
    assert m["held_back"]["label_text_rows_taken_down"] > 0
    assert m["held_back"]["nci_text_rows_taken_down"] > 0
    t = pq.read_table(tmp_path / "p" / "data/current/text_patient.parquet")
    assert sid not in t["set_id"].to_pylist()
    assert (
        sid in pq.read_table(tmp_path / "p" / "data/current/labels.parquet")["set_id"].to_pylist()
    )
    assert pack.check_pack(tmp_path / "p") == []


def test_bad_takedown_lists_are_refused(tmp_path):
    bad = tmp_path / "t.csv"
    bad.write_text("id\nx\n", encoding="utf-8")
    with pytest.raises(pack.PackError, match="columns"):
        pack.read_takedowns(bad)
    bad.write_text("kind,id,received,reason\nother,x,,\n", encoding="utf-8")
    with pytest.raises(pack.PackError, match="not valid"):
        pack.read_takedowns(bad)
    assert pack.read_takedowns(None) == {"set_id": set(), "url": set()}


def _redo(p, rel, fn):
    """Rewrite one file of the pack and update its manifest line, so only the content is wrong."""
    t = fn(pq.read_table(p / rel))
    pq.write_table(t, p / rel)
    m = json.loads((p / "manifest.json").read_text())
    for f in m["files"]:
        if f["path"] == rel:
            f.update(rows=t.num_rows, bytes=(p / rel).stat().st_size, sha256=pack._sha(p / rel))
    (p / "manifest.json").write_text(json.dumps(m))


def test_the_check_fails_on_each_problem(made):
    _out, p, _m = made
    (p / "data" / "stray.parquet").write_bytes(b"x")
    _redo(
        p,
        "data/current/text_patient.parquet",
        lambda t: t.set_column(
            t.schema.get_field_index("has_copyright_mark"),
            "has_copyright_mark",
            pa.array([True] * t.num_rows),
        ),
    )
    _redo(
        p,
        "data/current/codes.parquet",
        lambda t: t.append_column("vague_core", pa.array([1] * t.num_rows, pa.int32())),
    )
    _redo(
        p,
        "data/unlisted/labels.parquet",
        lambda t: t.append_column(
            "t_medication_guide_structured", pa.array([None] * t.num_rows, pa.int32())
        ),
    )
    _redo(
        p,
        "data/nci/text.parquet",
        lambda t: t.set_column(
            t.schema.get_field_index("credit_line"),
            "credit_line",
            pa.array(["Thanks."] * t.num_rows),
        ),
    )

    def strip(t):
        rows = t.to_pylist()
        for r in rows:
            r["structure_source"] = "json"
        return pa.Table.from_pylist(rows, t.schema)

    _redo(p, "data/current/labels.parquet", strip)
    card = (
        (p / "README.md")
        .read_text()
        .replace(
            "    path: data/nci/text.parquet", "    path: data/nci/text.parquet\n  default: true"
        )
    )
    (p / "README.md").write_text(card)
    problems = "\n".join(pack.check_pack(p))
    for want in (
        "stray.parquet is in the pack but not in the manifest",
        "text rows of marked labels",
        "experimental codes",
        "measures from structure in the unlisted",
        "without the NCI credit line",
        "current labels without structure",
        "names a default config",
    ):
        assert want in problems, want


def test_the_kaggle_mirror_holds_the_pack(made, tmp_path):
    _out, p, m = made
    k = tmp_path / "kaggle"
    meta = pack.build_kaggle(p, k)
    assert meta["id"] == pack.KAGGLE_ID and len(meta["resources"]) == len(m["files"])
    assert pack.check_kaggle(k, p) == []
    (k / "current_labels.parquet").write_bytes(b"changed")
    assert any("differs" in x for x in pack.check_kaggle(k, p))


def test_release_commands(made, tmp_path, monkeypatch, capsys):
    from plainpairs.cli import main

    out, p, _m = made
    assert main(["release", "check", "--pack", str(p)]) == 0
    assert "Pack check passed" in capsys.readouterr().out
    q = tmp_path / "q"
    assert (
        main(
            [
                "release",
                "build",
                "--version",
                "0.1.0",
                "--tables",
                str(out),
                "--out",
                str(q),
                "--takedown",
                str(tmp_path / "none.csv"),
                "--kaggle",
                str(tmp_path / "k2"),
            ]
        )
        == 0
    )
    assert main(["release", "check", "--pack", str(q), "--kaggle", str(tmp_path / "k2")]) == 0
    with pytest.raises(pack.PackError, match="not empty"):
        pack.build_pack(out, q, "0.1.0")


def test_the_check_fails_on_a_taken_down_text(made, tmp_path):
    _out, p, _m = made
    sid = pq.read_table(p / "data/current/text_patient.parquet")["set_id"].to_pylist()[0]
    take = tmp_path / "later.csv"
    take.write_text(f"kind,id,received,reason\nset_id,{sid},2026-11-16,invented\n")
    assert any("takedown list" in x for x in pack.check_pack(p, take))
    assert pack.check_pack(p, tmp_path / "missing.csv") == []


def test_the_removal_form_asks_for_what_the_document_names():
    from pathlib import Path

    form = Path(".github/ISSUE_TEMPLATE/removal-request.yml").read_text(encoding="utf-8")
    for want in ("set id", "page address", "Who is asking", "Why", "14 days", "takedown"):
        assert want in form
    doc = Path("docs/removal.md").read_text(encoding="utf-8")
    assert "data/takedown.csv" in doc and "record" in doc and "14 days" in doc
    head = Path("data/takedown.csv").read_text(encoding="utf-8").splitlines()
    assert head == [",".join(pack.TAKEDOWN_FIELDS)]  # no real entry
