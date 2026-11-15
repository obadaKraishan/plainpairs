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
