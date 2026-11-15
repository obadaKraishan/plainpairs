"""The records PlainPairs builds. Frozen, and strict about their fields.

A :class:`LabelRow` is one label: who and what it is, the sections written for prescribers,
and the texts written for patients. Field names follow the labels' own section names, not the
source's field names; :data:`PRESCRIBER_SOURCES` and :data:`PATIENT_SOURCES` say which source
fields each one is read from.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

LabelFormat = Literal["plr", "older", "otc_drug_facts", "unknown"]

#: Prescriber sections and the source fields they come from, in order of preference. For
#: ``warnings_and_precautions`` the newer format's single section is used when present;
#: otherwise the older format's two sections are joined.
PRESCRIBER_SOURCES: dict[str, tuple[str, ...]] = {
    "boxed_warning": ("boxed_warning",),
    "indications_and_usage": ("indications_and_usage",),
    "dosage_and_administration": ("dosage_and_administration",),
    "contraindications": ("contraindications",),
    "warnings_and_precautions": ("warnings_and_cautions",),
    "adverse_reactions": ("adverse_reactions",),
    "drug_interactions": ("drug_interactions",),
    "use_in_specific_populations": ("use_in_specific_populations",),
    # Section 17 of the newer format ("Patient Counseling Information") and the older
    # format's "Information for Patients" are both stored by the source in this one field.
    # Both are written to the prescriber, so they belong on this side.
    "patient_counseling_information": ("information_for_patients",),
    "description": ("description",),
    "how_supplied_storage": ("how_supplied", "storage_and_handling"),
}
OLDER_WARNINGS = ("warnings", "precautions")

#: Texts written for patients, and their source fields.
PATIENT_SOURCES: dict[str, str] = {
    "medication_guide": "spl_medguide",
    "patient_package_insert": "spl_patient_package_insert",
    "instructions_for_use": "instructions_for_use",
    "patient_medication_information": "patient_medication_information",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Identity(_Frozen):
    id: str
    set_id: str
    version: int | None
    effective_date: dt.date | None
    #: The date as the source gives it, kept when it cannot be read as a date.
    effective_time_raw: str | None
    #: True when the source's harmonized ``openfda`` block is present and not empty. Without
    #: it there is no product type, application number or standard name.
    harmonized: bool
    product_type: str | None
    label_format: LabelFormat
    routes: tuple[str, ...] = ()
    application_numbers: tuple[str, ...] = ()
    manufacturers: tuple[str, ...] = ()
    brand_names: tuple[str, ...] = ()
    generic_names: tuple[str, ...] = ()
    pharm_classes_epc: tuple[str, ...] = ()


class PrescriberSections(_Frozen):
    boxed_warning: str | None = None
    indications_and_usage: str | None = None
    dosage_and_administration: str | None = None
    contraindications: str | None = None
    warnings_and_precautions: str | None = None
    adverse_reactions: str | None = None
    drug_interactions: str | None = None
    use_in_specific_populations: str | None = None
    patient_counseling_information: str | None = None
    description: str | None = None
    how_supplied_storage: str | None = None


class PatientTexts(_Frozen):
    medication_guide: str | None = None
    patient_package_insert: str | None = None
    instructions_for_use: str | None = None
    patient_medication_information: str | None = None

    def present(self) -> tuple[str, ...]:
        """The names of the patient texts this label has."""
        return tuple(k for k, v in self.model_dump().items() if v)


class Table(_Frozen):
    section: str
    text: str


class LabelRow(_Frozen):
    identity: Identity
    prescriber: PrescriberSections
    patient: PatientTexts
    tables: tuple[Table, ...] = ()
    #: The source fields this row was read from, so nothing is taken without a trace.
    source_fields: tuple[str, ...] = ()
