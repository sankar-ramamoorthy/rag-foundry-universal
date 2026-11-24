"""#437: the product frontend's packaging and same-origin boundary.

Static checks of the Compose service, the nginx template, the Dockerfile and
the development proxy. The container itself was exercised by hand against a
mock upstream (see the PR); these tests keep the properties that matter from
regressing without needing Docker in CI.
"""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
NGINX = (ROOT / "frontend" / "nginx" / "default.conf.template").read_text(
    encoding="utf-8"
)
DOCKERFILE = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
VITE = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")


def _published_host_ports(service):
    return {str(p).split(":")[0] for p in COMPOSE["services"][service].get("ports", [])}


def test_frontend_is_opt_in_so_plain_up_and_prod_refresh_do_not_include_it():
    # scripts/prod-refresh.sh runs a plain `compose build` / `up -d`; a profile
    # keeps the frontend out of the operator's release until it is chosen.
    assert COMPOSE["services"]["frontend"]["profiles"] == ["frontend"]
    for name, service in COMPOSE["services"].items():
        if name != "frontend":
            assert "profiles" not in service, name


def test_frontend_builds_from_its_own_context_and_waits_for_the_orchestrator():
    service = COMPOSE["services"]["frontend"]
    assert service["build"]["context"] == "./frontend"
    assert service["depends_on"]["rag_orchestrator"]["condition"] == "service_healthy"
    assert "healthcheck" in service
    assert service["networks"] == ["ragnet"]


def test_orchestrator_address_comes_from_environment_not_the_image():
    env = COMPOSE["services"]["frontend"]["environment"]
    assert env["RAG_ORCHESTRATOR_URL"] == "http://rag_orchestrator:8000"
    assert "${RAG_ORCHESTRATOR_URL}" in NGINX
    assert not re.search(r"https?://", NGINX), "no literal service address in nginx"


def test_gradio_is_unchanged_and_ports_do_not_collide():
    assert _published_host_ports("gradio") == {"7860"}
    frontend = _published_host_ports("frontend")
    assert frontend == {"8080"}
    for name in COMPOSE["services"]:
        if name != "frontend":
            assert not (_published_host_ports(name) & frontend), name


def test_only_the_product_api_is_mapped_through_the_frontend_origin():
    proxied = re.findall(r"proxy_pass\s+([^;]+);", NGINX)
    assert proxied == ["$orchestrator"]
    assert 'set $orchestrator "${RAG_ORCHESTRATOR_URL}";' in NGINX
    # The product path is proxied; everything else under /v1 is a 404.
    assert re.search(r"location /v1/product/ \{", NGINX)
    assert re.search(r"location /v1/ \{\s*return 404;", NGINX)


def test_dev_proxy_and_container_use_the_same_browser_path():
    match = re.search(r'proxy:\s*\{\s*"(/v1/[^"]+)"', VITE)
    assert match, "vite dev proxy path not found"
    assert match.group(1) + "/" == re.search(
        r"location (/v1/product/) \{", NGINX
    ).group(1)


def test_dev_proxy_has_no_personal_default_address():
    assert 'process.env.FOUNDRY_API_URL ?? "http://localhost:8004"' in VITE


def test_response_headers_forbid_framing_sniffing_and_foreign_origins():
    for header in (
        "X-Content-Type-Options",
        "Referrer-Policy",
        "X-Frame-Options",
        "Content-Security-Policy",
    ):
        assert header in NGINX
    csp = re.search(r'Content-Security-Policy "([^"]+)"', NGINX).group(1)
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_image_is_multi_stage_non_root_and_resolves_upstream_at_request_time():
    stages = re.findall(r"^FROM\s+(\S+)", DOCKERFILE, flags=re.M)
    assert len(stages) == 2 and stages[1].startswith("nginxinc/nginx-unprivileged")
    assert not re.search(r"^USER\s+root", DOCKERFILE, flags=re.M)
    # nginx resolves a hostname proxy_pass once at start unless a resolver and a
    # variable upstream are used; the image must export the resolvers.
    assert "NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1" in DOCKERFILE
    assert "resolver ${NGINX_LOCAL_RESOLVERS}" in NGINX
