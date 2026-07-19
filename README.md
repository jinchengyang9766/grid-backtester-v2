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

- **Pure backtest engine: complete.** Parsing/cleaning of TongdaXin and
  CSV data, grid/zone generation, deterministic price paths, crossing
  planning, order execution, equity capture, two buy-and-hold benchmarks,
  metrics, and the full `run_backtest` orchestration are implemented and
  tested in `backend/app/` as framework-free Python.
- **Backend application: infrastructure only.** A FastAPI application with
  typed settings, SQLAlchemy 2.x session infrastructure, Alembic
  scaffolding, and a `GET /health` endpoint exists. No application
  database schema has been created yet.
- **Not yet implemented:** users/authentication, dataset upload APIs,
  backtest persistence and business endpoints, exports, optimization,
  frontend, Celery/Redis, and Docker.

See `docs/SPEC.md` Section 40 for the full implementation phase order.

## Getting started

Backend setup instructions: [`backend/README.md`](backend/README.md).

Frontend setup instructions will be added once the frontend is initialized.
