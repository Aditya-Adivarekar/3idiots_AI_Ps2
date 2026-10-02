from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from .document_readiness import DocumentReadinessChecker
from .matcher import profile_to_rule_matching
from .preconditions import validate_profile_preconditions
from .qwen import DEFAULT_QWEN_MODEL, QwenInferenceService


ExplanationGenerator = Callable[[dict[str, Any], list[dict[str, Any]]], str]


class OfficialClauseRetriever:
    """Retrieve matching policy clauses from indexed, official scholarship sources."""

    def __init__(self, indexer: Any, max_results: int = 5) -> None:
        self.indexer = indexer
        self.max_results = max_results

    def retrieve(
        self,
        rules: Iterable[dict[str, Any]],
        scholarship_id: str | None = None,
    ) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for rule in rules:
            query = self._query_for_rule(rule)
            if not query:
                continue

            sql = """
                SELECT s.id, s.title, s.organization, s.source_type, s.url,
                       s.eligibility, s.raw_text, bm25(scholarships_fts) AS rank
                FROM scholarships_fts
                JOIN scholarships s ON s.rowid = scholarships_fts.rowid
                WHERE scholarships_fts MATCH ? AND s.is_active = 1
            """
            params: list[Any] = [query]
            if scholarship_id:
                sql += " AND s.id = ?"
                params.append(scholarship_id)
            sql += " ORDER BY rank LIMIT 50"
            try:
                rows = self.indexer.conn.execute(sql, params).fetchall()
            except Exception:
                continue

            for row in rows:
                record = dict(row)
                if scholarship_id and record["id"] != scholarship_id:
                    continue
                if not self._is_official(record):
                    continue
                clause = self._best_clause(record, rule)
                if not clause:
                    continue
                item = {
                    "record_id": record["id"],
                    "title": record["title"],
                    "organization": record["organization"],
                    "source_type": record["source_type"],
                    "source_url": record["url"],
                    "clause": clause,
                    "rule_id": rule.get("id"),
                }
                found[(record["id"], rule.get("id"))] = item

        return list(found.values())[: self.max_results]

    def _query_for_rule(self, rule: dict[str, Any]) -> str:
        field_terms = {
            "annual_income": ["income", "family", "annual"],
            "state": ["domicile", "resident", "state"],
            "marks": ["marks", "percentage", "academic"],
            "category": ["category", "caste"],
            "course_level": ["course", "study", "degree"],
            "gender": ["gender", "women", "female"],
            "documents": ["documents", "certificate", "proof"],
        }
        terms = field_terms.get(rule.get("field"), [str(rule.get("field", ""))])
        terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", str(rule.get("description", ""))))
        value = rule.get("value")
        if isinstance(value, (list, tuple, set)):
            terms.extend(str(item) for item in value)
        elif isinstance(value, str):
            terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", value))
        unique_terms = list(dict.fromkeys(term.lower() for term in terms if len(term) >= 3))[:12]
        return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in unique_terms)

    def _is_official(self, record: dict[str, Any]) -> bool:
        source_type = str(record.get("source_type") or "").lower()
        source_labels = set(re.split(r"[^a-z0-9]+", source_type))
        if source_labels & {"government", "govt", "official"}:
            return True
        host = urlparse(str(record.get("url") or "")).hostname or ""
        host = host.lower().rstrip(".")
        return host == "gov" or host.endswith(".gov") or host.endswith(".gov.in")

    def _best_clause(self, record: dict[str, Any], rule: dict[str, Any]) -> str:
        text = str(record.get("eligibility") or "").strip()
        if not text or text.lower() == "not specified":
            text = str(record.get("raw_text") or "").strip()
        if not text:
            return ""

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
        search_terms = self._query_for_rule(rule).replace('"', "").split(" OR ")
        ranked = sorted(
            enumerate(sentences),
            key=lambda pair: sum(term.lower() in pair[1].lower() for term in search_terms),
            reverse=True,
        )
        selected = [sentence for _, sentence in ranked[:2] if sentence]
        return " ".join(selected)[:1200] or text[:1200]


class HybridEligibilityPipeline:
    """Run deterministic eligibility evaluation, official-clause RAG, then explanation synthesis."""

    def __init__(
        self,
        indexer: Any,
        explanation_generator: ExplanationGenerator | None = None,
        hf_token: str | None = None,
        model: str = DEFAULT_QWEN_MODEL,
        max_clauses: int = 5,
        qwen_service: QwenInferenceService | None = None,
    ) -> None:
        self.indexer = indexer
        self.retriever = OfficialClauseRetriever(indexer, max_results=max_clauses)
        self.document_checker = DocumentReadinessChecker()
        self.explanation_generator = explanation_generator
        self.qwen_service = qwen_service or QwenInferenceService(token=hf_token, model=model)
        self.model = model

    def run(
        self,
        profile: dict[str, Any],
        rules: Iterable[dict[str, Any]],
        scholarship_id: str | None = None,
        uploaded_files: Iterable[Any] | None = None,
        scheme: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rule_list = list(rules)
        scheme_info = {"id": scholarship_id, "rules": rule_list, **(scheme or {})}
        document_readiness = self.document_checker.check(scheme_info, uploaded_files)
        profile_rules = [
            rule for rule in rule_list
            if str(rule.get("field") or rule.get("attribute") or "").lower()
            not in {"documents", "required_documents", "required_docs"}
        ]
        preconditions = validate_profile_preconditions(profile, profile_rules)
        if not preconditions["ready"]:
            return {
                "status": "needs_input",
                "preconditions": preconditions,
                "missing_fields": preconditions["missing_fields"],
                "follow_up_questions": preconditions["follow_up_questions"],
                "document_readiness": document_readiness,
                "evaluation": None,
                "source_clauses": [],
                "audit": [],
                "failed_conditions": [],
                "explanation": "Provide the missing profile information to evaluate eligibility.",
                "explanation_provider": "none",
            }

        evaluation_profile = dict(profile)
        evaluation_profile["documents"] = document_readiness["provided_document_types"]
        evaluation = profile_to_rule_matching(evaluation_profile, rule_list)
        clauses = self.retriever.retrieve(rule_list, scholarship_id=scholarship_id)
        audit = self._build_audit(evaluation, clauses, rule_list)
        explanation = self._synthesize_explanation(evaluation, clauses)
        return {
            "status": "evaluated",
            "preconditions": preconditions,
            "missing_fields": [],
            "follow_up_questions": [],
            "document_readiness": document_readiness,
            "evaluation": evaluation,
            "source_clauses": clauses,
            "audit": audit,
            "failed_conditions": [entry for entry in audit if not entry["passed"]],
            "explanation": explanation,
            "explanation_provider": self._provider_name(),
        }

    def _build_audit(
        self,
        evaluation: dict[str, Any],
        clauses: list[dict[str, Any]],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        audit = []
        descriptions = {rule.get("id", "unknown"): rule.get("description", "") for rule in rules}
        for result in evaluation["results"]:
            rule_id = result["id"]
            matching_clauses = [
                {
                    "clause": clause["clause"],
                    "source_url": clause["source_url"],
                    "source_title": clause["title"],
                    "organization": clause["organization"],
                    "record_id": clause["record_id"],
                }
                for clause in clauses
                if clause.get("rule_id") == rule_id
            ]
            audit.append({
                "id": rule_id,
                "status": "passed" if result["passed"] else "failed",
                "passed": result["passed"],
                "condition": {
                    "field": result["field"],
                    "operator": result["operator"],
                    "description": descriptions.get(rule_id, ""),
                },
                "actual": result["actual"],
                "expected": result["expected"],
                "missing": result["missing"],
                "reason": result["reason"],
                "matching_official_clauses": matching_clauses,
            })
        return audit

    def _provider_name(self) -> str:
        if self.explanation_generator:
            return "custom"
        if self.qwen_service.token:
            return "huggingface_qwen_or_fallback"
        return "deterministic_fallback"

    def _synthesize_explanation(
        self,
        evaluation: dict[str, Any],
        clauses: list[dict[str, Any]],
    ) -> str:
        if self.explanation_generator:
            try:
                return self.explanation_generator(deepcopy(evaluation), deepcopy(clauses))
            except Exception:
                return self._fallback_explanation(evaluation, clauses)

        if self.qwen_service.token:
            try:
                return self.qwen_service.generate_explanation(evaluation, clauses)
            except Exception:
                pass

        return self._fallback_explanation(evaluation, clauses)

    def _fallback_explanation(
        self,
        evaluation: dict[str, Any],
        clauses: list[dict[str, Any]],
    ) -> str:
        passed = evaluation["passed_count"]
        total = evaluation["total_requirements"]
        status = "meets all evaluated requirements" if evaluation["eligible"] else "does not meet all evaluated requirements"
        explanation = f"The profile {status} ({passed} of {total} requirements passed)."
        failed = [result for result in evaluation["results"] if not result["passed"]]
        if failed:
            explanation += " Failed checks: " + "; ".join(
                f"{item['field']}: {item['reason']}" for item in failed
            ) + "."
        if not clauses:
            explanation += " No matching official source clauses were retrieved."
        return explanation
