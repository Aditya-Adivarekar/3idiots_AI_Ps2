from __future__ import annotations

from typing import Any, Iterable

from .matcher import resolve_profile_value


FIELD_CANONICALIZATION = {
    "domicile": "state",
    "domicile_state": "state",
    "residence_state": "state",
    "social_category": "category",
    "caste_category": "category",
}

FIELD_LABELS = {
    "state": "domicile state",
    "category": "social category",
    "annual_income": "annual family income",
    "marks": "academic marks percentage",
    "course_level": "course or study level",
    "gender": "gender",
    "documents": "required documents",
}

FIELD_QUESTIONS = {
    "state": "Which state are you domiciled in?",
    "category": "Which social category do you belong to (for example, SC, ST, OBC, EWS, or General)?",
    "annual_income": "What is your annual family income?",
    "marks": "What are your academic marks or percentage?",
    "course_level": "What course or level of study are you currently pursuing?",
    "gender": "What is your gender, if relevant to this scholarship?",
    "documents": "Which of the required documents do you currently have?",
}


def validate_profile_preconditions(
    profile: dict[str, Any],
    rules: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    missing_by_field: dict[str, dict[str, Any]] = {}

    for rule in rules:
        if not rule.get("required", True):
            continue
        rule_field = rule.get("field") or rule.get("attribute")
        if not rule_field:
            continue
        field = FIELD_CANONICALIZATION.get(rule_field.lower(), rule_field)
        value = resolve_profile_value(profile, field)
        if not _is_present(value):
            missing = missing_by_field.setdefault(field, {
                "field": field,
                "label": FIELD_LABELS.get(field, field.replace("_", " ")),
                "rule_ids": [],
                "question": FIELD_QUESTIONS.get(field, f"What is your {field.replace('_', ' ')}?"),
            })
            missing["rule_ids"].append(rule.get("id", "unknown"))

    missing_fields = list(missing_by_field.values())
    return {
        "ready": not missing_fields,
        "missing_fields": missing_fields,
        "follow_up_questions": [item["question"] for item in missing_fields],
    }


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True