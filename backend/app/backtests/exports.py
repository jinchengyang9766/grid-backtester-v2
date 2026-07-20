"""In-memory CSV/JSON exports of persisted backtest results (SPEC 25.4, 31).

Everything here is read-only and derived purely from already-persisted rows:
no engine call, no metric recomputation, no commit, and no file ever written
to disk. Exports are built per request and streamed back in the response.

CSV headers are frozen by SPEC 25.4: they are the table's own column names
from SPEC 23 minus ``id``, except that ``trades.csv`` replaces the internal
``event_id`` foreign key with the two human-meaningful columns joined from
the parent ``backtest_events`` row -- ``date`` and ``event_sequence``.
"""

import copy
import csv
import datetime
import io
from decimal import Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.backtests.persistence import ResultIntegrityError
from app.backtests.projections import load_daily_equity_projection, load_trade_projection
from app.backtests.serialization import JsonValue, plain_decimal
from app.db.models import BacktestRun

__all__ = [
    "DAILY_EQUITY_CSV_HEADER",
    "TRADE_CSV_HEADER",
    "build_complete_result_document",
    "build_daily_equity_csv",
    "build_trades_csv",
]

# SPEC 23.6 columns minus `id`, with `event_id` replaced by the parent
# BacktestEvent's `date`/`event_sequence` (SPEC 25.4). Order is frozen.
TRADE_CSV_HEADER: Final[tuple[str, ...]] = (
    "date",
    "event_sequence",
    "side",
    "grid_price",
    "execution_price",
    "shares",
    "notional",
    "commission",
    "slippage_cost",
    "cash_after",
    "shares_after",
    "equity_after",
    "status",
    "skip_reason",
)

# SPEC 23.8 columns minus `id`. `backtest_run_id` is a primary fact of this
# table (SPEC 23.8), not a denormalized copy, and SPEC 25.4 removes only `id`.
DAILY_EQUITY_CSV_HEADER: Final[tuple[str, ...]] = (
    "backtest_run_id",
    "date",
    "close",
    "cash",
    "shares",
    "equity",
    "drawdown",
    "zone_at_close",
)

# Output field name -> the key the value is already stored under inside
# BacktestRun.result_metrics. Only the output name is remapped; the stored
# document itself is never renamed or rewritten.
_BENCHMARK_SOURCE_KEYS: Final[tuple[tuple[str, str], ...]] = (
    ("benchmark_1", "benchmark1"),
    ("benchmark_2", "benchmark2"),
)

_DATASET_SUMMARY_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "name",
    "source_type",
    "original_filename",
    "security_name",
    "security_code",
    "data_mode",
    "start_date",
    "end_date",
    "row_count",
    "column_mapping",
    "cleaning_summary",
)


def _cell(value: object) -> str:
    """One CSV cell: None becomes empty, Decimal stays plain fixed-point."""
    if value is None:
        return ""
    if isinstance(value, bool):  # before int: bool is an int subclass
        raise TypeError("Unsupported boolean value in a CSV export column")
    if isinstance(value, Decimal):
        return plain_decimal(value)
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"Unsupported type for CSV serialization: {type(value).__name__}")


def _render_csv(header: tuple[str, ...], rows: list[list[object]]) -> str:
    """Header plus rows via csv.writer, so quoting/escaping is never manual."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return buffer.getvalue()


def build_trades_csv(session: Session, *, backtest_run_id: int) -> str:
    """Every Trade of one run, globally ordered by BacktestEvent.event_sequence.

    Ownership must already be resolved by the caller; the run id still scopes
    the query. One joined query, no per-row lookups. A run with no trades
    yields the header row alone.
    """
    rows: list[list[object]] = [
        [
            event_date,
            event_sequence,
            trade.side,
            trade.grid_price,
            trade.execution_price,
            trade.shares,
            trade.notional,
            trade.commission,
            trade.slippage_cost,
            trade.cash_after,
            trade.shares_after,
            trade.equity_after,
            trade.status,
            trade.skip_reason,
        ]
        for trade, event_date, event_sequence in load_trade_projection(
            session, backtest_run_id=backtest_run_id
        )
    ]
    return _render_csv(TRADE_CSV_HEADER, rows)


def build_daily_equity_csv(session: Session, *, backtest_run_id: int) -> str:
    """The Daily Close Equity series of one run, ordered by date then id.

    EventEquity is deliberately not part of this export (SPEC 31). A run with
    no daily rows yields the header row alone.
    """
    rows: list[list[object]] = [
        [
            row.backtest_run_id,
            row.date,
            row.close,
            row.cash,
            row.shares,
            row.equity,
            row.drawdown,
            row.zone_at_close,
        ]
        for row in load_daily_equity_projection(session, backtest_run_id=backtest_run_id)
    ]
    return _render_csv(DAILY_EQUITY_CSV_HEADER, rows)


def _benchmarks(result_metrics: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
    """Project the already-persisted benchmark documents, never recompute them."""
    if result_metrics is None:
        return {output_key: None for output_key, _ in _BENCHMARK_SOURCE_KEYS}
    projected: dict[str, JsonValue] = {}
    for output_key, stored_key in _BENCHMARK_SOURCE_KEYS:
        if stored_key not in result_metrics:
            # Loud server-side failure: silently recomputing would invent a
            # benchmark the stored result never contained. The message stays
            # server-side; no stored JSON content is exposed to the client.
            raise ResultIntegrityError(
                f"stored result_metrics is missing the {stored_key!r} benchmark document"
            )
        projected[output_key] = copy.deepcopy(result_metrics[stored_key])
    return projected


def _dataset_summary(run: BacktestRun) -> dict[str, JsonValue]:
    """Frozen Dataset fields only -- never user_id, PriceBars, or ORM state."""
    dataset = run.dataset
    summary: dict[str, JsonValue] = {}
    for field in _DATASET_SUMMARY_FIELDS:
        value = getattr(dataset, field)
        if isinstance(value, datetime.date):
            summary[field] = value.isoformat()
        elif isinstance(value, dict | list):
            summary[field] = copy.deepcopy(value)
        else:
            summary[field] = value
    return summary


def build_complete_result_document(run: BacktestRun) -> dict[str, JsonValue]:
    """The frozen result.json document (SPEC 31).

    Stored JSON is deep-copied verbatim -- decimal strings stay strings and
    are never widened to float, and the source objects are never mutated.
    Only the benchmark *output* key names differ from their stored keys.
    """
    document: dict[str, JsonValue] = {
        "configuration": copy.deepcopy(run.configuration),
        "result_metrics": copy.deepcopy(run.result_metrics),
    }
    document.update(_benchmarks(run.result_metrics))
    document["dataset_summary"] = _dataset_summary(run)
    return document
