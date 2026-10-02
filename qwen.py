from __future__ import annotations

import json
import os
import re
from typing import Any


DEFAULT_QWEN_MODEL = "Qwen/Qwen3-8B"


class QwenInferenceService:
    """Hugging Face Inference API adapter for Qwen3-8B explanations and extraction."""

    def __init__(
        self,
        token: str | None = None,
        model: str = DEFAULT_QWEN_MODEL,
        client: Any | None = None,
    ) -> None:
        self.token = token or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        self.model = model
        self.client = client

    def generate_explanation(
        self,
        evaluation: dict[str, Any],
        source_clauses: list[dict[str, Any]],
    ) -> str:
        response = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Explain the supplied eligibility evaluation in plain language. "
                        "The deterministic evaluation is authoritative and immutable: do not "
                        "recalculate, reinterpret, or change eligibility. Cite only the supplied "
                        "official source clauses. Clearly say when no supporting clause was retrieved. "
                        "Do not invent deadlines, rules, or requirements. Return explanation text only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Evaluation JSON:\n"
                        f"{json.dumps(evaluation, ensure_ascii=False)}\n"
                        "Official source clauses JSON:\n"
                        f"{json.dumps(source_clauses, ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=500,
        )
        return response.strip()

    def extract_document_fields(self, ocr_text: str) -> dict[str, Any]:
        fields = (
            "holder_name, certificate_number, domicile_state, category, annual_family_income, "
            "marks_percentage, issue_date, valid_until, issuing_authority, institution_name"
        )
        response = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract only certificate fields directly supported by OCR text. "
                        "Return one JSON object with optional document_type and a fields object. "
                        "Each field must be an object with value and evidence_text, where evidence_text "
                        "is an exact quote from the supplied OCR text. Omit uncertain fields. Never infer "
                        "or complete personal information. Output JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Allowed fields: {fields}\nOCR text:\n{ocr_text}",
                },
            ],
            temperature=0,
            max_tokens=900,
        )
        return self._parse_json(response)

    def generate_application_guidance(self, application: dict[str, Any]) -> str:
        response = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Guide the applicant's next step using only the supplied shortlist, document checklist, "
                        "deadline review state, and official source link. Do not claim eligibility, invent "
                        "requirements or dates, or say a file is valid. If requirements or a deadline are "
                        "unknown, tell the user to check the official page. Keep the answer concise and actionable."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(application, ensure_ascii=False),
                },
            ],
            temperature=0.2,
            max_tokens=300,
        )
        return response.strip()

    def _chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not self.token:
            raise RuntimeError("Set HF_TOKEN to enable remote Qwen inference")
        client = self.client or self._create_client()
        response = client.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ValueError("Hugging Face returned an invalid chat-completion response") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Qwen returned an empty response")
        return self._remove_thinking(content).strip()

    def _create_client(self) -> Any:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("Qwen inference requires huggingface_hub. Install it with `pip install huggingface_hub`.") from exc
        self.client = InferenceClient(model=self.model, token=self.token)
        return self.client

    def _remove_thinking(self, response: str) -> str:
        return re.sub(r"<think>.*?</think>", "", response, flags=re.IGNORECASE | re.DOTALL)

    def _parse_json(self, response: str) -> dict[str, Any]:
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Qwen response did not contain a JSON object")
        payload = json.loads(text[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Qwen extraction response must be a JSON object")
        return payload
