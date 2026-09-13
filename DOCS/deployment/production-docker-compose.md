---
title: "Production Docker Compose Release Process"
date: 2026-09-09
type: deployment-guide
status: accepted
tags: [deployment, production, docker-compose, release, provenance]
related:
  - "[Documentation Index](/DOCS/index.md)"
  - "[RAG Quality Evaluation Methodology](/DOCS/audit/08-RAG-Quality-Evaluation-Methodology.md)"
---

# Production Docker Compose Release Process

## Deployment cadence (2026-09-12, issue #111)

There are two deployment cadences for this stack:

- **Normal prod release**: slow, deliberate, tagged, CI-green, full release record — the process
  documented below, unchanged.
- **Ad hoc prod refresh**: exceptional, only for a narrow runtime defect that materially blocks
  evaluation, observability, or correctness, and has already passed CI on `main`.

An ad hoc refresh is justified only when the change is one of:

1. **Correctness blocker** — current prod behavior is known wrong.
2. **Observability blocker** — current prod cannot produce trustworthy evidence for work being
   actively evaluated.
3. **Security/availability issue** — an obvious urgent case.
4. **Evaluation invalidation** — the currently deployed runtime would make the next planned
   experiment misleading or impossible.

> **Rule:** ad hoc prod refreshes are allowed only for merged, CI-green runtime fixes that unblock
> correctness, observability, or a currently scheduled evaluation. They do not change the slower
> normal release cadence. A cosmetic change, docs-only change, or general improvement waits for the
> normal cycle.

`scripts/prod-refresh.sh` (issue #111) automates the safe *mechanics* of either cadence — checkout,
build, deploy, provenance verification, health checks — using the exact process below. It does
**not** decide whether a refresh is warranted, or which ref to deploy; those stay explicit human
decisions, made before running the script. Use a release label like `prod-hotfix-2026-09-12-107`
for an ad hoc refresh so it stays visibly distinct from a normal `prod-YYYY-MM-DD` release in
`DOCS/releases/`.

## Development vs. production

The default `docker-compose.yml` is optimized for local development. It
bind-mounts service source directories into containers so edits on the host are
reflected immediately.

Production uses `docker-compose.yml` plus `docker-compose.prod.yml`. The
production override removes application source bind mounts so containers run the
immutable image contents that were built and labeled for an exact Git commit.

Do not assume `latest` is a production release identifier. Production is
identified by an exact Git SHA, optionally with a human-readable tag such as
`prod-2026-09-12`.

The first successful release under this process is recorded as
[prod-2026-09-12](/DOCS/releases/2026-09-12-prod-release.md), deployed from
`202d91b34ee18e21c1dbb625d72acf9b82bce16d`. Its predecessor candidate
`827c9cdc182073966f0b794968f90a7dc4388d18` is recorded separately as a
[failed promotion](/DOCS/releases/2026-09-12-827c9cdc-failed-promotion.md);
do not infer success from a build label alone.

## Required release metadata

Set build metadata mechanically from the checked-out release commit:

```bash
export GIT_SHA=$(git rev-parse HEAD)
export BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export RELEASE_VERSION=prod-YYYY-MM-DD
```

Each application image records:

```text
org.opencontainers.image.source
org.opencontainers.image.url
org.opencontainers.image.title
org.opencontainers.image.description
org.opencontainers.image.licenses
org.opencontainers.image.revision
org.opencontainers.image.created
org.opencontainers.image.version
```

`org.opencontainers.image.revision` must equal the approved RAG-FOUNDRY-UNIVERSAL
Git SHA. It must not reflect the `astral/uv` base image revision.

## Pre-deploy capture

Before changing the production checkout, record:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.ID}}'
docker inspect rag-orchestrator --format '{{.Image}}'
docker image inspect <running-image-id> \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

For the first controlled release, the prior runtime Git SHA may be `unknown`.
Record prior image IDs anyway.

## Effective config proof

Before the first production deploy, render the effective Compose config:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

The rendered config must show:

- persistent Postgres storage: `./volumes/ingestion-db:/var/lib/postgresql/data`
- no application source bind mounts for service source directories or `shared`
- required production build args wired into every app image build
- no accidental dev-only mounts

If this proof fails, do not deploy.

## Deployment sequence

```bash
git fetch --tags origin
git status --short
git checkout <approved-sha-or-tag>

export GIT_SHA=$(git rev-parse HEAD)
export BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export RELEASE_VERSION=prod-YYYY-MM-DD

docker compose -f docker-compose.yml -f docker-compose.prod.yml config
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Before `up -d`, classify and record whether the release requires:

- DB migration
- DB backup
- repo re-ingestion
- graph rebuild
- vector re-embedding
- configuration changes

Back up the database before schema-changing releases. Never use
`docker compose down -v` or recreate `./volumes/ingestion-db` during normal
deploys.

## Validation

Check health:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:7860
```

Verify the running container image, not only the `latest` tag:

```bash
docker inspect rag-orchestrator --format '{{.Image}}'
docker image inspect <running-image-id> \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

For every app container, the approved Git SHA, running image ID label, and release
record must agree.

Run one known graph-aware RAG smoke query against a complete repository and
record pass/fail plus sources.

## Automated mechanics: `scripts/prod-refresh.sh`

The steps in "Deployment sequence" and "Validation" above are also available as a script, run on
the production host:

```bash
scripts/prod-refresh.sh --ref <sha-or-tag> --release <label> --check    # validate only, no deploy
scripts/prod-refresh.sh --ref <sha-or-tag> --release <label> --deploy   # full refresh
```

`--check` runs every step through image build and provenance verification but stops before
`up -d`. `--deploy` performs the full refresh: build, deploy, post-deploy provenance/mount/health
verification, an optional corpus + RAG smoke check, and a release-record skeleton written to
`DOCS/releases/`.

The script deliberately never: runs `docker compose down -v`, runs database migrations, triggers
repo re-ingestion, creates or pushes a git tag, chooses which ref to deploy, or decides whether a
refresh is safe or warranted. Those stay explicit human decisions — the operator always passes
`--ref`, and the "Deployment cadence" gate above is judged by a person before the script runs, not
by the script itself.

## Rollback

For ordinary code rollback:

```bash
git checkout <previous-prod-sha>
export GIT_SHA=$(git rev-parse HEAD)
export BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export RELEASE_VERSION=rollback-YYYY-MM-DD

docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

If an incompatible DB migration was applied, rollback requires restoring the
pre-migration DB backup or an explicitly reviewed downgrade path.

Application rollback and corpus re-ingestion are separate operations. Do not
automatically re-ingest repositories, rebuild graph state, or re-embed vectors as
part of application rollback.
