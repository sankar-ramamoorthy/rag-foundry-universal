---

### ✅ 1. Docker build & startup

```bash
docker-compose build --no-cache
docker-compose up -d
````

**Expected**

* All containers start
* No crash loops
* Postgres reachable

---

### ✅ 2. Database readiness

```bash
docker-compose exec postgres pg_isready -U ingestion_user -d ingestion_db
```

**Expected**

```
accepting connections
```

---

### ✅ 3. Alembic migration

```bash
docker-compose exec ingestion_service uv run alembic upgrade head
```

**Expected**

* No errors
* Migration reports head revision

Verify:

```bash
docker-compose exec postgres psql -U ingestion_user -d ingestion_db -c "\dt ingestion_service.*"
```

**Expected**

* `alembic_version`
* `ingestion_requests`

---

### ✅ 4. DB connectivity test

```bash
docker-compose exec ingestion_service \
  uv run python src/ingestion_service/test_db_connection.py
```

**Expected**

```
Successfully connected to the database!
```

---

### ✅ 5. DB read/write test

```bash
docker-compose exec ingestion_service \
  uv run pytest tests/test_db_operations.py
```

**Expected**

```
1 passed
```

---

### ✅ 6. Linting

```bash
uv run ruff check . --fix
```

**Expected**

* No errors (or auto-fixed)

---

### ✅ 7. Type checking (Pyright)

```bash
uv run pyright
```

**Expected**

* No errors

---

### ✅ 8. Pre-commit (full gate)

```bash
pre-commit run --all-files
```

**Expected**

* All hooks pass

---
