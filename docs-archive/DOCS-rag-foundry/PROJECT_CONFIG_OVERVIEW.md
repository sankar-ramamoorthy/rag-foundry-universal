---

# Project Configuration Overview

This document provides an overview of key configuration, environment, and tooling files in **RAG-Ingestion-Engine**. It is intended to help developers quickly understand the purpose of each file, its context, and any project-specific decisions.

---

## **1. alembic.ini**

**Purpose:**
Configuration for Alembic database migrations.

**Key Points:**

* `script_location`: Where migration scripts live (`migrations` folder).
* `sqlalchemy.url`: Database connection string (set via `.env` or environment variables). Uses Docker service name `postgres` for containerized development.
* `prepend_sys_path` and `path_separator`: Ensure Alembic scripts can resolve imports.
* `post_write_hooks`: Hooks for automatically formatting or linting new migration scripts (e.g., `ruff`, `black`).
* Logging configuration for Alembic and SQLAlchemy is included.

**Decisions Reflected:**

* Default templates and timezone left as local settings.
* Database URL left blank to encourage environment-specific configuration (`.env` or CI/CD).
* Supports post-write hooks for linting/formatting to maintain code quality.

---

## **2. pytest.ini**

**Purpose:**
Configuration for Pytest test discovery and markers.

**Key Points:**

* `pythonpath = src`: Ensures tests import from the `src` folder.
* `testpaths = tests`: Where Pytest looks for test files.
* `markers`:

  * `unit`: Fast, pure unit tests without DB or Docker.
  * `docker`: Tests requiring Dockerized Postgres / pgvector.
  * `integration`: Full integration tests (CI or production-level checks).
* `addopts = -ra`: Show extra summary info for skipped/failed tests.

**Decisions Reflected:**

* Separation of test types supports fast local iteration (`unit`) vs. environment-dependent testing (`docker`, `integration`).

---

## **3. ruff.toml**

**Purpose:**
Configuration for Ruff linter and code formatting.

**Key Points:**

* `line-length = 88`
* `target-version = "py312"`
* `exclude`: Common folders like `.venv`, `__pycache__`, `build`.
* `[lint] select`: Enforces specific categories of lint errors (`E`, `F`, `W`, `C`).

**Decisions Reflected:**

* Python 3.12 is standard for the project (pinned via `uv python pin 3.12`).
* Linting and formatting rules enforce consistent style without interfering with external dependencies.

---

## **4. pyrightconfig.json**

**Purpose:**
Configuration for Pyright static type checking.

**Key Points:**

* `include = ["src"]`: Only type-check source code, not tests.
* `typeCheckingMode = "standard"`: Ensures basic type coverage.
* `pythonVersion = "3.12"`: Matches pinned project Python version.
* `reportMissingTypeStubs = false`: Avoid unnecessary warnings on third-party libraries.

**Decisions Reflected:**

* Static type enforcement is part of the development workflow.
* Focused on project code, not dependencies.

---

## **5. .pre-commit-config.yaml**

**Purpose:**
Configuration for pre-commit hooks to maintain code quality.

**Key Points:**

* `ruff`: Linting and automatic fixes.
* `pyright`: Type checking integrated into commit process.
* `trailing-whitespace` and `end-of-file-fixer`: Enforces consistent file formatting.

**Decisions Reflected:**

* Local `pyright` runner ensures type checks use the correct Python environment.
* Pre-commit hooks help maintain consistency across developers and CI pipelines.

---

## **6. Environment Files**

### `.env` (Production / Default)

* `DATABASE_URL`: Connection to Postgres database.
* `EMBEDDING_PROVIDER` and `OLLAMA_*`: Configures embedding engine (Ollama).

### `.env.test` (Testing / CI)

* Points to containerized Postgres (`postgres`) for isolated tests.
* Maintains separate embedding settings for testing.

**Decisions Reflected:**

* Clear separation of production vs. test environments.
* Environment-driven configuration avoids hardcoding secrets or hostnames.

---

## **7. Summary Table of Purpose**

| File                      | Purpose                    | Notes / Decisions                                       |
| ------------------------- | -------------------------- | ------------------------------------------------------- |
| `alembic.ini`             | DB migration config        | Post-write hooks for linting, environment-driven DB URL |
| `pytest.ini`              | Test discovery & markers   | Separates unit/docker/integration tests                 |
| `ruff.toml`               | Linting rules              | Python 3.12, line length 88, excludes `.venv`           |
| `pyrightconfig.json`      | Type checking              | Checks `src` only, Python 3.12                          |
| `.pre-commit-config.yaml` | Pre-commit hooks           | Ruff, Pyright, whitespace checks                        |
| `.env`                    | Prod environment variables | Database, embedding provider settings                   |
| `.env.test`               | Test environment variables | Dockerized DB, test-specific settings                   |

---

## **8. How to Use**

* **Lint / Format:** `uv run ruff check . --fix`
* **Type check:** `uv run pyright .`
* **Run tests:**

  * Unit: `uv run pytest -m "not docker"`
  * Docker/Integration: `docker compose -f docker-compose.test.yml up -d && uv run pytest -m "docker"`
* **Database migrations:** `uv run alembic upgrade head`

---

## **9. Recommendations**

* Keep `.env` and `.env.test` up-to-date with containerized service names.
* Use pre-commit hooks consistently to avoid style drift.
* Regularly review `alembic.ini` and migration hooks when changing DB schema.
* Consider linking this document in the main `README.md` under a **Project Configuration** section.

---

This document provides a **single source of truth** for understanding project configuration files and why they exist, including the decisions they reflect and how they tie into development and testing workflows.

---
