from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, TypedDict

from .hybrid import HybridEligibilityPipeline
from .matcher import parse_numeric


class StudentProfile(TypedDict):
    state: str | None
    course_level: str | None
    year_of_study: str | None
    category: str | None
    annual_income: float | None
    marks: float | None
    gender: str | None
    documents: list[str]


STUDENT_PROFILE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "x-schema-version": 1,
    "additionalProperties": False,
    "required": ["state", "course_level", "year_of_study", "category", "annual_income", "marks", "gender", "documents"],
    "properties": {
        "state": {"type": ["string", "null"], "aliases": ["domicile", "domicile_state", "residence_state"]},
        "course_level": {"type": ["string", "null"], "aliases": ["course", "education_level", "study_level"]},
        "year_of_study": {"type": ["string", "null"], "aliases": ["year", "class"]},
        "category": {"type": ["string", "null"], "aliases": ["social_category", "caste_category"]},
        "annual_income": {"type": ["number", "null"], "unit": "INR per year", "aliases": ["family_income"]},
        "marks": {"type": ["number", "null"], "unit": "percent", "minimum": 0, "maximum": 100, "aliases": ["percentage", "score"]},
        "gender": {"type": ["string", "null"], "aliases": ["sex"]},
        "documents": {"type": "array", "items": {"type": "string"}, "aliases": ["docs", "required_documents"]},
    },
}

PROFILE_FIELDS = tuple(STUDENT_PROFILE_SCHEMA["properties"])
PROFILE_SCHEMA_VERSION = STUDENT_PROFILE_SCHEMA["x-schema-version"]


def normalize_student_profile(values: dict[str, Any] | None) -> StudentProfile:
    values = values or {}
    profile: StudentProfile = {
        "state": _normalize_text(_first(values, "state", "domicile", "domicile_state", "residence_state")),
        "course_level": _normalize_text(_first(values, "course_level", "course", "education_level", "study_level")),
        "year_of_study": _normalize_text(_first(values, "year_of_study", "year", "class")),
        "category": _normalize_category(_first(values, "category", "social_category", "caste_category")),
        "annual_income": _normalize_number(_first(values, "annual_income", "family_income")),
        "marks": _normalize_marks(_first(values, "marks", "percentage", "score")),
        "gender": _normalize_gender(_first(values, "gender", "sex")),
        "documents": _normalize_documents(_first(values, "documents", "docs", "required_documents")),
    }
    return profile


class StudentProfileStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> StudentProfile:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return normalize_student_profile({})

        if isinstance(payload, dict) and "profile" in payload:
            if payload.get("schema_version") != PROFILE_SCHEMA_VERSION:
                raise ValueError(f"Unsupported student profile schema version: {payload.get('schema_version')}")
            payload = payload["profile"]
        if not isinstance(payload, dict):
            raise ValueError("Stored student profile must be a JSON object")
        return normalize_student_profile(payload)

    def save(self, values: dict[str, Any]) -> StudentProfile:
        profile = normalize_student_profile(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps({"schema_version": PROFILE_SCHEMA_VERSION, "profile": profile}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
        return profile

    def update(self, values: dict[str, Any]) -> StudentProfile:
        updates = dict(values)
        aliases = {
            "domicile": "state",
            "domicile_state": "state",
            "residence_state": "state",
            "course": "course_level",
            "education_level": "course_level",
            "study_level": "course_level",
            "year": "year_of_study",
            "class": "year_of_study",
            "social_category": "category",
            "caste_category": "category",
            "family_income": "annual_income",
            "percentage": "marks",
            "score": "marks",
            "sex": "gender",
            "docs": "documents",
            "required_documents": "documents",
        }
        for alias, field in aliases.items():
            if alias in values and field not in values:
                updates[field] = values[alias]
        return self.save({**self.load(), **updates})


class StudentProfileService:
    def __init__(self, path: str | Path) -> None:
        self.store = StudentProfileStore(path)

    def get_profile(self) -> StudentProfile:
        return self.store.load()

    def save(self, values: dict[str, Any]) -> StudentProfile:
        return self.store.save(values)

    def update(self, values: dict[str, Any]) -> StudentProfile:
        return self.store.update(values)

    def evaluate_schemes(
        self,
        pipeline: HybridEligibilityPipeline,
        schemes: Iterable[dict[str, Any]],
        uploaded_files: Iterable[Any] | None = None,
    ) -> list[dict[str, Any]]:
        profile = self.get_profile()
        shared_uploads = tuple(uploaded_files or ())
        results = []
        for scheme in schemes:
            results.append({
                "scheme_id": scheme.get("id") or scheme.get("scholarship_id"),
                "title": scheme.get("title") or scheme.get("name", "Untitled scheme"),
                "result": pipeline.run(
                    profile=dict(profile),
                    rules=scheme.get("rules", []),
                    scholarship_id=scheme.get("scholarship_id"),
                    uploaded_files=scheme.get("uploaded_files", shared_uploads),
                    scheme=scheme,
                ),
            })
        return results


def _first(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in values:
            value = values[key]
            if value is not None and not (isinstance(value, str) and not value.strip()):
                return value
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"unsure", "not sure", "prefer not to say", "skip for now"}:
        return None
    return text


def _normalize_category(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    match = re.search(r"\b(SC|ST|OBC|EWS)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return text.title() if text.lower() == "general" else text


def _normalize_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and re.search(r"\b(below|under|above|over|between|to)\b|\d\s*[-–]\s*\d", value, re.IGNORECASE):
        return None
    number = parse_numeric(value)
    return number if number is not None and number >= 0 else None


def _normalize_marks(value: Any) -> float | None:
    number = _normalize_number(value)
    return number if number is not None and number <= 100 else None


def _normalize_gender(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"woman / girl", "woman", "girl", "female"}:
        return "female"
    if lowered in {"man / boy", "man", "boy", "male"}:
        return "male"
    return text


def _normalize_documents(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    return list(dict.fromkeys(
        str(item).strip()
        for item in items
        if item is not None and str(item).strip() and str(item).strip().lower() != "unsure"
    ))