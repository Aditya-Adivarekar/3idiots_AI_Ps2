# Scholarship Ingestion & Indexing Pipeline

This package builds a unified, searchable index for scholarship records coming from:

- government portals
- college notice boards
- PDF documents

The service normalizes each source into a common schema and stores the data in SQLite with an FTS-backed search layer.

## Quick start

```bash
pip install -r requirements.txt
python scholarship_pipeline/ingest.py --db scholarship_pipeline/data/scholarships.db --sources scholarship_pipeline/sample_sources.json --search "merit"
```

## Unified schema

The SQLite database stores the schema defined in `schema.sql` with tables for:

- `data_sources`
- `scholarships`
- `scholarships_fts`

Common fields include:

- `title`
- `organization`
- `source_type`
- `url`
- `description`
- `eligibility`
- `amount`
- `category`
- `state`
- `course_level`
- `gender`
- `income_band`
- `deadline`
- `document_hash`
- `raw_text`

The SQLite schema also includes `scholarship_rule_versions`, which retains source-scoped rule history and update metadata.

## Dataset criteria engine

`DatasetEligibilityEngine` consumes `dataset_2_eligibility_rules_2026_27.json` directly; it supports the dataset's symbolic/uppercase operators, inclusive and strict numeric boundaries, mandatory missing-value behavior, OR qualification groups, and current-evidence gates. `eligibility_status` is one of `ELIGIBLE`, `NOT_ELIGIBLE`, or `NEEDS_MORE_INFORMATION`; `application_status`, `application_gate_status`, `current_cycle_status`, and `selection_status` remain separate. Only `verified_current` rules are evaluated; unresolved/conditional rule evidence blocks a decision rather than being guessed. Optional and non-eligibility scopes do not disqualify applicants.

```python
from scholarship_pipeline import DatasetEligibilityEngine

engine = DatasetEligibilityEngine.from_json("dataset_2_eligibility_rules_2026_27.json")
result = engine.evaluate(
	"GOV02",
	{
		"gender": "female",
		"institution_approval": "AICTE-approved",
		"entry_year": "first_year",
		"family_income": 800000,
		"girls_per_family_receiving_scheme": 1,
		"gap_after_qualifying_exam_years": 1,
	},
	application_context={"today": "2026-10-02"},
)
```

`simulate` evaluates a temporary cloned profile and returns before/after rule results with `SIMULATION_ONLY` and `PROFILE_UNCHANGED` flags. Document evidence issues (mismatch, expiry, unreadable scans, or instruction-like text) are review flags, not eligibility failures. Rule source links and citation fields are returned with each rule result; absent page/clause data stays absent. The dataset tests read the source JSON directly and cover exact/strict thresholds, OR paths, evidence gaps, profile-document mismatches, invalid uploads, prompt injection, deadlines, and what-if isolation.

## Typical ingestion flow

1. Read source definitions from JSON.
2. Fetch HTML or PDF content from each source.
3. Normalize text and extract eligibility metadata.
4. Upsert the source and scholarship record into SQLite.
5. Search using the FTS virtual table.

## Hybrid eligibility pipeline

`HybridEligibilityPipeline` combines three separate stages:

1. The deterministic matcher evaluates each supplied rule against the student profile. This evaluation is authoritative.
2. `OfficialClauseRetriever` searches the FTS index for relevant clauses and returns only records marked as government/official sources or hosted on a government domain. Each result includes its source URL and record ID.
3. Qwen3-8B can synthesize plain-language context from the fixed evaluation and retrieved clauses. Its output cannot change the evaluation. To enable Hugging Face inference, install requirements and set `HF_TOKEN`; without a token or if inference fails, the pipeline returns a deterministic explanation.

The Application Copilot browser page keeps shortlist, documents, and deadlines in local storage. To enable its Qwen “Get next step” action, run the local API in a second terminal while serving the dashboard on port 8000:

```powershell
$env:HF_TOKEN = "your Hugging Face user-access token"
python -m scholarship_pipeline.copilot_api --host 127.0.0.1 --port 8001
```

Keep the token in an environment variable, never in browser JavaScript. The browser sends only scheme title/source, checklist status, missing document labels, deadline review status, and application stage to `http://127.0.0.1:8001`; profile fields and uploaded filenames are excluded. If the API is stopped, checklist and deadline tracking continue locally and the page shows the next deterministic action.

Example:

```python
from scholarship_pipeline import HybridEligibilityPipeline, UnifiedScholarshipIndexer

indexer = UnifiedScholarshipIndexer("scholarship_pipeline/data/scholarships.db")
try:
	pipeline = HybridEligibilityPipeline(indexer)
	result = pipeline.run(
		profile={"annual_income": 180000, "state": "Maharashtra"},
		rules=[
			{"id": "income-limit", "field": "annual_income", "operator": "lte", "value": 250000},
			{"id": "domicile", "field": "state", "operator": "eq", "value": "Maharashtra"},
		],
	)
finally:
	indexer.close()
```

The returned object separates `evaluation`, cited `source_clauses`, per-rule `audit`, `failed_conditions`, and `explanation`. Each audit item includes the condition description, field/operator, actual and expected values, failure reason, and matching official clause citations. If no official text is found, `matching_official_clauses` is empty rather than inferred. Pass `scholarship_id` to scope retrieval to a single indexed scholarship.

Before evaluation, required profile fields are validated against the rule set. If any are missing or blank, the pipeline returns `status: "needs_input"`, `evaluation: null`, `missing_fields`, and targeted `follow_up_questions`; matching, clause retrieval, and explanation generation are skipped. Optional rules (`required: false`) do not block evaluation. Domicile/state and category aliases are supported.

### Document readiness

`DocumentReadinessChecker` builds a checklist from a scheme's `required_documents` or its `documents` rules, then matches those requirements against uploaded filename strings or metadata objects (`filename`/`name` plus optional `document_type`). Common income, domicile, caste/category, marksheet, bank, identity, admission, and fee document aliases are normalized. Pass `uploaded_files` to `HybridEligibilityPipeline.run` or `StudentProfileService.evaluate_schemes`; the result includes `document_readiness.checklist`, `missing_documents`, and counts. If no scheme requirements are configured, status is `not_configured` and `ready` is `null`, not a false assurance. File contents are not opened or validated; filename matches only indicate a likely document type.

```python
result = pipeline.run(
	profile=profiles.get_profile(),
	rules=[{"field": "documents", "operator": "all_of", "value": ["income_certificate", "domicile_proof"]}],
	uploaded_files=["family-income-certificate.pdf", {"filename": "residence-proof.jpg"}],
)
```

### Document intelligence and user verification

`DocumentIntelligenceService` extracts candidate values such as holder name, certificate number, domicile, category, annual income, marks, issue/expiry dates, and issuing authority. Text PDFs are parsed directly; scanned PDFs and raster images use OCR. Install the Python packages in `requirements.txt` and install the Tesseract OCR executable for local OCR. Qwen3-8B extraction is optional: set `HF_TOKEN` and explicitly pass `allow_remote_llm=True` to send OCR text to Hugging Face. Remote extraction is off by default because certificates contain sensitive information.

Each returned field includes its evidence excerpt, extraction method, confidence, and `needs_verification` status. Full OCR text and uploaded bytes are not returned or persisted. Call `confirm_fields` with the user's accepted or corrected values; only verified domicile, category, income, and marks are emitted as `verified_profile_values` for updating the saved profile. This is a review aid, not certificate authenticity validation.

```python
from scholarship_pipeline import DocumentIntelligenceService, StudentProfileService

documents = DocumentIntelligenceService()
extraction = documents.extract(uploaded_file, allow_remote_llm=False)
reviewed = documents.confirm_fields(extraction, {
    "annual_family_income": 180000,
    "domicile_state": "Maharashtra",
})
profiles.update(reviewed["verified_profile_values"])
```

### Rule version history and source audit

`RuleVersionTracker` stores each rule version by scheme, stable rule ID (or field when no ID is present), and source URL. Identical content from a source only refreshes its observation date; a changed condition or description increments that source's version. Use `complete_snapshot=True` only when the supplied list is the full source snapshot; omitted rules are then marked withdrawn without deleting their history.

```python
from scholarship_pipeline import RuleVersionTracker

tracker = RuleVersionTracker(indexer.conn, stale_after_days=365)
tracker.record_rules(
	scheme_id="scheme-1",
	rules=parsed_policy["rules"],
	source_url="https://scholarships.gov.in/scheme-1",
	source_name="National Scholarship Portal",
	source_updated_at="2026-04-15",
	complete_snapshot=True,
)
audit = tracker.audit(scheme_id="scheme-1")
history = tracker.get_history("scheme-1", "rule-income")
```

`audit` flags different current conditions for the same scheme/rule across sources as conflicts. It flags old source update dates as outdated; when a published update date is absent, it falls back to `last_seen_at` and identifies that basis. Rule rows retain version, source link/name, source update date, first/last seen dates, and withdrawal date.

## Reusable student profile

`STUDENT_PROFILE_SCHEMA` defines the versioned canonical profile fields: state, course level, year of study, category, annual income in rupees, marks percentage, gender, and documents. `StudentProfileService` normalizes aliases, saves the profile to a versioned JSON file, and can reuse one saved profile across multiple scheme rules:

```python
from scholarship_pipeline import StudentProfileService

profiles = StudentProfileService("data/student-profile.json")
profiles.save({"domicile": "Maharashtra", "annual_income": 180000, "marks": 82})
results = profiles.evaluate_schemes(pipeline, [
	{"id": "income-scheme", "rules": [{"field": "annual_income", "operator": "lte", "value": 250000}]},
	{"id": "merit-scheme", "rules": [{"field": "marks", "operator": "gte", "value": 75}]},
])
```

The dashboard uses the same canonical fields through `student-profile.js`; its `YojanaSetuProfile` API provides `load`, `save`, `update`, `forEvaluation`, `evaluateMany`, and `subscribe`. Browser data stays in versioned local storage on that device.

## Files in this package

- `ingest.py` — ingestion and indexing logic
- `hybrid.py` — deterministic evaluation, official-clause retrieval, and explanation synthesis
- `document_readiness.py` — scheme checklists and uploaded filename matching
- `document_intelligence.py` — OCR/LLM-assisted certificate field extraction and verification
- `rule_versions.py` — source-scoped rule history and stale/conflict auditing
- `qwen.py` — Hugging Face Qwen3-8B explanation and extraction adapter
- `application_guidance.py` — privacy-minimized, next-step guidance and fallback
- `copilot_api.py` — loopback-only HTTP endpoint for the browser Copilot
- `student_profile.py` — canonical profile schema, persistence, and multi-scheme reuse
- `schema.sql` — unified storage schema
- `sample_sources.json` — example input sources
- `fixtures/` — sample HTML and PDF test content
