#### **Schema Name**

This will list the schema you’re using for your Postgres database.

```markdown
# Postgres Schema Documentation

## Schema Name
- **ingestion_service**: This is the schema used by the ingestion service for storing ingestion-related data.
```

#### **Initial Tables and Columns**

Document all the tables and columns in your schema. For example:

```markdown
## Initial Tables and Columns

### 1. Table: `ingestion_requests`
- **ingestion_id** (UUID, Primary Key): Unique identifier for each ingestion request.
- **source_type** (VARCHAR): Type of source for the ingestion request.
- **ingestion_metadata** (JSON): Metadata associated with the ingestion request.
- **status** (VARCHAR, default 'pending'): Status of the ingestion request.
- **created_at** (TIMESTAMP, default NOW()): Timestamp of when the ingestion request was created.
```

#### **Migration Strategy**

This section should explain how to manage schema changes, both for local development and production environments. For example:

````markdown
## Migration Strategy

1. **Migrations via Alembic**: The schema migrations are managed using Alembic. To apply migrations:
    ```bash
    uv run alembic upgrade head
    ```

2. **Versioning**: Each migration has a unique revision ID and can be checked using:
    ```bash
    uv run alembic history
    ```

3. **Automatic Migrations in Docker**: Migrations are run automatically when the ingestion service container starts. However, if you need to run migrations manually, you can do so with the following command:
    ```bash
    docker-compose exec ingestion_service uv run alembic upgrade head
    ```

4. **Rollback Migrations**: To roll back to a previous migration, use:
    ```bash
    uv run alembic downgrade <revision_id>
    ```

````

#### **Example SQL to Create or Migrate Schema**

You may want to include a generic SQL for creating the schema and tables manually in case of emergencies.

````markdown
## Example SQL to Create or Migrate Schema

### Create Schema
```sql
CREATE SCHEMA IF NOT EXISTS ingestion_service;
````

### Create Tables

```sql
CREATE TABLE ingestion_service.ingestion_requests (
    ingestion_id UUID PRIMARY KEY,
    source_type VARCHAR NOT NULL,
    ingestion_metadata JSON,
    status VARCHAR NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

#### **Instructions for Local Development**

This section should guide developers on how to set up the local environment to work with the Postgres database and Alembic migrations.

````markdown
## Instructions for Local Development

1. **Set Up Postgres**: Ensure you have Postgres running locally or use Docker to spin up a Postgres container.
    ```bash
    docker-compose up -d postgres
    ```

2. **Create a Virtual Environment**:
    ```bash
    uv sync install
    ```

3. **Run Migrations**: Run migrations to set up the schema in your local database:
    ```bash
    uv run alembic upgrade head
    ```

4. **Test Database Connection**: Run a connectivity test to ensure your application can communicate with the database:
    ```bash
    uv run python src/ingestion_service/tests/test_db_operations.py
    ```

5. **Running the Application**: Finally, start your ingestion service:
    ```bash
    docker-compose up -d ingestion_service
    ```

---

### **Final Notes**

Ensure that your schema and migration strategy are regularly updated as new tables or columns are added. You can use the `alembic revision --autogenerate` command to generate migration scripts when changes are made to the database models.

````

---
