from scholarship_pipeline import ApplicationGuidanceService
from scholarship_pipeline.copilot_api import create_request_handler
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json


class FakeQwen:
    token = "configured"

    def __init__(self):
        self.context = None

    def generate_application_guidance(self, context):
        self.context = context
        return "Confirm the income certificate against the official checklist."


def test_guidance_uses_qwen_with_only_non_personal_application_metadata():
    qwen = FakeQwen()
    service = ApplicationGuidanceService(qwen_service=qwen)

    result = service.guide({
        "scheme_title": "Merit scholarship",
        "official_source_url": "https://scholarships.gov.in/merit",
        "deadline": "2026-10-20",
        "deadline_reviewed": True,
        "no_deadline": False,
        "stage": "preparing",
        "missing_documents": ["Income certificate"],
        "profile": {"annual_income": 180000},
        "uploaded_filenames": ["asha-sharma-income.pdf"],
    })

    assert result["provider"] == "huggingface_qwen"
    assert "income certificate" in result["guidance"].lower()
    assert qwen.context["scheme_title"] == "Merit scholarship"
    assert "profile" not in qwen.context
    assert "uploaded_filenames" not in qwen.context


def test_guidance_has_truthful_fallback_without_qwen_credentials():
    result = ApplicationGuidanceService().guide({
        "scheme_title": "Merit scholarship",
        "requirements_configured": True,
        "deadline_reviewed": False,
        "missing_documents": ["Marksheets"],
    })

    assert result["provider"] == "deterministic_fallback"
    assert "Marksheets" in result["guidance"]
    assert "deadline" in result["guidance"].lower()


def test_local_copilot_api_returns_guidance_and_restricts_cors_origin():
    service = ApplicationGuidanceService()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        create_request_handler(service, {"http://localhost:8000"}),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = Request(
            f"{base_url}/api/copilot/guidance",
            data=json.dumps({"scheme_title": "Merit", "requirements_configured": True}).encode(),
            headers={"Content-Type": "application/json", "Origin": "http://localhost:8000"},
            method="POST",
        )
        with urlopen(request) as response:
            payload = json.loads(response.read())
            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8000"
        assert payload["provider"] == "deterministic_fallback"
        assert "official scheme page" in payload["guidance"]

        denied_origin = Request(
            f"{base_url}/api/copilot/guidance",
            data=b'{"scheme_title":"Merit"}',
            headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
            method="POST",
        )
        with urlopen(denied_origin) as response:
            assert response.headers.get("Access-Control-Allow-Origin") is None

        invalid_route = Request(f"{base_url}/unexpected", method="POST", data=b"{}")
        try:
            urlopen(invalid_route)
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("Unknown API routes should return 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
