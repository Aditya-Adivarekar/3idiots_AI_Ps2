from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .application_guidance import ApplicationGuidanceService


MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def create_request_handler(
    guidance_service: ApplicationGuidanceService | None = None,
    allowed_origins: set[str] | None = None,
) -> type[BaseHTTPRequestHandler]:
    service = guidance_service or ApplicationGuidanceService()
    origins = allowed_origins or DEFAULT_ALLOWED_ORIGINS

    class CopilotRequestHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._add_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send_json(404, {"error": "Not found"})
                return
            self._send_json(200, {"status": "ok"})

        def do_POST(self) -> None:
            if self.path != "/api/copilot/guidance":
                self._send_json(404, {"error": "Not found"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length"})
                return
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                status = 413 if content_length > MAX_REQUEST_BYTES else 400
                self._send_json(status, {"error": "Invalid request size"})
                return
            try:
                payload = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": "Request body must be valid JSON"})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "Request body must be a JSON object"})
                return
            self._send_json(200, service.guide(payload))

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _add_cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin in origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._add_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return CopilotRequestHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Application Copilot guidance API backed by Qwen when configured.")
    parser.add_argument("--host", default=os.getenv("COPILOT_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("COPILOT_API_PORT", "8001")))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), create_request_handler())
    print(f"Application Copilot API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()