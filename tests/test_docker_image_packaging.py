from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

APP_SERVICES = (
    "ingestion_service",
    "vector_store_service",
    "llm_service",
    "rag_orchestrator",
    "gradio",
)


def _python_files_for_service(service: str) -> list[Path]:
    if service == "gradio":
        return [REPO_ROOT / "ingestion_service" / "src" / "ui" / "gradio_app.py"]

    service_root = REPO_ROOT / service
    return sorted((service_root / "src").rglob("*.py"))


def _service_imports_shared(service: str) -> bool:
    for path in _python_files_for_service(service):
        text = path.read_text(encoding="utf-8")
        if "from shared" in text or "import shared" in text:
            return True
    return False


def _dockerfile_copies_shared(service: str) -> bool:
    dockerfile = REPO_ROOT / service / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    return any(
        line.strip().startswith("COPY shared ") for line in text.splitlines()
    )


def test_services_that_import_shared_copy_it_into_the_image() -> None:
    missing_shared_copy = [
        service
        for service in APP_SERVICES
        if _service_imports_shared(service) and not _dockerfile_copies_shared(service)
    ]

    assert missing_shared_copy == []
