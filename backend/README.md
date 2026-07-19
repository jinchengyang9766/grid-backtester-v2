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
- **Authentication: complete.** `POST /api/auth/register`,
  `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me`
  exist. Passwords are stored as Argon2id hashes; sessions use an HS256
  JWT delivered exclusively in an `HttpOnly` cookie (`Path=/api`,
  `SameSite=Lax`, 24-hour default expiry). Errors use the standard
  `{"error": {"code", "message", "details?"}}` envelope.
- **Dataset preview/save: complete.** `POST /api/datasets/preview` accepts
  a TongdaXin text-export `.xls` or a `.csv` upload (multipart), runs the
  deterministic parsing/cleaning pipeline in memory, and returns the
  mapping, bad/duplicate rows, cleaning summary, and a 30-minute
  `preview_token`. `POST /api/datasets` persists the cleaned rows as a
  `Dataset` plus `PriceBar` rows from that token alone. Editing the column
  mapping requires a fresh preview call — a token is bound to exactly one
  mapping/cleaning result. A successful save consumes the token. Raw
  uploads are never persisted; only cleaned `PriceBar` rows are stored.
  The preview cache is in-process (per application instance) and intended
  for local single-worker use; a Redis-backed shared cache is deferred to
  the background-job stage.
- **No other business APIs exist yet.** Dataset list/detail/delete,
  backtest persistence endpoints, exports, and optimization APIs are not
  implemented, and the frontend upload wizard does not exist. There are no
  refresh tokens and no password-reset or email-verification flow yet.

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

## Authentication

Cookie-based JWT authentication assuming the SPEC's same-origin Next.js
`/api` proxy architecture (no browser-facing CORS, no extra CSRF token,
no cookie `Domain` attribute):

- The access token is an HS256 JWT (`sub`/`iat`/`exp` only) signed with
  `GRID_BACKTESTER_AUTH_SECRET_KEY`. The in-code default secret is a
  labeled development-only value and is **not** production-safe —
  production must set a long random secret via the environment.
- The token lives only in an `HttpOnly` cookie (`Path=/api`,
  `SameSite=Lax`, `Max-Age` = `GRID_BACKTESTER_ACCESS_TOKEN_EXPIRE_MINUTES`
  × 60, default 24 hours). The cookie is not `Secure` in local development
  only because localhost uses plain HTTP; in production
  (`GRID_BACKTESTER_APP_ENVIRONMENT=production`) it is `Secure`.
- No refresh tokens: when the token expires, the user logs in again.
- Passwords are hashed with Argon2id (library-recommended parameters);
  plaintext is never stored or logged. The only password rule is the
  frozen minimum of 8 characters.

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
│   ├── api/            # FastAPI routers, schemas, error envelope
│   ├── auth/           # Argon2id hashing, JWTs, current-user dependency
│   ├── core/           # Typed application settings
│   ├── datasets/       # Preview cache + dataset preview/save services
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
