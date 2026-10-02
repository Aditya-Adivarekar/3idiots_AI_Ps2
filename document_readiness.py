from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable


DOCUMENT_LABELS = {
    "income_certificate": "Income certificate",
    "domicile_proof": "Domicile or residence proof",
    "caste_certificate": "Caste or category certificate",
    "marksheet": "Marksheet or academic transcript",
    "bank_passbook": "Bank passbook or account proof",
    "identity_proof": "Identity proof",
    "admission_proof": "Admission proof",
    "bonafide_certificate": "Bonafide certificate",
    "fee_receipt": "Fee receipt",
    "passport_photo": "Passport-size photograph",
}

DOCUMENT_ALIASES = {
    "income_certificate": ("income certificate", "family income certificate", "income proof", "income"),
    "domicile_proof": ("domicile certificate", "domicile proof", "residence certificate", "residence proof", "address proof", "domicile"),
    "caste_certificate": ("caste certificate", "category certificate", "sc certificate", "st certificate", "sc st certificate", "obc certificate", "scheduled caste certificate", "scheduled tribe certificate", "backward class certificate", "caste proof"),
    "marksheet": ("marksheet", "mark sheet", "transcript", "academic record", "school result", "exam result"),
    "bank_passbook": ("bank passbook", "passbook", "bank account proof", "bank statement", "bank details"),
    "identity_proof": ("identity proof", "identity card", "aadhaar", "aadhar", "voter id", "pan card"),
    "admission_proof": ("admission proof", "admission letter", "admission receipt", "enrolment proof", "enrollment proof"),
    "bonafide_certificate": ("bonafide certificate", "bona fide certificate", "bonafide"),
    "fee_receipt": ("fee receipt", "tuition receipt", "fee proof"),
    "passport_photo": ("passport photo", "passport size photo", "photograph", "photo"),
}


class DocumentReadinessChecker:
    """Compare scheme document requirements with uploaded file names or metadata."""

    def check(
        self,
        scheme: dict[str, Any],
        uploaded_files: Iterable[Any] | None = None,
    ) -> dict[str, Any]:
        requirements = self._requirements(scheme)
        uploads = [self._uploaded_file(item) for item in (uploaded_files or [])]
        uploads = [item for item in uploads if item["filename"]]

        checklist = []
        for requirement in requirements:
            accepted_types = requirement["document_types"]
            matches = [
                item["filename"]
                for item in uploads
                if item["document_type"] in accepted_types
                or any(self._matches(item["filename"], required) for required in accepted_types)
            ]
            present = bool(matches)
            required = requirement["required"]
            status = "present" if present else "missing" if required else "optional"
            checklist.append({
                "id": requirement["id"],
                "document_type": accepted_types[0] if len(accepted_types) == 1 else accepted_types,
                "label": requirement["label"],
                "required": required,
                "status": status,
                "matched_files": list(dict.fromkeys(matches)),
            })

        required_items = [item for item in checklist if item["required"]]
        missing_documents = [
            item["document_type"] for item in required_items if item["status"] == "missing"
        ]
        provided_types = list(dict.fromkeys(
            item["document_type"] for item in uploads if item["document_type"]
        ))
        requirements_configured = bool(requirements)
        return {
            "scheme_id": scheme.get("id") or scheme.get("scholarship_id"),
            "status": "not_configured" if not requirements_configured else "missing_documents" if missing_documents else "ready",
            "ready": None if not requirements_configured else not missing_documents,
            "requirements_configured": requirements_configured,
            "summary": {
                "required": len(required_items),
                "matched": len(required_items) - len(missing_documents),
                "missing": len(missing_documents),
            },
            "checklist": checklist,
            "missing_documents": missing_documents,
            "provided_document_types": provided_types,
            "uploaded_file_count": len(uploads),
            "disclaimer": "Filename matches indicate presence only; document contents and validity were not verified.",
        }

    def _requirements(self, scheme: dict[str, Any]) -> list[dict[str, Any]]:
        requirements: list[dict[str, Any]] = []
        explicit_requirements = scheme.get("required_documents", []) or []
        if isinstance(explicit_requirements, (str, dict)):
            explicit_requirements = [explicit_requirements]
        for index, document in enumerate(explicit_requirements):
            parsed = self._requirement(document, f"required-document-{index + 1}")
            if parsed:
                requirements.append(parsed)

        for rule in scheme.get("rules", []) or []:
            field = str(rule.get("field") or rule.get("attribute") or "").lower()
            if field not in {"documents", "required_documents", "required_docs"}:
                continue
            values = rule.get("value")
            if values is None:
                continue
            values = list(values) if isinstance(values, (list, tuple, set)) else [values]
            if not values:
                continue
            operator = str(rule.get("operator", "all_of")).lower()
            if operator in {"any_of", "in"} and len(values) > 1:
                types = [self._document_type(value) for value in values]
                label = "One of: " + ", ".join(self._label(value) for value in types)
                requirements.append({
                    "id": rule.get("id", "document-alternative"),
                    "document_types": types,
                    "label": label,
                    "required": rule.get("required", True),
                })
                continue
            for index, value in enumerate(values):
                parsed = self._requirement(value, f"{rule.get('id', 'document-rule')}-{index + 1}", rule.get("required", True))
                if parsed:
                    requirements.append(parsed)

        unique: dict[tuple[str, ...], dict[str, Any]] = {}
        for requirement in requirements:
            key = tuple(requirement["document_types"])
            if key not in unique:
                unique[key] = requirement
            else:
                unique[key]["required"] = unique[key]["required"] or requirement["required"]
        return list(unique.values())

    def _requirement(
        self,
        document: Any,
        default_id: str,
        default_required: bool = True,
    ) -> dict[str, Any] | None:
        if isinstance(document, dict):
            value = document.get("document_type") or document.get("type") or document.get("name") or document.get("label")
            identifier = document.get("id", default_id)
            required = document.get("required", default_required)
        else:
            value = document
            identifier = default_id
            required = default_required
        if value is None or not str(value).strip():
            return None
        document_type = self._document_type(value)
        return {
            "id": identifier,
            "document_types": [document_type],
            "label": self._label(document_type, str(value)),
            "required": bool(required),
        }

    def _uploaded_file(self, item: Any) -> dict[str, str]:
        if isinstance(item, dict):
            filename = item.get("filename") or item.get("name") or item.get("path") or ""
            explicit_type = item.get("document_type") or item.get("document_category") or ""
        elif hasattr(item, "filename") or hasattr(item, "name"):
            filename = getattr(item, "filename", None) or getattr(item, "name", "")
            explicit_type = getattr(item, "document_type", "") or ""
        else:
            filename = str(item) if item is not None else ""
            explicit_type = ""
        filename = str(filename).replace("\\", "/").rsplit("/", 1)[-1].strip()
        document_type = self._document_type(explicit_type or filename) if filename else ""
        return {"filename": filename, "document_type": document_type}

    def _document_type(self, value: Any) -> str:
        text = str(value).lower()
        text = re.sub(r"\.[a-z0-9]{1,8}$", "", text)
        normalized = re.sub(r"[^a-z0-9]+", " ", text).strip()
        for document_type, aliases in DOCUMENT_ALIASES.items():
            if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
                return document_type
        return re.sub(r"\s+", "_", normalized)

    def _label(self, document_type: str, fallback: str | None = None) -> str:
        return DOCUMENT_LABELS.get(document_type, fallback or document_type.replace("_", " ").title())

    def _matches(self, filename: str, document_type: str) -> bool:
        return self._document_type(filename) == document_type