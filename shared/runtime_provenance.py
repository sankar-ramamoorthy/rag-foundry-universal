"""Read-only build identity for API services (WP-R6/#169)."""

import os

from fastapi import FastAPI


def install_version_route(app: FastAPI, service: str) -> None:
    """Expose only public build fields; image labels remain release evidence."""

    @app.get("/version", tags=["operations"])
    def version() -> dict[str, str]:
        return {
            "service": service,
            "git_sha": os.getenv("APP_GIT_SHA", "unknown"),
            "build_date": os.getenv("APP_BUILD_DATE", "unknown"),
            "release_version": os.getenv("APP_RELEASE_VERSION", "dev"),
        }
