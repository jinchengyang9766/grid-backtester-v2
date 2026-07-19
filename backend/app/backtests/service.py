"""Synchronous backtest creation: ownership, engine execution, persistence.

Flow: ownership-scoped Dataset lookup -> ordered PriceBars -> pure Bars ->
adapted BacktestConfig -> run_backtest -> one transactional persistence of
the COMPLETED (or FAILED) run. Validation failures never insert a run;
only the narrow supported runtime failure persists a FAILED run.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas.backtests import BacktestCreateRequest
from app.backtests.configuration import adapt_configuration, generate_backtest_name
from app.backtests.persistence import persist_completed_run, persist_failed_run
from app.db.models import BacktestRun, Dataset, PriceBar
from app.domain.enums import DataMode
from app.domain.models import Bar
from app.engine import (
    EmptyDatasetError,
    GridCollapsesAfterTickRoundingError,
    GridTooDenseError,
    InvalidLotSizeError,
    InvalidOhlcvBarError,
    InvalidRiskFreeRateError,
    InvalidTradeLotsError,
    InvalidZoneConfigError,
    NegativeCommissionComponentError,
    NegativeInitialCashError,
    NegativeInitialSharesError,
    NegativeSlippageError,
    NonPositiveBaselineError,
    NonPositiveDistanceError,
    NonPositiveExecutionPriceError,
    NonPositiveGridStepError,
    NonPositiveTickSizeError,
    OhlcPathModeRequiredError,
    ZeroInitialEquityError,
    run_backtest,
)

__all__ = ["create_backtest"]

# Engine input/configuration validation -> 422 with the SPEC's code; no run row.
_VALIDATION_ERROR_CODES: dict[type[Exception], str] = {
    NonPositiveBaselineError: "NON_POSITIVE_BASELINE",
    NonPositiveDistanceError: "NON_POSITIVE_DISTANCE",
    InvalidZoneConfigError: "INVALID_ZONE_CONFIG",
    NonPositiveGridStepError: "NON_POSITIVE_GRID_STEP",
    GridTooDenseError: "GRID_TOO_DENSE",
    GridCollapsesAfterTickRoundingError: "GRID_COLLAPSES_AFTER_TICK_ROUNDING",
    InvalidLotSizeError: "INVALID_LOT_SIZE",
    InvalidTradeLotsError: "INVALID_TRADE_LOTS",
    NegativeInitialCashError: "NEGATIVE_INITIAL_CASH",
    NegativeInitialSharesError: "NEGATIVE_INITIAL_SHARES",
    ZeroInitialEquityError: "ZERO_INITIAL_EQUITY",
    NegativeCommissionComponentError: "NEGATIVE_COMMISSION_COMPONENT",
    NegativeSlippageError: "NEGATIVE_SLIPPAGE",
    NonPositiveTickSizeError: "NON_POSITIVE_TICK_SIZE",
    InvalidRiskFreeRateError: "INVALID_RISK_FREE_RATE",
    # No dedicated SPEC codes exist for these input problems:
    InvalidOhlcvBarError: "VALIDATION_ERROR",
    OhlcPathModeRequiredError: "VALIDATION_ERROR",
    EmptyDatasetError: "VALIDATION_ERROR",
}

_VALIDATION_EXCEPTIONS = tuple(_VALIDATION_ERROR_CODES)

# Narrow SPEC-supported runtime failures: the run row persists as FAILED.
_RUNTIME_FAILURE_EXCEPTIONS = (NonPositiveExecutionPriceError,)

_VALIDATION_FIELD_HINTS: dict[type[Exception], str] = {
    InvalidLotSizeError: "configuration.lot_size",
    InvalidTradeLotsError: "configuration.trade_lots",
    NegativeInitialCashError: "configuration.initial_cash",
    NegativeInitialSharesError: "configuration.initial_shares",
    NonPositiveTickSizeError: "configuration.tick_size.value",
    InvalidRiskFreeRateError: "configuration.risk_free_rate_annual",
    NonPositiveGridStepError: "configuration.grid_step",
    NonPositiveBaselineError: "configuration.baseline",
    NegativeSlippageError: "configuration.slippage",
    InvalidZoneConfigError: "configuration.c_distance",
}


def _dataset_not_found() -> ApiError:
    return ApiError(404, "DATASET_NOT_FOUND", "Dataset not found.")


def _validation_api_error(error: Exception) -> ApiError:
    code = _VALIDATION_ERROR_CODES[type(error)]
    details: dict[str, object] | None = None
    field = _VALIDATION_FIELD_HINTS.get(type(error))
    if field is not None:
        details = {"field": field, "reason": str(error)}
    return ApiError(422, code, str(error), details)


def _load_bars(session: Session, dataset: Dataset, data_mode: DataMode) -> list[Bar]:
    rows = (
        session.execute(
            select(PriceBar)
            .where(PriceBar.dataset_id == dataset.id)
            .order_by(PriceBar.date.asc(), PriceBar.id.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Dataset contains no price bars.",
            {"field": "dataset_id", "reason": "the dataset has zero stored rows"},
        )
    if data_mode is DataMode.OHLCV:
        bars: list[Bar] = []
        for row in rows:
            if row.open is None or row.high is None or row.low is None:
                raise ApiError(
                    422,
                    "VALIDATION_ERROR",
                    "Stored OHLCV dataset row is missing open/high/low values.",
                    {"field": "dataset_id", "reason": f"row for {row.date} is incomplete"},
                )
            bars.append(
                Bar(
                    date=row.date,
                    close=row.close,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    volume=row.volume,
                )
            )
        return bars
    # CLOSE_ONLY: nullable OHLC fields are never reinterpreted as OHLCV data.
    return [Bar(date=row.date, close=row.close) for row in rows]


def create_backtest(
    session: Session,
    *,
    current_user_id: int,
    request: BacktestCreateRequest,
    now: datetime | None = None,
) -> BacktestRun:
    current_time = now if now is not None else datetime.now(UTC)
    dataset = session.execute(
        select(Dataset).where(Dataset.id == request.dataset_id, Dataset.user_id == current_user_id)
    ).scalar_one_or_none()
    if dataset is None:
        raise _dataset_not_found()

    data_mode = DataMode(dataset.data_mode)
    bars = _load_bars(session, dataset, data_mode)
    adapted = adapt_configuration(request.configuration, data_mode=data_mode)
    name = request.name or generate_backtest_name(
        security_code=dataset.security_code,
        dataset_name=dataset.name,
        grid_step=request.configuration.grid_step,
        today=current_time.date(),
    )

    try:
        result = run_backtest(bars, adapted.engine_config)
    except _VALIDATION_EXCEPTIONS as error:
        raise _validation_api_error(error) from error
    except _RUNTIME_FAILURE_EXCEPTIONS as error:
        run = persist_failed_run(
            session,
            user_id=current_user_id,
            dataset=dataset,
            name=name,
            configuration_json=adapted.configuration_json,
            ohlc_path_mode=adapted.ohlc_path_mode,
            error_message=str(error),
            completed_at=current_time,
        )
        session.commit()
        session.refresh(run)
        return run

    try:
        run = persist_completed_run(
            session,
            user_id=current_user_id,
            dataset=dataset,
            name=name,
            configuration_json=adapted.configuration_json,
            ohlc_path_mode=adapted.ohlc_path_mode,
            result=result,
            completed_at=current_time,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(run)
    return run
