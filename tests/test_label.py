import datetime as dt

import pytest
from pydantic import ValidationError

from plainpairs import label
from plainpairs.schema import LabelRow
from tests.label_samples import MISSING_SECTIONS, OLDER_WITH_INSERT, OTC_DRUG_FACTS, PLR_WITH_GUIDE


def test_a_newer_format_label_with_a_guide():
    row = label.parse_label(PLR_WITH_GUIDE)
    ident = row.identity
    assert (ident.set_id, ident.version, ident.effective_date) == (
        "set-aaaa",
        7,
        dt.date(2026, 3, 1),
    )
    assert ident.harmonized and ident.product_type == "HUMAN PRESCRIPTION DRUG"
    assert ident.label_format == "plr"
    assert ident.application_numbers == ("NDA000001",)
    assert ident.pharm_classes_epc == ("Made-up Blocker [EPC]",)
    p = row.prescriber
    assert p.warnings_and_precautions.startswith("5 WARNINGS AND PRECAUTIONS")
    assert p.patient_counseling_information.startswith("17 PATIENT COUNSELING INFORMATION")
    assert p.how_supplied_storage == "16 HOW SUPPLIED Bottles of 30.\n\nStore at room temperature."
    assert row.patient.medication_guide.startswith("MEDICATION GUIDE ZORVAN")
    assert row.patient.present() == ("medication_guide",)
    assert [(t.section, t.text) for t in row.tables] == [
        ("adverse_reactions", "Reaction | ZORVAN\nHeadache | 2%")
    ]
    assert "package_label_principal_display_panel" not in row.source_fields
    assert "adverse_reactions_table" in row.source_fields


def test_an_older_format_label_joins_warnings_and_precautions():
    row = label.parse_label(OLDER_WITH_INSERT)
    assert row.identity.label_format == "older"
    assert not row.identity.harmonized and row.identity.product_type is None
    assert row.prescriber.warnings_and_precautions == (
        "WARNINGS Do not use for anything real.\n\nPRECAUTIONS General: none."
    )
    assert row.prescriber.use_in_specific_populations is None
    assert row.patient.present() == ("patient_package_insert",)


def test_drug_facts_warnings_are_not_read_as_prescriber_warnings():
    row = label.parse_label(OTC_DRUG_FACTS)
    assert row.identity.label_format == "otc_drug_facts"
    assert row.prescriber.warnings_and_precautions is None
    assert row.patient.instructions_for_use == "Directions apply a thin layer"


def test_a_label_with_missing_sections_parses_to_empty_fields():
    row = label.parse_label(MISSING_SECTIONS)
    assert row.identity.version is None
    assert row.identity.effective_date is None
    assert row.identity.effective_time_raw == "20261399"
    assert row.identity.label_format == "unknown"
    assert all(v is None for v in row.prescriber.model_dump().values())
    assert row.patient.present() == ()
    assert row.tables == () and row.source_fields == ()


def test_records_without_identity_or_with_odd_fields_are_refused():
    with pytest.raises(label.LabelError, match="no id or no set_id"):
        label.parse_label({"id": "x"})
    with pytest.raises(label.LabelError, match="is not text"):
        label.parse_label({"id": "x", "set_id": "y", "boxed_warning": [1, 2]})


def test_a_single_string_field_is_read_too():
    row = label.parse_label({"id": "x", "set_id": "y", "boxed_warning": "WARNING: TEST"})
    assert row.prescriber.boxed_warning == "WARNING: TEST"


def test_dates_and_versions_that_cannot_be_read_become_none():
    assert label._date("2026-03-01") is None
    assert label._date(None) is None
    assert label._version(None) is None


def test_rows_are_frozen_and_strict():
    row = label.parse_label(PLR_WITH_GUIDE)
    with pytest.raises(ValidationError):
        row.identity = row.identity
    data = row.model_dump()
    data["unexpected"] = 1
    with pytest.raises(ValidationError):
        LabelRow.model_validate(data)


def test_iter_rows_reads_a_part(tmp_path):
    import json
    import zipfile

    z = tmp_path / "p.json.zip"
    with zipfile.ZipFile(z, "w") as zf:
        body = {"meta": {}, "results": [PLR_WITH_GUIDE, OLDER_WITH_INSERT, MISSING_SECTIONS]}
        zf.writestr("drug-label-0001-of-0001.json", json.dumps(body))
    assert [r.identity.set_id for r in label.iter_rows(z)] == ["set-aaaa", "set-bbbb", "set-dddd"]
