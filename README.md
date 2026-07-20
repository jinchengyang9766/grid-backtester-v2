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
- **Backend application: complete through exports.** Cookie-based
  authentication, dataset preview/save/management APIs, backtest execution
  and persistence, history/rename/delete, rerun/duplicate/compare, and all
  four export endpoints (`trades.csv`, `equity.csv`, `result.json`,
  `report.pdf`) are implemented and tested. See
  [`backend/README.md`](backend/README.md) for the endpoint-level detail.
- **Frontend: authentication, datasets, and backtest execution.** A Next.js App
  Router application with TypeScript, Tailwind CSS, a same-origin `/api` proxy,
  and a typed API client. Implemented pages: `/` (public landing), `/login`,
  `/register`, `/app` (authenticated shell), `/datasets` (list, detail,
  delete), and `/backtest/new`, which runs the full SPEC Section 28 wizard:
  upload → column mapping → cleaning review → cleaned preview → dataset saved →
  strategy configuration → running → result handoff. Financial values are
  handled as exact decimal strings and never converted through floating point;
  uploaded files and preview tokens stay in memory only.
- **Not yet implemented:** the detailed result dashboard, backtest history,
  charts, run comparison, export download buttons, optimization (backend and
  frontend), Celery/Redis, and Docker.

See `docs/SPEC.md` Section 40 for the full implementation phase order.

## Getting started

- Backend setup: [`backend/README.md`](backend/README.md)
- Frontend setup: [`frontend/README.md`](frontend/README.md)

Run the backend first (it listens on `http://127.0.0.1:8000` by default), then
start the frontend with `BACKEND_ORIGIN` pointing at it. The browser only ever
talks to the Next.js origin, which proxies `/api/*` to the backend.
