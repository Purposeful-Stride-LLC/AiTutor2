"""A tiny stand-in for the Ollama HTTP API (version, tags, chat, pull)."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def fake_course(user_prompt: str) -> dict:
    ids = sorted(set(re.findall(r"^- (S\d+):", user_prompt, re.MULTILINE))) or ["S1"]
    subject = re.search(r"^Subject: (.+)$", user_prompt, re.MULTILINE)
    title = subject.group(1).strip() if subject else "Test course"
    return {
        "course_id": "fake-course",
        "title": f"{title} (built)",
        "audience": "adult",
        "goal": "Learn the material.",
        "duration_hint": "2 weeks",
        "sources": [{"id": i, "title": "model title", "note": "model note"} for i in ids]
        + [{"id": "S99", "title": "Invented Manual", "note": "hallucinated"}],
        "weeks": [
            {"week": "1", "title": "Foundations", "objective": "Know the basics.",
             "topics": ["pipes", "filters"], "activity": "Write a pipeline.",
             "source_ids": [ids[0], "S99"], "assessment": "Pipeline runs."},
            {"week": "2", "title": "Practice", "objective": "Apply it.",
             "topics": ["grep"], "activity": "Search logs.",
             "source_ids": ids, "assessment": "Finds the error lines."},
        ],
        "gaps": [],
        "tutor_notes": "Go slow.",
    }


class FakeOllama:
    def __init__(self, models: list[str] | None = None):
        self.models = list(models or [])
        self.requests: list[tuple[str, dict]] = []
        self.chat_reply: str | None = None  # override tutor replies
        self.chat_replies: list[str] = []  # queued tutor replies, used first, in order
        self.build_reply: str | None = None  # override the course JSON reply
        self.delay = 0.0  # seconds to wait between streamed chunks
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _json(self, code: int, obj: dict) -> None:
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _stream(self, chunks: list[dict]) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for c in chunks:
                    if outer.delay:
                        time.sleep(outer.delay)
                    self.wfile.write((json.dumps(c) + "\n").encode())
                    self.wfile.flush()

            def do_GET(self):
                outer.requests.append((self.path, {}))
                if self.path == "/api/version":
                    return self._json(200, {"version": "0.0.0-fake"})
                if self.path == "/api/tags":
                    return self._json(200, {"models": [{"name": m} for m in outer.models]})
                return self._json(404, {"error": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.requests.append((self.path, body))
                if self.path == "/api/pull":
                    outer.models.append(body["model"])
                    return self._stream([
                        {"status": "pulling manifest"},
                        {"status": "downloading", "completed": 50, "total": 100},
                        {"status": "success"},
                    ])
                if self.path == "/api/chat":
                    model = body.get("model")
                    if model not in outer.models and f"{model}:latest" not in outer.models:
                        return self._json(404, {"error": f'model "{model}" not found, try pulling it first'})
                    msgs = body.get("messages") or []
                    system = msgs[0]["content"] if msgs else ""
                    last = msgs[-1]["content"] if msgs else ""
                    if isinstance(body.get("format"), dict) and outer.build_reply is not None:
                        text = outer.build_reply
                    elif isinstance(body.get("format"), dict):
                        text = json.dumps(fake_course(last))
                    elif outer.chat_replies:
                        text = outer.chat_replies.pop(0)
                    elif outer.chat_reply is not None:
                        text = outer.chat_reply
                    else:
                        text = f"<think>hidden</think>Tutor says: {last[:60]}"
                        if "SCORE: N/10" in system:
                            text = "SCORE: 8/10\n" + text
                    half = len(text) // 2
                    return self._stream([
                        {"message": {"role": "assistant", "content": text[:half]}, "done": False},
                        {"message": {"role": "assistant", "content": text[half:]}, "done": False},
                        {"message": {"role": "assistant", "content": ""}, "done": True},
                    ])
                return self._json(404, {"error": "not found"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def chats(self) -> list[dict]:
        return [b for p, b in self.requests if p == "/api/chat"]
