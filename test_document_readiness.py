from scholarship_pipeline import (
    DocumentReadinessChecker,
    HybridEligibilityPipeline,
    UnifiedScholarshipIndexer,
)


def test_document_checker_builds_scheme_checklist_and_flags_missing_certificates():
    checker = DocumentReadinessChecker()
    result = checker.check(
        {
            "id": "need-based",
            "required_documents": [
                "income_certificate",
                "domicile_proof",
                "caste_certificate",
                "marksheet",
            ],
        },
        [
            {"filename": "family-income-certificate.pdf"},
            {"name": "residence-proof.jpg"},
            "Class12-transcript.pdf",
        ],
    )

    assert result["ready"] is False
    assert result["scheme_id"] == "need-based"
    assert result["summary"] == {"required": 4, "matched": 3, "missing": 1}
    assert result["missing_documents"] == ["caste_certificate"]
    checklist_by_type = {item["document_type"]: item for item in result["checklist"]}
    assert checklist_by_type["income_certificate"]["matched_files"] == ["family-income-certificate.pdf"]
    assert checklist_by_type["domicile_proof"]["status"] == "present"
    assert checklist_by_type["marksheet"]["status"] == "present"


def test_document_checker_reads_document_rules_and_matches_aliases():
    checker = DocumentReadinessChecker()
    result = checker.check(
        {
            "rules": [{
                "id": "required-documents",
                "field": "documents",
                "operator": "all_of",
                "value": ["income_certificate", "domicile_proof"],
            }],
        },
        ["income.pdf", "proof_of_domicile.png"],
    )

    assert result["ready"] is True
    assert result["missing_documents"] == []
    assert result["provided_document_types"] == ["income_certificate", "domicile_proof"]


def test_document_checker_accepts_uploaded_file_objects():
    class UploadedFile:
        filename = "family-income-certificate.pdf"

    result = DocumentReadinessChecker().check(
        {"required_documents": ["income_certificate"]},
        [UploadedFile()],
    )

    assert result["ready"] is True
    assert result["checklist"][0]["matched_files"] == ["family-income-certificate.pdf"]


def test_document_checker_does_not_claim_ready_without_scheme_requirements():
    result = DocumentReadinessChecker().check({"id": "unconfigured"}, ["income.pdf"])

    assert result["status"] == "not_configured"
    assert result["ready"] is None
    assert result["requirements_configured"] is False


def test_hybrid_pipeline_returns_readiness_without_precondition_block(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "documents.db"))
    try:
        result = HybridEligibilityPipeline(indexer).run(
            profile={},
            rules=[{
                "id": "documents-rule",
                "field": "documents",
                "operator": "all_of",
                "value": ["income_certificate", "domicile_proof"],
                "description": "Income and domicile documents are required.",
            }],
            uploaded_files=["income-certificate.pdf"],
        )
    finally:
        indexer.close()

    assert result["status"] == "evaluated"
    assert result["document_readiness"]["ready"] is False
    assert result["document_readiness"]["missing_documents"] == ["domicile_proof"]
    assert result["evaluation"]["eligible"] is False
