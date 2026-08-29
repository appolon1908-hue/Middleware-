"""HTTP entrypoint for the Middleware automation control plane."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .service import AutomationError, AutomationService


SERVICE = AutomationService(state_path=os.environ.get("AUTOMATION_STATE_PATH"))


class AutomationHandler(BaseHTTPRequestHandler):
    server_version = "CodestraAutomation/0.1"

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        try:
            body = self._read_json()
            path = urlparse(self.path).path
            result = self._route(method, path, body)
            self._json(200, result)
        except AutomationError as exc:
            self._json(exc.status, exc.body())
        except json.JSONDecodeError:
            self._json(400, {"error": "BAD_JSON", "message": "request body must be JSON"})

    def _route(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        parts = [part for part in path.split("/") if part]
        if method == "POST" and path == "/v2/automation/jobs/claim":
            return SERVICE.claim_job(body)
        if method == "POST" and path == "/v2/automation/jobs/reconcile":
            return SERVICE.reconcile_jobs(body)
        if method == "POST" and path == "/v2/automation/commands":
            return SERVICE.submit_command(body, self.headers.get("Idempotency-Key", ""))
        if method == "GET" and len(parts) == 4 and parts[:3] == ["v2", "automation", "commands"]:
            return SERVICE.get_command(parts[3])
        if method == "GET" and len(parts) == 4 and parts[:3] == ["v2", "automation", "jobs"]:
            return SERVICE.get_job(parts[3])
        if method == "POST" and len(parts) == 5 and parts[:3] == ["v2", "automation", "jobs"]:
            job_id, action = parts[3], parts[4]
            if action == "heartbeat":
                return SERVICE.heartbeat_job(job_id, body)
            if action == "steps":
                return SERVICE.record_step(job_id, body)
            if action == "complete":
                return SERVICE.complete_job(job_id, body)
            if action == "fail":
                return SERVICE.fail_job(job_id, body)
        if method == "POST" and len(parts) == 6 and parts[:3] == ["v2", "automation", "dead-letters"] and parts[4] == "replay":
            return SERVICE.replay_dead_letter(parts[3], body)
        if method == "GET" and len(parts) == 4 and parts[:3] == ["v2", "automation", "capabilities"]:
            return SERVICE.capability(parts[3])
        raise AutomationError(404, "NOT_FOUND", "route does not exist")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise AutomationError(400, "BAD_JSON", "request body must be a JSON object")
        return value

    def _json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8095) -> None:
    ThreadingHTTPServer((host, port), AutomationHandler).serve_forever()


if __name__ == "__main__":
    run()
