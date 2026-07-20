"""Tests for stored-config reconstruction, deep merge, rerun, and duplicate."""

from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from app.api.errors import ApiError
from app.api.schemas.backtests import BacktestConfigurationInput
from app.backtests.replay import (
    configuration_request_from_stored,
    deep_merge_configuration,
    duplicate_backtest,
    rerun_backtest,
)
from app.backtests.service import create_backtest
from app.db import Base
from app.db.models import BacktestEvent, BacktestRun, Dataset, PriceBar, User
from app.db.session import create_database_engine, create_session_factory
from sqlalchemy.orm import Session, sessionmaker

NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
START = date(2026, 1, 5)


def stored_configuration(**overrides: Any) -> dict[str, Any]:
    """A canonical stored configuration document (all Decimals as strings)."""
    config: dict[str, Any] = {
        "initial_cash": "9.00000000",
        "initial_shares": 0,
        "lot_size": 1,
        "trade_lots": 1,
        "baseline": None,
        "a_distance": {"mode": "FIXED", "value": "2"},
        "c_distance": {"mode": "FIXED", "value": "4"},
        "grid_step": {"mode": "FIXED", "value": "1"},
        "tick_size": {"enabled": False, "value": None},
        "ohlc_path_mode": None,
        "buy_commission": {
            "rate_enabled": False,
            "rate": "0",
            "minimum_enabled": False,
            "minimum": "0",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "sell_commission": {
            "rate_enabled": False,
            "rate": "0",
            "minimum_enabled": False,
            "minimum": "0",
            "fixed_enabled": False,
            "fixed": "0",
        },
        "slippage": {"shared": True, "mode": "FIXED", "value": "0", "buy": None, "sell": None},
        "risk_free_rate_annual": "0.0",
    }
    config.update(overrides)
    return config


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'replay.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def seed(session: Session, email: str = "replay@example.com") -> tuple[int, int]:
    user = User(email=email, password_hash="hash")
    dataset = Dataset(
        user=user,
        name="replay-ds",
        source_type="CSV",
        original_filename="r.csv",
        security_name=None,
        security_code="159999",
        data_mode="CLOSE_ONLY",
        start_date=START,
        end_date=START + timedelta(days=2),
        row_count=3,
        column_mapping={"date": "Date", "close": "Close"},
        cleaning_summary={"bad_rows": 0},
    )
    for offset, close in enumerate(["10", "7", "10"]):
        PriceBar(dataset=dataset, date=START + timedelta(days=offset), close=Decimal(close))
    session.add(user)
    session.commit()
    return user.id, dataset.id


def make_source_run(
    session: Session, user_id: int, dataset_id: int, **config_overrides: Any
) -> BacktestRun:
    from app.api.schemas.backtests import BacktestCreateRequest

    request = BacktestCreateRequest.model_validate(
        {
            "dataset_id": dataset_id,
            "name": "Original Custom Name",
            "configuration": _create_configuration(**config_overrides),
        }
    )
    return create_backtest(session, current_user_id=user_id, request=request, now=NOW)


def _create_configuration(**overrides: Any) -> dict[str, Any]:
    config = stored_configuration()
    config.update(overrides)
    return config


def count(session: Session, model: type) -> int:
    return session.execute(sa.select(sa.func.count()).select_from(model)).scalar_one()


class TestReconstruction:
    def test_reconstructs_full_schema_with_decimals(self) -> None:
        stored = stored_configuration(initial_cash="12345.67")
        result = configuration_request_from_stored(stored)
        assert isinstance(result, BacktestConfigurationInput)
        assert isinstance(result.initial_cash, Decimal)
        assert result.initial_cash == Decimal("12345.67")
        assert isinstance(result.a_distance.value, Decimal)
        assert isinstance(result.buy_commission.rate, Decimal)

    def test_does_not_mutate_stored(self) -> None:
        stored = stored_configuration()
        snapshot = deepcopy(stored)
        configuration_request_from_stored(stored)
        assert stored == snapshot

    def test_missing_required_field_rejected(self) -> None:
        stored = stored_configuration()
        del stored["grid_step"]
        with pytest.raises(ApiError) as excinfo:
            configuration_request_from_stored(stored)
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "VALIDATION_ERROR"
        assert excinfo.value.details == {
            "field": "configuration",
            "reason": "Stored backtest configuration is invalid.",
        }

    def test_unknown_field_rejected(self) -> None:
        stored = stored_configuration(surprise=1)
        with pytest.raises(ApiError) as excinfo:
            configuration_request_from_stored(stored)
        assert excinfo.value.code == "VALIDATION_ERROR"

    def test_invalid_slippage_shape_rejected(self) -> None:
        stored = stored_configuration(
            slippage={
                "shared": True,
                "mode": None,
                "value": None,
                "buy": None,
                "sell": None,
            }
        )
        with pytest.raises(ApiError) as excinfo:
            configuration_request_from_stored(stored)
        assert excinfo.value.code == "VALIDATION_ERROR"

    def test_error_does_not_leak_stored_configuration(self) -> None:
        stored = stored_configuration(initial_cash="SECRET_BAD_VALUE")
        with pytest.raises(ApiError) as excinfo:
            configuration_request_from_stored(stored)
        assert "SECRET_BAD_VALUE" not in str(excinfo.value.details)
        assert "SECRET_BAD_VALUE" not in excinfo.value.message


class TestDeepMerge:
    def test_empty_override_equals_source(self) -> None:
        base = stored_configuration()
        assert deep_merge_configuration(base, {}) == base

    def test_nested_merge_preserves_siblings(self) -> None:
        base = {"a_distance": {"mode": "PERCENT", "value": "0.05"}}
        merged = deep_merge_configuration(base, {"a_distance": {"value": "0.06"}})
        assert merged == {"a_distance": {"mode": "PERCENT", "value": "0.06"}}

    def test_scalar_replacement(self) -> None:
        merged = deep_merge_configuration({"initial_cash": "9"}, {"initial_cash": "200000"})
        assert merged == {"initial_cash": "200000"}

    def test_null_is_explicit_replacement(self) -> None:
        merged = deep_merge_configuration({"baseline": "1.25"}, {"baseline": None})
        assert merged == {"baseline": None}

    def test_list_replacement_not_concatenation(self) -> None:
        merged = deep_merge_configuration({"levels": [1, 2, 3]}, {"levels": [9]})
        assert merged == {"levels": [9]}

    def test_does_not_mutate_inputs(self) -> None:
        base = {"a_distance": {"mode": "FIXED", "value": "2"}}
        overrides = {"a_distance": {"value": "3"}}
        base_snapshot = deepcopy(base)
        overrides_snapshot = deepcopy(overrides)
        deep_merge_configuration(base, overrides)
        assert base == base_snapshot
        assert overrides == overrides_snapshot

    def test_deterministic(self) -> None:
        base = stored_configuration()
        overrides = {"grid_step": {"value": "0.02"}}
        assert deep_merge_configuration(base, overrides) == deep_merge_configuration(
            base, overrides
        )

    def test_mapping_replaces_scalar_when_base_is_scalar(self) -> None:
        merged = deep_merge_configuration({"x": 5}, {"x": {"nested": 1}})
        assert merged == {"x": {"nested": 1}}


class TestRerun:
    def test_completed_source_reruns_and_source_unchanged(
        self, session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        source_id = source.id
        source_config = deepcopy(source.configuration)
        source_events = count(session, BacktestEvent)

        new_run = rerun_backtest(session, current_user_id=user_id, backtest_id=source_id, now=LATER)
        assert new_run.id != source_id
        assert new_run.status == "COMPLETED"
        assert new_run.configuration == source_config
        # Auto name uses current UTC date, not the copied custom name.
        assert new_run.name != "Original Custom Name"
        assert new_run.name.endswith("2026-08-01")

        with session_factory() as fresh:
            stored_source = fresh.get(BacktestRun, source_id)
            assert stored_source is not None
            assert stored_source.name == "Original Custom Name"
            assert stored_source.configuration == source_config
        # New run has its own freshly executed children.
        assert count(session, BacktestEvent) == source_events * 2

    def test_failed_source_can_rerun(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        # Force a FAILED source via sell slippage larger than the sell price.
        source = make_source_run(
            session,
            user_id,
            dataset_id,
            slippage={
                "shared": False,
                "mode": None,
                "value": None,
                "buy": {"mode": "FIXED", "value": "0"},
                "sell": {"mode": "FIXED", "value": "20"},
            },
        )
        assert source.status == "FAILED"
        new_run = rerun_backtest(session, current_user_id=user_id, backtest_id=source.id, now=LATER)
        # Same stored config -> same FAILED outcome, but a distinct run.
        assert new_run.id != source.id
        assert new_run.status == "FAILED"

    def test_missing_and_wrong_owner_not_found(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        with pytest.raises(ApiError) as missing:
            rerun_backtest(session, current_user_id=user_id, backtest_id=999999, now=LATER)
        with pytest.raises(ApiError) as foreign:
            rerun_backtest(session, current_user_id=user_id + 1, backtest_id=source.id, now=LATER)
        for excinfo in (missing, foreign):
            assert excinfo.value.status_code == 404
            assert excinfo.value.code == "BACKTEST_NOT_FOUND"

    def test_malformed_stored_config_yields_422_and_no_new_run(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        # Corrupt the persisted configuration directly.
        source.configuration = {"broken": True}
        session.commit()
        runs_before = count(session, BacktestRun)
        with pytest.raises(ApiError) as excinfo:
            rerun_backtest(session, current_user_id=user_id, backtest_id=source.id, now=LATER)
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "VALIDATION_ERROR"
        assert count(session, BacktestRun) == runs_before


class TestDuplicate:
    def test_empty_override_reproduces_source_config(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        new_run = duplicate_backtest(
            session,
            current_user_id=user_id,
            backtest_id=source.id,
            configuration_overrides={},
            now=LATER,
        )
        assert new_run.id != source.id
        assert new_run.configuration == source.configuration
        assert new_run.status == "COMPLETED"

    def test_nested_override_merges_and_source_unchanged(
        self, session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        source_config = deepcopy(source.configuration)
        new_run = duplicate_backtest(
            session,
            current_user_id=user_id,
            backtest_id=source.id,
            configuration_overrides={"grid_step": {"value": "2"}},
            now=LATER,
        )
        assert new_run.configuration["grid_step"] == {"mode": "FIXED", "value": "2"}
        # Sibling fields untouched.
        assert new_run.configuration["a_distance"] == source_config["a_distance"]
        with session_factory() as fresh:
            stored_source = fresh.get(BacktestRun, source.id)
            assert stored_source is not None
            assert stored_source.configuration == source_config

    def test_commission_override(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        new_run = duplicate_backtest(
            session,
            current_user_id=user_id,
            backtest_id=source.id,
            configuration_overrides={"buy_commission": {"minimum": "10"}},
            now=LATER,
        )
        assert new_run.configuration["buy_commission"]["minimum"] == "10"
        assert new_run.configuration["buy_commission"]["rate"] == "0"

    def test_auto_name_uses_merged_grid_step(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        new_run = duplicate_backtest(
            session,
            current_user_id=user_id,
            backtest_id=source.id,
            configuration_overrides={"grid_step": {"mode": "PERCENT", "value": "0.02"}},
            now=LATER,
        )
        assert new_run.name == "159999 — A Grid 2% — 2026-08-01"

    def test_merged_invalid_config_uses_specific_engine_code(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        runs_before = count(session, BacktestRun)
        # c_distance (2) not > a_distance (2) -> engine INVALID_ZONE_CONFIG.
        with pytest.raises(ApiError) as excinfo:
            duplicate_backtest(
                session,
                current_user_id=user_id,
                backtest_id=source.id,
                configuration_overrides={"c_distance": {"value": "2"}},
                now=LATER,
            )
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "INVALID_ZONE_CONFIG"
        assert count(session, BacktestRun) == runs_before

    def test_missing_and_wrong_owner_not_found(self, session: Session) -> None:
        user_id, dataset_id = seed(session)
        source = make_source_run(session, user_id, dataset_id)
        with pytest.raises(ApiError) as missing:
            duplicate_backtest(
                session,
                current_user_id=user_id,
                backtest_id=999999,
                configuration_overrides={},
                now=LATER,
            )
        with pytest.raises(ApiError) as foreign:
            duplicate_backtest(
                session,
                current_user_id=user_id + 1,
                backtest_id=source.id,
                configuration_overrides={},
                now=LATER,
            )
        for excinfo in (missing, foreign):
            assert excinfo.value.code == "BACKTEST_NOT_FOUND"
