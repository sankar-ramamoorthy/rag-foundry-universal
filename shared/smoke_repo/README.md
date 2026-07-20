# smoke_repo — live smoke-test fixture

Not product code. A minimal Python repo used to smoke-test the graph
pipeline against the running Docker stack. It lives under `shared/`
because that directory is volume-mounted into the ingestion container,
making it ingestable as a local repo:

```
MSYS_NO_PATHCONV=1 curl -X POST http://localhost:8001/v1/ingest-repo \
  -F "local_path=/app/shared/smoke_repo"
```

(`MSYS_NO_PATHCONV=1` stops Git Bash from mangling the container path.)

What it exercises, in three tiny files:

- `animals.py` — base class `Animal` with `speak` and `eat`
- `dogs.py` — `Dog(Animal)` **overrides** `speak` (OVERRIDES edge),
  `Dog.fetch` calls `self.eat()` defined only on the base (inherited
  self-call resolution), and `train_dog()` is a cross-symbol callee
- `kennel.py` — `run_demo()` calls `train_dog()` cross-file (reverse
  caller queries)

Expected edges after ingestion: `Dog INHERITS Animal`,
`Dog.speak OVERRIDES Animal.speak`, `Dog.fetch CALL Animal.eat`,
`run_demo CALL train_dog`.

Useful queries against `/v1/rag` (with this repo's repo_id):
"what functions call train_dog?", "what subclasses Animal?",
"which methods are overridden in Dog?" — use a low `top_k` (1) to force
graph expansion rather than having vector search seed everything.
