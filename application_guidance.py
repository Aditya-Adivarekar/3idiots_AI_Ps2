from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .qwen import QwenInferenceService


class ApplicationGuidanceService:
    """Create next-step guidance from a sanitized application checklist."""

    def __init__(self, qwen_service: QwenInferenceService | None = None) -> None:
        self.qwen_service = qwen_service or QwenInferenceService()

    def guide(self, application: dict[str, Any]) -> dict[str, str]:
        context = self._sanitize(application)
        if self.qwen_service.token:
            try:
                guidance = self.qwen_service.generate_application_guidance(context)
                if guidance:
                    return {"guidance": guidance, "provider": "huggingface_qwen"}
            except Exception:
                pass
        return {
            "guidance": self._fallback(context),
            "provider": "deterministic_fallback",
        }

    def _sanitize(self, application: dict[str, Any]) -> dict[str, Any]:
        source_url = str(application.get("official_source_url") or "")
        parsed_url = urlparse(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            source_url = ""

        deadline = str(application.get("deadline") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline):
            deadline = ""

        missing_documents = [
            str(item).strip()[:100]
            for item in application.get("missing_documents", [])
            if str(item).strip()
        ][:20]
        return {
            "scheme_title": str(application.get("scheme_title") or "Scholarship scheme")[:180],
            "official_source_url": source_url,
            "deadline": deadline or None,
            "deadline_reviewed": bool(application.get("deadline_reviewed")),
            "no_deadline_published": bool(application.get("no_deadline")),
            "stage": application.get("stage") if application.get("stage") in {"shortlisted", "preparing", "submitted"} else "shortlisted",
            "requirements_configured": bool(application.get("requirements_configured")),
            "missing_documents": missing_documents,
        }

    def _fallback(self, context: dict[str, Any]) -> str:
        if not context["requirements_configured"]:
            return "Open the official scheme page and add its required documents to your checklist. No document requirements have been configured yet."
        if context["missing_documents"]:
            missing = ", ".join(context["missing_documents"])
            guidance = f"Next, add or locate these required documents: {missing}. Confirm each item against the official scheme page."
            if not context["deadline_reviewed"] and not context["no_deadline_published"]:
                guidance += " Also confirm the current deadline on that page."
            return guidance
        if not context["deadline_reviewed"] and not context["no_deadline_published"]:
            return "Review the current deadline on the official scheme page, or record that no deadline is published."
        return "Your checklist is complete. Review each original document and the current instructions on the official scheme page before applying."
