# YojanaSetu Implementation Checklist

## Scholarship Data and Rules

- [x] Ingest HTML notices and PDF sources into a unified SQLite scholarship schema.
- [x] Index scholarship content for full-text search with SQLite FTS5.
- [x] Parse policy text into evaluator-compatible rule JSON, with an LLM path and deterministic extraction fallback.
- [x] Evaluate normalized rule operators, numeric boundaries, missing values, aliases, and per-rule evidence deterministically.
- [x] Load the 2026-27 scholarship eligibility rules from `dataset_2_eligibility_rules_2026_27.json`.
- [x] Keep eligibility (`ELIGIBLE`, `NOT_ELIGIBLE`, `NEEDS_MORE_INFORMATION`) separate from application availability, application gates, cycle applicability, and selection gates.
- [x] Handle grouped OR qualification paths, strict/inclusive comparisons, conditional rules, and current-evidence requirements.
- [x] Preserve rule-level source URLs, version history, dates, conflicts, stale flags, and withdrawn-rule history.
- [x] Simulate temporary profile changes without mutating the saved profile.

## Student Profile

- [x] Define a versioned canonical profile schema for domicile/state, course, study year, category, income, marks, gender, and documents.
- [x] Normalize common profile aliases and save/reload profile data.
- [x] Reuse the same saved profile across multiple scheme evaluations.
- [x] Detect missing or blank required profile values and return targeted follow-up questions before evaluation.

## Documents

- [x] Build per-scheme document checklists from explicit requirements or document rules.
- [x] Match uploaded-file names and metadata to common certificate types and flag missing checklist items.
- [x] Extract candidate certificate fields using PDF text extraction, OCR, and optional Qwen structuring.
- [x] Return candidate values with evidence excerpts, extraction method, confidence, and user-verification state.
- [x] Require user confirmation before applying extracted values to the student profile.
- [x] Flag profile/document mismatches, expired or unreadable evidence, missing evidence, and instruction-like text as review issues rather than silent eligibility failures.

## Application Copilot

- [x] Track shortlisted schemes as local application records.
- [x] Configure scheme-specific document requirements and compare them against selected filenames.
- [x] Track a user-entered deadline and require the user to confirm it or record that none is published.
- [x] Track shortlisted, preparing, and submitted progress states.
- [x] Calculate a ready-to-apply state only when requirements are configured, required filenames match, and deadline status is reviewed.
- [x] Provide per-scheme next-step guidance through the local API, with a deterministic offline fallback.
- [x] Keep profile fields and uploaded filenames out of Copilot guidance requests.

## Verification Coverage

- [x] Test rule boundaries, OR paths, evidence gaps, document inconsistencies, status separation, prompt-injection handling, and what-if profile immutability using the supplied datasets.
- [x] Test document extraction consent, evidence grounding, user confirmation, and scanned-PDF OCR fallback.
- [x] Test Copilot local persistence, filename matching, deadline gating, and guidance API behavior.
- [x] Preserve the supplied 97-rule and 60-edge-case dataset files without editing their source records.

## Setup and Scope Notes

- Hugging Face Qwen3-8B requires a local `HF_TOKEN`. When no token is configured or inference fails, deterministic guidance/explanations are used.
- Image/scanned-PDF OCR requires the Tesseract executable in addition to the Python packages in `requirements.txt`.
- The browser Copilot stores filenames and document types only; it does not upload or inspect file bytes. Certificate OCR/extraction is available as a Python service and is not a browser upload workflow.
- Scheme requirements and dates must be checked against current official sources; the demo does not invent or automatically verify them.
- Dataset edge cases are retained in the source JSON. Automated tests cover representative high-risk cases; not every one of the 60 edge records is currently run as a parameterized test.
