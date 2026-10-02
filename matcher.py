from __future__ import annotations

import json
import re
from typing import Any, Iterable


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    return str(value).strip().lower()


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [normalize_text(v) for v in value if v not in (None, "")]
    if isinstance(value, str):
        return [normalize_text(v) for v in re.split(r"[,;|\n]+", value) if v.strip()]
    return [normalize_text(value)]


def parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.lower().replace(",", "").strip()
        if not text:
            return None
        multiplier = 1
        if "lakh" in text or "lac" in text:
            multiplier = 100000
        elif "crore" in text:
            multiplier = 10000000
        elif "k" in text:
            multiplier = 1000

        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            return None
        parsed = float(match.group(0))
        return parsed * multiplier
    return None


def resolve_profile_value(profile: dict[str, Any], field: str) -> Any:
    aliases = {
        "annual_income": ["annual_income", "family_income", "income", "income_band"],
        "state": ["state", "domicile", "domicile_state", "residence_state"],
        "domicile": ["domicile", "state", "domicile_state", "residence_state"],
        "domicile_state": ["domicile_state", "state", "domicile", "residence_state"],
        "residence_state": ["residence_state", "state", "domicile", "domicile_state"],
        "category": ["category", "social_category", "caste_category"],
        "social_category": ["social_category", "category", "caste_category"],
        "caste_category": ["caste_category", "category", "social_category"],
        "course_level": ["course_level", "course", "education_level", "study_level"],
        "gender": ["gender", "sex"],
        "marks": ["marks", "percentage", "score", "grade"],
        "documents": ["documents", "required_documents", "doc_set"],
    }

    for candidate in aliases.get(field, [field]):
        if candidate in profile and _is_profile_value_present(profile[candidate]):
            return profile[candidate]
    return None


def _is_profile_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def compare_values(actual: Any, expected: Any, operator: str) -> tuple[bool, str]:
    if operator in {"exists", "required"}:
        return (actual is not None and actual not in ("", [], {}), "field is present")

    if actual is None:
        return False, "missing value in profile"

    actual_norm = normalize_text(actual)
    expected_norm = normalize_text(expected)

    if operator == "eq":
        return actual_norm == expected_norm, f"expected '{expected}' but found '{actual}'"

    if operator == "ne":
        return actual_norm != expected_norm, f"expected not equal to '{expected}' but found '{actual}'"

    if operator == "in":
        expected_values = normalize_list(expected)
        actual_values = normalize_list(actual)
        intersect = set(actual_values) & set(expected_values)
        return bool(intersect), f"actual '{actual}' is not in {expected}"

    if operator == "not_in":
        expected_values = normalize_list(expected)
        actual_values = normalize_list(actual)
        return not (set(actual_values) & set(expected_values)), f"actual '{actual}' overlaps with forbidden values: {expected}"

    if operator == "contains":
        if isinstance(actual, (list, tuple, set)) or isinstance(expected, (list, tuple, set)):
            actual_values = normalize_list(actual)
            expected_values = normalize_list(expected)
            return all(item in actual_values for item in expected_values), f"missing required values in '{actual}'"
        return normalize_text(expected) in normalize_text(actual), f"'{actual}' does not contain '{expected}'"

    if operator == "gt":
        actual_num = parse_numeric(actual)
        expected_num = parse_numeric(expected)
        if actual_num is None or expected_num is None:
            return False, "numeric comparison required but value is not numeric"
        return actual_num > expected_num, f"{actual} is not greater than {expected}"

    if operator == "gte":
        actual_num = parse_numeric(actual)
        expected_num = parse_numeric(expected)
        if actual_num is None or expected_num is None:
            return False, "numeric comparison required but value is not numeric"
        return actual_num >= expected_num, f"{actual} is below {expected}"

    if operator == "lt":
        actual_num = parse_numeric(actual)
        expected_num = parse_numeric(expected)
        if actual_num is None or expected_num is None:
            return False, "numeric comparison required but value is not numeric"
        return actual_num < expected_num, f"{actual} is not less than {expected}"

    if operator == "lte":
        actual_num = parse_numeric(actual)
        expected_num = parse_numeric(expected)
        if actual_num is None or expected_num is None:
            return False, "numeric comparison required but value is not numeric"
        return actual_num <= expected_num, f"{actual} is above {expected}"

    if operator == "between":
        if not isinstance(expected, (list, tuple)) or len(expected) != 2:
            return False, "between operator expects [min, max]"
        lower, upper = expected
        actual_num = parse_numeric(actual)
        lower_num = parse_numeric(lower)
        upper_num = parse_numeric(upper)
        if actual_num is None or lower_num is None or upper_num is None:
            return False, "numeric range required but value is not numeric"
        return lower_num <= actual_num <= upper_num, f"{actual} is outside {lower} to {upper}"

    if operator == "all_of":
        expected_values = normalize_list(expected)
        actual_values = normalize_list(actual)
        missing = [v for v in expected_values if v not in actual_values]
        return not missing, f"missing required values: {missing}"

    if operator == "any_of":
        expected_values = normalize_list(expected)
        actual_values = normalize_list(actual)
        match = any(v in actual_values for v in expected_values)
        return match, f"none of {expected_values} were found in {actual_values}"

    raise ValueError(f"Unsupported operator: {operator}")


def evaluate_requirement(profile: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    field = rule.get("field") or rule.get("attribute")
    if not field:
        raise ValueError("Each rule must include a 'field' attribute")

    expected = rule.get("value")
    operator = rule.get("operator", "eq")
    actual = resolve_profile_value(profile, field)

    if actual is None:
        return {
            "id": rule.get("id", "unknown"),
            "field": field,
            "operator": operator,
            "passed": False,
            "required": rule.get("required", True),
            "missing": True,
            "actual": None,
            "expected": expected,
            "reason": "profile missing required field",
            "evidence": f"No value found for '{field}' in student profile",
        }

    passed, reason = compare_values(actual, expected, operator)

    return {
        "id": rule.get("id", "unknown"),
        "field": field,
        "operator": operator,
        "passed": passed,
        "required": rule.get("required", True),
        "missing": False,
        "actual": actual,
        "expected": expected,
        "reason": reason,
        "evidence": f"Profile field '{field}'='{actual}' compared against rule '{rule.get('description', '') or operator}'",
    }


def profile_to_rule_matching(profile: dict[str, Any], rule_set: Iterable[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for rule in rule_set:
        results.append(evaluate_requirement(profile, rule))
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "eligible": passed_count == len(results),
        "profile_summary": {
            "state": resolve_profile_value(profile, "state"),
            "category": resolve_profile_value(profile, "category"),
            "course_level": resolve_profile_value(profile, "course_level"),
            "annual_income": resolve_profile_value(profile, "annual_income"),
            "gender": resolve_profile_value(profile, "gender"),
        },
        "total_requirements": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "results": results,
    }


if __name__ == "__main__":
    example_profile = {
        "state": "Maharashtra",
        "category": "SC",
        "course_level": "College degree",
        "family_income": "₹1.8 lakh",
        "gender": "female",
        "documents": ["income_certificate", "domicile_proof"],
    }

    example_rules = [
        {"id": "rule-state", "field": "state", "operator": "in", "value": ["Maharashtra", "Karnataka"], "description": "Must be a resident of Maharashtra or Karnataka"},
        {"id": "rule-category", "field": "category", "operator": "in", "value": ["SC", "ST", "OBC"], "description": "Must belong to SC/ST/OBC"},
        {"id": "rule-income", "field": "annual_income", "operator": "lte", "value": "250000", "description": "Annual family income must be below ₹2.5 lakh"},
        {"id": "rule-docs", "field": "documents", "operator": "all_of", "value": ["income_certificate", "domicile_proof"], "description": "Must have income certificate and domicile proof"},
    ]

    print(json.dumps(profile_to_rule_matching(example_profile, example_rules), indent=2))
