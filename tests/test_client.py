import csv

import pytest
import requests

from plainpairs import client as cl

BASE = "https://api.example.org/drug/label.json"


class FakeResponse:
    def __init__(self, status=200, body=b"{}", headers=None, chunk=65536):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self._chunk = chunk
        self.closed = False

    def iter_content(self, chunk_size=65536):
        size = min(chunk_size, self._chunk)
        for i in range(0, len(self._body), size):
            yield self._body[i : i + size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def request(self, method, url, headers, timeout, stream):
        self.calls.append({"method": method, "url": url, "headers": headers, "stream": stream})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def make(tmp_path, answers, **kw):
    clock = Clock()
    session = FakeSession(answers)
    c = cl.PoliteClient(
        log=cl.UsageLog(tmp_path / "usage_log.csv"),
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        clock=lambda: "2026-11-15T00:00:00.000Z",
        **kw,
    )
    return c, session, clock


def log_rows(tmp_path):
    with (tmp_path / "usage_log.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


def test_user_agent_names_the_project_a_url_and_the_library():
    ua = cl.user_agent()
    assert ua.startswith("plainpairs/")
    assert "(https://github.com/obadaKraishan)" in ua
    assert "python-requests/" in ua
    assert "@" not in ua


def test_build_url_keeps_search_expressions_readable():
    url = cl.build_url(BASE, {"search": "_exists_:spl_medguide AND x:[1 TO 2]", "limit": 1})
    assert url == BASE + "?search=_exists_:spl_medguide%20AND%20x:[1%20TO%202]&limit=1"
    assert cl.build_url(BASE) == BASE


def test_get_json_logs_metadata_only(tmp_path):
    c, session, _ = make(tmp_path, [FakeResponse(body=b'{"meta": {"results": {"total": 3}}}')])
    data = c.get_json(BASE, {"limit": 1})
    assert data == {"meta": {"results": {"total": 3}}}
    assert session.calls[0]["headers"]["User-Agent"] == cl.user_agent()
    assert session.calls[0]["stream"] is True
    (row,) = log_rows(tmp_path)
    assert row["host"] == "api.example.org"
    assert row["path"] == "/drug/label.json"
    assert row["query"] == "limit=1"
    assert row["status"] == "200"
    assert row["bytes"] == str(len(b'{"meta": {"results": {"total": 3}}}'))
    assert list(row) == cl.LOG_FIELDS
    assert c.budget.calls == 1


def test_get_json_refuses_a_non_200_answer(tmp_path):
    c, _, _ = make(tmp_path, [FakeResponse(status=400, body=b"bad filter")])
    with pytest.raises(RuntimeError, match="HTTP 400"):
        c.get_json(BASE)


def test_requests_are_spaced(tmp_path):
    c, _, clock = make(tmp_path, [FakeResponse(), FakeResponse()], min_interval=1.5)
    c.get(BASE)
    c.get(BASE)
    assert clock.sleeps == [1.5]


def test_backs_off_on_429_and_honors_retry_after(tmp_path):
    answers = [FakeResponse(status=429, headers={"Retry-After": "7"}), FakeResponse()]
    c, _, clock = make(tmp_path, answers, min_interval=0)
    assert c.get(BASE).status == 200
    assert clock.sleeps == [7.0]
    assert [r["status"] for r in log_rows(tmp_path)] == ["429", "200"]
    assert c.budget.calls == 2


def test_gives_up_after_repeated_server_errors(tmp_path):
    answers = [FakeResponse(status=503)] * 3
    c, _, clock = make(tmp_path, answers, min_interval=0, max_retries=2, base_delay=2)
    with pytest.raises(cl.SourceBlocked, match="HTTP 503"):
        c.get(BASE)
    assert clock.sleeps == [2, 4]


def test_network_errors_are_logged_and_retried(tmp_path):
    answers = [requests.ConnectionError("down"), FakeResponse()]
    c, _, _ = make(tmp_path, answers, min_interval=0)
    assert c.get(BASE).status == 200
    assert [r["status"] for r in log_rows(tmp_path)] == ["0", "200"]


def test_network_errors_that_persist_stop_the_run(tmp_path):
    answers = [requests.Timeout("slow")] * 2
    c, _, _ = make(tmp_path, answers, min_interval=0, max_retries=1)
    with pytest.raises(cl.SourceBlocked, match="network error"):
        c.get(BASE)


def test_403_stops_at_once(tmp_path):
    c, session, _ = make(tmp_path, [FakeResponse(status=403), FakeResponse()])
    with pytest.raises(cl.SourceBlocked, match="403"):
        c.get(BASE)
    assert len(session.calls) == 1


def test_a_large_answer_is_cut_off_and_logged(tmp_path):
    body = b"x" * 300
    c, _, _ = make(tmp_path, [FakeResponse(body=body, chunk=100)], max_response_bytes=150)
    with pytest.raises(cl.ResponseTooLarge, match="Nothing was saved"):
        c.get(BASE)
    (row,) = log_rows(tmp_path)
    assert row["bytes"] == "200"


def test_a_declared_large_answer_is_not_read(tmp_path):
    big = FakeResponse(body=b"", headers={"Content-Length": "999999999"})
    c, _, _ = make(tmp_path, [big])
    with pytest.raises(cl.ResponseTooLarge, match="999,999,999"):
        c.get(BASE)
    assert big.closed


def test_head_never_reads_the_body(tmp_path):
    resp = FakeResponse(body=b"should not be read", headers={"Content-Length": "5000000000"})
    c, session, _ = make(tmp_path, [resp])
    answer = c.head(BASE + ".zip")
    assert answer.content == b""
    assert answer.headers["Content-Length"] == "5000000000"
    assert session.calls[0]["headers"]["Accept-Encoding"] == "identity"
    assert log_rows(tmp_path)[0]["bytes"] == "0"


def test_call_cap_stops_before_the_request(tmp_path):
    c, session, _ = make(tmp_path, [FakeResponse()], budget=cl.Budget(max_calls=0))
    with pytest.raises(cl.CapReached, match="call cap"):
        c.get(BASE)
    assert session.calls == []


def test_byte_cap_stops_before_the_request(tmp_path):
    budget = cl.Budget(max_bytes=10, nbytes=10)
    c, _, _ = make(tmp_path, [FakeResponse()], budget=budget)
    with pytest.raises(cl.CapReached, match="byte cap"):
        c.get(BASE)


def test_budget_from_log_counts_only_the_session(tmp_path):
    log = cl.UsageLog(tmp_path / "usage_log.csv")
    log.append("2026-11-14T23:00:00.000Z", "GET", BASE, 200, 500, 0.1)
    log.append("2026-11-15T01:00:00.000Z", "GET", BASE, 200, 700, 0.1)
    log.append("2026-11-15T02:00:00.000Z", "HEAD", BASE, 200, 0, 0.1)
    budget = cl.Budget.from_log(log.rows(), since="2026-11-15T00:00:00Z")
    assert (budget.calls, budget.nbytes) == (2, 700)


def test_usage_log_rows_of_a_missing_file_is_empty(tmp_path):
    assert cl.UsageLog(tmp_path / "none.csv").rows() == []


def test_retry_after_that_is_not_a_number_falls_back(tmp_path):
    answers = [FakeResponse(status=500, headers={"Retry-After": "soon"}), FakeResponse()]
    c, _, clock = make(tmp_path, answers, min_interval=0, base_delay=3)
    c.get(BASE)
    assert clock.sleeps == [3]


def test_default_session_is_created():
    c = cl.PoliteClient(log=cl.UsageLog("unused.csv"))
    assert isinstance(c.session, requests.Session)


def test_download_streams_to_disk_and_logs_the_size(tmp_path):
    body = b"z" * 2500
    resp = FakeResponse(body=body, headers={"Content-Length": "2500"}, chunk=1000)
    c, session, _ = make(tmp_path, [resp])
    digest, size = c.download(BASE + ".zip", tmp_path / "raw" / "part.zip", max_bytes=10_000)
    assert size == 2500
    assert (tmp_path / "raw" / "part.zip").read_bytes() == body
    assert len(digest) == 64
    assert session.calls[0]["headers"]["Accept-Encoding"] == "identity"
    (row,) = log_rows(tmp_path)
    assert (row["status"], row["bytes"]) == ("200", "2500")
    assert c.budget.nbytes == 2500
    assert resp.closed


def test_download_refuses_a_declared_size_over_its_limit(tmp_path):
    resp = FakeResponse(body=b"z" * 50, headers={"Content-Length": "5000"})
    c, _, _ = make(tmp_path, [resp])
    with pytest.raises(cl.ResponseTooLarge, match="Nothing was downloaded"):
        c.download(BASE + ".zip", tmp_path / "part.zip", max_bytes=1000)
    assert not (tmp_path / "part.zip").exists()
    assert log_rows(tmp_path)[0]["bytes"] == "0"


def test_download_stops_a_stream_that_passes_its_limit(tmp_path):
    resp = FakeResponse(body=b"z" * 3000, chunk=1000)
    c, _, _ = make(tmp_path, [resp])
    with pytest.raises(cl.ResponseTooLarge, match="nothing was kept"):
        c.download(BASE + ".zip", tmp_path / "part.zip", max_bytes=1500)
    assert not (tmp_path / "part.zip").exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_download_respects_what_is_left_of_the_byte_cap(tmp_path):
    resp = FakeResponse(body=b"z" * 50, headers={"Content-Length": "800"})
    c, _, _ = make(tmp_path, [resp], budget=cl.Budget(max_bytes=1000, nbytes=500))
    with pytest.raises(cl.ResponseTooLarge, match="limit of 500"):
        c.download(BASE + ".zip", tmp_path / "part.zip", max_bytes=10_000)


def test_download_of_a_missing_file_saves_nothing(tmp_path):
    c, _, _ = make(tmp_path, [FakeResponse(status=404, body=b"no")])
    with pytest.raises(cl.SourceBlocked, match="HTTP 404"):
        c.download(BASE + ".zip", tmp_path / "part.zip", max_bytes=1000)
    assert not (tmp_path / "part.zip").exists()
    assert log_rows(tmp_path)[0]["status"] == "404"


def test_download_network_errors_are_logged_and_not_retried(tmp_path):
    c, session, _ = make(tmp_path, [requests.ConnectionError("down"), FakeResponse()])
    with pytest.raises(cl.SourceBlocked, match="could not be reached"):
        c.download(BASE + ".zip", tmp_path / "part.zip", max_bytes=1000)
    assert len(session.calls) == 1
    assert log_rows(tmp_path)[0]["status"] == "0"


def test_download_cut_off_mid_stream_keeps_nothing(tmp_path):
    class Broken(FakeResponse):
        def iter_content(self, chunk_size=65536):
            yield b"ab"
            raise requests.ConnectionError("cut")

    c, _, _ = make(tmp_path, [Broken()])
    with pytest.raises(cl.SourceBlocked, match="cut off"):
        c.download(BASE + ".zip", tmp_path / "part.zip", max_bytes=1000)
    assert not (tmp_path / "part.zip").exists()
