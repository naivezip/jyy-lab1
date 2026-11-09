"""Local fake OpenAI-compatible SSE server for offline tests."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SSEEvent = tuple[float, dict[str, Any] | str]
DONE = "[DONE]"


def chunk(
    delta: dict[str, Any] | None = None,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "deepseek-flash",
        "choices": [],
    }
    if delta is not None or finish_reason is not None:
        payload["choices"] = [{"index": 0, "delta": delta or {}, "finish_reason": finish_reason}]
    if usage is not None:
        payload["usage"] = usage
    return payload


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.owner._serve(self, body)  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        pass


class FakeSSEServer:
    """Serve queued SSE scripts and record every request body."""

    def __init__(self, responses: list[list[SSEEvent]]) -> None:
        self.responses = [list(response) for response in responses]
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.owner = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"

    def start(self) -> FakeSSEServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> FakeSSEServer:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def _serve(self, handler: _Handler, body: bytes) -> None:
        request = json.loads(body)
        with self._lock:
            self.requests.append(request)
            script = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()
        try:
            for delay, payload in script:
                if delay:
                    time.sleep(delay)
                data = payload if isinstance(payload, str) else json.dumps(payload)
                handler.wfile.write(f"data: {data}\n\n".encode())
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            handler.close_connection = True
