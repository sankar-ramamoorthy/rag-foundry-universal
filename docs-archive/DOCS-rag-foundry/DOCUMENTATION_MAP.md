# Documentation Map for RAG-Ingestion-Engine

This document provides an overview of the DOCS folder structure, purpose of key files, and how different documentation categories relate to each other. It is intended for developers, maintainers, and anyone navigating the repository.

---

## DOCS Root Files

| File | Purpose |
|------|---------|
| `ARCHITECTURE_NOTES.md` | General architecture observations, integration notes, and design rationale for the ingestion service. |
| `DEVELOPMENT_SETUP.md` | Instructions for local development, including environment setup, dependencies, and Docker usage. |
| `DOCUMENTATION_MAP.md` | This file: provides a high-level map and purpose of all documentation. |
| `INGESTION_INTEGRATION_OVERVIEW.md` | Explains how the ingestion service interacts with other services in the Agentic-RAG platform. |
| `INGESTION_RETRIEVAL_EXPECTATIONS.md` | Expected behavior for retrieval of vectorized content; guidance for API consumers and internal developers. |
| `POSTGRES_SCHEMA.md` | Details the database schema, including tables and indexes for ingestion and vector storage. |
| `PROJECT_CONFIG_OVERVIEW.md` | Overview of configuration files, environment variables, and project-specific setup. |

---

## Architecture Folder (`DOCS/ARCHITECTURE`)

Contains **Architecture Decision Records (ADRs)** documenting important technical decisions.

| File | Purpose |
|------|---------|
| `adr-005-vector-store-no-orm.md` | Decision to use vector storage without an ORM, rationale and implications. |
| `adr-006-ocr-boundaries-and-progressive-understanding.md` | Decision on OCR ingestion boundaries and progressive understanding approach. |
| `adr-008-python-version-lock.md` | Decision to pin Python version to 3.12 across the project. |

> **Note:** ADRs capture **key design decisions** and the reasoning behind them. They should be referenced when making architecture changes.

---

## Design Folder (`DOCS/DESIGN`)

Contains design-oriented documentation, API contracts, and architecture overviews.

| File | Purpose |
|------|---------|
| `Design Principles.md` | Core principles guiding the ingestion service design and code quality. |
| `INGESTION_API_CONTRACT.md` | Defines API endpoints, request/response models, and contract expectations. |
| `INGESTION_OVERVIEW.md` | High-level description of the ingestion pipeline, chunking, embedding, and storage. |
| `OCR_ARCHITECTURE.md` | Architecture of OCR ingestion, including boundaries and integration points. |
| `PIPELINE_STAGEs.md` | Details stages of content processing pipeline and responsibilities. |
| `SCHEMA_OWNERSHIP.md` | Explains ownership of database tables and vector storage schema. |
| `UI_BOUNDARY.md` | Defines responsibilities and limits of optional Gradio UI for ingestion. |

---

## Development Folder (`DOCS/DEVELOPMENT`)

| File | Purpose |
|------|---------|
| `TESTING_STRATEGY.md` | Explains testing methodology, separation of unit, Dockerized integration, and CI tests. Includes instructions for running tests manually and via scripts. |

---

## Usage Folder (`DOCS/USAGE`)

| File | Purpose |
|------|---------|
| `INGESTION_SERVICE_GUIDE.md` | User guide for interacting with the ingestion service, including API calls, optional UI usage, and example workflows. |

---

## Recommended Documentation Standards

1. **ADRs** → `DOCS/ARCHITECTURE`
   *Formal design decisions.*
2. **Design and Architecture Notes** → `DOCS/DESIGN`
   *Guidance, contracts, and architectural rationale.*
3. **Usage / Guides** → `DOCS/USAGE`
   *How to use the service, examples, and workflows.*
4. **Development / Testing** → `DOCS/DEVELOPMENT`
   *Setup, test strategy, coding standards.*
5. **Project / Config Reference** → root DOCS (`PROJECT_CONFIG_OVERVIEW.md`)
   *Environment, configs, Docker, and operational details.*

> Following this separation ensures **clarity**, **discoverability**, and **ease of maintenance** for both human readers and automated tools.

---

## Notes

* Documentation should always reference ADRs when design decisions are relevant.
* Design principles are referenced in ADRs, design docs, and guides where applicable.
* `DOCUMENTATION_MAP.md` serves as a **central navigation point** for developers and contributors.
* Archive files in `DOCS-ARCHIVE` are **deprecated** and should not be used for current development or reference.

---

## References

* ADRs: `DOCS/ARCHITECTURE/`
* Design Docs: `DOCS/DESIGN/`
* Usage Guides: `DOCS/USAGE/`
* Development Notes: `DOCS/DEVELOPMENT/`
* Project Config: `DOCS/PROJECT_CONFIG_OVERVIEW.md`
