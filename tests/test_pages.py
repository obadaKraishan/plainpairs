import csv

from plainpairs import client as cl
from plainpairs import pages
from tests.test_client import FakeResponse, make

PAGE = """<!DOCTYPE html><html><head><title>T</title><style>p {color: red}</style>
<script>var x = "hidden";</script></head><body><nav>Menu</nav>
<h1>Terms&nbsp;of Service</h1><p>Data are offered
   \u201cas is\u201d &amp; without warranty.</p><ul><li>One</li><li>Two</li></ul></body></html>"""


def test_html_to_text_keeps_blocks_and_drops_scripts():
    text = pages.html_to_text(PAGE)
    assert "hidden" not in text
    assert "color" not in text
    assert text.splitlines() == [
        "T",
        "Menu",
        "Terms of Service",
        "Data are offered \u201cas is\u201d & without warranty.",
        "One",
        "Two",
    ]


def test_normalize_straightens_quotes_and_spaces():
    assert pages.normalize("\u201cas  is\u201d \u2014 it\u2019s\n ok") == '"as is" - it\'s ok'


def test_page_path_is_made_from_the_url(tmp_path):
    assert pages.page_path(tmp_path, "2026-11-15", "https://open.example.gov/terms/") == (
        tmp_path / "2026-11-15" / "open.example.gov" / "terms.html"
    )
    assert pages.page_path(tmp_path, "d", "https://x.gov/").name == "index.html"
    assert pages.page_path(tmp_path, "d", "https://x.gov/robots.txt").name == "robots.txt"
    assert pages.page_path(tmp_path, "d", "https://x.gov/a?b=1").name == "a__b_1.html"


def test_fetch_page_saves_the_page_and_a_manifest_line(tmp_path):
    c, _, _ = make(tmp_path, [FakeResponse(body=PAGE.encode())])
    root = tmp_path / "pages"
    saved = pages.fetch_page(c, "https://open.example.gov/terms/", root, "2026-11-15")
    assert saved.status == 200
    assert saved.path.read_bytes() == PAGE.encode()
    with (root / "manifest.csv").open(newline="") as fh:
        (row,) = list(csv.DictReader(fh))
    assert row["path"] == "2026-11-15/open.example.gov/terms.html"
    assert row["sha256"] == saved.sha256
    assert pages.latest_pages(root) == {"https://open.example.gov/terms/": saved.path}


def test_a_page_that_is_not_200_is_kept_under_its_status_but_never_quoted(tmp_path):
    c, _, _ = make(tmp_path, [FakeResponse(status=404, body=b"gone")])
    root = tmp_path / "pages"
    saved = pages.fetch_page(c, "https://x.gov/old", root, "d")
    assert saved.path.name == "old.html.http404"
    assert pages.latest_pages(root) == {}
    assert pages.latest_pages(tmp_path / "none") == {}


def test_check_quotes_finds_quotes_word_for_word(tmp_path):
    c, _, _ = make(tmp_path, [FakeResponse(body=PAGE.encode())], budget=cl.Budget())
    root = tmp_path / "pages"
    pages.fetch_page(c, "https://open.example.gov/terms/", root, "d")
    quotes = tmp_path / "quotes.csv"
    with quotes.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["url", "quote"])
        w.writerow(["https://open.example.gov/terms/", 'Data are offered "as is" & without'])
        w.writerow(["https://open.example.gov/terms/", "Data are offered as it is"])
        w.writerow(["https://other.gov/", "anything"])
    found = [(r.found, r.reason) for r in pages.check_quotes(quotes, root)]
    assert found == [(True, ""), (False, "not on the page"), (False, "no saved copy of this page")]


def test_page_text_reads_plain_files_as_they_are(tmp_path):
    f = tmp_path / "robots.txt"
    f.write_text("User-agent: *\nDisallow: /a\n")
    assert pages.page_text(f) == "User-agent: *\nDisallow: /a\n"


def test_the_same_page_fetched_twice_in_a_day_keeps_both_copies(tmp_path):
    c, _, _ = make(tmp_path, [FakeResponse(body=b"one"), FakeResponse(body=b"two")])
    root = tmp_path / "pages"
    a = pages.fetch_page(c, "https://x.gov/download.json", root, "d")
    b = pages.fetch_page(c, "https://x.gov/download.json", root, "d")
    assert (a.path.name, b.path.name) == ("download.json", "download.2.json")
    assert pages.latest_pages(root)["https://x.gov/download.json"].read_bytes() == b"two"
