---
title: "Mac setup with local Ollama"
date: 2026-11-11
type: note
status: complete
tags: [deployment, macos, ollama, onboarding]
related:
  - "[Documentation index](/DOCS/index.md)"
  - "[README](/README.md)"
  - "[Mac environment template](/.env.mac.example)"
  - "[Local model registry](/llm_service/models.local.yaml)"
---

# Mac setup with local Ollama

Everything runs on your Mac. You do not need a remote machine, Tailscale,
cloud account, or API key. These instructions target Apple Silicon Macs
(M2, M3, M5) with 32–96 GB of memory.

The starting generation model is `qwen3:8b` on every Mac, so the setup and
model menu stay consistent. This is a starting choice, not a measured quality
or speed guarantee for this application. The embedding model must stay
`mxbai-embed-large:latest` because the database expects 1024-dimensional vectors.

## 1. Install and open the two applications

- Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
  for Apple Silicon. Open it and wait until its engine is running.
- Install [Ollama for Mac](https://ollama.com/download/mac). Open it and allow
  its command-line tool to be installed when prompted. Keep Ollama running.

Ollama runs directly on macOS to use the Apple GPU. The database and application
run in Docker. Ollama's [Mac requirements](https://docs.ollama.com/macos)
currently specify macOS 14 or newer and GPU support for Apple M-series chips.

Initial builds and model downloads need internet access and substantial disk
space. Allow time for downloads; the first application build can be slow.
Docker also needs memory alongside Ollama and macOS. If containers run out of
memory, increase Docker Desktop's memory allocation while leaving room for
Ollama and macOS; there is no measured universal allocation for this stack.

## 2. Download the project and models

Download the repository ZIP from GitHub and extract it, or clone it:

```bash
git clone https://github.com/sankar-ramamoorthy/rag-foundry-universal.git
cd rag-foundry-universal
```

If you downloaded a ZIP, open Terminal, type `cd `, drag the extracted folder
onto Terminal, and press Return. Run the remaining commands from that folder.

```bash
ollama pull mxbai-embed-large:latest
ollama pull qwen3:8b
ollama list
```

Both names should appear. You can check generation before starting the app:

```bash
ollama run qwen3:8b "Say hello in one sentence."
```

The [Qwen3 8B download](https://ollama.com/library/qwen3:8b) is about 5.2 GB;
running it also needs memory for context and other runtime state.

## 3. Use the Mac configuration

For a fresh download:

```bash
cp -n .env.mac.example .env
```

This preserves an existing `.env`. If you already have one, compare it with
`.env.mac.example` before proceeding; the commands below expect the Mac settings.
Do not copy another person's `.env`.

The template points to a local-only model registry. The generation model menu
will contain one entry: `default — ollama/qwen3:8b`. No remote or cloud model
entries are registered. `host.docker.internal` in the template means your own
Mac as reached by Docker containers; no server address needs to be supplied.

## 4. Build, prepare the database, and start

Run these commands in order. If a command fails, inspect its error before
continuing. Database migrations run inside Docker, so you do not need to install
Python or uv on your Mac.

```bash
docker compose build
docker compose up -d --wait postgres
docker compose run --rm --no-deps ingestion_service uv run alembic upgrade head
docker compose up -d --wait --wait-timeout 600
docker compose ps
```

Open **http://localhost:7860** once services are healthy. The first startup may
download additional Python dependencies. First use of document parsing can
also download parser models; an entirely offline first run is not promised.

## 5. First use

1. In **Codebase Ingestion**, leave **Source Type** as `git` and paste a
   repository's HTTPS Git URL. Start with a small public repository.
2. Leave **Embedding Provider** blank; the configuration already selects Ollama.
3. Submit the repository and wait for ingestion to complete.
4. Refresh/select the repository in the query section.
5. Leave **LLM Provider** blank and **Model** on `default`. Ask a question
   about the selected repository.

The UI still has general-purpose provider fields and allows custom model text;
you can leave those alone. Its `local` source option refers to a path **inside
the ingestion container**, so pasting a Mac folder path there will not work
without additional volume configuration. Use a Git URL for this setup.

For uploaded documents, use the document upload and **Document Query** sections.
Keep the same default model and leave the provider blank.

## Stop and resume whenever convenient

Stop the application:

```bash
docker compose down
```

The database remains in `volumes/ingestion-db`; Ollama keeps its downloaded
models separately. Do not delete these folders to stop the application.

To resume, open Docker Desktop and Ollama, return to the project folder, and run:

```bash
docker compose up -d --wait --wait-timeout 600
```

Then reopen **http://localhost:7860**. You do not need to download the models or
repeat migrations on ordinary restarts. After updating the repository, rebuild
and run the migration/start commands in step 4 again.

## If something fails

- **Ollama command missing:** open Ollama and finish its CLI installation, then
  reopen Terminal.
- **Model missing:** run `ollama list` and repeat the two pull commands above.
- **Application unhealthy:** run `docker compose ps` and
  `docker compose logs --tail=100 ingestion_service llm_service rag_orchestrator`.
- **Ollama connection failure:** confirm Ollama is open. Check the host with
  `curl --fail http://localhost:11434/api/tags`. Check the container connection:

  ```bash
  docker compose run --rm --no-deps ingestion_service curl --fail http://host.docker.internal:11434/api/tags
  ```

- **Cloud or Windows/Linux model names appear:** confirm `.env` contains
  `MODELS_CONFIG_PATH=/app/llm_service/models.local.yaml`, then run
  `docker compose up -d --build --force-recreate llm_service` and reload the page.
- **Confirm the menu directly:** run `curl --fail http://localhost:8003/v1/models`.
  Expect only the `default` model, with empty `endpoints` and `providers` lists.

## Verification limits

This guide and profile have been checked against the repository's Compose,
Dockerfiles, registry loader, migration entry point, and UI menu construction.
Automated registry tests check that the profile exposes only local Qwen even
when remote environment settings exist. A complete build, ingestion, and query
on an Apple Silicon Mac is still required before calling this handoff Mac-tested.
