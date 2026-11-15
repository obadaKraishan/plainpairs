import json

import pytest

from plainpairs import probe
from tests.test_client import FakeResponse, make


def answer(body, status=200):
    return FakeResponse(status=status, body=json.dumps(body).encode())


TOTAL = {"meta": {"last_updated": "2026-11-13", "results": {"total": 42}}, "results": [{}]}
NOT_FOUND = {"error": {"code": "NOT_FOUND", "message": "No matches found!"}}


def test_search_helpers():
    assert probe.exists("a", "b") == "_exists_:a AND _exists_:b"
    assert probe.pattern(("a",), ("b", "c")) == "_exists_:a AND _missing_:b AND _missing_:c"


def test_total_reads_the_meta_and_saves_it(tmp_path):
    c, session, _ = make(tmp_path, [answer(TOTAL)])
    p = probe.Probe(c, tmp_path / "counts.json")
    assert p.total("all") == 42
    assert "search=" not in session.calls[0]["url"]
    saved = json.loads((tmp_path / "counts.json").read_text())
    assert saved["all"] == {"search": None, "total": 42, "last_updated": "2026-11-13"}


def test_total_of_no_match_is_zero(tmp_path):
    c, session, _ = make(tmp_path, [answer(NOT_FOUND, status=404)])
    p = probe.Probe(c, tmp_path / "counts.json")
    assert p.total("none", probe.exists("spl_medguide")) == 0
    assert "search=_exists_:spl_medguide" in session.calls[0]["url"]


def test_a_saved_answer_is_not_asked_again(tmp_path):
    (tmp_path / "counts.json").write_text(json.dumps({"all": {"search": None, "total": 7}}))
    c, session, _ = make(tmp_path, [])
    p = probe.Probe(c, tmp_path / "counts.json")
    assert p.total("all") == 7
    assert session.calls == []


def test_other_errors_are_raised_in_plain_words(tmp_path):
    bad = {"error": {"code": "BAD_REQUEST", "message": "Syntax error in search"}}
    c, _, _ = make(tmp_path, [answer(bad, status=400), FakeResponse(status=400, body=b"<html>")])
    p = probe.Probe(c, tmp_path / "counts.json")
    with pytest.raises(probe.ProbeError, match="Syntax error"):
        p.total("x", "bad:")
    with pytest.raises(probe.ProbeError, match="without JSON"):
        p.total("y", "bad:")


def test_terms_are_kept_with_their_counts(tmp_path):
    body = {
        "results": [{"term": "HUMAN PRESCRIPTION DRUG", "count": 9}, {"term": "OTC", "count": 2}]
    }
    c, session, _ = make(tmp_path, [answer(body), answer(NOT_FOUND, status=404)])
    p = probe.Probe(c, tmp_path / "counts.json")
    t = p.terms("types", "openfda.product_type.exact", probe.exists("spl_medguide"))
    assert t.terms == [("HUMAN PRESCRIPTION DRUG", 9), ("OTC", 2)]
    assert (t.distinct, t.capped) == (2, False)
    assert "count=openfda.product_type.exact&limit=1000" in session.calls[0]["url"]
    assert p.terms("empty", "set_id").terms == []
    again = probe.Probe(c, tmp_path / "counts.json").terms("types", "x")
    assert again.terms == t.terms


def test_a_full_list_of_terms_is_only_a_lower_bound():
    assert probe.Terms([(str(i), 1) for i in range(1000)]).capped


def test_daily_counts_add_up_to_years(tmp_path):
    body = {
        "results": [
            {"time": "20090601", "count": 2},
            {"time": "20091231", "count": 3},
            {"time": "20260101", "count": 1},
        ]
    }
    c, _, _ = make(tmp_path, [answer(body)])
    p = probe.Probe(c, tmp_path / "counts.json")
    assert probe.by_year(p.terms("days", "effective_time")) == {"2009": 5, "2026": 1}


def test_the_standard_plan_covers_every_combination_once():
    plan = probe.standard_plan()
    names = [name for name, *_ in plan]
    assert len(names) == len(set(names))
    assert sum(1 for n in names if n.startswith("only:")) == 31
    only_mg = dict((n, s) for n, _, _, s in plan)["only:MG"]
    assert only_mg.startswith("_exists_:spl_medguide AND _missing_:spl_patient_package_insert")


def test_run_plan_asks_each_question(tmp_path):
    plan = [("all", "total", None, None), ("t", "terms", "f.exact", "x:1")]
    c, session, _ = make(tmp_path, [answer(TOTAL), answer({"results": []})])
    p = probe.Probe(c, tmp_path / "counts.json")
    probe.run_plan(p, plan)
    probe.run_plan(p, plan)
    assert len(session.calls) == 2
    assert set(p.results) == {"all", "t"}
