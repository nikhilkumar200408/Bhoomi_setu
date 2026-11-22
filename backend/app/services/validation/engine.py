"""
Validation Engine.

Runs explainable, rule-based domain checks over an extracted land record.
Every result carries: rule, status (PASS|WARNING|FAIL), severity
(LOW|MEDIUM|HIGH), a human-readable message, and the affected field.

IMPORTANT: this engine never labels anything as legally fraudulent. It only
flags "potential inconsistencies" that require official verification.
"""
import re
from datetime import datetime
from typing import Dict, List, Optional, TypedDict

from ...database import records_collection


class ValidationOutcome(TypedDict):
    rule: str
    status: str
    severity: str
    message: str
    affected_field: Optional[str]


DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y"]
SURVEY_PATTERN = re.compile(r"^\d+[A-Za-z0-9/\-]*$")
AREA_PATTERN = re.compile(r"([\d.]+)\s*(acre|acres|hectare|hectares|sqft|sq\.?ft)?", re.IGNORECASE)


def _get_val(fields: Dict[str, Optional[str]], name: str) -> Optional[str]:
    v = fields.get(name)
    if v is None:
        return None
    v = v.strip()
    return v if v else None


def _parse_area(value: str) -> Optional[float]:
    m = AREA_PATTERN.search(value)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _valid_date(value: str) -> bool:
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


async def run_validation(
    record_id: str,
    fields: Dict[str, Optional[str]],
    related_area_evidence: Optional[str] = None,
) -> List[ValidationOutcome]:
    results: List[ValidationOutcome] = []

    def add(rule, status, severity, message, affected_field=None):
        results.append(
            {
                "rule": rule,
                "status": status,
                "severity": severity,
                "message": message,
                "affected_field": affected_field,
            }
        )

    # ---------------- Required fields ----------------
    owner = _get_val(fields, "owner_name")
    if owner:
        add("required_owner", "PASS", "LOW", "Owner name present.", "owner_name")
    else:
        add("required_owner", "FAIL", "HIGH", "Owner name is missing.", "owner_name")

    survey = _get_val(fields, "survey_number")
    khasra = _get_val(fields, "khasra_number")
    if survey or khasra:
        add("required_survey_khasra", "PASS", "LOW", "Survey/Khasra number present.", "survey_number")
    else:
        add("required_survey_khasra", "FAIL", "HIGH", "Both survey number and khasra number are missing.", "survey_number")

    village = _get_val(fields, "village")
    tehsil = _get_val(fields, "tehsil")
    district = _get_val(fields, "district")
    if village and tehsil and district:
        add("required_location", "PASS", "LOW", "Village, tehsil and district are present.", "village")
    else:
        missing = [n for n, v in [("village", village), ("tehsil", tehsil), ("district", district)] if not v]
        add(
            "required_location",
            "WARNING",
            "MEDIUM",
            f"Missing location detail(s): {', '.join(missing)}.",
            "village",
        )

    # ---------------- Format checks ----------------
    for fname in ("survey_number", "khasra_number"):
        val = _get_val(fields, fname)
        if val is None:
            continue
        if SURVEY_PATTERN.match(val):
            add(f"format_{fname}", "PASS", "LOW", f"{fname.replace('_', ' ').title()} format looks valid.", fname)
        else:
            add(f"format_{fname}", "WARNING", "MEDIUM", f"{fname.replace('_', ' ').title()} format looks unusual and should be checked.", fname)

    for fname in ("mutation_date", "registration_date"):
        val = _get_val(fields, fname)
        if val is None:
            continue
        if _valid_date(val):
            add(f"format_{fname}", "PASS", "LOW", f"{fname.replace('_', ' ').title()} format valid.", fname)
        else:
            add(f"format_{fname}", "WARNING", "MEDIUM", f"{fname.replace('_', ' ').title()} does not match an expected date format (DD-MM-YYYY).", fname)

    area_raw = _get_val(fields, "plot_area")
    area_val = _parse_area(area_raw) if area_raw else None
    if area_raw is not None:
        if area_val is not None and area_val > 0:
            add("format_plot_area", "PASS", "LOW", "Plot area is a valid positive numeric value.", "plot_area")
        else:
            add("logical_plot_area", "FAIL", "HIGH", "Plot area is missing units, non-numeric, or not positive.", "plot_area")

    # ---------------- Consistency checks ----------------
    # Duplicate survey/khasra across other records in the system
    dup_field = survey or khasra
    if dup_field:
        existing = await records_collection.find_one(
            {
                "_id": {"$ne": record_id},
                "fields": {
                    "$elemMatch": {
                        "field_name": {"$in": ["survey_number", "khasra_number"]},
                        "value": dup_field,
                    }
                },
            }
        )
        if existing:
            add(
                "consistency_duplicate_survey",
                "WARNING",
                "HIGH",
                f"Survey/Khasra number '{dup_field}' already exists on another record (record {existing['_id']}). "
                "Potential inconsistency detected — requires official verification.",
                "survey_number",
            )
        else:
            add("consistency_duplicate_survey", "PASS", "LOW", "No duplicate survey/khasra number found.", "survey_number")

    # Area mismatch against a related record's recorded area (e.g. mutation record)
    if related_area_evidence:
        related_val = _parse_area(related_area_evidence)
        if related_val is not None and area_val is not None and abs(related_val - area_val) > 0.01:
            add(
                "consistency_area_mismatch",
                "WARNING",
                "HIGH",
                f"Plot area ({area_val} ) differs from the area recorded in a related record "
                f"({related_val}). Potential inconsistency detected — requires official verification.",
                "plot_area",
            )
        elif related_val is not None:
            add("consistency_area_mismatch", "PASS", "LOW", "Plot area matches the related record.", "plot_area")

    # Missing mutation information
    mutation_no = _get_val(fields, "mutation_number")
    mutation_date = _get_val(fields, "mutation_date")
    if not mutation_no and not mutation_date:
        add(
            "consistency_missing_mutation",
            "WARNING",
            "MEDIUM",
            "Mutation number and mutation date are both missing from this record. Review required.",
            "mutation_number",
        )
    elif not mutation_no or not mutation_date:
        add(
            "consistency_missing_mutation",
            "WARNING",
            "LOW",
            "Mutation information is incomplete.",
            "mutation_number",
        )
    else:
        add("consistency_missing_mutation", "PASS", "LOW", "Mutation information present.", "mutation_number")

    return results
