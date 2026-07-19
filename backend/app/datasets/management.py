"""Owned-dataset management services: list, detail, delete (SPEC 24.4, 25.2).

Ownership filtering lives inside every SQL query — a non-owner's Dataset
row never enters application memory, so missing and wrong-owner resources
are indistinguishable by construction. PriceBars are removed by the
database's ON DELETE CASCADE, never by per-row deletes.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Dataset

__all__ = [
    "DatasetInUseError",
    "delete_owned_dataset",
    "get_owned_dataset",
    "is_foreign_key_violation",
    "list_owned_datasets",
]

_SQLITE_FK_MESSAGE = "FOREIGN KEY constraint failed"
_POSTGRESQL_FK_SQLSTATE = "23503"


class DatasetInUseError(Exception):
    """Deletion blocked by a dependent resource through ON DELETE RESTRICT."""


def is_foreign_key_violation(error: IntegrityError) -> bool:
    """Recognize a foreign-key restriction across PostgreSQL and SQLite.

    PostgreSQL drivers expose SQLSTATE 23503 (psycopg3 ``sqlstate``,
    psycopg2 ``pgcode``); SQLite reports a fixed message text. Other
    integrity failures (unique, not-null, check) are never treated as
    foreign-key violations.
    """
    original = error.orig
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate == _POSTGRESQL_FK_SQLSTATE:
        return True
    return _SQLITE_FK_MESSAGE in str(original)


def list_owned_datasets(session: Session, *, owner_user_id: int) -> tuple[Dataset, ...]:
    """All Datasets owned by the user, newest first (id breaks ties).

    Read-only: never commits or mutates rows, and never loads PriceBars.
    """
    statement = (
        select(Dataset)
        .where(Dataset.user_id == owner_user_id)
        .order_by(Dataset.created_at.desc(), Dataset.id.desc())
    )
    return tuple(session.execute(statement).scalars().all())


def get_owned_dataset(session: Session, *, dataset_id: int, owner_user_id: int) -> Dataset | None:
    """The Dataset only when it exists AND belongs to the user; else None."""
    statement = select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == owner_user_id)
    return session.execute(statement).scalar_one_or_none()


def delete_owned_dataset(session: Session, *, dataset_id: int, owner_user_id: int) -> bool:
    """Delete an owned Dataset; PriceBars go via the database cascade.

    Returns False when the Dataset is missing or owned by someone else.
    Raises DatasetInUseError when a dependent resource's ON DELETE
    RESTRICT foreign key blocks the delete (rolled back, session usable).
    """
    dataset = get_owned_dataset(session, dataset_id=dataset_id, owner_user_id=owner_user_id)
    if dataset is None:
        return False
    session.delete(dataset)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if is_foreign_key_violation(error):
            raise DatasetInUseError("Dataset is referenced by dependent resources.") from error
        raise
    return True
