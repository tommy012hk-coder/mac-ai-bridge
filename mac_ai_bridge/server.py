"""A small loopback-only HTTP interface to the local UI automation."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from ipaddress import ip_address
from urllib.parse import urlsplit

from .automation import APPS, MAX_PROMPT_LENGTH, BridgeError, ask


MAX_BODY_BYTES = 16_384


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "mac-ai-bridge/0.1"

    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/health":
            self.send_error(404, "Use GET /health or POST /ask")
            return
        self._send_json(200, {"ok": True, "apps": sorted(APPS)})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/ask":
            self.send_error(404, "Use POST /ask")
            return
        if not self._is_loopback_request():
            self.send_error(403, "Requests must originate from localhost")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(411, "Content-Length is required")
            return
        if length < 1 or length > MAX_BODY_BYTES:
            self.send_error(413, f"Body must be between 1 and {MAX_BODY_BYTES} bytes")
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415, "Content-Type must be application/json")
            return
        try:
            request = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400, "Request body must be valid JSON")
            return
        if not isinstance(request, dict):
            self.send_error(400, "Request body must be a JSON object")
            return
        app = request.get("app", "copilot")
        prompt = request.get("prompt")
        if not isinstance(app, str) or app not in APPS:
            self.send_error(400, f"app must be one of: {', '.join(sorted(APPS))}")
            return
        if not isinstance(prompt, str) or not prompt.strip():
            self.send_error(400, "prompt must be a non-empty string")
            return
        if len(prompt) > MAX_PROMPT_LENGTH:
            self.send_error(413, f"prompt must be at most {MAX_PROMPT_LENGTH} characters")
            return
        try:
            response = ask(app, prompt)
        except BridgeError as exc:
            self._send_json(502, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(response.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(response.encode("utf-8"))

    def _is_loopback_request(self) -> bool:
        try:
            host = self.headers.get("Host", "").split(":", 1)[0].strip("[]")
            return ip_address(self.client_address[0]).is_loopback and host.lower() in {
                "localhost",
                "127.0.0.1",
                "::1",
            }
        except ValueError:
            return False

    def _send_json(self, status: int, value: dict[str, object]) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Do not log request content; standard access details remain on stderr.
        super().log_message(format, *args)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    if not ip_address(host).is_loopback:
        raise ValueError("The bridge may only bind to a loopback address")
    server = HTTPServer((host, port), BridgeHandler)
    print(f"mac-ai-bridge listening at http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mac-ai-bridge", flush=True)
    finally:
        server.server_close()
