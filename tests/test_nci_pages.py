"""The NCI summary list and the once-only fetch, on invented sitemaps and pages."""

import pytest

from plainpairs import client as cl
from plainpairs import nci_pages
from tests.test_client import FakeResponse, make

SITEMAP = """<urlset>
<url><loc>https://www.cancer.gov/types/zorvan/hp/zorvan-treatment-pdq</loc></url>
<url><loc>https://www.cancer.gov/types/zorvan/patient/zorvan-treatment-pdq</loc></url>
<url><loc>https://www.cancer.gov/about-cancer/coping/zorvan-hp-pdq</loc></url>
<url><loc>https://www.cancer.gov/about-cancer/coping/zorvan-pdq</loc></url>
<url><loc>https://www.cancer.gov/espanol/tipos/zorvan/pro/tratamiento-zorvan-pdq</loc></url>
<url><loc>https://www.cancer.gov/espanol/cancer/sobrellevar/zorvan-pro-pdq</loc></url>
<url><loc>https://www.cancer.gov/espanol/tipos/zorvan/paciente/tratamiento-zorvan-pdq</loc></url>
<url><loc>https://www.cancer.gov/espanol/publicaciones/pdq/proceso-editorial/el-proceso-pdq</loc></url>
<url><loc>https://www.cancer.gov/types/zorvan/hp/zorvan-treatment-pdq</loc></url>
<url><loc>https://www.cancer.gov/types/zorvan</loc></url>
<url><loc>https://example.org/other-pdq</loc></url>
</urlset>"""


def test_summary_urls_language_and_version():
    got = nci_pages.summary_urls(SITEMAP)
    assert [(g.language, g.version_guess) for g in got] == [
        ("en", "health_professional"),
        ("en", "patient"),
        ("en", "health_professional"),
        ("en", "patient"),
        ("es", "health_professional"),
        ("es", "health_professional"),
        ("es", "patient"),
    ]


def test_fetch_summaries_reads_each_page_once(tmp_path):
    urls = nci_pages.summary_urls(SITEMAP)[:3]
    c = make(tmp_path, [FakeResponse(200, b"<html>a</html>"), FakeResponse(404, b"gone")])[0]
    root = tmp_path / "nci"
    # the first page was read before: it is in the manifest and is skipped
    from plainpairs import pages

    root.mkdir()
    (root / "manifest.csv").write_text(
        ",".join(pages.MANIFEST_FIELDS) + f"\n2026,{urls[0].url},200,x,1,y\n", encoding="utf-8"
    )
    lines = []
    counts = nci_pages.fetch_summaries(c, urls, root, "2026-11-15", log=lines.append)
    assert counts == {"skipped_already_fetched": 1, "200": 1, "404": 1}
    assert nci_pages.fetched(root)[urls[2].url] == "404"
    assert any("HTTP 404" in s for s in lines)


def test_fetch_summaries_refuses_non_html_and_stops_on_403(tmp_path):
    bad = [nci_pages.SummaryUrl("https://www.cancer.gov/images/zorvan.jpg", "en", "patient")]
    c = make(tmp_path, [])[0]
    with pytest.raises(ValueError, match="not an HTML page"):
        nci_pages.fetch_summaries(c, bad, tmp_path / "nci", "2026-11-15", log=lambda s: None)
    c = make(tmp_path, [FakeResponse(403, b"no")])[0]
    urls = nci_pages.summary_urls(SITEMAP)[:1]
    with pytest.raises(cl.SourceBlocked):
        nci_pages.fetch_summaries(c, urls, tmp_path / "nci2", "2026-11-15", log=lambda s: None)
    assert nci_pages.fetched(tmp_path / "none") == {}
