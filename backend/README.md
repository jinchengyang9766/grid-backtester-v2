# Backend — Grid Backtester V2

Python backend for the Grid Backtester V2 engine, API, and services. See
[`../docs/BLUEPRINT.md`](../docs/BLUEPRINT.md) and
[`../docs/SPEC.md`](../docs/SPEC.md) for the product blueprint and the
detailed implementation contract this backend is built against.

## Current status

- **Pure backtest engine: complete.** `app/domain`, `app/importing`, and
  `app/engine` implement parsing/cleaning, grids, price paths, crossings,
  execution, equity capture, benchmarks, metrics, and the full
  `run_backtest` orchestration — with no framework dependencies.
- **Application infrastructure: minimal.** FastAPI app factory, typed
  Pydantic settings, SQLAlchemy 2.x base/session plumbing, and Alembic
  scaffolding exist, with a single `GET /health` endpoint.
- **First persistence schema: exists.** `app/db/models/` defines the
  `users`, `datasets`, and `price_bars` tables (SQLAlchemy 2.x typed
  declarative models) and `alembic/versions/` contains the first
  migration. Deleting a user cascades to their datasets, and deleting a
  dataset cascades to its price bars, enforced at database level.
- **No application APIs exist yet.** Authentication, registration/login,
  dataset upload/preview endpoints, backtest persistence, and all other
  business endpoints are not implemented. Nothing hashes passwords yet.

## Requirements

- Python 3.12
- Windows PowerShell (commands below use PowerShell syntax)

## Setup (Windows PowerShell)

Run these commands from the `backend/` directory.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Configuration

All settings load through `app/core/config.py` (Pydantic Settings) using
the `GRID_BACKTESTER_` environment-variable prefix, with an optional local
`.env` file. Copy `.env.example` to `.env` and adjust as needed — never
commit `.env`. The default database URL is a local SQLite file, suitable
only for development; PostgreSQL is the target production database.

## Running checks

```powershell
pytest
ruff check .
ruff format --check .
mypy
```

## Running the API locally

```powershell
uvicorn app.main:app --reload
```

Then:

- Health check: <http://127.0.0.1:8000/health>
- Interactive docs: <http://127.0.0.1:8000/docs>

Startup opens no database connection and creates no tables.

## Database migrations (Alembic)

Alembic is configured in `alembic.ini` and `alembic/`, and owns all schema
creation. The database URL comes from application settings
(`GRID_BACKTESTER_DATABASE_URL`), never from `alembic.ini`. Run commands
from the `backend/` directory, for example:

```powershell
alembic upgrade head    # apply all migrations (creates the schema)
alembic downgrade base  # revert all migrations (drops the schema)
alembic heads
alembic history
alembic current
```

Alembic — not application startup — creates and drops tables; importing
or running the API never emits DDL. The single revision so far creates
`users`, `datasets`, and `price_bars`.

## Project layout

```text
backend/
├── app/
│   ├── api/            # FastAPI routers (health only, for now)
│   ├── core/           # Typed application settings
│   ├── db/             # SQLAlchemy base, engine/session, persistence models
│   ├── domain/         # Pure domain models and enums
│   ├── engine/         # Pure deterministic backtest engine (complete)
│   ├── importing/      # Pure parsing/cleaning pipeline (complete)
│   └── main.py         # FastAPI application factory
├── alembic/            # Migration environment and revisions
├── alembic.ini         # Alembic configuration (no database URL inside)
├── tests/              # Pytest suite
├── .env.example        # Example environment configuration (no secrets)
├── pyproject.toml      # Project metadata, dependencies, tool configuration
└── README.md           # This file
```

The engine and importing packages never import FastAPI, Pydantic,
SQLAlchemy, or Alembic; the application layer may call into the engine,
never the reverse.
