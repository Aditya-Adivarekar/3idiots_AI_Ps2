from scholarship_pipeline import HybridEligibilityPipeline, UnifiedScholarshipIndexer
from scholarship_pipeline.ingest import ScholarshipRecord


def make_record(record_id, source_type, url, text):
    return ScholarshipRecord(
        id=record_id,
        title=f"{record_id} scholarship",
        organization="Test authority",
        source_id=record_id,
        source_type=source_type,
        url=url,
        description=text,
        eligibility=text,
        amount="Not specified",
        category="Any",
        state="Maharashtra",
        course_level="Any",
        gender="Any",
        income_band="Not specified",
        deadline="Not specified",
        document_hash=record_id,
        raw_text=text,
        fetched_at="2026-01-01T00:00:00+00:00",
    )


def test_hybrid_pipeline_evaluates_rules_and_retrieves_official_clauses(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "scholarships.db"))
    try:
        indexer.insert_record(make_record(
            "official",
            "government_portal",
            "https://scholarships.gov.in/notice",
            "Annual family income must not exceed 250000 rupees. Applicants must be residents of Maharashtra.",
        ))
        indexer.insert_record(make_record(
            "unofficial",
            "college_notice",
            "https://college.example/notice",
            "Annual family income must not exceed 250000 rupees.",
        ))

        captured = {}

        def explain(evaluation, clauses):
            captured["evaluation"] = evaluation
            captured["clauses"] = clauses
            evaluation["eligible"] = False
            return "Income is within the published limit."

        pipeline = HybridEligibilityPipeline(indexer, explanation_generator=explain)
        result = pipeline.run(
            {"annual_income": 200000},
            [{"id": "income", "field": "annual_income", "operator": "lte", "value": 250000}],
        )

        assert result["evaluation"]["eligible"] is True
        assert result["explanation"] == "Income is within the published limit."
        assert captured["evaluation"]["eligible"] is False
        assert captured["clauses"]
        assert all(clause["source_type"] == "government_portal" for clause in captured["clauses"])
        assert all("gov.in" in clause["source_url"] for clause in captured["clauses"])
    finally:
        indexer.close()


def test_hybrid_pipeline_audits_failed_condition_with_official_clause(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "audit.db"))
    try:
        indexer.insert_record(make_record(
            "official-income-rule",
            "government_portal",
            "https://scholarships.gov.in/notice",
            "Annual family income must not exceed 250000 rupees.",
        ))

        result = HybridEligibilityPipeline(indexer).run(
            {"annual_income": 300000},
            [{
                "id": "income-limit",
                "field": "annual_income",
                "operator": "lte",
                "value": 250000,
                "description": "Annual family income must not exceed 250000 rupees.",
            }],
        )

        assert result["failed_conditions"][0]["id"] == "income-limit"
        failure = result["failed_conditions"][0]
        assert failure["actual"] == 300000
        assert failure["expected"] == 250000
        assert failure["reason"]
        assert failure["condition"]["description"] == (
            "Annual family income must not exceed 250000 rupees."
        )
        assert failure["matching_official_clauses"][0]["clause"] == (
            "Annual family income must not exceed 250000 rupees."
        )
        assert failure["matching_official_clauses"][0]["source_url"] == (
            "https://scholarships.gov.in/notice"
        )
    finally:
        indexer.close()


def test_hybrid_pipeline_stops_for_missing_profile_fields(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "preconditions.db"))
    try:
        explanation_calls = []
        pipeline = HybridEligibilityPipeline(
            indexer,
            explanation_generator=lambda evaluation, clauses: explanation_calls.append(True) or "unexpected",
        )
        retrieval_calls = []
        pipeline.retriever.retrieve = lambda *args, **kwargs: retrieval_calls.append(True) or []

        result = pipeline.run(
            {"annual_income": 180000, "category": " "},
            [
                {"id": "domicile-rule", "field": "state", "operator": "eq", "value": "Maharashtra"},
                {"id": "category-rule", "field": "category", "operator": "in", "value": ["SC", "ST"]},
                {"id": "income-rule", "field": "annual_income", "operator": "lte", "value": 250000},
                {"id": "optional-gender", "field": "gender", "operator": "eq", "value": "female", "required": False},
            ],
        )

        assert result["status"] == "needs_input"
        assert result["evaluation"] is None
        assert {item["field"] for item in result["missing_fields"]} == {"state", "category"}
        assert "domicile" in result["follow_up_questions"][0].lower()
        assert any("category" in question.lower() for question in result["follow_up_questions"])
        assert not retrieval_calls
        assert not explanation_calls
    finally:
        indexer.close()


def test_domicile_profile_alias_satisfies_state_precondition(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "domicile.db"))
    try:
        result = HybridEligibilityPipeline(indexer).run(
            {"domicile": "Maharashtra", "category": "SC"},
            [
                {"id": "state-rule", "field": "state", "operator": "eq", "value": "Maharashtra"},
                {"id": "category-rule", "field": "category", "operator": "eq", "value": "SC"},
            ],
        )

        assert result["status"] == "evaluated"
        assert result["evaluation"]["eligible"] is True

        reverse_alias_result = HybridEligibilityPipeline(indexer).run(
            {"state": "Maharashtra", "category": "SC"},
            [
                {"id": "domicile-field-rule", "field": "domicile", "operator": "eq", "value": "Maharashtra"},
                {"id": "category-rule", "field": "category", "operator": "eq", "value": "SC"},
            ],
        )
        assert reverse_alias_result["status"] == "evaluated"
        assert reverse_alias_result["evaluation"]["eligible"] is True
    finally:
        indexer.close()
