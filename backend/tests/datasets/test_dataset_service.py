"""Unit tests for the dataset preview/save service layer."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from app.api.errors import ApiError
from app.datasets.preview_cache import PreviewCache
from app.datasets.service import (
    build_preview_entry,
    cleaning_summary_to_json,
    sanitize_filename,
    save_dataset,
)
from app.db import Base
from app.db.models import Dataset, PriceBar, User
from app.db.session import create_database_engine, create_session_factory
from app.domain.enums import DataMode
from app.importing import decode_tdx_bytes
from sqlalchemy.orm import Session, sessionmaker

TDX_TEXT = (
    "农业ETF基金 (159825)\t\t\t\t\t\n"
    "时间\t开盘\t最高\t最低\t收盘\t成交量\n"
    "2024/07/23\t1.00\t1.10\t0.90\t1.05\t1000\n"
    "2024/07/24\t1.05\t1.15\t1.00\t1.10\t1200\n"
    "数据来源：通达信\n"
)
CSV_TEXT = "Date,Close\n2024/07/23,1.05\n2024/07/24,1.10\n"


def tdx_bytes() -> bytes:
    return TDX_TEXT.encode("gb18030")


def build(raw: bytes, filename: str, manual: str | None = None, owner: int = 1):  # type: ignore[no-untyped-def]
    return build_preview_entry(
        raw=raw, filename=filename, manual_mapping_json=manual, owner_user_id=owner
    )


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("supplied", "expected"),
        [
            (r"C:\fakepath\159825.xls", "159825.xls"),
            ("../../private.csv", "private.csv"),
            ("plain.csv", "plain.csv"),
            (r"mixed/style\name.xls", "name.xls"),
            ("  spaced.csv  ", "spaced.csv"),
        ],
    )
    def test_basename_only(self, supplied: str, expected: str) -> None:
        assert sanitize_filename(supplied) == expected


class TestBuildPreviewEntry:
    def test_tdx_entry_fields(self) -> None:
        entry = build(tdx_bytes(), "159825.xls")
        assert entry.detected_format == "TDX_XLS"
        assert entry.detected_encoding == "gb18030"
        assert entry.security_name == "农业ETF基金"
        assert entry.security_code == "159825"
        assert entry.data_mode is DataMode.OHLCV
        assert len(entry.bars) == 2
        assert entry.bars[0].close == Decimal("1.05")
        assert entry.original_filename == "159825.xls"
        decoded = decode_tdx_bytes(tdx_bytes())
        expected_hash = hashlib.sha256(decoded.text.encode("utf-8")).hexdigest()
        assert entry.source_content_hash == expected_hash
        assert entry.expires_at - entry.created_at == timedelta(minutes=30)

    def test_csv_close_only_entry(self) -> None:
        entry = build(CSV_TEXT.encode("utf-8-sig"), "data.csv")
        assert entry.detected_format == "CSV"
        assert entry.detected_encoding == "utf-8-sig"
        assert entry.data_mode is DataMode.CLOSE_ONLY
        assert entry.security_name is None
        assert entry.security_code is None

    def test_tdx_without_title_has_null_metadata(self) -> None:
        text = "时间\t收盘\n2024/07/23\t1.05\n"
        entry = build(text.encode("gb18030"), "plain.xls")
        assert entry.security_name is None
        assert entry.security_code is None

    def test_tab_separated_title_form(self) -> None:
        text = "某证券\t159999\n时间\t收盘\n2024/07/23\t1.05\n"
        entry = build(text.encode("gb18030"), "tab.xls")
        assert entry.security_name == "某证券"
        assert entry.security_code == "159999"

    def test_unsupported_extension(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(b"whatever", "data.txt")
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "UNSUPPORTED_FILE_TYPE"

    def test_binary_ole2_xls_rejected(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16, "book.xls")
        assert excinfo.value.code == "UNSUPPORTED_FILE_TYPE"

    def test_zip_container_xls_rejected(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(b"PK\x03\x04rest-of-zip", "book.xls")
        assert excinfo.value.code == "UNSUPPORTED_FILE_TYPE"

    def test_undecodable_bytes(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(b"\xff\xff\xff", "data.csv")
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "ENCODING_DETECTION_FAILED"

    def test_header_not_found(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(b"no headers here\njust prose\n", "notes.xls")
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "HEADER_NOT_FOUND"

    def test_zero_cleaned_rows_rejected(self) -> None:
        text = "Date,Close\nnot-a-date,abc\n"
        with pytest.raises(ApiError) as excinfo:
            build(text.encode(), "bad.csv")
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "VALIDATION_ERROR"

    def test_unknown_manual_mapping_key(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(CSV_TEXT.encode(), "data.csv", manual='{"adjusted": "Close"}')
        assert excinfo.value.status_code == 422
        assert excinfo.value.code == "VALIDATION_ERROR"

    def test_unknown_source_header(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(CSV_TEXT.encode(), "data.csv", manual='{"close": "Nope"}')
        assert excinfo.value.status_code == 422

    def test_duplicate_source_column(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(tdx_bytes(), "data.xls", manual='{"open": "收盘"}')
        assert excinfo.value.status_code == 422

    def test_partial_ohlc_rejected(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(tdx_bytes(), "data.xls", manual='{"open": null}')
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "MISSING_REQUIRED_COLUMN"
        assert excinfo.value.details == {"partial_ohlc_fields": ["high", "low"]}

    def test_missing_close_rejected(self) -> None:
        with pytest.raises(ApiError) as excinfo:
            build(CSV_TEXT.encode(), "data.csv", manual='{"close": null}')
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "MISSING_REQUIRED_COLUMN"
        assert excinfo.value.details == {"missing_fields": ["close"]}


class TestCleaningSummaryJson:
    def test_exact_shape(self) -> None:
        entry = build(tdx_bytes(), "159825.xls")
        assert cleaning_summary_to_json(entry.cleaning_summary) == {
            "total_rows_parsed": 2,
            "valid_rows": 2,
            "bad_rows": 0,
            "duplicate_dates": 0,
            "final_row_count": 2,
            "date_range": {"start": "2024-07-23", "end": "2024-07-24"},
            "data_mode": "OHLCV",
            "bad_row_reasons": {
                "UNPARSEABLE_DATE": 0,
                "MISSING_CLOSE": 0,
                "NON_POSITIVE_PRICE": 0,
                "MISSING_OHLC_FIELD": 0,
                "INVALID_OHLC_RANGE": 0,
                "INVALID_VOLUME": 0,
                "NEGATIVE_VOLUME": 0,
            },
        }


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'service_test.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def make_user(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        user = User(email="owner@example.com", password_hash="hash")
        session.add(user)
        session.commit()
        return user.id


class TestSaveDataset:
    def test_saves_dataset_and_price_bars(self, session_factory: sessionmaker[Session]) -> None:
        owner_id = make_user(session_factory)
        cache = PreviewCache()
        entry = build(tdx_bytes(), "159825.xls", owner=owner_id)
        token = cache.put(entry)
        with session_factory() as session:
            dataset = save_dataset(
                session, cache, token=token, name="  My Dataset  ", owner_user_id=owner_id
            )
            assert dataset.name == "My Dataset"
            assert dataset.user_id == owner_id
            assert dataset.row_count == 2
            assert dataset.start_date == date(2024, 7, 23)
            assert dataset.end_date == date(2024, 7, 24)
        with session_factory() as session:
            bars = session.execute(sa.select(PriceBar).order_by(PriceBar.date)).scalars().all()
            assert len(bars) == 2
            assert isinstance(bars[0].close, Decimal)
            assert bars[0].close == Decimal("1.05")

    def test_token_consumed_after_save(self, session_factory: sessionmaker[Session]) -> None:
        owner_id = make_user(session_factory)
        cache = PreviewCache()
        token = cache.put(build(tdx_bytes(), "a.xls", owner=owner_id))
        with session_factory() as session:
            save_dataset(session, cache, token=token, name="One", owner_user_id=owner_id)
        with session_factory() as session, pytest.raises(ApiError) as excinfo:
            save_dataset(session, cache, token=token, name="Two", owner_user_id=owner_id)
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "PREVIEW_TOKEN_NOT_FOUND"

    def test_wrong_owner_does_not_consume(self, session_factory: sessionmaker[Session]) -> None:
        owner_id = make_user(session_factory)
        cache = PreviewCache()
        entry = build(tdx_bytes(), "a.xls", owner=owner_id)
        token = cache.put(entry)
        with session_factory() as session, pytest.raises(ApiError):
            save_dataset(session, cache, token=token, name="X", owner_user_id=owner_id + 1)
        assert cache.get_for_owner(token, owner_id) is entry

    def test_failure_rolls_back_and_restores_token(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        owner_id = make_user(session_factory)
        cache = PreviewCache()
        token = cache.put(build(tdx_bytes(), "a.xls", owner=owner_id))

        def failing_commit(self: Session) -> None:
            raise RuntimeError("database temporarily unavailable")

        with session_factory() as session:
            monkeypatch.setattr(Session, "commit", failing_commit)
            with pytest.raises(RuntimeError):
                save_dataset(session, cache, token=token, name="X", owner_user_id=owner_id)
            monkeypatch.undo()
        with session_factory() as session:
            assert (
                session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 0
            )
            assert (
                session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 0
            )
        with session_factory() as session:
            dataset = save_dataset(
                session, cache, token=token, name="Retry", owner_user_id=owner_id
            )
            assert dataset.id is not None

    def test_expired_entry_yields_not_found(self, session_factory: sessionmaker[Session]) -> None:
        owner_id = make_user(session_factory)
        cache = PreviewCache()
        stale = build_preview_entry(
            raw=tdx_bytes(),
            filename="a.xls",
            manual_mapping_json=None,
            owner_user_id=owner_id,
            now=datetime.now(UTC) - timedelta(minutes=31),
        )
        token = cache.put(stale)
        with session_factory() as session, pytest.raises(ApiError) as excinfo:
            save_dataset(session, cache, token=token, name="X", owner_user_id=owner_id)
        assert excinfo.value.code == "PREVIEW_TOKEN_NOT_FOUND"
