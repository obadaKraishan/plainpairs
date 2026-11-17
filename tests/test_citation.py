"""How to cite PlainPairs: the paper first, then the dataset's version, then the software.

Every place that tells a reader how to cite (the card of any version, the Kaggle description,
CITATION.cff, the README, the data card, .zenodo.json and the package links) gives the same
paper, from the constants in ``plainpairs.pack``."""

import json
import re
from pathlib import Path

from plainpairs import pack
from tests.test_pack import made  # noqa: F401  (the fixture)
from tests.test_release import built  # noqa: F401  (the fixture made needs)

PAPER = (
    "Kraishan, O. (2026). PlainPairs: A Corpus Pairing the Prescriber and Patient Texts of "
    "U.S. Prescription Medicine Labels. arXiv:2611.21160. https://arxiv.org/abs/2611.21160 "
    "(doi:10.48550/arXiv.2611.21160)"
)
FIRST = "If you use PlainPairs, please cite the paper:"
SECOND = "To name the exact data you used, also give the dataset and its version:"


def read_cff(text: str) -> dict:
    """A strict reader for the YAML that CITATION.cff uses: mappings, lists, plain or
    double-quoted scalars and folded blocks (``>-``). Anything else fails the test, so the
    file stays readable by any YAML parser (GitHub's included)."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    assert all("\t" not in ln for ln in lines), "CITATION.cff has a tab"
    pos = 0

    def indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def scalar(s: str) -> str:
        s = s.strip()
        if s.startswith('"'):
            assert len(s) > 1 and s.endswith('"') and '"' not in s[1:-1], s
            return s[1:-1]
        assert s and s[0] not in "'{[&*!|>%@`" and " #" not in s, s
        return s

    def node(at: int):
        nonlocal pos
        if not lines[pos][at:].startswith("- "):
            return mapping(at)
        items = []
        while pos < len(lines) and indent(lines[pos]) == at and lines[pos][at:].startswith("- "):
            rest = lines[pos][at + 2 :]
            if re.match(r"[A-Za-z][\w-]*:( |$)", rest):
                lines[pos] = " " * (at + 2) + rest
                items.append(mapping(at + 2))
            else:
                items.append(scalar(rest))
                pos += 1
        return items

    def mapping(at: int) -> dict:
        nonlocal pos
        out: dict = {}
        while pos < len(lines) and indent(lines[pos]) == at:
            m = re.fullmatch(r"([A-Za-z][\w-]*):(?: (.*))?", lines[pos][at:])
            assert m, f"not a key and value: {lines[pos]!r}"
            key, value = m.groups()
            assert key not in out, f"{key} twice"
            pos += 1
            if value == ">-":
                parts = []
                while pos < len(lines) and indent(lines[pos]) > at:
                    parts.append(lines[pos].strip())
                    pos += 1
                out[key] = " ".join(parts)
            elif value is None:
                assert pos < len(lines) and indent(lines[pos]) > at, f"{key} is empty"
                out[key] = node(indent(lines[pos]))
            else:
                out[key] = scalar(value)
        return out

    data = mapping(0)
    assert pos == len(lines), f"CITATION.cff: cannot read {lines[pos]!r}"
    return data


def cff() -> dict:
    return read_cff(Path("CITATION.cff").read_text(encoding="utf-8"))


def how_to_cite(text: str) -> str:
    return text.split("## How to cite\n", 1)[1].split("\n## ", 1)[0]


def flat(text: str) -> str:
    """Markdown read as words: no quote marks at line starts, autolinks as plain addresses."""
    text = re.sub(r"^> ?", "", text, flags=re.M)
    return " ".join(re.sub(r"<(https?://[^<>\s]+)>", r"\1", text).split())


def test_the_paper_constants_give_one_citation_and_one_bibtex_entry():
    assert pack.paper_citation() == PAPER
    assert pack.PAPER_URL == "https://arxiv.org/abs/2611.21160"
    assert pack.PAPER_DOI == "10.48550/arXiv.2611.21160"
    bib = pack.paper_bibtex()
    assert bib.startswith("@misc{kraishan2026plainpairs,\n") and bib.endswith("\n}")
    for field in (
        "author        = {Kraishan, Obada},",
        "eprint        = {2611.21160},",
        "archivePrefix = {arXiv},",
        "primaryClass  = {cs.CL},",
        "doi           = {10.48550/arXiv.2611.21160},",
        "url           = {https://arxiv.org/abs/2611.21160}",
        "{PlainPairs}: A Corpus Pairing the Prescriber and Patient Texts of {U.S.} Prescription",
    ):
        assert field in bib, field
    assert bib.count("{") == bib.count("}")


def test_the_card_of_any_version_cites_the_paper_first(made):  # noqa: F811
    _out, p, m = made
    for manifest in (m, {**m, "version": "0.1.1", "created": "2027-01-04"}):
        card = pack.card(manifest)
        how = how_to_cite(card)
        dataset = pack.citation(manifest["version"], manifest["created"])
        assert how.startswith(f"{FIRST}\n\n{PAPER}\n")
        assert f"```bibtex\n{pack.paper_bibtex()}\n```" in how
        assert how.index(PAPER) < how.index(SECOND) < how.index(dataset)
        assert how.index(dataset) < how.index(f"https://doi.org/{pack.SOFTWARE_DOI}")
        assert "arXiv:2611.21160" in how and "https://arxiv.org/abs/2611.21160" in how
        assert "credit lines" in how and pack.raw_tags(card) == []
    assert pack.check_pack(p) == []


def test_the_check_fails_on_a_card_without_the_paper_or_with_the_dataset_first(made):  # noqa: F811
    _out, p, m = made
    card = (p / "README.md").read_text(encoding="utf-8")
    (p / "README.md").write_text(card.replace(PAPER, "the paper"), encoding="utf-8")
    assert pack.check_pack(p) == [
        "the card does not cite the paper (its citation and BibTeX entry)"
    ]
    dataset = pack.citation(m["version"], m["created"])
    swapped = card.replace(PAPER, "@@").replace(dataset, PAPER).replace("@@", dataset)
    (p / "README.md").write_text(swapped, encoding="utf-8")
    assert pack.check_pack(p) == ["the card cites the dataset's version before the paper"]


def test_the_kaggle_description_cites_the_paper_within_kaggles_limits(made, tmp_path):  # noqa: F811
    _out, p, m = made
    k = tmp_path / "kaggle"
    meta = pack.build_kaggle(p, k)
    d = meta["description"]
    dataset = pack.citation(m["version"], m["created"])
    assert f"{FIRST} {PAPER}. To name the exact data you used" in d
    assert d.index(PAPER) < d.index(dataset) and d.endswith(pack.HF_URL)
    for field, (low, high) in pack.KAGGLE_LIMITS.items():
        assert low <= len(meta[field]) <= high, field
    assert pack.check_kaggle(k, p) == [] and pack.raw_tags(d) == []
    meta["description"] = d.replace(PAPER, "the paper")
    (k / "dataset-metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    assert pack.check_kaggle(k, p) == [
        "the Kaggle description does not cite the paper as the card does."
    ]


def test_citation_cff_parses_and_prefers_the_paper():
    c = cff()
    assert c["cff-version"] == "1.2.0" and c["type"] == "software"
    assert "cite the paper" in c["message"]
    pref = c["preferred-citation"]
    assert pref["title"] == pack.PAPER_TITLE and pref["year"] == pack.PAPER_YEAR
    assert pref["doi"] == pack.PAPER_DOI and pref["url"] == pack.PAPER_URL
    assert pref["status"] == "preprint" and pref["publisher"] == {"name": "arXiv"}
    assert pref["identifiers"][0]["value"] == f"arXiv:{pack.PAPER_ARXIV_ID}"
    assert [a["family-names"] for a in pref["authors"]] == ["Kraishan"]
    assert pref["authors"] == c["authors"]
    # The software's own DOI and identifiers stay; the dataset's version is a reference.
    assert c["doi"] == pack.SOFTWARE_DOI
    assert [i["value"] for i in c["identifiers"]] == [pack.SOFTWARE_DOI, "10.5281/zenodo.24267451"]
    (data,) = [r for r in c["references"] if r["type"] == "data"]
    assert data["title"] == pack.TITLE and data["url"] == pack.HF_URL


def test_the_readme_and_the_data_card_cite_the_paper_first():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "[![arXiv](https://img.shields.io/badge/arXiv-2611.21160-b31b1b.svg)]" in readme
    assert "(https://arxiv.org/abs/2611.21160)" in readme.split("\n\n", 2)[1]
    data_card = Path("docs/data-card.md").read_text(encoding="utf-8")
    assert "DRAFT" not in data_card
    for text in (readme, data_card):
        how = how_to_cite(text)
        words = flat(how)
        assert words.startswith(f"{FIRST} {PAPER}")
        assert f"```bibtex\n{pack.paper_bibtex()}\n```" in how
        assert words.index(PAPER) < words.index(SECOND) < words.index(pack.SOFTWARE_DOI)
        assert "credit line" in words and pack.raw_tags(how) == []
