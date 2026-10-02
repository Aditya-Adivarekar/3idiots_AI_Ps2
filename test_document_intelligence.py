from io import BytesIO

from scholarship_pipeline import DocumentIntelligenceService


SAMPLE_CERTIFICATE_TEXT = """
INCOME CERTIFICATE
Certificate No: INC-2025-0194
Name of Applicant: Asha Sharma
Annual family income: Rs. 180000
Issued by: District Revenue Officer, Pune
Date of issue: 12/04/2025
"""


def test_extracts_key_values_with_evidence_and_marks_them_unverified():
    service = DocumentIntelligenceService(ocr_engine=lambda content, mime_type: SAMPLE_CERTIFICATE_TEXT)

    result = service.extract(b"image-bytes", filename="income-certificate.png")

    assert result["document_type"]["value"] == "income_certificate"
    assert result["fields"]["holder_name"]["value"] == "Asha Sharma"
    assert result["fields"]["annual_family_income"]["value"] == 180000
    assert "INC-2025-0194" in result["fields"]["certificate_number"]["evidence_text"]
    assert all(field["verification"]["status"] == "needs_verification" for field in result["fields"].values())
    assert result["verification_status"] == "needs_user_review"


def test_remote_llm_is_opt_in_and_unsubstantiated_fields_are_rejected():
    calls = []

    def llm_extractor(text):
        calls.append(text)
        return {
            "fields": {
                "holder_name": {"value": "Asha Sharma", "evidence_text": "Name of Applicant: Asha Sharma"},
                "category": {"value": "SC", "evidence_text": "Category: OBC"},
            }
        }

    service = DocumentIntelligenceService(
        ocr_engine=lambda content, mime_type: SAMPLE_CERTIFICATE_TEXT,
        llm_extractor=llm_extractor,
    )

    local_result = service.extract(b"doc", filename="certificate.png")
    assert not calls
    llm_result = service.extract(b"doc", filename="certificate.png", allow_remote_llm=True)

    assert len(calls) == 1
    assert llm_result["extraction_method"] == "ocr+llm"
    assert llm_result["fields"]["holder_name"]["value"] == "Asha Sharma"
    assert "category" not in llm_result["fields"]
    assert local_result["verification_status"] == "needs_user_review"


def test_confirmed_values_can_be_applied_to_student_profile_only_after_review():
    service = DocumentIntelligenceService(ocr_engine=lambda content, mime_type: SAMPLE_CERTIFICATE_TEXT)
    result = service.extract(b"doc", filename="income-certificate.png")

    reviewed = service.confirm_fields(result, {
        "annual_family_income": 175000,
        "holder_name": "Asha Sharma",
    })

    assert reviewed["fields"]["annual_family_income"]["verification"] == {
        "status": "verified",
        "verified_by_user": True,
    }
    assert reviewed["verified_profile_values"] == {"annual_income": 175000}
    assert reviewed["verification_status"] == "partially_verified"


def test_scanned_pdf_falls_back_to_page_ocr():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf = BytesIO()
    writer.write(pdf)

    service = DocumentIntelligenceService(ocr_engine=lambda content, mime_type: SAMPLE_CERTIFICATE_TEXT)
    result = service.extract(pdf.getvalue(), filename="income.pdf")

    assert result["extraction_method"] == "ocr"
    assert result["source_text_length"] > 0
    assert result["fields"]["annual_family_income"]["value"] == 180000
