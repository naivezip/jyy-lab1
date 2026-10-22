"""A tiny OpenAI-compatible / Anthropic-compatible SSE server for tests.

Runs a real HTTP server so the actual SDKs are exercised end to end, without
network access and without mocks of the transport layer.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

OPENAI_CHUNKS = [
    {"id": "1", "object": "chat.completion.chunk", "created": 0, "model": "m",
     "choices": [{"index": 0, "delta": {"role": "assistant", "content": None, "tool_calls": [
         {"index": 0, "id": "c1", "type": "function",
          "function": {"name": "read", "arguments": '{"pa'}}]}, "finish_reason": None}]},
    {"id": "1", "object": "chat.completion.chunk", "created": 0, "model": "m",
     "choices": [{"index": 0, "delta": {"tool_calls": [
         {"index": 0, "function": {"arguments": 'th": "demo.txt"}'}}]},
         "finish_reason": "tool_calls"}]},
    {"id": "1", "object": "chat.completion.chunk", "created": 0, "model": "m",
     "choices": [], "usage": {"prompt_tokens": 42, "completion_tokens": 9, "total_tokens": 51}},
]


def _event(name: str, data: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


ANTHROPIC_EVENTS = [
    _event("message_start", {"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "m", "content": [],
        "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 37, "output_tokens": 1}}}),
    _event("content_block_start", {"type": "content_block_start", "index": 0,
                                   "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
    _event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                   "delta": {"type": "thinking_delta", "thinking": "Need to read it."}}),
    _event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                   "delta": {"type": "signature_delta", "signature": "SIG-ABC"}}),
    _event("content_block_stop", {"type": "content_block_stop", "index": 0}),
    _event("content_block_start", {"type": "content_block_start", "index": 1,
                                   "content_block": {"type": "tool_use", "id": "tu_1", "name": "read", "input": {}}}),
    _event("content_block_delta", {"type": "content_block_delta", "index": 1,
                                   "delta": {"type": "input_json_delta", "partial_json": '{"path":'}}),
    _event("content_block_delta", {"type": "content_block_delta", "index": 1,
                                   "delta": {"type": "input_json_delta", "partial_json": ' "demo.txt"}'}}),
    _event("content_block_stop", {"type": "content_block_stop", "index": 1}),
    _event("message_delta", {"type": "message_delta",
                             "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                             "usage": {"output_tokens": 22}}),
    _event("message_stop", {"type": "message_stop"}),
]


class _Handler(BaseHTTPRequestHandler):
    protocol = "openai"

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        if self.protocol == "openai":
            for chunk in OPENAI_CHUNKS:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            for event in ANTHROPIC_EVENTS:
                self.wfile.write(event)
        self.wfile.flush()

    def log_message(self, *args) -> None:
        pass


def serve(protocol: str) -> tuple[HTTPServer, str]:
    handler = type("Handler", (_Handler,), {"protocol": protocol})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"
