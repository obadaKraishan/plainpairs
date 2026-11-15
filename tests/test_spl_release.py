import hashlib
import io
import zipfile
from collections import Counter

import pytest
import requests

from plainpairs import client as cl
from plainpairs import durable, spl_release

URL = "https://dailymed-data.nlm.nih.gov/public-release-files/dm_spl_release_human_rx_part1.zip"


class Resp:
    def __init__(self, status=200, body=b"", headers=None, cut_after=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self._cut = cut_after
        self.closed = False

    def iter_content(self, chunk_size=1 << 20):
        sent = 0
        for i in range(0, len(self._body), 4):
            if self._cut is not None and sent >= self._cut:
                raise requests.exceptions.ChunkedEncodingError("cut off")
            piece = self._body[i : i + 4]
            sent += len(piece)
            yield piece

    def close(self):
        self.closed = True


class Session:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def request(self, method, url, headers, timeout, stream):
        self.calls.append(dict(headers))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def make(tmp_path, answers, **kw):
    t = {"now": 0.0}

    def sleep(s):
        t["now"] += s

    return cl.PoliteClient(
        log=cl.UsageLog(tmp_path / "log.csv"),
        session=Session(answers),
        sleep=sleep,
        monotonic=lambda: t["now"],
        clock=lambda: "2026-11-15T00:00:00.000Z",
        **kw,
    )


BODY = b"invented archive bytes, not a real file" * 3


def md5(b):
    return hashlib.md5(b).hexdigest()


def test_resumable_download_whole(tmp_path):
    c = make(tmp_path, [Resp(200, BODY, {"Content-Length": str(len(BODY))})])
    dest = tmp_path / "out" / "p.zip"
    got_md5, sha, size, retries = c.download_resumable(URL, dest, 10_000, expected_md5=md5(BODY))
    assert dest.read_bytes() == BODY
    assert (got_md5, size, retries) == (md5(BODY), len(BODY), 0)
    assert sha == hashlib.sha256(BODY).hexdigest()
    assert not (dest.stat().st_mode & 0o222)
    assert not dest.with_name(".p.zip.partial").exists()
    assert "Range" not in c.session.calls[0]


def test_resumable_download_resumes_after_cut(tmp_path):
    n = len(BODY)
    first = Resp(200, BODY, {"Content-Length": str(n)}, cut_after=40)
    rest = BODY[40:]
    second = Resp(
        206, rest, {"Content-Length": str(len(rest)), "Content-Range": f"bytes 40-{n - 1}/{n}"}
    )
    c = make(tmp_path, [first, second])
    dest = tmp_path / "p.zip"
    lines = []
    _, _, size, retries = c.download_resumable(
        URL, dest, 10_000, expected_md5=md5(BODY), progress=lines.append
    )
    assert dest.read_bytes() == BODY
    assert (size, retries) == (n, 1)
    assert c.session.calls[1]["Range"] == "bytes=40-"
    assert c.budget.calls == 2
    assert any("cut off" in s for s in lines)


def test_resumable_download_short_stream_counts_as_cut(tmp_path):
    n = len(BODY)
    first = Resp(200, BODY[:10], {"Content-Length": str(n)})
    second = Resp(206, BODY[10:], {"Content-Range": f"bytes 10-{n - 1}/{n}"})
    c = make(tmp_path, [first, second])
    dest = tmp_path / "p.zip"
    c.download_resumable(URL, dest, 10_000)
    assert dest.read_bytes() == BODY


def test_resumable_download_restarts_when_range_ignored(tmp_path):
    n = len(BODY)
    first = Resp(200, BODY, {"Content-Length": str(n)}, cut_after=20)
    second = Resp(200, BODY, {"Content-Length": str(n)})
    c = make(tmp_path, [first, second])
    dest = tmp_path / "p.zip"
    c.download_resumable(URL, dest, 10_000, expected_md5=md5(BODY))
    assert dest.read_bytes() == BODY


def test_resumable_download_retries_5xx_and_network_errors(tmp_path):
    c = make(tmp_path, [Resp(503), requests.ConnectionError("down"), Resp(200, BODY)])
    dest = tmp_path / "p.zip"
    _, _, _, retries = c.download_resumable(URL, dest, 10_000)
    assert retries == 2
    assert dest.read_bytes() == BODY


def test_resumable_download_md5_mismatch_keeps_partial(tmp_path):
    c = make(tmp_path, [Resp(200, BODY)])
    dest = tmp_path / "p.zip"
    with pytest.raises(durable.WriteCheckFailed, match="MD5"):
        c.download_resumable(URL, dest, 10_000, expected_md5="0" * 32)
    assert not dest.exists()
    assert dest.with_name(".p.zip.partial").read_bytes() == BODY


def test_resumable_download_stops_on_403_and_on_size(tmp_path):
    c = make(tmp_path, [Resp(403)])
    with pytest.raises(cl.SourceBlocked):
        c.download_resumable(URL, tmp_path / "a.zip", 10_000)
    c = make(tmp_path, [Resp(200, BODY, {"Content-Length": "99999"})])
    with pytest.raises(cl.ResponseTooLarge):
        c.download_resumable(URL, tmp_path / "b.zip", 10_000)
    c = make(tmp_path, [Resp(200, BODY)])
    with pytest.raises(cl.ResponseTooLarge):
        c.download_resumable(URL, tmp_path / "c.zip", 10)


def test_resumable_download_bad_resume_point_and_existing_file(tmp_path):
    dest = tmp_path / "p.zip"
    dest.with_name(".p.zip.partial").write_bytes(BODY[:8])
    c = make(tmp_path, [Resp(206, BODY, {"Content-Range": "bytes 0-9/10"})])
    with pytest.raises(cl.SourceBlocked, match="resumed"):
        c.download_resumable(URL, dest, 10_000)
    dest.write_bytes(b"x")
    with pytest.raises(FileExistsError):
        c.download_resumable(URL, dest, 10_000)


def test_resumable_download_gives_up(tmp_path):
    c = make(tmp_path, [Resp(500)] * 5)
    with pytest.raises(cl.SourceBlocked, match="kept failing"):
        c.download_resumable(URL, tmp_path / "p.zip", 10_000)


def test_resumable_download_resumes_a_partial_from_an_earlier_run(tmp_path):
    n = len(BODY)
    dest = tmp_path / "p.zip"
    dest.with_name(".p.zip.partial").write_bytes(BODY[:30])
    c = make(tmp_path, [Resp(206, BODY[30:], {"Content-Range": f"bytes 30-{n - 1}/{n}"})])
    c.download_resumable(URL, dest, 10_000, expected_md5=md5(BODY))
    assert dest.read_bytes() == BODY


def page(parts, extra_link=True):
    rows = []
    for n, files, size, h, day in parts:
        name = f"dm_spl_release_human_rx_part{n}.zip"
        link = f'<a href="{spl_release.FILE_HOST}{name}">HTTPS</a>' if extra_link else "HTTPS"
        rows.append(
            f"<li><b>{name}</b> [ {link} / <a href='ftp://x/{name}'>FTP</a> ]"
            f"<br>Number of files: {files}<br>File size: {size}<br>MD5 checksum: {h}"
            f"<br>Last Modified: {day}</li>"
        )
    return "<html><body><ul>" + "".join(rows) + "</ul></body></html>"


PARTS = [
    (1, "14,989", "3.00GB", "a" * 32, "Nov 13, 2026"),
    (2, "4,709", "1.83GB", "b" * 32, "Nov 13, 2026"),
]


def test_parse_parts_reads_the_list():
    found = spl_release.parse_parts(page(PARTS))
    assert [p.number for p in found] == [1, 2]
    assert found[0].files == 14989
    assert found[0].url.endswith("part1.zip")
    assert found[1].size_bytes_upper == int(1.83 * 2**30)
    assert spl_release.release_date(found) == "2026-11-13"
    assert spl_release.check_total(found) == 3 * 2**30 + int(1.83 * 2**30)


def test_parse_parts_refuses_odd_pages():
    with pytest.raises(spl_release.ReleaseError, match="links"):
        spl_release.parse_parts(page(PARTS, extra_link=False))
    with pytest.raises(spl_release.ReleaseError, match="No human"):
        spl_release.parse_parts("<html>nothing here</html>")
    with pytest.raises(spl_release.ReleaseError, match="not 1 to"):
        spl_release.parse_parts(page([PARTS[1]]))
    mixed = [PARTS[0], (2, "1", "1.00MB", "c" * 32, "Nov 14, 2026")]
    with pytest.raises(spl_release.ReleaseError, match="different days"):
        spl_release.release_date(spl_release.parse_parts(page(mixed)))
    big = [(1, "1", "25.00GB", "d" * 32, "Nov 13, 2026")]
    with pytest.raises(spl_release.ReleaseError, match="stop line"):
        spl_release.check_total(spl_release.parse_parts(page(big)))


def test_fetch_parts_downloads_then_skips(tmp_path):
    body = b"invented part"
    parts = [
        spl_release.ReleasePart(
            1, "dm_spl_release_human_rx_part1.zip", URL, 1, "1.00KB", md5(body), "2026-11-13"
        )
    ]
    c = make(tmp_path, [Resp(200, body)])
    rows = spl_release.fetch_parts(c, parts, tmp_path / "rel", clock=c.clock, log=lambda s: None)
    assert rows[0]["md5"] == md5(body)
    assert rows[0]["bytes"] == str(len(body))
    c2 = make(tmp_path, [])
    again = spl_release.fetch_parts(c2, parts, tmp_path / "rel", clock=c2.clock, log=lambda s: None)
    assert again == rows
    assert c2.budget.calls == 0


def test_fetch_parts_refuses_unrecorded_or_changed_files(tmp_path):
    body = b"invented part"
    part = spl_release.ReleasePart(
        1, "dm_spl_release_human_rx_part1.zip", URL, 1, "1.00KB", md5(body), "2026-11-13"
    )
    root = tmp_path / "rel"
    (root / "2026-11-13").mkdir(parents=True)
    (root / "2026-11-13" / part.filename).write_bytes(body)
    c = make(tmp_path, [])
    with pytest.raises(spl_release.ReleaseError, match="not in the manifest"):
        spl_release.fetch_parts(c, [part], root, clock=c.clock, log=lambda s: None)
    spl_release._append(
        spl_release.manifest_path(root, "2026-11-13"), {"file": part.filename, "bytes": 999}
    )
    with pytest.raises(spl_release.ReleaseError, match="does not match"):
        spl_release.fetch_parts(c, [part], root, clock=c.clock, log=lambda s: None)


def inner_zip(xml_name, xml, others=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(xml_name, xml)
        for name, data in others:
            z.writestr(name, data)
    return buf.getvalue()


def test_iter_documents_reads_only_xml(tmp_path):
    part = tmp_path / "part.zip"
    with zipfile.ZipFile(part, "w") as z:
        z.writestr(
            "prescription/20261101_aaaa.zip",
            inner_zip("doc1.xml", b"<document/>", [("img1.jpg", b"\xff\xd8 not read")]),
        )
        z.writestr("prescription/20261102_bbbb.zip", inner_zip("doc2.xml", b"<document/>"))
        z.writestr("prescription/broken.zip", b"not a zip")
        z.writestr("readme.txt", b"invented")
    counts = Counter()
    docs = list(spl_release.iter_documents(part, counts))
    assert [d.xml_name for d in docs] == ["doc1.xml", "doc2.xml"]
    assert docs[0].member == "prescription/20261101_aaaa.zip"
    assert counts["inner_zips"] == 3
    assert counts["inner_not_zip"] == 1
    assert counts["other:jpg"] == 1
    assert counts["outer_other:txt"] == 1
    assert counts["xml_files"] == 2
