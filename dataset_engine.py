from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .matcher import compare_values, parse_numeric, resolve_profile_value


OPERATOR_MAP = {
    "==": "eq",
    "!=": "ne",
    "<": "lt",
    "<=": "lte",
    ">": "gt",
    ">=": "gte",
    "IN": "in",
    "NOT_IN": "not_in",
    "BETWEEN": "between",
    "REQUIRED": "exists",
}
ELIGIBILITY_SCOPES = {"eligibility", "evidence_gate"}
NON_ELIGIBILITY_SCOPES = {
    "application_availability",
    "application_gate",
    "selection_gate",
    "current_cycle",
    "classification",
    "preference",
}


class DatasetEligibilityEngine:
    """Deterministic evaluator for the normalized Dataset 2 rule contract."""

    def __init__(
        self,
        rules: Iterable[dict[str, Any]] | dict[str, Any],
        academic_year: str | None = "2026-27",
    ) -> None:
        if isinstance(rules, dict):
            rules = rules.get("eligibility_rules", [])
        self.rules = list(rules)
        self.academic_year = academic_year

    @classmethod
    def from_json(cls, path: str | Path, academic_year: str | None = "2026-27") -> "DatasetEligibilityEngine":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload, academic_year=academic_year)

    def evaluate(
        self,
        scholarship_id: str,
        profile: dict[str, Any],
        document_evidence: dict[str, Any] | None = None,
        application_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        applicable = [
            rule for rule in self.rules
            if rule.get("scholarship_id") == scholarship_id
            and (self.academic_year is None or rule.get("academic_year") == self.academic_year)
        ]
        decision_rules = [
            rule for rule in applicable
            if rule.get("rule_scope") in ELIGIBILITY_SCOPES
        ]
        if not decision_rules:
            return self._empty_decision(
                scholarship_id,
                applicable,
                application_context or {},
                profile,
                document_evidence or {},
            )

        evidence = document_evidence or {}
        results: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        passed_groups: list[str] = []
        failed_groups: list[str] = []
        groups: dict[str, list[dict[str, Any]]] = {}

        for rule in decision_rules:
            group = rule.get("condition_group")
            if group and str(rule.get("group_logic", "AND")).upper() == "OR":
                groups.setdefault(group, []).append(rule)
                continue
            result = self._evaluate_rule(rule, profile, evidence)
            results.append(result)
            if result["status"] == "missing":
                missing.append(self._missing_information(rule, result["reason"]))
            elif result["status"] == "failed":
                failures.append(self._public_rule(rule))

        for group_name, group_rules in groups.items():
            group_results = [self._evaluate_rule(rule, profile, evidence) for rule in group_rules]
            results.extend(group_results)
            if any(item["status"] == "passed" for item in group_results):
                passed_groups.append(group_name)
                continue
            group_missing = [item for item in group_results if item["status"] == "missing"]
            if group_missing:
                missing.extend(
                    self._missing_information(rule, result["reason"])
                    for rule, result in zip(group_rules, group_results)
                    if result["status"] == "missing"
                )
            else:
                failed_groups.append(group_name)
                failures.append({
                    "rule_id": group_name,
                    "field": None,
                    "operator": "OR",
                    "description": f"At least one qualification path in {group_name} must pass.",
                    "source_url": None,
                })

        document_flags, document_issues = self._inspect_document_evidence(profile, evidence)
        missing.extend(document_issues)

        if failures:
            eligibility_status = "NOT_ELIGIBLE"
        elif missing:
            eligibility_status = "NEEDS_MORE_INFORMATION"
        else:
            eligibility_status = "ELIGIBLE"

        application = self._evaluate_application_status(applicable, application_context or {}, profile)
        application_gate = self._evaluate_scope(applicable, "application_gate", profile, evidence)
        selection = self._evaluate_scope(applicable, "selection_gate", profile, evidence)
        current_cycle = self._evaluate_scope(applicable, "current_cycle", profile, evidence)
        application_gate_status = {
            "NOT_CONFIGURED": "NOT_CONFIGURED",
            "NOT_MET": "APPLICATION_BLOCKED",
            "NEEDS_MORE_INFORMATION": "NEEDS_MORE_INFORMATION",
            "MET": "READY_TO_SUBMIT",
        }[application_gate["status"]]
        selection_status = {
            "NOT_CONFIGURED": "NOT_CONFIGURED",
            "NOT_MET": "NOT_SELECTED",
            "NEEDS_MORE_INFORMATION": "NEEDS_MORE_INFORMATION",
            "MET": "SELECTION_GATE_PASSED",
        }[selection["status"]]
        flags: list[str] = list(document_flags)
        if missing:
            flags.append("EVIDENCE_OR_PROFILE_INCOMPLETE")
        if failed_groups:
            flags.append("OR_QUALIFICATION_PATHS_FAILED")

        return {
            "scholarship_id": scholarship_id,
            "academic_year": self.academic_year,
            "eligibility_status": eligibility_status,
            "application_status": application["status"],
            "application_status_basis": application["basis"],
            "application_gate_status": application_gate_status,
            "selection_status": selection_status,
            "current_cycle_status": current_cycle["status"],
            "rule_results": results,
            "failed_rules": failures,
            "missing_information": self._deduplicate_missing(missing),
            "passed_groups": passed_groups,
            "failed_groups": failed_groups,
            "flags": flags,
        }

    def simulate(
        self,
        scholarship_id: str,
        profile: dict[str, Any],
        mutation: dict[str, Any],
        document_evidence: dict[str, Any] | None = None,
        application_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        original_profile = copy.deepcopy(profile)
        hypothetical_profile = copy.deepcopy(profile)
        hypothetical_evidence = copy.deepcopy(document_evidence or {})
        hypothetical_context = copy.deepcopy(application_context or {})
        for field, value in mutation.items():
            if field == "document_state" and isinstance(value, dict):
                hypothetical_evidence.update(value)
            elif field == "application_date":
                hypothetical_context["today"] = value
            else:
                hypothetical_profile[field] = value

        before = self.evaluate(scholarship_id, original_profile, document_evidence, application_context)
        after = self.evaluate(scholarship_id, hypothetical_profile, hypothetical_evidence, hypothetical_context)
        before_results = {item.get("rule_id"): item.get("status") for item in before["rule_results"]}
        after_results = {item.get("rule_id"): item.get("status") for item in after["rule_results"]}
        changed_rules = [
            {"rule_id": rule_id, "before": before_status, "after": after_results.get(rule_id)}
            for rule_id, before_status in before_results.items()
            if before_status != after_results.get(rule_id)
        ]
        return {
            "scholarship_id": scholarship_id,
            "before": before,
            "after": after,
            "changed_rules": changed_rules,
            "flags": ["SIMULATION_ONLY", "PROFILE_UNCHANGED"],
            "profile_unchanged": profile == original_profile,
        }

    def _evaluate_rule(
        self,
        rule: dict[str, Any],
        profile: dict[str, Any],
        document_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        base = self._public_rule(rule)
        if rule.get("mandatory") == "conditional":
            return {
                **base,
                "status": "missing",
                "actual": None,
                "reason": "conditional_rule_applicability_unverified",
            }
        if rule.get("verification_status") != "verified_current":
            return {
                **base,
                "status": "missing",
                "actual": None,
                "reason": "rule_evidence_not_current",
            }

        field = str(rule.get("field", ""))
        actual = self._get_actual(field, profile, document_evidence)
        operator = OPERATOR_MAP.get(str(rule.get("operator", "")).upper())
        if operator is None:
            return {**base, "status": "missing", "actual": actual, "reason": "unsupported_operator"}

        if operator == "exists":
            passed, reason = compare_values(actual, rule.get("value"), operator)
        elif self._is_missing(actual):
            return {**base, "status": "missing", "actual": None, "reason": "profile_value_missing"}
        else:
            passed, reason = compare_values(actual, rule.get("value"), operator)

        return {
            **base,
            "status": "passed" if passed else "failed",
            "actual": actual,
            "reason": reason,
        }

    def _get_actual(
        self,
        field: str,
        profile: dict[str, Any],
        document_evidence: dict[str, Any],
    ) -> Any:
        evidence_field = field.removesuffix("_evidence_status")
        if field.endswith("_evidence_status"):
            if evidence_field == "disability":
                disability_certificate = document_evidence.get("disability_certificate")
                consent = document_evidence.get("udid_consent") is True
                certificate_usable = (
                    isinstance(disability_certificate, dict)
                    and disability_certificate.get("expired") is not True
                    and disability_certificate.get("readable") is not False
                )
                if certificate_usable and consent:
                    return "verified"
                return None
            evidence_value = document_evidence.get(evidence_field)
            if isinstance(evidence_value, dict):
                return "verified" if self._evidence_is_valid(evidence_value) else None
            return evidence_value
        return resolve_profile_value(profile, field)

    def _evidence_is_valid(self, evidence: dict[str, Any]) -> bool:
        if evidence.get("expired") is True or evidence.get("readable") is False:
            return False
        return evidence.get("verified") is True or evidence.get("valid") is True or evidence.get("udid_consent") is True

    def _inspect_document_evidence(
        self,
        profile: dict[str, Any],
        document_evidence: dict[str, Any],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        flags: list[str] = []
        issues: list[dict[str, Any]] = []
        for document_name, document in document_evidence.items():
            if not isinstance(document, dict):
                continue
            lowered_name = str(document_name).lower()
            if document.get("expired") is True or document.get("valid") is False:
                flags.append("DOCUMENT_INVALID_OR_EXPIRED")
                issues.append(self._document_issue(document_name, "document_expired_or_invalid"))
            if document.get("readable") is False:
                flags.append("DOCUMENT_UNREADABLE")
                issues.append(self._document_issue(document_name, "document_unreadable"))

            if "source" in lowered_name and document.get("text") and not document.get("page"):
                flags.append("NO_FAKE_PAGE_NUMBER")

            text_values = [value for key, value in document.items() if "text" in str(key).lower() and isinstance(value, str)]
            if any(self._contains_prompt_injection(value) for value in text_values):
                flags.append("PROMPT_INJECTION_IGNORED")

            comparisons = [
                ("income", ("family_income", "annual_income", "income")),
                ("category", ("category", "social_category", "caste_category")),
                ("marks", ("marks", "percentage", "marks_percent")),
            ]
            for kind, fields in comparisons:
                if kind not in lowered_name and not any(field in document for field in fields):
                    continue
                profile_value = self._first_present(profile, fields)
                evidence_value = self._first_present(document, fields)
                if self._is_missing(profile_value) or self._is_missing(evidence_value):
                    continue
                if kind == "income" or kind == "marks":
                    left, right = parse_numeric(profile_value), parse_numeric(evidence_value)
                    mismatch = left is not None and right is not None and left != right
                else:
                    mismatch = str(profile_value).strip().casefold() != str(evidence_value).strip().casefold()
                if mismatch:
                    flags.extend(("PROFILE_DOCUMENT_MISMATCH", "MANUAL_REVIEW"))
                    issues.append(self._document_issue(document_name, f"profile_document_{kind}_mismatch"))

        unique_flags = list(dict.fromkeys(flags))
        return unique_flags, issues

    def _first_present(self, values: dict[str, Any], fields: tuple[str, ...]) -> Any:
        for field in fields:
            if field in values:
                return values[field]
        return None

    def _contains_prompt_injection(self, text: str) -> bool:
        lowered = text.casefold()
        patterns = (
            "ignore rules",
            "ignore previous instructions",
            "ignore scholarship rules",
            "mark applicant eligible",
            "mark the applicant eligible",
            "override system",
        )
        return any(pattern in lowered for pattern in patterns)

    def _document_issue(self, document_name: Any, reason: str) -> dict[str, Any]:
        return {
            "rule_id": None,
            "field": str(document_name),
            "reason": reason,
            "source_url": None,
        }

    def _evaluate_application_status(
        self,
        rules: list[dict[str, Any]],
        context: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        explicit_status = context.get("application_status")
        if explicit_status:
            return {"status": str(explicit_status).upper(), "basis": "application_context"}

        today_value = context.get("today")
        if not today_value:
            return {"status": "UNKNOWN", "basis": "no_current_date"}
        try:
            today = date.fromisoformat(str(today_value))
        except ValueError:
            return {"status": "UNKNOWN", "basis": "invalid_current_date"}

        start_dates = []
        close_dates = []
        for rule in rules:
            if rule.get("rule_scope") != "application_availability" or rule.get("verification_status") != "verified_current":
                continue
            field = str(rule.get("field", "")).lower()
            try:
                value = date.fromisoformat(str(rule.get("value")))
            except ValueError:
                continue
            if any(marker in field for marker in ("start", "open", "begin")):
                start_dates.append(value)
            elif any(marker in field for marker in ("close", "deadline", "end")):
                close_dates.append(value)

        if any(today < start for start in start_dates):
            return {"status": "NOT_OPEN", "basis": "verified_application_start"}
        if any(today > close for close in close_dates):
            return {"status": "DEADLINE_PASSED", "basis": "verified_application_deadline"}
        if start_dates or close_dates:
            return {"status": "OPEN", "basis": "verified_application_window"}
        return {"status": "UNKNOWN", "basis": "no_verified_application_window"}

    def _evaluate_scope(
        self,
        rules: list[dict[str, Any]],
        scope: str,
        profile: dict[str, Any],
        document_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        scope_rules = [rule for rule in rules if rule.get("rule_scope") == scope]
        if not scope_rules:
            return {"status": "NOT_CONFIGURED", "results": []}
        results = [self._evaluate_rule(rule, profile, document_evidence) for rule in scope_rules]
        if any(result["status"] == "failed" for result in results):
            status = "NOT_MET"
        elif any(result["status"] == "missing" for result in results):
            status = "NEEDS_MORE_INFORMATION"
        else:
            status = "MET"
        return {"status": status, "results": results}

    def _public_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        return {
            "rule_id": rule.get("rule_id"),
            "field": rule.get("field"),
            "operator": rule.get("operator"),
            "value": rule.get("value"),
            "description": rule.get("evidence_summary") or rule.get("description") or "",
            "source_url": rule.get("source_url"),
            "source_document": rule.get("source_document"),
            "page": rule.get("page"),
            "clause": rule.get("clause"),
            "rule_scope": rule.get("rule_scope"),
        }

    def _missing_information(self, rule: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "rule_id": rule.get("rule_id"),
            "field": rule.get("field"),
            "reason": reason,
            "source_url": rule.get("source_url"),
        }

    def _deduplicate_missing(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, Any, Any]] = set()
        results = []
        for item in values:
            key = (item.get("rule_id"), item.get("field"), item.get("reason"))
            if key not in seen:
                seen.add(key)
                results.append(item)
        return results

    def _is_missing(self, value: Any) -> bool:
        return value is None or isinstance(value, str) and not value.strip()

    def _empty_decision(
        self,
        scholarship_id: str,
        rules: list[dict[str, Any]],
        application_context: dict[str, Any],
        profile: dict[str, Any],
        document_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        application = self._evaluate_application_status(rules, application_context, {})
        application_gate = self._evaluate_scope(rules, "application_gate", profile, document_evidence)
        selection = self._evaluate_scope(rules, "selection_gate", profile, document_evidence)
        current_cycle = self._evaluate_scope(rules, "current_cycle", profile, document_evidence)
        application_gate_status = {
            "NOT_CONFIGURED": "NOT_CONFIGURED",
            "NOT_MET": "APPLICATION_BLOCKED",
            "NEEDS_MORE_INFORMATION": "NEEDS_MORE_INFORMATION",
            "MET": "READY_TO_SUBMIT",
        }[application_gate["status"]]
        selection_status = {
            "NOT_CONFIGURED": "NOT_CONFIGURED",
            "NOT_MET": "NOT_SELECTED",
            "NEEDS_MORE_INFORMATION": "NEEDS_MORE_INFORMATION",
            "MET": "SELECTION_GATE_PASSED",
        }[selection["status"]]
        return {
            "scholarship_id": scholarship_id,
            "academic_year": self.academic_year,
            "eligibility_status": "NEEDS_MORE_INFORMATION",
            "application_status": application["status"],
            "application_status_basis": application["basis"],
            "application_gate_status": application_gate_status,
            "selection_status": selection_status,
            "current_cycle_status": current_cycle["status"],
            "rule_results": [],
            "failed_rules": [],
            "missing_information": [{
                "rule_id": None,
                "field": None,
                "reason": "no_current_eligibility_rules",
                "source_url": None,
            }],
            "passed_groups": [],
            "failed_groups": [],
            "flags": ["NO_CURRENT_ELIGIBILITY_RULES"],
        }
