from types import SimpleNamespace

from scholarship_pipeline import (
    DocumentIntelligenceService,
    HybridEligibilityPipeline,
    QwenInferenceService,
    UnifiedScholarshipIndexer,
)


class FakeInferenceClient:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        content = next(self.contents)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class FakeQwenService:
    token = "test-token"

    def __init__(self):
        self.explanation_calls = 0
        self.extraction_calls = 0

    def generate_explanation(self, evaluation, source_clauses):
        self.explanation_calls += 1
        return "Qwen explanation"

    def extract_document_fields(self, ocr_text):
        self.extraction_calls += 1
        return {
            "fields": {
                "holder_name": {
                    "value": "Asha Sharma",
                    "evidence_text": "Name of Applicant: Asha Sharma",
                }
            }
        }


def test_qwen_provider_synthesizes_explanation_from_evaluation_and_citations():
    client = FakeInferenceClient(["The income condition passes based on the provided profile."])
    service = QwenInferenceService(token="test-token", client=client)

    explanation = service.generate_explanation(
        {"eligible": True, "passed_count": 1, "total_requirements": 1},
        [{"clause": "Income below Rs. 2.5 lakh", "source_url": "https://example.gov.in/rule"}],
    )

    assert explanation.startswith("The income condition")
    assert client.calls[0]["messages"][0]["role"] == "system"
    assert "immutable" in client.calls[0]["messages"][0]["content"]
    assert "https://example.gov.in/rule" in client.calls[0]["messages"][1]["content"]


def test_qwen_provider_extracts_json_from_thinking_wrapped_response():
    client = FakeInferenceClient([
        '<think>Read the income value.</think>{"fields":{"annual_family_income":{"value":180000,"evidence_text":"Income: Rs. 180000"}}}'
    ])
    service = QwenInferenceService(token="test-token", client=client)

    extraction = service.extract_document_fields("Income: Rs. 180000")

    assert extraction["fields"]["annual_family_income"]["value"] == 180000
    assert client.calls[0]["temperature"] == 0


def test_qwen_provider_generates_bounded_application_next_step():
    client = FakeInferenceClient(["Check the official page for the current date, then upload your marksheet."])
    service = QwenInferenceService(token="test-token", client=client)
    context = {
        "scheme_title": "Merit scholarship",
        "deadline_reviewed": False,
        "missing_documents": ["Marksheet"],
    }

    guidance = service.generate_application_guidance(context)

    assert "official page" in guidance
    assert "Do not claim eligibility" in client.calls[0]["messages"][0]["content"]
    assert "Marksheet" in client.calls[0]["messages"][1]["content"]


def test_qwen_provider_requires_token_before_remote_calls():
    service = QwenInferenceService(token="", client=FakeInferenceClient([]))

    try:
        service.generate_explanation({}, [])
    except RuntimeError as error:
        assert "HF_TOKEN" in str(error)
    else:
        raise AssertionError("Qwen calls must require an explicit Hugging Face token")


def test_hybrid_pipeline_uses_configured_qwen_for_explanations(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "qwen.db"))
    qwen = FakeQwenService()
    try:
        result = HybridEligibilityPipeline(indexer, qwen_service=qwen).run({}, [])
    finally:
        indexer.close()

    assert result["explanation"] == "Qwen explanation"
    assert result["explanation_provider"] == "huggingface_qwen_or_fallback"
    assert qwen.explanation_calls == 1


def test_document_intelligence_only_sends_text_to_qwen_after_consent():
    qwen = FakeQwenService()
    service = DocumentIntelligenceService(
        ocr_engine=lambda content, mime_type: "Name of Applicant: Asha Sharma",
        qwen_service=qwen,
    )

    service.extract(b"image", filename="certificate.png")
    assert qwen.extraction_calls == 0

    result = service.extract(b"image", filename="certificate.png", allow_remote_llm=True)

    assert qwen.extraction_calls == 1
    assert result["fields"]["holder_name"]["value"] == "Asha Sharma"
