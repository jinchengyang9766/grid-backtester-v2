"""Persistence models.

Importing this package registers every model on Base.metadata, which is what
Alembic's env.py relies on before evaluating target_metadata.
"""

from app.db.models.dataset import Dataset
from app.db.models.price_bar import PriceBar
from app.db.models.user import User

__all__ = ["Dataset", "PriceBar", "User"]
