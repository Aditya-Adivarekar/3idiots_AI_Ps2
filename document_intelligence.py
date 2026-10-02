from __future__ import annotations

import json
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader

from .document_readiness import DOCUMENT_LABELS
from .qwen import DEFAULT_QWEN_MODEL, QwenInferenceService


MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 20
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
PROFILE_FIELD_MAP = {
    "domicile_state": "state",
    "category": "category",
    "annual_family_income": "annual_income",
    "marks_percentage": "marks",
}
FIELD_LABELS = {
    "holder_name": "Certificate holder name",
    "certificate_number": "Certificate number",
    "domicile_state": "Domicile state",
    "category": "Social category",
    "annual_family_income": "Annual family income",
    "marks_percentage": "Marks percentage",
    "issue_date": "Issue date",
    "valid_until": "Valid until",
    "issuing_authority": "Issuing authority",
    "institution_name": "Institution name",
}


class DocumentIntelligenceService:
    """Extract certificate fields for user review without retaining uploaded file bytes."""

    def __init__(
        self,
        ocr_engine: Callable[[bytes, str], str] | None = None,
        llm_extractor: Callable[[str], dict[str, Any]] | None = None,
        hf_token: str | None = None,
        model: str = DEFAULT_QWEN_MODEL,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
        max_pdf_pages: int = MAX_PDF_PAGES,
        qwen_service: QwenInferenceService | None = None,
    ) -> None:
        self.ocr_engine = ocr_engine
        self.llm_extractor = llm_extractor
        self.qwen_service = qwen_service or QwenInferenceService(token=hf_token, model=model)
        self.model = model
        self.max_upload_bytes = max_upload_bytes
        self.max_pdf_pages = max_pdf_pages

    def extract(
        self,
        upload: Any,
        filename: str | None = None,
        allow_remote_llm: bool = False,
    ) -> dict[str, Any]:
        content, resolved_filename = self._read_upload(upload, filename)
        extension = Path(resolved_filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported document type: {extension or 'unknown'}")
        if len(content) > self.max_upload_bytes:
            raise ValueError(f"Upload exceeds the {self.max_upload_bytes}-byte size limit")

        warnings: list[str] = []
        if extension == ".pdf":
            text, method = self._extract_pdf_text(content)
            if not text.strip():
                text = self._ocr_pdf(content)
                method = "ocr"
        else:
            text = self._ocr_image(content, extension)
            method = "ocr"

        text = self._normalize_text(text)
        if not text:
            warnings.append("No readable text was detected; try a clearer scan or image.")

        document_type = self._detect_document_type(text, resolved_filename)
        fields = self._extract_heuristic_fields(text)
        extraction_method = method
        if allow_remote_llm and text:
            llm_data = self._extract_with_llm(text, warnings)
            if llm_data:
                document_type, fields = self._merge_llm_fields(document_type, fields, llm_data, text)
                extraction_method = "ocr+llm" if method == "ocr" else "text+llm"
        elif self.qwen_service.token and not allow_remote_llm:
            warnings.append("Remote Qwen extraction was not used; explicitly enable it to send document text to Hugging Face.")

        return {
            "document_id": str(uuid.uuid4()),
            "filename": Path(resolved_filename).name,
            "document_type": {
                "value": document_type,
                "label": DOCUMENT_LABELS.get(document_type, document_type.replace("_", " ").title()),
                "verification": {"status": "needs_verification", "verified_by_user": False},
            },
            "fields": fields,
            "verification_status": "needs_user_review",
            "extraction_method": extraction_method,
            "source_text_length": len(text),
            "warnings": warnings,
            "privacy": {"uploaded_bytes_retained": False, "full_text_returned": False},
        }

    def confirm_fields(
        self,
        extraction: dict[str, Any],
        confirmations: dict[str, Any],
    ) -> dict[str, Any]:
        reviewed = json.loads(json.dumps(extraction))
        fields = reviewed.get("fields", {})
        for field_name, confirmed_value in confirmations.items():
            if field_name == "document_type":
                if isinstance(reviewed.get("document_type"), dict) and confirmed_value:
                    reviewed["document_type"]["value"] = str(confirmed_value)
                    reviewed["document_type"]["verification"] = {
                        "status": "verified",
                        "verified_by_user": True,
                    }
                continue
            field = fields.get(field_name)
            if field is None:
                continue
            if isinstance(confirmed_value, dict):
                value = confirmed_value.get("value")
                accepted = bool(confirmed_value.get("verified", True))
            else:
                value = confirmed_value
                accepted = confirmed_value is not None
            if not accepted:
                field["verification"] = {"status": "rejected", "verified_by_user": True}
                continue
            field["value"] = value
            field["verification"] = {"status": "verified", "verified_by_user": True}

        verified_profile_values: dict[str, Any] = {}
        for field_name, profile_field in PROFILE_FIELD_MAP.items():
            field = fields.get(field_name)
            if field and field.get("verification", {}).get("status") == "verified":
                verified_profile_values[profile_field] = field.get("value")
        reviewed["verified_profile_values"] = verified_profile_values
        statuses = [
            item.get("verification", {}).get("status")
            for item in fields.values()
        ]
        if reviewed.get("document_type", {}).get("verification", {}).get("status") == "verified":
            statuses.append("verified")
        if statuses and all(status in {"verified", "rejected"} for status in statuses):
            reviewed["verification_status"] = "reviewed"
        elif any(status == "verified" for status in statuses):
            reviewed["verification_status"] = "partially_verified"
        else:
            reviewed["verification_status"] = "needs_user_review"
        return reviewed

    def _read_upload(self, upload: Any, filename: str | None) -> tuple[bytes, str]:
        if isinstance(upload, (bytes, bytearray, memoryview)):
            content = bytes(upload)
            resolved_filename = filename or "upload"
        elif isinstance(upload, (str, Path)):
            path = Path(upload)
            if path.stat().st_size > self.max_upload_bytes:
                raise ValueError(f"Upload exceeds the {self.max_upload_bytes}-byte size limit")
            content = path.read_bytes()
            resolved_filename = filename or path.name
        else:
            resolved_filename = filename or getattr(upload, "filename", None) or getattr(upload, "name", None) or "upload"
            stream = getattr(upload, "file", upload)
            original_position = None
            try:
                if hasattr(stream, "tell") and hasattr(stream, "seek"):
                    original_position = stream.tell()
                    stream.seek(0)
                content = stream.read(self.max_upload_bytes + 1)
            finally:
                if original_position is not None:
                    stream.seek(original_position)
            if not isinstance(content, bytes):
                raise TypeError("Uploaded file stream must return bytes")
        if len(content) > self.max_upload_bytes:
            raise ValueError(f"Upload exceeds the {self.max_upload_bytes}-byte size limit")
        return content, str(resolved_filename)

    def _extract_pdf_text(self, content: bytes) -> tuple[str, str]:
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as exc:
            raise ValueError("Could not read PDF document") from exc
        texts = [(page.extract_text() or "") for page in reader.pages[: self.max_pdf_pages]]
        return "\n".join(texts), "pdf_text"

    def _ocr_pdf(self, content: bytes) -> str:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Scanned PDF OCR requires PyMuPDF. Install it with `pip install PyMuPDF`.") from exc
        document = fitz.open(stream=content, filetype="pdf")
        page_texts = []
        try:
            for page in document[: self.max_pdf_pages]:
                image_bytes = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
                page_texts.append(self._run_ocr(image_bytes, "image/png"))
        finally:
            document.close()
        return "\n".join(page_texts)

    def _ocr_image(self, content: bytes, extension: str) -> str:
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".bmp": "image/bmp",
        }[extension]
        return self._run_ocr(content, mime_type)

    def _run_ocr(self, content: bytes, mime_type: str) -> str:
        if self.ocr_engine:
            return str(self.ocr_engine(content, mime_type) or "")
        try:
            from PIL import Image
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("Image OCR requires Pillow and pytesseract. Install them with `pip install Pillow pytesseract` and install Tesseract OCR.") from exc
        try:
            return pytesseract.image_to_string(Image.open(BytesIO(content)))
        except Exception as exc:
            raise RuntimeError("OCR failed. Check that the Tesseract OCR engine is installed and the image is readable.") from exc

    def _extract_with_llm(self, text: str, warnings: list[str]) -> dict[str, Any] | None:
        if self.llm_extractor:
            try:
                return self.llm_extractor(text)
            except Exception:
                warnings.append("LLM extraction failed; OCR-based extraction was retained.")
                return None
        if not self.qwen_service.token:
            warnings.append("Remote Qwen extraction was requested but HF_TOKEN is not configured; OCR-based extraction was used.")
            return None
        try:
            return self.qwen_service.extract_document_fields(text)
        except Exception:
            warnings.append("LLM extraction failed; OCR-based extraction was retained.")
            return None

    def _merge_llm_fields(
        self,
        document_type: str,
        fields: dict[str, Any],
        llm_data: dict[str, Any],
        source_text: str,
    ) -> tuple[str, dict[str, Any]]:
        candidate_type = llm_data.get("document_type")
        if isinstance(candidate_type, dict):
            type_evidence = str(candidate_type.get("evidence_text") or "").strip()
            candidate_value = candidate_type.get("value")
            if type_evidence and self._contains_evidence(source_text, type_evidence):
                normalized_type = self._normalize_document_type(str(candidate_value or ""))
                if normalized_type != "unknown":
                    document_type = normalized_type

        for field_name, item in (llm_data.get("fields") or {}).items():
            if field_name not in FIELD_LABELS or not isinstance(item, dict):
                continue
            evidence = str(item.get("evidence_text") or "").strip()
            if not evidence or not self._contains_evidence(source_text, evidence):
                continue
            value = item.get("value")
            if value is None or str(value).strip() == "":
                continue
            fields[field_name] = self._field_result(field_name, value, evidence, "llm", 0.9)
        return document_type, fields

    def _extract_heuristic_fields(self, text: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        patterns = {
            "certificate_number": r"(?:certificate\s*(?:no\.?|number|#)|cert\.?\s*(?:no\.?|number|#))\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{3,})",
            "holder_name": r"(?:name\s+of\s+(?:the\s+)?applicant|applicant\s+name|holder\s+name|student\s+name|name)\s*[:\-]\s*([A-Za-z][A-Za-z .'-]{1,80})",
            "issuing_authority": r"(?:issued\s+by|issuing\s+authority|authority)\s*[:\-]\s*([^\n.;]{3,120})",
            "institution_name": r"(?:institution|college|school|university)\s+name\s*[:\-]\s*([^\n.;]{3,120})",
            "issue_date": r"(?:date\s+of\s+issue|issued\s+on|issue\s+date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            "valid_until": r"(?:valid\s+(?:until|till|through)|expiry\s+date|validity\s+up\s+to)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            "domicile_state": r"(?:domicile\s+state|resident\s+of|belongs\s+to\s+the\s+state\s+of|state\s+of\s+residence)\s*[:\-]?\s*([A-Za-z ]{2,50})",
            "category": r"(?:social\s+category|category|caste)\s*[:\-]\s*(SC|ST|OBC|EWS|General|Scheduled\s+Caste|Scheduled\s+Tribe|Other\s+Backward\s+Class)",
        }
        for field_name, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;-\n")
                if field_name == "category":
                    value = self._normalize_category(value)
                fields[field_name] = self._field_result(field_name, value, match.group(0).strip(), "regex", 0.82)

        income_match = re.search(
            r"(?:annual\s+family\s+income|family\s+income|annual\s+income|income)\s*[:\-]?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore)?",
            text,
            re.IGNORECASE,
        )
        if income_match:
            amount = float(income_match.group(1).replace(",", ""))
            unit = (income_match.group(2) or "").lower()
            multiplier = 10000000 if unit == "crore" else 100000 if unit in {"lakh", "lac"} else 1
            fields["annual_family_income"] = self._field_result(
                "annual_family_income",
                amount * multiplier,
                income_match.group(0).strip(),
                "regex",
                0.85,
            )

        marks_match = re.search(
            r"(?:marks|percentage|aggregate|score)\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%",
            text,
            re.IGNORECASE,
        )
        if marks_match and float(marks_match.group(1)) <= 100:
            fields["marks_percentage"] = self._field_result(
                "marks_percentage",
                float(marks_match.group(1)),
                marks_match.group(0).strip(),
                "regex",
                0.82,
            )
        return fields

    def _field_result(
        self,
        field_name: str,
        value: Any,
        evidence: str,
        method: str,
        confidence: float,
    ) -> dict[str, Any]:
        return {
            "label": FIELD_LABELS.get(field_name, field_name.replace("_", " ").title()),
            "value": value,
            "evidence_text": evidence,
            "extraction_method": method,
            "confidence": confidence,
            "verification": {"status": "needs_verification", "verified_by_user": False},
        }

    def _detect_document_type(self, text: str, filename: str) -> str:
        return self._normalize_document_type(f"{filename} {text[:1200]}")

    def _normalize_document_type(self, value: str) -> str:
        text = re.sub(r"[^a-z0-9]+", " ", value.lower())
        if "income" in text and ("certificate" in text or "family" in text):
            return "income_certificate"
        if any(term in text for term in ("domicile", "residence certificate", "residence proof")):
            return "domicile_proof"
        if any(term in text for term in ("caste", "category certificate", "scheduled caste", "scheduled tribe")):
            return "caste_certificate"
        if any(term in text for term in ("marksheet", "mark sheet", "transcript", "academic record")):
            return "marksheet"
        return "unknown"

    def _normalize_category(self, value: str) -> str:
        lowered = value.lower()
        for code in ("SC", "ST", "OBC", "EWS"):
            if re.search(rf"\b{code}\b", value, re.IGNORECASE):
                return code
        if "scheduled caste" in lowered:
            return "SC"
        if "scheduled tribe" in lowered:
            return "ST"
        if "other backward class" in lowered:
            return "OBC"
        return value

    def _contains_evidence(self, source_text: str, evidence: str) -> bool:
        return self._normalize_text(evidence).casefold() in self._normalize_text(source_text).casefold()

    def _normalize_text(self, text: str) -> str:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines()]
        return "\n".join(line for line in lines if line)
