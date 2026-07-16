# Backend — Grid Backtester V2

Python backend for the Grid Backtester V2 engine, API, and services. See
[`../docs/BLUEPRINT.md`](../docs/BLUEPRINT.md) and
[`../docs/SPEC.md`](../docs/SPEC.md) for the product blueprint and the
detailed implementation contract this backend is built against.

## Current status

Environment and tooling foundation only. No application code (parsing,
engine, API routes, database models, or auth) has been implemented yet.

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

## Running checks

```powershell
pytest
ruff check .
ruff format --check .
mypy
```

## Project layout

```text
backend/
├── app/            # Backend application package (empty for now)
├── tests/          # Pytest test suite
├── pyproject.toml  # Project metadata, dependencies, tool configuration
└── README.md       # This file
```
