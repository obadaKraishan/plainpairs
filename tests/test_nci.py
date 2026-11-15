"""The NCI summary reader, pairing and tables, on invented pages (no real summary text)."""

import pyarrow.parquet as pq
import pytest

from plainpairs import nci, pages

BASE = "https://www.cancer.gov"


def page(
    path,
    lang="en",
    audience="Health Professionals",
    other_version=None,
    other_lang=None,
    body="",
    updated="2026-01-02",
    kind="pdqCancerInfoSummary",
):
    alt = [f'<link rel="alternate" hreflang="{lang}" href="{BASE}{path}" />']
    if other_lang:
        ol, op = other_lang
        alt.append(f'<link rel="alternate" hreflang="{ol}" href="{BASE}{op}" />')
    toggle = (
        f'<div class="pdq-hp-patient-toggle"><a href="{other_version}">Go to other</a></div>'
        if other_version
        else ""
    )
    return f"""<!DOCTYPE html><html lang="{lang}"><head>
<meta name="dcterms.type" content="{kind}" />
<meta name="dcterms.audience" content="{audience}" />
<meta property="og:title" content="Zorvan Condition ({path[-6:]})" />
<meta property="og:url" content="{BASE}{path}" />
{"".join(alt)}
<script>var x = "not text";</script></head><body>
<nav class="on-this-page"><ul><li>Not read</li></ul></nav>
<div class="summary-sections"><div class="accordion">
<section id="_1"><h2>About the zorvan condition</h2>{toggle}
<div class="key-points"><h3>Key Points</h3><ul><li>A listed point.</li></ul></div>
{body}
</section>
<section id="_AboutThis_1"><h2>About This Summary</h2><p>Permission text, not kept.</p></section>
</div></div>
<footer><div class="document-dates"><strong>Updated:</strong>
<time datetime="{updated}T12:00:00Z">January 2</time></div></footer></body></html>"""


BODY = (
    '<p>The zorvan condition is invented for tests.[<a href="#cit/s_1.1">1</a>,'
    '<a href="#cit/s_1.2">2</a>] It has two parts.</p>'
    "<ul><li>First part of it</li><li>Second part<ul><li>A nested part</li></ul></li></ul>"
    '<figure id="f1"><img src="x.jpg" alt="x"><figcaption>A drawing of it.</figcaption></figure>'
    "<p>Drawing reprinted with permission of an invented artist.</p>"
    "<h3>Stages</h3>"
    "<table><caption>Table 1. Invented stages</caption><tr><th>Stage</th><th>Size</th></tr>"
    "<tr><td>I</td><td>2 cm</td></tr><tr><td>II</td><td>4 cm</td></tr></table>"
    "<h6>References</h6><ol><li>One invented reference.</li><li>Two.</li></ol>"
    "<table><caption>Table 2. Borrowed</caption><tr><td>Row</td><td>1</td></tr><tfoot><tr>"
    "<td>Adapted from an invented source.</td></tr></tfoot></table>"
    "<p>The data was used from an invented study, adapted from an invented plan.</p>"
    "<p>Call your doctor if you have a fever.<br/>Take the test once a day.</p>"
)


def test_parse_page_keeps_body_and_leaves_out_the_rest():
    p = nci.parse_page(
        page(
            "/types/zorvan/hp/zorvan-pdq",
            other_version="/types/zorvan/patient/zorvan-pdq",
            other_lang=("es", "/espanol/tipos/zorvan/pro/zorvan-pdq"),
            body=BODY,
        ),
        "x",
    )
    assert p.url == BASE + "/types/zorvan/hp/zorvan-pdq"
    assert (p.language, p.version, p.updated) == ("en", "health_professional", "2026-01-02")
    assert p.other_version_url == BASE + "/types/zorvan/patient/zorvan-pdq"
    assert p.other_language_urls == {"es": BASE + "/espanol/tipos/zorvan/pro/zorvan-pdq"}
    got = [(b.kind, b.text, b.level) for b in p.blocks]
    assert got == [
        ("heading", "About the zorvan condition", 2),
        ("paragraph", "The zorvan condition is invented for tests. It has two parts.", 0),
        ("item", "First part of it", 0),
        ("item", "Second part", 0),
        ("item", "A nested part", 0),
        ("heading", "Stages", 3),
        ("caption", "Table 1. Invented stages", 0),
        ("data_cell", "Stage", 0),
        ("data_cell", "Size", 0),
        ("data_cell", "I", 0),
        ("data_cell", "2 cm", 0),
        ("data_cell", "II", 0),
        ("data_cell", "4 cm", 0),
        (
            "paragraph",
            "The data was used from an invented study, adapted from an invented plan.",
            0,
        ),
        ("paragraph", "Call your doctor if you have a fever.", 0),
        ("paragraph", "Take the test once a day.", 0),
    ]
    assert p.references == 2
    lo = p.left_out
    assert lo["citation_mark"] == 2 and lo["figure"] == 1 and lo["credit_line"] == 1
    assert lo["key_points"] >= 1 and lo["about_this"] >= 1 and lo["navigation"] >= 1
    assert lo["reference"] == 2 and lo["credited_table"] == 1
    joined = " ".join(b.text for b in p.blocks)
    for gone in (
        "drawing",
        "permission",
        "Key Points",
        "listed point",
        "invented reference",
        "Permission text",
        "not text",
        "Not read",
    ):
        assert gone not in joined


def test_parse_page_refuses_other_pages():
    with pytest.raises(nci.NciError, match="not a cancer information summary"):
        nci.parse_page(page("/x-pdq", kind="article"), "x")
    with pytest.raises(nci.NciError, match="no summary body"):
        nci.parse_page(page("/x-pdq").replace('class="accordion"', 'class="other"'), "x")


def test_measures_english_and_spanish():
    en = nci.parse_page(page("/a-pdq", body=BODY), "x")
    m = nci.measures(en.blocks, "en")
    assert m["words"] > 0 and m["flesch_kincaid"] is not None and m["smog"] is not None
    assert m["szigriszt_pazos"] is None and m["blocks_data_cell"] == 6
    es = nci.parse_page(
        page("/espanol/a-pdq", lang="es", body="<p>La casa es grande. El ni\u00f1o come.</p>"), "x"
    )
    ms = nci.measures(es.blocks, "es")
    assert ms["flesch_kincaid"] is None and ms["szigriszt_pazos"] is not None
    assert ms["inflesz_band"] is not None
    c = nci.trusted_codes(en.blocks)
    assert c["you_words"] == 2 and c["contact_sentences"] == 1 and c["frequencies"] == 1
    assert c["command_sentences"] >= 1 and set(c) == set(nci.CODE_FIELDS)


def _write(root, url, markup):
    return pages.fetch_page(_Fake(markup), url, root, "2026-11-15")


class _Fake:
    """A stand-in for the polite client: answers one page."""

    def __init__(self, markup):
        self.markup = markup.encode("utf-8")

    def get(self, url):
        class R:
            status = 200
            content = self.markup

        return R()

    def clock(self):
        return "2026-11-15T19:00:00.000Z"


def test_build_pairs_by_links_and_writes_three_tables(tmp_path):
    root = tmp_path / "nci"
    hp, pt = "/types/zorvan/hp/zorvan-pdq", "/types/zorvan/patient/zorvan-pdq"
    es_hp = "/espanol/tipos/zorvan/pro/zorvan-pdq"
    lone = "/types/other/hp/other-pdq"
    _write(root, BASE + hp, page(hp, other_version=pt, other_lang=("es", es_hp), body=BODY))
    _write(root, BASE + pt, page(pt, audience="Patients", other_version=hp, body=BODY))
    _write(root, BASE + es_hp, page(es_hp, lang="es", other_lang=("en", hp), body="<p>Texto.</p>"))
    _write(root, BASE + lone, page(lone, body="<p>Alone here.</p>"))
    _write(root, BASE + "/not-a-summary-pdq", page("/n", kind="article"))
    out = tmp_path / "t"
    counts = nci.build(root, out, date_read=lambda u: "2026-11-15", log=lambda s: None)
    assert counts["not_a_summary"] == 1
    assert counts["pairs:version"] == 1 and counts["pairs:language"] == 1
    s = {r["url"]: r for r in pq.read_table(out / "nci_summaries.parquet").to_pylist()}
    assert len(s) == 4
    assert s[BASE + hp]["topic_id"] == s[BASE + pt]["topic_id"] == s[BASE + es_hp]["topic_id"]
    assert s[BASE + lone]["topic_id"] == BASE + lone
    assert all(r["credit_line"].endswith(r["url"]) for r in s.values())
    assert all("National Cancer Institute" in r["credit_line"] for r in s.values())
    assert s[BASE + es_hp]["codes"] is None and s[BASE + hp]["codes"]["you_words"] == 2
    pairs = pq.read_table(out / "nci_pairs.parquet").to_pylist()
    v = next(p for p in pairs if p["pair_kind"] == "version")
    assert (v["url_a"], v["url_b"], v["linked_from"]) == (BASE + hp, BASE + pt, "both")
    lang = next(p for p in pairs if p["pair_kind"] == "language")
    assert (lang["url_a"], lang["url_b"]) == (BASE + hp, BASE + es_hp)
    t = pq.read_table(out / "nci_text.parquet").to_pylist()
    assert {r["configuration"] for r in t} == {"nci"}
    assert all(r["credit_line"] and r["date_read"] and r["nci_updated"] for r in t)


def test_rebuild_text_by_reading_the_pages_again(tmp_path):
    root = tmp_path / "nci"
    hp = "/types/zorvan/hp/zorvan-pdq"
    first = page(hp, body=BODY)
    _write(root, BASE + hp, first)
    out = tmp_path / "t"
    nci.build(root, out, date_read=lambda u: "2026-11-15", log=lambda s: None)
    summaries = pq.read_table(out / "nci_summaries.parquet").to_pylist()
    same = nci.rebuild_text(summaries, lambda u: first)
    assert same["counts"] == {"same": 1}
    assert len(same["rows"]) == summaries[0]["n_blocks"]
    later = page(hp, body=BODY + "<p>A new line.</p>", updated="2027-01-01")
    changed = nci.rebuild_text(summaries, lambda u: later)
    assert changed["counts"] == {"changed": 1, "changed_with_new_update_date": 1}
    assert nci.rebuild_text(summaries, lambda u: None)["counts"] == {"missing": 1}
    odd = nci.rebuild_text(summaries, lambda u: page(hp, kind="article"))
    assert odd["counts"] == {"not_a_summary": 1}


def test_nci_commands_on_saved_invented_pages(tmp_path, monkeypatch, capsys):
    from plainpairs.cli import main

    monkeypatch.chdir(tmp_path)
    hp = "/types/zorvan/hp/zorvan-pdq"
    _write(tmp_path / "nci", BASE + hp, page(hp, body=BODY))
    assert main(["nci-build", "--root", "nci", "--out", "t"]) == 0
    assert '"rows:nci_summaries": 1' in capsys.readouterr().out
    assert main(["nci-text", "--tables", "t", "--saved", "nci", "--out", "r/x.parquet"]) == 0
    out = capsys.readouterr().out
    assert "saved under nci" in out and '"same": 1' in out
