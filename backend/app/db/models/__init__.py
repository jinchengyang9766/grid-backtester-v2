"""Persistence models.

Importing this package registers every model on Base.metadata, which is what
Alembic's env.py relies on before evaluating target_metadata.
"""

from app.db.models.backtest_event import BacktestEvent
from app.db.models.backtest_run import BacktestRun
from app.db.models.daily_equity import DailyEquity
from app.db.models.dataset import Dataset
from app.db.models.event_equity import EventEquity
from app.db.models.price_bar import PriceBar
from app.db.models.trade import Trade
from app.db.models.user import User
from app.db.models.zone_event import ZoneEventRecord

__all__ = [
    "BacktestEvent",
    "BacktestRun",
    "DailyEquity",
    "Dataset",
    "EventEquity",
    "PriceBar",
    "Trade",
    "User",
    "ZoneEventRecord",
]
