"""WP-R6/#169: execute real probes, including failure, without Docker."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import yaml

from shared.runtime_provenance import install_version_route


ROOT = Path(__file__).resolve().parents[1]
PORTS = {
    "ingestion_service": 8000,
    "vector_store_service": 8002,
    "llm_service": 8000,
    "rag_orchestrator": 8000,
    "gradio": 7860,
}


@pytest.fixture
def probe_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            responses = {
                "/health": (200, b'{"status":"ok"}'),
                "/failed": (503, b'{"status":"failed"}'),
                "/wrong": (200, b'{"status":"failed"}'),
                "/malformed": (200, b"not json"),
                "/": (200, b"<html>UI</html>"),
            }
            code, body = responses.get(self.path, (404, b"missing"))
            self.send_response(code)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def run_probe(url, *args):
    return subprocess.run(
        [sys.executable, "-m", "shared.healthcheck", url, "--timeout", "0.5", *args],
        cwd=ROOT,
        capture_output=True,
        timeout=5,
        check=False,
    )


@pytest.mark.parametrize("service,port", PORTS.items())
def test_compose_probe_executes_and_uses_container_port(service, port, probe_server):
    config = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    health = config["services"][service]["healthcheck"]
    command = health["test"]
    assert command[:4] == ["CMD", "python3", "-m", "shared.healthcheck"]
    path = "/" if service == "gradio" else "/health"
    assert command[4] == f"http://127.0.0.1:{port}{path}"
    # Execute the actual Compose argument vector with only interpreter/port changed.
    actual = [sys.executable, *command[2:]]
    actual[3] = probe_server + path
    result = subprocess.run(actual, cwd=ROOT, timeout=5, capture_output=True)
    assert result.returncode == 0, result.stderr
    actual[3] = probe_server + "/failed"
    assert subprocess.run(actual, cwd=ROOT, timeout=5).returncode != 0
    assert health["timeout"] == "3s"


@pytest.mark.parametrize("path", ["/failed", "/wrong", "/malformed", "/missing"])
def test_failed_or_invalid_health_exits_nonzero(probe_server, path):
    assert run_probe(probe_server + path).returncode != 0


def test_unreachable_endpoint_exits_nonzero():
    # Retain a bound-but-not-listening socket so the port cannot be reused.
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        assert run_probe(f"http://127.0.0.1:{sock.getsockname()[1]}/health").returncode


def test_timeout_is_enforced():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        # TCP accepts a connection, but no HTTP response is ever sent.
        assert run_probe(f"http://127.0.0.1:{sock.getsockname()[1]}/health").returncode


def test_version_defaults_and_build_identity(monkeypatch):
    for key in ("APP_GIT_SHA", "APP_BUILD_DATE", "APP_RELEASE_VERSION"):
        monkeypatch.delenv(key, raising=False)
    app = FastAPI()
    install_version_route(app, "test-service")
    client = TestClient(app)
    assert client.get("/version").json() == {
        "service": "test-service",
        "git_sha": "unknown",
        "build_date": "unknown",
        "release_version": "dev",
    }
    monkeypatch.setenv("APP_GIT_SHA", "a" * 40)
    monkeypatch.setenv("APP_BUILD_DATE", "2026-09-16T00:00:00Z")
    monkeypatch.setenv("APP_RELEASE_VERSION", "test-release")
    assert client.get("/version").json()["git_sha"] == "a" * 40
    assert client.get("/version").json()["release_version"] == "test-release"


@pytest.mark.parametrize("service", PORTS)
def test_build_identity_is_baked_from_same_args_as_oci_labels(service):
    source = (ROOT / service / "Dockerfile").read_text(encoding="utf-8")
    assert "APP_GIT_SHA=${GIT_SHA}" in source
    assert "APP_BUILD_DATE=${BUILD_DATE}" in source
    assert "APP_RELEASE_VERSION=${RELEASE_VERSION}" in source
    if service != "gradio":
        main = (ROOT / service / "src/api/v1/main.py").read_text(encoding="utf-8")
        assert f'install_version_route(app, "{service}")' in main
