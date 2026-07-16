# Grid Backtester V2

A portfolio-grade, full-stack grid-trading backtesting platform: upload
historical price data, configure an A/C-zone grid strategy, run a
deterministic backtest engine, and compare results against two
buy-and-hold benchmarks — with parameter optimization, history, and
exports on top.

This is a research and educational backtester. It does not place live
trades and is not investment advice.

## Documentation

- [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md) — the frozen, high-level product
  and architecture blueprint (source of truth for *what* the product does).
- [`docs/SPEC.md`](docs/SPEC.md) — the detailed, approved implementation
  specification derived from the blueprint (source of truth for *exactly
  how* it is implemented).

## Planned architecture

```text
grid-backtester-v2/
├── backend/    # Python: backtest engine, FastAPI, PostgreSQL, Celery worker
├── frontend/   # Next.js + React + TypeScript
└── docs/       # Product blueprint and implementation specification
```

- **Backend:** Python, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic,
  PostgreSQL, pandas. The backtest engine itself is a pure Python package
  with no framework dependencies.
- **Frontend:** Next.js (App Router), React, TypeScript, Tailwind CSS,
  TanStack Query, Plotly.js.
- **Background jobs:** Celery + Redis for parameter optimization, after a
  synchronous version of the optimizer is implemented and tested.
- **Docker:** added after the application works locally.

## Current implementation status

Monorepo and backend development-environment foundation only:

- `backend/` has a Python 3.12 project (`pyproject.toml`) with pytest,
  pytest-cov, Ruff, and mypy configured, and one environment test.
- No parsing, cleaning, grid generation, trading logic, API routes,
  database models, authentication, or frontend code has been written yet.

See `docs/SPEC.md` Section 40 for the full implementation phase order.

## Getting started

Backend setup instructions: [`backend/README.md`](backend/README.md).

Frontend setup instructions will be added once the frontend is initialized.
