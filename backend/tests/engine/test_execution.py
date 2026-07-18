"""Tests for order execution, portfolio accounting, slippage, and commission."""

import inspect
from datetime import date
from decimal import Decimal

import pytest
from app.domain.enums import (
    SkipReason,
    TradeSide,
    TradeStatus,
    ValueMode,
    ZoneEventType,
    ZoneState,
)
from app.engine.costs import (
    compute_commission,
    compute_execution_price,
    compute_slippage_amount,
)
from app.engine.execution import (
    create_portfolio_state,
    execute_or_skip,
    materialize_segment_actions,
    order_share_quantity,
    validate_execution_config,
)
from app.engine.execution_models import (
    CommissionConfig,
    ExecutionConfig,
    InvalidLotSizeError,
    InvalidTradeLotsError,
    NegativeCommissionComponentError,
    NegativeInitialCashError,
    NegativeInitialSharesError,
    NegativeSlippageError,
    NonPositiveExecutionPriceError,
    PortfolioState,
    SlippageConfig,
    TradeResult,
)
from app.engine.grid import NonPositiveTickSizeError
from app.engine.grid_models import TickSizeConfig
from app.engine.segment_models import (
    PlannedGridCrossing,
    SegmentTraversalState,
    ZoneEvent,
)

D = Decimal

DAY = date(2026, 1, 2)

TICK_OFF = TickSizeConfig(enabled=False)


def fixed_slip(value: str = "0") -> SlippageConfig:
    return SlippageConfig(mode=ValueMode.FIXED, value=D(value))


def pct_slip(value: str) -> SlippageConfig:
    return SlippageConfig(mode=ValueMode.PERCENT, value=D(value))


def commission_config(
    *,
    rate_enabled: bool = False,
    rate: str = "0",
    minimum_enabled: bool = False,
    minimum: str = "0",
    fixed_enabled: bool = False,
    fixed: str = "0",
) -> CommissionConfig:
    return CommissionConfig(
        rate_enabled=rate_enabled,
        rate=D(rate),
        minimum_enabled=minimum_enabled,
        minimum=D(minimum),
        fixed_enabled=fixed_enabled,
        fixed=D(fixed),
    )


NO_COMMISSION = commission_config()


def make_config(
    *,
    lot_size: int = 10,
    trade_lots: int = 1,
    buy_slip: SlippageConfig | None = None,
    sell_slip: SlippageConfig | None = None,
    buy_comm: CommissionConfig | None = None,
    sell_comm: CommissionConfig | None = None,
    tick: TickSizeConfig = TICK_OFF,
) -> ExecutionConfig:
    return ExecutionConfig(
        lot_size=lot_size,
        trade_lots=trade_lots,
        buy_slippage=buy_slip if buy_slip is not None else fixed_slip(),
        sell_slippage=sell_slip if sell_slip is not None else fixed_slip(),
        buy_commission=buy_comm if buy_comm is not None else NO_COMMISSION,
        sell_commission=sell_comm if sell_comm is not None else NO_COMMISSION,
        tick_size=tick,
    )


DEMO_CONFIG = make_config(
    buy_slip=fixed_slip("0.01"),
    sell_slip=fixed_slip("0.01"),
    buy_comm=commission_config(minimum_enabled=True, minimum="0.50"),
    sell_comm=commission_config(minimum_enabled=True, minimum="0.50"),
    tick=TickSizeConfig(enabled=True, value=D("0.01")),
)


def crossing(level: str, side: TradeSide, day: int = 2) -> PlannedGridCrossing:
    return PlannedGridCrossing(grid_level=D(level), side=side, event_date=date(2026, 1, day))


def make_traversal(anchor: str = "1.00") -> SegmentTraversalState:
    return SegmentTraversalState(
        market_cursor=D("1.00"), trade_anchor=D(anchor), zone_state=ZoneState.IN_A
    )


ZONE_EVENT = ZoneEvent(
    event_type=ZoneEventType.ENTER_C_ZONE,
    boundary_price=D("1.10"),
    event_date=DAY,
    old_zone=ZoneState.IN_A,
    new_zone=ZoneState.IN_C,
)


# ---------------------------------------------------------------------------
# Portfolio initialization
# ---------------------------------------------------------------------------


def test_nonnegative_initial_values_accepted() -> None:
    portfolio = create_portfolio_state(D("100.50"), 7)
    assert portfolio.cash == D("100.50")
    assert portfolio.shares == 7  # not a lot multiple: allowed


def test_zero_cash_and_zero_shares_accepted() -> None:
    portfolio = create_portfolio_state(D("0"), 0)
    assert portfolio.cash == D("0")
    assert portfolio.shares == 0


def test_negative_cash_rejected() -> None:
    with pytest.raises(NegativeInitialCashError):
        create_portfolio_state(D("-0.01"), 0)


def test_negative_shares_rejected() -> None:
    with pytest.raises(NegativeInitialSharesError):
        create_portfolio_state(D("1"), -1)


def test_portfolio_state_is_mutable() -> None:
    portfolio = create_portfolio_state(D("10"), 5)
    portfolio.cash = D("20")
    portfolio.shares = 6
    assert portfolio == PortfolioState(cash=D("20"), shares=6)


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


def test_minimal_valid_config_accepted() -> None:
    validate_execution_config(make_config(lot_size=1, trade_lots=1))


@pytest.mark.parametrize("lot_size", [0, -1])
def test_invalid_lot_size_rejected(lot_size: int) -> None:
    with pytest.raises(InvalidLotSizeError) as exc_info:
        validate_execution_config(make_config(lot_size=lot_size))
    assert exc_info.value.lot_size == lot_size


@pytest.mark.parametrize("trade_lots", [0, -2])
def test_invalid_trade_lots_rejected(trade_lots: int) -> None:
    with pytest.raises(InvalidTradeLotsError) as exc_info:
        validate_execution_config(make_config(trade_lots=trade_lots))
    assert exc_info.value.trade_lots == trade_lots


def test_zero_and_positive_slippage_accepted() -> None:
    validate_execution_config(make_config(buy_slip=fixed_slip("0"), sell_slip=pct_slip("0.001")))


def test_negative_buy_slippage_rejected() -> None:
    with pytest.raises(NegativeSlippageError) as exc_info:
        validate_execution_config(make_config(buy_slip=fixed_slip("-0.01")))
    assert exc_info.value.side is TradeSide.BUY
    assert exc_info.value.value == D("-0.01")


def test_negative_sell_slippage_rejected() -> None:
    with pytest.raises(NegativeSlippageError) as exc_info:
        validate_execution_config(make_config(sell_slip=pct_slip("-0.001")))
    assert exc_info.value.side is TradeSide.SELL


@pytest.mark.parametrize("component", ["rate", "minimum", "fixed"])
@pytest.mark.parametrize("side", [TradeSide.BUY, TradeSide.SELL])
def test_enabled_negative_commission_component_rejected(side: TradeSide, component: str) -> None:
    bad = commission_config(**{f"{component}_enabled": True, component: "-1"})  # type: ignore[arg-type]
    config = make_config(buy_comm=bad) if side is TradeSide.BUY else make_config(sell_comm=bad)
    with pytest.raises(NegativeCommissionComponentError) as exc_info:
        validate_execution_config(config)
    assert exc_info.value.side is side
    assert exc_info.value.component == component
    assert exc_info.value.value == D("-1")


def test_disabled_negative_components_are_ignored() -> None:
    unused_negative = commission_config(rate="-1", minimum="-1", fixed="-1")
    validate_execution_config(make_config(buy_comm=unused_negative, sell_comm=unused_negative))


def test_tick_disabled_allows_none() -> None:
    validate_execution_config(make_config(tick=TickSizeConfig(enabled=False, value=None)))


@pytest.mark.parametrize("value", [None, "0", "-0.01"])
def test_tick_enabled_requires_positive_value(value: str | None) -> None:
    tick = TickSizeConfig(enabled=True, value=None if value is None else D(value))
    with pytest.raises(NonPositiveTickSizeError):
        validate_execution_config(make_config(tick=tick))


# ---------------------------------------------------------------------------
# Order quantity
# ---------------------------------------------------------------------------


def test_order_quantity_is_exact_product_and_int() -> None:
    quantity = order_share_quantity(make_config(lot_size=100, trade_lots=3))
    assert quantity == 300
    assert type(quantity) is int


# ---------------------------------------------------------------------------
# Slippage and execution price
# ---------------------------------------------------------------------------


def test_fixed_slippage_amount() -> None:
    assert compute_slippage_amount(D("1.00"), fixed_slip("0.02")) == D("0.02")


def test_percent_slippage_uses_canonical_grid_price() -> None:
    assert compute_slippage_amount(D("1.005"), pct_slip("0.1")) == D("0.1005")


def test_buy_adds_and_sell_subtracts_slippage() -> None:
    buy = compute_execution_price(
        grid_price=D("1.00"), side=TradeSide.BUY, slippage=fixed_slip("0.02"), tick_size=TICK_OFF
    )
    sell = compute_execution_price(
        grid_price=D("1.00"), side=TradeSide.SELL, slippage=fixed_slip("0.02"), tick_size=TICK_OFF
    )
    assert buy == D("1.02")
    assert sell == D("0.98")


def test_tick_disabled_execution_price_is_exact() -> None:
    price = compute_execution_price(
        grid_price=D("1.00"),
        side=TradeSide.BUY,
        slippage=pct_slip("0.0015"),
        tick_size=TICK_OFF,
    )
    assert price == D("1.0015")
    assert str(price) == "1.001500"  # exact Decimal arithmetic, no quantization


def test_tick_enabled_rounds_after_slippage_with_half_up() -> None:
    price = compute_execution_price(
        grid_price=D("1.00"),
        side=TradeSide.BUY,
        slippage=pct_slip("0.015"),
        tick_size=TickSizeConfig(enabled=True, value=D("0.01")),
    )
    assert price == D("1.02")  # raw 1.015 rounds half-up to 1.02


def test_canonical_grid_price_is_not_rounded_again() -> None:
    # Slippage derives from the 1.005 canonical price itself; if the grid were
    # re-rounded to 1.00 or 1.01 first, the result would be 1.11 or 1.12 via a
    # different slippage amount.
    price = compute_execution_price(
        grid_price=D("1.005"),
        side=TradeSide.BUY,
        slippage=pct_slip("0.1"),
        tick_size=TickSizeConfig(enabled=True, value=D("0.01")),
    )
    assert price == D("1.11")  # round_to_tick(1.005 + 0.1005) == round(1.1055)


def test_non_positive_execution_price_raises_with_fields() -> None:
    with pytest.raises(NonPositiveExecutionPriceError) as exc_info:
        compute_execution_price(
            grid_price=D("0.95"),
            side=TradeSide.SELL,
            slippage=fixed_slip("1.00"),
            tick_size=TICK_OFF,
        )
    assert exc_info.value.grid_price == D("0.95")
    assert exc_info.value.execution_price == D("-0.05")


def test_execution_price_failure_does_not_mutate_state() -> None:
    portfolio = create_portfolio_state(D("100"), 50)
    traversal = make_traversal()
    config = make_config(sell_slip=fixed_slip("1.00"))
    with pytest.raises(NonPositiveExecutionPriceError):
        execute_or_skip(
            crossing("0.95", TradeSide.SELL),
            portfolio=portfolio,
            traversal=traversal,
            config=config,
        )
    assert portfolio == PortfolioState(cash=D("100"), shares=50)
    assert traversal.trade_anchor == D("1.00")


def test_compute_execution_price_rejects_enabled_tick_without_value() -> None:
    with pytest.raises(NonPositiveTickSizeError):
        compute_execution_price(
            grid_price=D("1.00"),
            side=TradeSide.BUY,
            slippage=fixed_slip("0.01"),
            tick_size=TickSizeConfig(enabled=True, value=None),
        )


def test_zero_execution_price_also_raises() -> None:
    with pytest.raises(NonPositiveExecutionPriceError):
        compute_execution_price(
            grid_price=D("0.95"),
            side=TradeSide.SELL,
            slippage=fixed_slip("0.95"),
            tick_size=TICK_OFF,
        )


# ---------------------------------------------------------------------------
# Commission
# ---------------------------------------------------------------------------


def test_all_components_disabled_gives_zero() -> None:
    assert compute_commission(D("100"), NO_COMMISSION) == D("0")


def test_rate_only() -> None:
    config = commission_config(rate_enabled=True, rate="0.001")
    assert compute_commission(D("100"), config) == D("0.100")


def test_minimum_only_with_rate_disabled() -> None:
    config = commission_config(minimum_enabled=True, minimum="5")
    assert compute_commission(D("100"), config) == D("5")


def test_fixed_only() -> None:
    config = commission_config(fixed_enabled=True, fixed="2")
    assert compute_commission(D("100"), config) == D("2")


def test_rate_plus_minimum_floors_small_percentage() -> None:
    config = commission_config(rate_enabled=True, rate="0.001", minimum_enabled=True, minimum="5")
    assert compute_commission(D("100"), config) == D("5")  # 0.10 floored to 5
    assert compute_commission(D("10000"), config) == D("10.000")  # 10 not floored


def test_rate_plus_fixed() -> None:
    config = commission_config(rate_enabled=True, rate="0.001", fixed_enabled=True, fixed="2")
    assert compute_commission(D("100"), config) == D("2.100")


def test_minimum_plus_fixed() -> None:
    config = commission_config(minimum_enabled=True, minimum="5", fixed_enabled=True, fixed="2")
    assert compute_commission(D("100"), config) == D("7")


def test_all_three_enabled() -> None:
    config = commission_config(
        rate_enabled=True,
        rate="0.001",
        minimum_enabled=True,
        minimum="5",
        fixed_enabled=True,
        fixed="2",
    )
    assert compute_commission(D("100"), config) == D("7")  # max(0.10, 5) + 2


def test_disabled_minimum_does_not_floor() -> None:
    config = commission_config(rate_enabled=True, rate="0.001", minimum="99")
    assert compute_commission(D("100"), config) == D("0.100")


def test_disabled_rate_and_fixed_values_are_ignored() -> None:
    config = commission_config(rate="99", minimum_enabled=True, minimum="5", fixed="99")
    assert compute_commission(D("100"), config) == D("5")


def test_separate_buy_and_sell_configs_differ() -> None:
    buy = commission_config(rate_enabled=True, rate="0.001")
    sell = commission_config(fixed_enabled=True, fixed="5")
    assert compute_commission(D("1000"), buy) != compute_commission(D("1000"), sell)


def test_commission_can_exceed_notional() -> None:
    config = commission_config(minimum_enabled=True, minimum="5")
    assert compute_commission(D("3"), config) == D("5")


def test_commission_preserves_decimal_precision_and_is_never_rounded() -> None:
    config = commission_config(rate_enabled=True, rate="0.0015")
    assert str(compute_commission(D("9.60"), config)) == "0.014400"


# ---------------------------------------------------------------------------
# BUY execution
# ---------------------------------------------------------------------------


def test_successful_buy_full_contract() -> None:
    portfolio = create_portfolio_state(D("25.00"), 20)
    traversal = make_traversal()
    result = execute_or_skip(
        crossing("0.95", TradeSide.BUY),
        portfolio=portfolio,
        traversal=traversal,
        config=DEMO_CONFIG,
    )
    assert result.status is TradeStatus.EXECUTED
    assert result.skip_reason is None
    assert result.side is TradeSide.BUY
    assert result.grid_price == D("0.95")
    assert result.execution_price == D("0.96")  # 0.95 + 0.01 fixed slippage, on tick
    assert result.shares == 10
    assert result.notional == D("9.60")
    assert result.commission == D("0.50")  # minimum floor over disabled rate
    assert result.slippage_cost == D("0.10")  # |0.96 - 0.95| * 10
    assert result.cash_after == D("14.90")
    assert result.shares_after == 30
    assert result.equity_after == D("14.90") + 30 * D("0.95")  # canonical grid mark
    assert result.event_date == DAY
    assert portfolio.cash == D("14.90")
    assert portfolio.shares == 30
    assert traversal.trade_anchor == D("0.95")  # canonical grid, not 0.96
    assert traversal.market_cursor == D("1.00")  # unchanged
    assert traversal.zone_state is ZoneState.IN_A  # unchanged


def test_buy_with_exact_affordability_executes() -> None:
    portfolio = create_portfolio_state(D("10.10"), 0)  # exactly notional 9.60 + 0.50
    traversal = make_traversal()
    result = execute_or_skip(
        crossing("0.95", TradeSide.BUY),
        portfolio=portfolio,
        traversal=traversal,
        config=DEMO_CONFIG,
    )
    assert result.status is TradeStatus.EXECUTED
    assert portfolio.cash == D("0.00")


def test_skipped_buy_contract() -> None:
    portfolio = create_portfolio_state(D("5.30"), 40)
    traversal = make_traversal(anchor="0.90")
    result = execute_or_skip(
        crossing("0.85", TradeSide.BUY),
        portfolio=portfolio,
        traversal=traversal,
        config=DEMO_CONFIG,
    )
    assert result.status is TradeStatus.SKIPPED
    assert result.skip_reason is SkipReason.INSUFFICIENT_CASH
    assert result.execution_price is None
    assert result.notional is None
    assert result.commission is None
    assert result.slippage_cost is None
    assert result.shares == 10  # attempted quantity remains populated
    assert result.cash_after == D("5.30")
    assert result.shares_after == 40
    assert result.equity_after == D("5.30") + 40 * D("0.85")
    assert portfolio == PortfolioState(cash=D("5.30"), shares=40)
    assert traversal.trade_anchor == D("0.90")  # unchanged


# ---------------------------------------------------------------------------
# SELL execution
# ---------------------------------------------------------------------------


def test_successful_sell_full_contract() -> None:
    portfolio = create_portfolio_state(D("5.30"), 40)
    traversal = make_traversal(anchor="0.90")
    result = execute_or_skip(
        crossing("1.00", TradeSide.SELL),
        portfolio=portfolio,
        traversal=traversal,
        config=DEMO_CONFIG,
    )
    assert result.status is TradeStatus.EXECUTED
    assert result.execution_price == D("0.99")
    assert result.notional == D("9.90")
    assert result.commission == D("0.50")
    assert result.cash_after == D("14.70")
    assert result.shares_after == 30
    assert result.equity_after == D("14.70") + 30 * D("1.00")
    assert traversal.trade_anchor == D("1.00")


def test_sell_commission_exceeding_notional_may_execute() -> None:
    portfolio = create_portfolio_state(D("1.00"), 10)
    traversal = make_traversal()
    config = make_config(
        sell_slip=fixed_slip("0.01"),
        sell_comm=commission_config(minimum_enabled=True, minimum="0.50"),
    )
    result = execute_or_skip(
        crossing("0.04", TradeSide.SELL), portfolio=portfolio, traversal=traversal, config=config
    )
    assert result.status is TradeStatus.EXECUTED
    assert result.notional == D("0.30")  # exec 0.03 * 10
    assert result.commission == D("0.50")  # exceeds notional
    assert portfolio.cash == D("0.80")  # 1.00 + 0.30 - 0.50: decreased


def test_sell_reaching_exact_zero_cash_is_allowed() -> None:
    portfolio = create_portfolio_state(D("0.20"), 10)
    traversal = make_traversal()
    config = make_config(
        sell_slip=fixed_slip("0.01"),
        sell_comm=commission_config(minimum_enabled=True, minimum="0.50"),
    )
    result = execute_or_skip(
        crossing("0.04", TradeSide.SELL), portfolio=portfolio, traversal=traversal, config=config
    )
    assert result.status is TradeStatus.EXECUTED
    assert portfolio.cash == D("0.00")


def test_insufficient_shares_skip_wins_over_cash_for_commission() -> None:
    # Cash 0 with a huge minimum commission would also fail the cash check,
    # but the shares check is evaluated first per SPEC 16.3.
    portfolio = create_portfolio_state(D("0"), 5)
    traversal = make_traversal()
    config = make_config(sell_comm=commission_config(minimum_enabled=True, minimum="999"))
    result = execute_or_skip(
        crossing("1.00", TradeSide.SELL), portfolio=portfolio, traversal=traversal, config=config
    )
    assert result.status is TradeStatus.SKIPPED
    assert result.skip_reason is SkipReason.INSUFFICIENT_SHARES
    assert portfolio == PortfolioState(cash=D("0"), shares=5)
    assert traversal.trade_anchor == D("1.00")


def test_insufficient_cash_for_commission_skip() -> None:
    portfolio = create_portfolio_state(D("0.10"), 10)
    traversal = make_traversal()
    config = make_config(
        sell_slip=fixed_slip("0.01"),
        sell_comm=commission_config(minimum_enabled=True, minimum="0.50"),
    )
    result = execute_or_skip(
        crossing("0.04", TradeSide.SELL), portfolio=portfolio, traversal=traversal, config=config
    )
    assert result.status is TradeStatus.SKIPPED
    assert result.skip_reason is SkipReason.INSUFFICIENT_CASH_FOR_COMMISSION
    assert result.execution_price is None
    assert result.notional is None
    assert result.commission is None
    assert result.slippage_cost is None
    assert portfolio == PortfolioState(cash=D("0.10"), shares=10)
    assert traversal.trade_anchor == D("1.00")


# ---------------------------------------------------------------------------
# Ordered action materialization
# ---------------------------------------------------------------------------


def test_materialize_preserves_order_and_transforms_crossings() -> None:
    portfolio = create_portfolio_state(D("25.00"), 20)
    traversal = make_traversal()
    actions = (
        crossing("0.95", TradeSide.BUY),
        ZONE_EVENT,
        crossing("0.90", TradeSide.BUY),
    )
    results = materialize_segment_actions(
        actions, portfolio=portfolio, traversal=traversal, config=DEMO_CONFIG
    )
    assert len(results) == 3
    assert isinstance(results[0], TradeResult)
    assert results[1] is ZONE_EVENT  # exact object passthrough
    assert isinstance(results[2], TradeResult)
    assert actions == (
        crossing("0.95", TradeSide.BUY),
        ZONE_EVENT,
        crossing("0.90", TradeSide.BUY),
    )  # input not mutated


def test_zone_event_passthrough_does_not_reapply_transition_or_touch_portfolio() -> None:
    portfolio = create_portfolio_state(D("25.00"), 20)
    traversal = make_traversal()
    materialize_segment_actions(
        (ZONE_EVENT,), portfolio=portfolio, traversal=traversal, config=DEMO_CONFIG
    )
    assert traversal.zone_state is ZoneState.IN_A  # planning already applied it
    assert traversal.trade_anchor == D("1.00")
    assert portfolio == PortfolioState(cash=D("25.00"), shares=20)


def test_materialize_continues_after_skips_and_updates_anchor_on_fills() -> None:
    portfolio = create_portfolio_state(D("25.00"), 20)
    traversal = make_traversal()
    actions = (
        crossing("0.95", TradeSide.BUY),
        crossing("0.90", TradeSide.BUY),
        crossing("0.85", TradeSide.BUY),
        crossing("1.00", TradeSide.SELL),
    )
    results = materialize_segment_actions(
        actions, portfolio=portfolio, traversal=traversal, config=DEMO_CONFIG
    )
    statuses = [r.status for r in results if isinstance(r, TradeResult)]
    assert statuses == [
        TradeStatus.EXECUTED,
        TradeStatus.EXECUTED,
        TradeStatus.SKIPPED,
        TradeStatus.EXECUTED,
    ]
    skipped = results[2]
    assert isinstance(skipped, TradeResult)
    assert skipped.skip_reason is SkipReason.INSUFFICIENT_CASH
    assert traversal.trade_anchor == D("1.00")  # last fill's canonical grid price
    assert portfolio.cash == D("14.70")
    assert portfolio.shares == 30


def test_skipped_first_crossing_leaves_anchor_and_later_levels_attempted() -> None:
    portfolio = create_portfolio_state(D("0"), 50)
    traversal = make_traversal(anchor="1.05")
    actions = (
        crossing("1.00", TradeSide.BUY),  # skipped: no cash
        crossing("0.95", TradeSide.SELL),  # sell attempt still occurs afterwards
    )
    results = materialize_segment_actions(
        actions, portfolio=portfolio, traversal=traversal, config=make_config()
    )
    first, second = results
    assert isinstance(first, TradeResult)
    assert isinstance(second, TradeResult)
    assert first.status is TradeStatus.SKIPPED
    assert traversal.trade_anchor == D("0.95")  # updated by the later successful sell
    assert second.status is TradeStatus.EXECUTED


def test_all_event_dates_are_preserved() -> None:
    portfolio = create_portfolio_state(D("25.00"), 20)
    traversal = make_traversal()
    results = materialize_segment_actions(
        (crossing("0.95", TradeSide.BUY, day=3),),
        portfolio=portfolio,
        traversal=traversal,
        config=DEMO_CONFIG,
    )
    result = results[0]
    assert isinstance(result, TradeResult)
    assert result.event_date == date(2026, 1, 3)


def test_no_event_sequence_field_exists() -> None:
    assert "event_sequence" not in TradeResult.__dataclass_fields__


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_public_imports_work_from_app_engine() -> None:
    import app.engine as engine_pkg

    for name in (
        "SlippageConfig",
        "CommissionConfig",
        "ExecutionConfig",
        "PortfolioState",
        "TradeResult",
        "NegativeInitialCashError",
        "NegativeInitialSharesError",
        "InvalidLotSizeError",
        "InvalidTradeLotsError",
        "NegativeSlippageError",
        "NegativeCommissionComponentError",
        "NonPositiveExecutionPriceError",
        "create_portfolio_state",
        "validate_execution_config",
        "order_share_quantity",
        "compute_slippage_amount",
        "compute_execution_price",
        "compute_commission",
        "execute_or_skip",
        "materialize_segment_actions",
    ):
        assert hasattr(engine_pkg, name), name
        assert name in engine_pkg.__all__


def test_prior_task_exports_remain_available() -> None:
    import app.engine as engine_pkg

    for name in (
        "build_grid_setup",
        "classify_zone",
        "round_to_tick",
        "build_price_path",
        "build_path_segments",
        "initialize_path_state",
        "plan_segment_actions",
        "apply_boundary_transition",
        "eligible_grid_levels",
        "transition_rule",
    ):
        assert callable(getattr(engine_pkg, name)), name


def test_execution_modules_have_no_framework_or_downstream_dependencies() -> None:
    import app.engine.costs
    import app.engine.execution
    import app.engine.execution_models

    modules = (app.engine.costs, app.engine.execution, app.engine.execution_models)
    for module in modules:
        source = inspect.getsource(module).lower()
        for forbidden in (
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "app.importing",
            "metric",
            "benchmark",
            "eventequity",
            "dailyequity",
        ):
            assert forbidden not in source, f"{module.__name__} contains {forbidden!r}"


def test_no_equity_row_models_are_introduced() -> None:
    import app.engine as engine_pkg

    assert not hasattr(engine_pkg, "EventEquity")
    assert not hasattr(engine_pkg, "DailyEquity")
    assert not hasattr(engine_pkg, "BacktestEvent")
