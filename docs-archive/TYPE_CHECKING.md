--

### 1️⃣  `DOCS/TYPE_CHECKING.md`

This is the “why we switched” document.

#### Suggested structure

````md
# Type Checking Strategy

## Overview
This project uses static type checking to catch bugs early and improve maintainability.

As of Milestone 1, we use **Pyright** as the primary type checker.

## Why Pyright (and not mypy)

We evaluated mypy during early MS1 development. While viable, it introduced
significant complexity due to:

- src/ layout import resolution issues
- SQLAlchemy 2.0 plugin requirements
- Environment mismatches with uv and pre-commit
- Increased onboarding cost for new contributors

Pyright was selected because it:

- Works out-of-the-box with src/ layouts
- Natively understands modern SQLAlchemy typing
- Requires minimal configuration
- Executes faster in CI and pre-commit
- Is widely adopted in modern Python backends

## Tools Used

- Ruff – linting & formatting
- Pyright – static type checking
- pre-commit – local enforcement
- uv – dependency & environment management

## Running Type Checks Locally

```bash
uv run pyright
````

Or via pre-commit:

```bash
pre-commit run --all-files
```

## CI/CD Integration

Pyright is executed as part of the CI pipeline to ensure type safety before merge.

````

---
