from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable


STATES = [
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
]

CATEGORIES = [
    "sc",
    "st",
    "obc",
    "ews",
    "general",
    "minority",
    "women",
    "female",
    "disabled",
    "transgender",
]


class PolicyRuleParser:
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def parse_policy_text(self, policy_text: str, source_name: str | None = None) -> dict[str, Any]:
        policy_text = (policy_text or "").strip()
        if not policy_text:
            return {
                "source_name": source_name,
                "policy_text": "",
                "rules": [],
                "metadata": {
                    "parsed_at": datetime.now(timezone.utc).isoformat(),
                    "parser": "heuristic",
                    "confidence": 0.0,
                },
                "warnings": ["Empty policy text provided."],
            }

        try:
            llm_result = self._llm_parse(policy_text)
            if llm_result:
                return {
                    "source_name": source_name,
                    "policy_text": policy_text,
                    **llm_result,
                    "metadata": {
                        **llm_result.get("metadata", {}),
                        "parsed_at": datetime.now(timezone.utc).isoformat(),
                        "parser": "llm",
                    },
                }
        except Exception:
            pass

        return self._heuristic_parse(policy_text, source_name=source_name)

    def _llm_parse(self, policy_text: str) -> dict[str, Any] | None:
        if not self.api_key:
            return None

        try:
            import openai
        except ImportError:
            return None

        prompt = (
            "You are converting scholarship policy text into structured JSON rules. "
            "Return only valid JSON with the following schema: "
            "{\"rules\": [{\"id\": \"string\", \"field\": \"state|category|annual_income|marks|course_level|documents|gender\", "
            "\"operator\": \"in|eq|contains|gte|lte|gt|lt|all_of\", \"value\": \"number|string|array\", "
            "\"description\": \"string\", \"required\": true}], \"metadata\": {\"confidence\": 0.0}}. "
            "Use annual_income in rupees, marks as numeric percentage, and state values as Indian state names. "
            "Do not add any explanation outside JSON.\n\nText:\n"
            f"{policy_text}"
        )

        completion = openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Extract evaluatable eligibility rules from policy language."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        content = completion.choices[0].message.content
        if not content:
            return None

        data = json.loads(content)
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            return None

        for rule in data["rules"]:
            rule.setdefault("required", True)
            if "id" not in rule:
                rule["id"] = f"rule-{len(data['rules'])}"

        return data

    def _heuristic_parse(self, policy_text: str, source_name: str | None = None) -> dict[str, Any]:
        text = self._normalize_text(policy_text)
        rules: list[dict[str, Any]] = []
        warnings: list[str] = []

        state_values = self._find_states(text)
        if state_values:
            rules.append(self._build_rule(
                "state",
                "in",
                state_values,
                "Candidate must be a resident of one of the required states.",
                source_text=text,
            ))

        category_values = self._find_categories(text)
        if category_values:
            rules.append(self._build_rule(
                "category",
                "in",
                [value.upper() if value.upper() in {"SC", "ST", "OBC", "EWS"} else value.title() for value in category_values],
                "Candidate must belong to one of the eligible categories.",
                source_text=text,
            ))

        income_rule = self._parse_income_rule(text)
        if income_rule:
            rules.append(income_rule)

        marks_rule = self._parse_marks_rule(text)
        if marks_rule:
            rules.append(marks_rule)

        if not rules:
            warnings.append("No explicit eligibility rules were detected using the built-in parser.")

        return {
            "source_name": source_name,
            "policy_text": policy_text,
            "rules": rules,
            "metadata": {
                "parsed_at": datetime.now(timezone.utc).isoformat(),
                "parser": "heuristic",
                "confidence": 0.8 if rules else 0.0,
            },
            "warnings": warnings,
        }

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _build_rule(
        self,
        field: str,
        operator: str,
        value: Any,
        description: str,
        source_text: str,
    ) -> dict[str, Any]:
        return {
            "id": f"rule-{field}",
            "field": field,
            "operator": operator,
            "value": value,
            "description": description,
            "required": True,
            "source_text": source_text,
        }

    def _find_states(self, text: str) -> list[str]:
        matches: list[str] = []
        # Use a lower-cased search to keep the output stable and evaluatable.
        lowered = text.lower()
        for state in STATES:
            if state in lowered:
                matches.append(state.title())
        return matches

    def _find_categories(self, text: str) -> list[str]:
        lowered = text.lower()
        matches: list[str] = []
        for category in CATEGORIES:
            if category in lowered:
                matches.append(category)

        # Canonicalize a few common labels so they match the matcher schema.
        canonical_map = {
            "female": "female",
            "women": "women",
            "general": "general",
            "minority": "minority",
            "sc": "SC",
            "st": "ST",
            "obc": "OBC",
            "ews": "EWS",
            "disabled": "disabled",
            "transgender": "transgender",
        }
        return [canonical_map.get(value, value.title()) for value in matches]

    def _parse_income_rule(self, text: str) -> dict[str, Any] | None:
        patterns = [
            r"(?:annual|family|household|parental)\s+(?:income|salary)\s+(?:should be|must be|is)\s*(?:less than|below|not more than|not exceeding|within|under|upto|up to|less than or equal to)?\s*₹?\s*(\d+(?:\.\d+)?)\s*(lakh|lac|crore|thousand|k|hundred)?",
            r"(?:income)\s*(?:should be|must be|is)\s*(?:less than|below|not more than|not exceeding|upto|up to|under)\s*₹?\s*(\d+(?:\.\d+)?)\s*(lakh|lac|crore|thousand|k|hundred)?",
            r"(?:income)\s*(?:should not|must not|above|exceed)\s*₹?\s*(\d+(?:\.\d+)?)\s*(lakh|lac|crore|thousand|k|hundred)?",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = float(match.group(1))
                unit = (match.group(2) or "").lower()
                value = self._money_to_rupees(amount, unit)
                operator = "lte"
                if "more than" in match.group(0).lower() or "above" in match.group(0).lower() or "exceed" in match.group(0).lower():
                    operator = "gt"
                description = f"Annual family income must be {('below' if operator == 'lte' else 'above')} ₹{value:,.0f}."
                return {
                    "id": "rule-income",
                    "field": "annual_income",
                    "operator": operator,
                    "value": value,
                    "description": description,
                    "required": True,
                    "source_text": text,
                }
        return None

    def _parse_marks_rule(self, text: str) -> dict[str, Any] | None:
        patterns = [
            r"(?:minimum|at least|not less than|minimum of|atleast)\s*(\d+(?:\.\d+)?)\s*%?\s*(?:marks?|percentage)",
            r"(\d+(?:\.\d+)?)\s*%\s*(?:marks?|percentage)\s*(?:minimum|required|needed)",
            r"(?:secured|score|obtained)\s*(?:at least|minimum)\s*(\d+(?:\.\d+)?)\s*%?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                return {
                    "id": "rule-marks",
                    "field": "marks",
                    "operator": "gte",
                    "value": value,
                    "description": f"Candidate must have at least {value}% marks.",
                    "required": True,
                    "source_text": text,
                }
        return None

    def _money_to_rupees(self, amount: float, unit: str) -> float:
        if unit in {"lakh", "lac"}:
            return amount * 100000
        if unit in {"crore"}:
            return amount * 10000000
        if unit in {"thousand", "k"}:
            return amount * 1000
        return amount


def extract_policy_rules(policy_text: str, source_name: str | None = None) -> dict[str, Any]:
    return PolicyRuleParser().parse_policy_text(policy_text, source_name=source_name)


def parse_policy_text(policy_text: str, source_name: str | None = None) -> dict[str, Any]:
    return extract_policy_rules(policy_text, source_name=source_name)


if __name__ == "__main__":
    sample_text = (
        "Applicant must be a resident of Maharashtra or Karnataka. "
        "Annual family income should be less than ₹2.5 lakh. "
        "Minimum 75% marks in Class 12 are required."
    )
    print(json.dumps(parse_policy_text(sample_text), indent=2, ensure_ascii=False))
