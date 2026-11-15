"""Invented labels for the tests. Every name and every sentence here is made up."""

PLR_WITH_GUIDE = {
    "id": "doc-0001",
    "set_id": "set-aaaa",
    "version": "7",
    "effective_time": "20260301",
    "openfda": {
        "product_type": ["HUMAN PRESCRIPTION DRUG"],
        "route": ["ORAL"],
        "application_number": ["NDA000001"],
        "manufacturer_name": ["Example Pharma Inc."],
        "brand_name": ["ZORVAN"],
        "generic_name": ["ZORVANIDE"],
        "pharm_class_epc": ["Made-up Blocker [EPC]"],
    },
    "boxed_warning": ["WARNING: SLEEPINESS See full prescribing information."],
    "indications_and_usage": ["1 INDICATIONS AND USAGE ZORVAN is indicated for testing."],
    "dosage_and_administration": ["2 DOSAGE AND ADMINISTRATION Take 1 tablet daily."],
    "contraindications": ["4 CONTRAINDICATIONS Known allergy to zorvanide."],
    "warnings_and_cautions": ["5 WARNINGS AND PRECAUTIONS 5.1 Sleepiness Advise caution."],
    "adverse_reactions": ["6 ADVERSE REACTIONS The most common reaction was headache."],
    "adverse_reactions_table": [
        "<table><tr><th>Reaction</th><th>ZORVAN</th></tr><tr><td>Headache</td><td>2%</td></tr></table>"
    ],
    "drug_interactions": ["7 DRUG INTERACTIONS None known."],
    "use_in_specific_populations": ["8 USE IN SPECIFIC POPULATIONS 8.1 Pregnancy No data."],
    "information_for_patients": ["17 PATIENT COUNSELING INFORMATION Advise the patient to read."],
    "description": ["11 DESCRIPTION ZORVAN tablets contain zorvanide."],
    "how_supplied": ["16 HOW SUPPLIED Bottles of 30."],
    "storage_and_handling": ["Store at room temperature."],
    "spl_medguide": [
        "MEDICATION GUIDE ZORVAN (zor-van) tablets What is the most important information I "
        "should know about ZORVAN? ZORVAN may make you sleepy. What is ZORVAN? ZORVAN is a "
        "made-up medicine. How should I take ZORVAN? Take 1 tablet each day."
    ],
    "package_label_principal_display_panel": ["PRINCIPAL DISPLAY PANEL"],
}

OLDER_WITH_INSERT = {
    "id": "doc-0002",
    "set_id": "set-bbbb",
    "version": "2",
    "effective_time": "20111015",
    "openfda": {},
    "indications_and_usage": ["INDICATIONS AND USAGE For testing only."],
    "warnings": ["WARNINGS Do not use for anything real."],
    "precautions": ["PRECAUTIONS General: none."],
    "information_for_patients": ["Information for Patients Patients should be told this."],
    "spl_patient_package_insert": ["PATIENT INFORMATION What is EXAMPLA? A made-up cream."],
}

OTC_DRUG_FACTS = {
    "id": "doc-0003",
    "set_id": "set-cccc",
    "version": "1",
    "effective_time": "20250505",
    "openfda": {"product_type": ["HUMAN OTC DRUG"]},
    "purpose": ["Purpose Made-up reliever"],
    "warnings": ["Warnings For external use only"],
    "instructions_for_use": ["Directions apply a thin layer"],
}

#: A label with almost nothing: no openfda block, no sections, a broken date and version.
MISSING_SECTIONS = {
    "id": "doc-0004",
    "set_id": "set-dddd",
    "version": "",
    "effective_time": "20261399",
    "spl_unclassified_section": ["Some text the source could not classify."],
}
