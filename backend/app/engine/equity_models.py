"""Immutable equity-capture models and their pure-domain exceptions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import ZoneState
from app.engine.execution_models import TradeResult
from app.engine.segment_models import ZoneEvent

__all__ = [
    "DailyEquityPoint",
    "EventEquityPoint",
    "InvalidEventSequenceError",
    "NonPositiveRunningPeakError",
    "SequencedAction",
    "ZeroInitialEquityError",
]


@dataclass(frozen=True, slots=True)
class DailyEquityPoint:
    date: date
    close: Decimal
    cash: Decimal
    shares: int
    equity: Decimal
    drawdown: Decimal
    zone_at_close: ZoneState


@dataclass(frozen=True, slots=True)
class EventEquityPoint:
    date: date
    event_sequence: int
    market_price: Decimal
    cash: Decimal
    shares: int
    equity: Decimal


@dataclass(frozen=True, slots=True)
class SequencedAction:
    """Ordering wrapper only; the Task 12 orchestrator allocates the sequence.

    The wrapped action already carries its own event date and market price, so
    neither is duplicated here.
    """

    event_sequence: int
    action: TradeResult | ZoneEvent


class ZeroInitialEquityError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Initial equity must be > 0; zero cash with zero shares is not a runnable portfolio."
        )


class NonPositiveRunningPeakError(Exception):
    def __init__(self, value: Decimal) -> None:
        super().__init__(f"Running equity peak must be > 0; got {value}.")
        self.value = value


class InvalidEventSequenceError(Exception):
    def __init__(self, event_sequence: int) -> None:
        super().__init__(f"event_sequence must be >= 1; got {event_sequence}.")
        self.event_sequence = event_sequence
