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
- **Frontend: complete through exports.** A Next.js App Router
  application with TypeScript, Tailwind CSS, a same-origin `/api` proxy, and a
  typed API client. Implemented pages: `/` (public landing), `/login`,
  `/register`, `/history` (the authenticated landing — searchable, filterable,
  paginated backtest history), `/history/{id}` (the full persisted-result
  dashboard with metrics, configuration, dependency-free SVG equity/drawdown/
  price charts, and all four result tables), `/history/compare` (side-by-side
  stored metrics), `/datasets` (list, detail, delete), and `/backtest/new`,
  which runs the full SPEC Section 28 wizard from upload through strategy
  configuration to execution. Runs can be renamed, rerun, duplicated with
  edited settings, deleted, and compared, and all four exports download through
  plain `<a download>` links so the browser streams each file straight to disk
  without JavaScript touching the bytes. Financial values are handled as exact
  decimal strings and converted to numbers only at the SVG-coordinate boundary;
  uploaded files and preview tokens stay in memory only.
- **End-to-end verified.** A Playwright (Chromium) suite drives the real
  application against a real backend — registration, sign-in, the full dataset
  wizard, strategy configuration and execution, history, the result dashboard,
  rename/rerun/duplicate/delete/compare, all four downloads, and responsive and
  accessibility sweeps at 390×844, 768×1024, and 1440×900. It starts both
  servers itself against a throwaway database with a generated secret, so it
  needs no manual setup and leaves nothing behind. See
  [`frontend/README.md`](frontend/README.md#end-to-end-suite).
- **Not yet implemented:** optimization (backend and frontend), Celery/Redis,
  and Docker.

See `docs/SPEC.md` Section 40 for the full implementation phase order.

## Getting started

- Backend setup: [`backend/README.md`](backend/README.md)
- Frontend setup: [`frontend/README.md`](frontend/README.md)

Run the backend first (it listens on `http://127.0.0.1:8000` by default), then
start the frontend with `BACKEND_ORIGIN` pointing at it. The browser only ever
talks to the Next.js origin, which proxies `/api/*` to the backend.
