"""Counts the label API can answer without downloading anything.

Two kinds of question:

- a **total**: how many labels match a search (``meta.results.total`` of a ``limit=1`` query);
- **terms**: the values of one field among the labels that match a search, with a count for
  each (``count=<field>``). The API returns at most 1,000 terms, so a list of 1,000 is a lower
  bound on the number of distinct values, and :class:`Terms` says so.

A search that matches nothing answers HTTP 404 with the code ``NOT_FOUND``; that is a count of
0, not an error. Every answer is saved at once to a JSON file, so a run that stops can be
started again and skips what it already has.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plainpairs import durable
from plainpairs.client import PoliteClient

LABEL_URL = "https://api.fda.gov/drug/label.json"
MAX_TERMS = 1000

#: The fields that hold a text written for patients, or named as if they do.
PATIENT_FIELDS = (
    "spl_medguide",
    "spl_patient_package_insert",
    "instructions_for_use",
    "information_for_patients",
    "patient_medication_information",
)


class ProbeError(RuntimeError):
    """The API answered something other than a count."""


@dataclass(frozen=True)
class Terms:
    terms: list[tuple[str, int]]

    @property
    def distinct(self) -> int:
        return len(self.terms)

    @property
    def capped(self) -> bool:
        """True when the API's limit was reached, so ``distinct`` is only a lower bound."""
        return len(self.terms) >= MAX_TERMS


def exists(*fields: str) -> str:
    return " AND ".join(f"_exists_:{f}" for f in fields)


def pattern(present: tuple[str, ...], absent: tuple[str, ...]) -> str:
    """A search for labels that have every field in ``present`` and none in ``absent``."""
    parts = [f"_exists_:{f}" for f in present] + [f"_missing_:{f}" for f in absent]
    return " AND ".join(parts)


class Probe:
    """Runs counts through the polite client and keeps every answer in ``store``."""

    def __init__(self, client: PoliteClient, store: Path, url: str = LABEL_URL) -> None:
        self.client = client
        self.store = Path(store)
        self.url = url
        self.results: dict[str, Any] = {}
        if self.store.exists():
            self.results = json.loads(self.store.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store.with_name(self.store.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self.results, fh, indent=1, sort_keys=True)
            durable.flush_file(fh)
        tmp.replace(self.store)

    def _ask(self, params: dict[str, Any]) -> tuple[int, Any]:
        resp = self.client.get(self.url, params)
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProbeError(f"{resp.url} answered HTTP {resp.status} without JSON.") from exc
        if resp.status == 404 and body.get("error", {}).get("code") == "NOT_FOUND":
            return 404, None
        if resp.status != 200:
            message = body.get("error", {}).get("message", "no message")
            raise ProbeError(f"{resp.url} answered HTTP {resp.status}: {message}")
        return 200, body

    def total(self, name: str, search: str | None = None) -> int:
        """How many labels match ``search`` (all labels when it is None)."""
        if name in self.results:
            return int(self.results[name]["total"])
        params: dict[str, Any] = {"limit": 1}
        if search:
            params = {"search": search, "limit": 1}
        status, body = self._ask(params)
        total = 0 if status == 404 else int(body["meta"]["results"]["total"])
        entry: dict[str, Any] = {"search": search, "total": total}
        if body is not None and "last_updated" in body.get("meta", {}):
            entry["last_updated"] = body["meta"]["last_updated"]
        self.results[name] = entry
        self._save()
        return total

    def terms(self, name: str, field: str, search: str | None = None) -> Terms:
        """The values of ``field`` among the labels that match ``search``, most common first."""
        if name not in self.results:
            params: dict[str, Any] = {"count": field, "limit": MAX_TERMS}
            if search:
                params = {"search": search, "count": field, "limit": MAX_TERMS}
            status, body = self._ask(params)
            rows = [] if status == 404 else body.get("results", [])
            terms = [(str(r.get("term", r.get("time"))), int(r["count"])) for r in rows]
            self.results[name] = {"search": search, "count": field, "terms": terms}
            self._save()
        return Terms([(t, n) for t, n in self.results[name]["terms"]])


def by_year(terms: Terms) -> dict[str, int]:
    """Add up daily counts (``YYYYMMDD`` terms) into years."""
    years: dict[str, int] = {}
    for day, n in terms.terms:
        years[day[:4]] = years.get(day[:4], 0) + n
    return dict(sorted(years.items()))


MG = "spl_medguide"
PPI = "spl_patient_package_insert"
MG_OR_PPI = f"(_exists_:{MG} OR _exists_:{PPI})"
SHORT = {
    "spl_medguide": "MG",
    "spl_patient_package_insert": "PPI",
    "instructions_for_use": "IFU",
    "information_for_patients": "IFP",
    "patient_medication_information": "PMI",
}


def standard_plan() -> list[tuple[str, str, str | None, str | None]]:
    """The S1 counts: (name, kind, field to count or None, search or None)."""
    plan: list[tuple[str, str, str | None, str | None]] = [("all", "total", None, None)]
    for f in PATIENT_FIELDS:
        plan.append((f"has:{SHORT[f]}", "total", None, exists(f)))
    plan += [
        ("has:MG|PPI", "total", None, MG_OR_PPI),
        ("has:MG&PPI", "total", None, exists(MG, PPI)),
        ("has:boxed_warning", "total", None, exists("boxed_warning")),
        ("has:boxed_warning&(MG|PPI)", "total", None, f"_exists_:boxed_warning AND {MG_OR_PPI}"),
        (
            "has:warnings_and_cautions&(MG|PPI)",
            "total",
            None,
            f"_exists_:warnings_and_cautions AND {MG_OR_PPI}",
        ),
        ("has:warnings&(MG|PPI)", "total", None, f"_exists_:warnings AND {MG_OR_PPI}"),
        ("missing:openfda.product_type", "total", None, "_missing_:openfda.product_type"),
        (
            "IFP:phrase:patient counseling information",
            "total",
            None,
            'information_for_patients:"patient counseling information"',
        ),
        (
            "unclassified:phrase:medication guide&!MG",
            "total",
            None,
            f'spl_unclassified_section:"medication guide" AND _missing_:{MG}',
        ),
        (
            "IFP:phrase:medication guide&!MG",
            "total",
            None,
            f'information_for_patients:"medication guide" AND _missing_:{MG}',
        ),
    ]
    # Every combination of the five patient fields: present ones and absent ones.
    n = len(PATIENT_FIELDS)
    for mask in range(1, 2**n):
        present = tuple(f for i, f in enumerate(PATIENT_FIELDS) if mask >> i & 1)
        absent = tuple(f for i, f in enumerate(PATIENT_FIELDS) if not mask >> i & 1)
        name = "only:" + "+".join(SHORT[f] for f in present)
        plan.append((name, "total", None, pattern(present, absent)))
    plan.append(("types:all", "terms", "openfda.product_type.exact", None))
    for f in PATIENT_FIELDS:
        plan.append((f"types:{SHORT[f]}", "terms", "openfda.product_type.exact", exists(f)))
    plan.append(("types:MG|PPI", "terms", "openfda.product_type.exact", MG_OR_PPI))
    for f in (MG, PPI, "instructions_for_use", "patient_medication_information"):
        plan.append((f"generic:{SHORT[f]}", "terms", "openfda.generic_name.exact", exists(f)))
    plan += [
        ("generic:MG|PPI", "terms", "openfda.generic_name.exact", MG_OR_PPI),
        ("brand:MG|PPI", "terms", "openfda.brand_name.exact", MG_OR_PPI),
        ("set_id:MG|PPI", "terms", "set_id.exact", MG_OR_PPI),
        ("application:MG|PPI", "terms", "openfda.application_number.exact", MG_OR_PPI),
        ("manufacturer:MG|PPI", "terms", "openfda.manufacturer_name.exact", MG_OR_PPI),
        ("route:MG|PPI", "terms", "openfda.route.exact", MG_OR_PPI),
        (
            "manufacturer:PMI",
            "terms",
            "openfda.manufacturer_name.exact",
            exists("patient_medication_information"),
        ),
        ("days:all", "terms", "effective_time", None),
        ("days:MG|PPI", "terms", "effective_time", MG_OR_PPI),
        ("days:PMI", "terms", "effective_time", exists("patient_medication_information")),
    ]
    return plan


def run_plan(p: Probe, plan: list[tuple[str, str, str | None, str | None]]) -> None:
    """Ask every question in ``plan`` that ``p`` has no answer for yet."""
    for name, kind, field, search in plan:
        if kind == "total":
            p.total(name, search)
        else:
            assert field is not None
            p.terms(name, field, search)
