"""The Kaggle mirror's page: the description, every file and column described from the schema
documentation, the sources, the cover, and the settings sent with `metadata --update`.

The invented pack of ``tests.test_release`` (invented labels, no real label text) is the pack."""

import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from plainpairs import cli, codes, cover, kaggle_meta, nci, pack, tables
from tests.test_pack import made  # noqa: F401  (the fixture)
from tests.test_release import built  # noqa: F401  (the fixture made needs)

FIXTURE = Path(__file__).with_name("fixtures") / "manifest-0.1.0.json"
#: The git blob ids of README.md and LICENSES.md on the Hub at b08fd122 (version 0.1.0).
HUB_CARD_BLOB = "1818e33d76c5e0dcef719062b4b9f06ae4b885ed"
HUB_LICENSES_BLOB = "a0a5e4a791fd9626f5c8ed3d175287115a6e5c57"


def blob_id(text: str) -> str:
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def kaggle(made, tmp_path):  # noqa: F811
    _out, p, m = made
    k = tmp_path / "kaggle"
    meta = pack.build_kaggle(p, k)
    return p, m, k, meta


def rewrite(k: Path, meta: dict) -> None:
    (k / "dataset-metadata.json").write_text(json.dumps(meta), encoding="utf-8")


# --- the schema documentation ----------------------------------------------------------------


def test_the_schema_doc_describes_every_column_of_every_release_table():
    doc = kaggle_meta.read_schema_doc()
    release = {
        **{name: s for name, s in tables.SCHEMAS.items()},
        "codes": codes.SCHEMA,
        **nci.TABLES,
    }
    missing = [
        f"{table}.{column}"
        for table, schema in release.items()
        for column in schema.names
        if not doc.describe(table, column)
    ]
    assert missing == []
    for table in release:
        assert doc.rows[table].startswith("one row per"), table


def test_patterns_stand_only_for_the_known_sections_and_texts():
    doc = kaggle_meta.read_schema_doc()
    assert doc.describe("labels", "p_boxed_warning_sha256").startswith(
        "The SHA-256 of the label's boxed_warning text"
    )
    assert "medication_guide" in doc.describe("labels", "t_medication_guide_structured")
    assert doc.describe("labels", "p_not_a_section_sha256") is None
    assert doc.describe("labels", "no_such_column") is None
    # a value in backticks keeps its case; no backtick reaches Kaggle
    assert doc.describe("nci_pairs", "pair_kind").startswith("version: the health-professional")
    assert all("`" not in doc.describe("labels", c) for c in tables.SCHEMAS["labels"].names)


def test_a_bad_schema_doc_is_refused_with_its_line(tmp_path):
    bad = tmp_path / "schema.md"
    bad.write_text("## `t`: one row per x\n| column | type | notes |\n|---|---|---|\n| a | b |\n")
    with pytest.raises(kaggle_meta.SchemaDocError, match="line 4"):
        kaggle_meta.read_schema_doc(bad)
    bad.write_text(
        "## `t`\n| column | type | notes |\n|---|---|---|\n| `a` | int | x |\n| `a` | int | y |\n"
    )
    with pytest.raises(kaggle_meta.SchemaDocError, match="described twice"):
        kaggle_meta.read_schema_doc(bad)
    bad.write_text("Intro\n\n| column | type | notes |\n|---|---|---|\n| `a` | int | x |\n")
    with pytest.raises(kaggle_meta.SchemaDocError, match="under no table name"):
        kaggle_meta.read_schema_doc(bad)
    with pytest.raises(kaggle_meta.SchemaDocError, match="checkout"):
        kaggle_meta.read_schema_doc(tmp_path / "missing.md")


# --- the description ---------------------------------------------------------------------------


def test_the_description_has_the_headings_in_order_and_the_bold_line(made, tmp_path):  # noqa: F811
    p, m, k, meta = kaggle(made, tmp_path)
    d = meta["description"]
    assert kaggle_meta.headings(d) == list(kaggle_meta.HEADINGS)
    first, inside = d.index("## What PlainPairs is\n"), d.index("## What is inside\n")
    assert f"\n{kaggle_meta.NOT_MEDICAL}\n" in d[first:inside]
    assert "https://www.cancer.gov" in d[first:inside]  # the card's box, lifted whole
    for f in m["files"]:  # the file table: every data file with its rows
        assert f"| `{f['config']}.parquet` |" in d and f"| {f['rows']:,} |" in d
    assert f'pd.read_parquet("/kaggle/input/plainpairs/{kaggle_meta.LOAD_FILE}")' in d
    limits = kaggle_meta.card_section((p / "README.md").read_text(encoding="utf-8"), "Limits")
    assert limits in d and 3 <= limits.count("\n- ") + 1 <= 5
    assert "LICENSES.md" in d[d.index("## Sources, terms and credit") :]
    links = d[d.index("## Links\n") :]
    assert pack.HF_URL in links and kaggle_meta.REPO_URL in links and pack.PAPER_URL in links
    assert len(d) <= kaggle_meta.DESCRIPTION_MAX and pack.raw_tags(d) == []
    assert pack.check_kaggle(k, p) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d.replace("## Limits\n", "## Caveats\n"), "headings are"),
        (
            lambda d: (
                d.replace("## Limits\n", "## L\n")
                .replace("## Load one table\n", "## Limits\n")
                .replace("## L\n", "## Load one table\n")
            ),
            "headings are",
        ),
        (lambda d: d.replace(f"\n{kaggle_meta.NOT_MEDICAL}\n", "\n"), "lacks the bold line"),
        (lambda d: d.replace("```bibtex\n", "```\n"), "lacks the paper's BibTeX entry"),
        (lambda d: d + "x" * kaggle_meta.DESCRIPTION_MAX, "characters; the cap is"),
        (lambda d: d + "\n<details>\n", "read as an HTML tag"),
    ],
)
def test_each_description_check_fails(made, tmp_path, change, problem):  # noqa: F811
    p, _m, k, meta = kaggle(made, tmp_path)
    meta["description"] = change(meta["description"])
    rewrite(k, meta)
    problems = pack.check_kaggle(k, p)
    assert any(problem in x for x in problems), problems


def test_the_dataset_version_after_the_paper_is_a_problem(made, tmp_path):  # noqa: F811
    _p, m, _k, meta = kaggle(made, tmp_path)
    paper = pack.paper_citation()
    dataset = pack.citation(m["version"], m["created"])
    d = (
        meta["description"]
        .replace(paper, "PAPER")
        .replace(dataset, paper)
        .replace("PAPER", dataset)
    )
    problems = kaggle_meta.description_problems(d, m, [kaggle_meta.LOAD_FILE])
    assert problems == [
        "the Kaggle description's How to cite does not name the paper before the dataset's version."
    ]
    assert kaggle_meta.description_problems(meta["description"], m, ["other.parquet"]) == [
        f"the Kaggle description loads {kaggle_meta.LOAD_FILE}, which is not one of its files."
    ]


# --- files, columns, sources -------------------------------------------------------------------


def test_every_file_and_every_column_is_described_in_order(made, tmp_path):  # noqa: F811
    p, m, k, meta = kaggle(made, tmp_path)
    res = meta["resources"]
    assert [r["path"] for r in res] == [f"{f['config']}.parquet" for f in m["files"]] + [
        "LICENSES.md",
        "manifest.json",
    ]
    for r in res:
        assert 20 <= len(r["description"]) <= 400, r["path"]
    for f, r in zip(m["files"], res, strict=False):
        names = pq.read_schema(p / f["path"]).names
        assert [x["name"] for x in r["schema"]["fields"]] == names
        assert all(x["description"].strip() for x in r["schema"]["fields"])
        assert f["configuration"] is None or f["configuration"] in r["description"]
    labels = next(r for r in res if r["path"] == "current_labels.parquet")["schema"]["fields"]
    types = {x["name"]: x.get("type") for x in labels}
    assert types["version"] == "integer" and types["set_id"] == "string"
    assert types["has_copyright_mark"] == "boolean" and types["effective_date"] == "datetime"
    assert types["p_boxed_warning"] is None and types["routes"] is None  # structs, lists
    # one column without a description, then columns out of order
    labels[3]["description"] = ""
    rewrite(k, meta)
    assert pack.check_kaggle(k, p) == [
        "the Kaggle file current_labels.parquet has 1 columns without a description (version); "
        "describe them in docs/schema.md."
    ]
    labels[3]["description"] = "x"
    labels[0], labels[1] = labels[1], labels[0]
    rewrite(k, meta)
    assert pack.check_kaggle(k, p) == [
        "the Kaggle columns of current_labels.parquet are not the file's columns in order."
    ]


def test_no_text_of_the_pack_reaches_the_page(made, tmp_path):  # noqa: F811
    p, m, _k, meta = kaggle(made, tmp_path)
    page = json.dumps(meta)
    for f in m["files"]:
        if f["layer"] != "text":
            continue
        for value in pq.read_table(p / f["path"], columns=["text"])["text"].to_pylist():
            if len(value) >= 25:
                assert value not in page and value[:25] not in page


def test_the_frequency_sources_keywords_and_cover(made, tmp_path):  # noqa: F811
    p, _m, k, meta = kaggle(made, tmp_path)
    assert meta["expectedUpdateFrequency"] == "not specified"
    assert meta["expectedUpdateFrequency"] in kaggle_meta.UPDATE_FREQUENCIES
    assert all(a in meta["userSpecifiedSources"] for a in kaggle_meta.SOURCE_ADDRESSES)
    assert meta["keywords"][:3] == ["health", "nlp", "text"]
    assert (k / kaggle_meta.COVER_NAME).read_bytes() == cover.TRACKED.read_bytes()
    meta["expectedUpdateFrequency"] = "weekly"
    meta["userSpecifiedSources"] = ""
    rewrite(k, meta)
    problems = pack.check_kaggle(k, p)
    assert len(problems) == 2 and "no schedule is promised" in problems[0]
    assert "do not name all three sources" in problems[1]
    (k / kaggle_meta.COVER_NAME).write_bytes(b"not the cover")
    assert any("is not the project's cover" in x for x in pack.check_kaggle(k, p))


def test_the_card_rewrite_refreshes_the_page_and_keeps_the_data(made, tmp_path):  # noqa: F811
    p, _m, k, _meta = kaggle(made, tmp_path)
    data = {x.name: x.read_bytes() for x in k.glob("*.parquet")}
    (k / "dataset-metadata.json").write_text("{}", encoding="utf-8")
    (k / kaggle_meta.COVER_NAME).unlink()
    written = pack.write_card(p, k)
    assert k / kaggle_meta.COVER_NAME in written
    assert pack.check_kaggle(k, p) == []
    assert {x.name: x.read_bytes() for x in k.glob("*.parquet")} == data


# --- the 0.1.0 card on the Hub ----------------------------------------------------------------


def test_the_0_1_0_card_and_licenses_are_byte_for_byte_those_on_the_hub():
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert manifest["version"] == "0.1.0"
    assert blob_id(pack.card(manifest)) == HUB_CARD_BLOB
    assert blob_id(pack._template(pack.LICENSES_TEMPLATE, manifest)) == HUB_LICENSES_BLOB


# --- the settings sent with `metadata --update` -------------------------------------------------


def live_info(**over) -> dict:
    info = {
        "datasetId": 1,
        "datasetSlug": "plainpairs",
        "ownerUser": "someone",
        "usabilityRating": 0.5,
        "totalViews": 9,
        "title": pack.KAGGLE_TITLE,
        "subtitle": pack.KAGGLE_SUBTITLE,
        "description": "the old description",
        "keywords": ["health", "a-tag-added-on-the-website"],
        "licenses": [{"name": "other"}],
        "expectedUpdateFrequency": "not specified",
    }
    info.update(over)
    return {"info": info}


def test_the_settings_start_from_the_live_page(made, tmp_path):  # noqa: F811
    _p, _m, k, meta = kaggle(made, tmp_path)
    live = tmp_path / "live.json"
    live.write_text(json.dumps(live_info()), encoding="utf-8")
    path, changed = kaggle_meta.write_update_settings(live, k, tmp_path / "out")
    sent = json.loads(path.read_text(encoding="utf-8"))
    assert sent["title"] == pack.KAGGLE_TITLE and sent["licenses"] == [{"name": "other"}]
    assert sent["description"] == meta["description"]
    assert sent["resources"] == meta["resources"]
    assert sent["isPrivate"] is False and sent["collaborators"] == []
    assert sent["keywords"][-1] == "a-tag-added-on-the-website"  # never dropped
    assert sent["keywords"][: len(kaggle_meta.KEYWORDS)] == list(kaggle_meta.KEYWORDS)
    assert not {"datasetId", "usabilityRating", "totalViews", "ownerUser"} & set(sent)
    assert changed == [
        "description",
        "keywords",
        "userSpecifiedSources",
        "resources",
        "image",
    ]
    assert (tmp_path / "out" / kaggle_meta.COVER_NAME).read_bytes() == cover.TRACKED.read_bytes()
    assert sorted(x.name for x in (tmp_path / "out").iterdir()) == [
        kaggle_meta.COVER_NAME,
        "dataset-metadata.json",
    ]


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"title": "Another title"}, "the live title"),
        ({"subtitle": "Another subtitle for the page"}, "the live subtitle"),
        ({"licenses": [{"name": "CC0-1.0"}]}, "the live license"),
    ],
)
def test_the_settings_never_change_title_subtitle_or_license(made, tmp_path, over, message):  # noqa: F811
    _p, _m, k, _meta = kaggle(made, tmp_path)
    live = tmp_path / "live.json"
    live.write_text(json.dumps(live_info(**over)), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        kaggle_meta.write_update_settings(live, k, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_private_page_stays_private_and_the_folder_must_be_new(made, tmp_path):  # noqa: F811
    _p, _m, k, _meta = kaggle(made, tmp_path)
    live = tmp_path / "live.json"
    live.write_text(json.dumps(live_info(isPrivate=True)), encoding="utf-8")
    path, _changed = kaggle_meta.write_update_settings(live, k, tmp_path / "out")
    assert json.loads(path.read_text(encoding="utf-8"))["isPrivate"] is True
    with pytest.raises(ValueError, match="not empty"):
        kaggle_meta.write_update_settings(live, k, tmp_path / "out")


def test_the_kaggle_settings_command(made, tmp_path, capsys):  # noqa: F811
    _p, _m, k, _meta = kaggle(made, tmp_path)
    live = tmp_path / "live.json"
    live.write_text(json.dumps(live_info()), encoding="utf-8")
    out = tmp_path / "settings"
    args = ["release", "kaggle-settings", "--live", str(live), "--kaggle", str(k)]
    assert cli.main([*args, "--out", str(out)]) == 0
    said = capsys.readouterr().out
    assert "description, keywords" in said and "kaggle datasets metadata --update" in said
    live.write_text(json.dumps(live_info(title="Another title")), encoding="utf-8")
    with pytest.raises(SystemExit, match="No settings written"):
        cli.main([*args, "--out", str(tmp_path / "again")])


# --- the cover -----------------------------------------------------------------------------------


def test_the_cover_is_drawn_by_the_code(tmp_path):
    size, pixels = cover.read_png(cover.TRACKED.read_bytes())
    assert size == (cover.WIDTH, cover.HEIGHT) == (560, 280)
    assert (size, pixels) == cover.read_png(cover.png(cover.draw()))
    assert cover.main([str(tmp_path / "c.png")]) == 0
    assert cover.read_png((tmp_path / "c.png").read_bytes()) == (size, pixels)
    # the name sits inside the centred 280 by 280 thumbnail Kaggle crops
    rows = cover.draw()
    ink = [
        x for row in rows for x in range(cover.WIDTH) if tuple(row[3 * x : 3 * x + 3]) == cover.INK
    ]
    assert min(ink) >= 140 and max(ink) < 420
