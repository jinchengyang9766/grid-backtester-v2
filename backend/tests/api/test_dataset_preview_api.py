"""Tests for POST /api/datasets/preview."""

from datetime import date, timedelta
from pathlib import Path

import httpx
import sqlalchemy as sa
from app.db.models import Dataset, PriceBar
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

TDX_TEXT = (
    "农业ETF基金 (159825)\t\t\t\t\t\n"
    "时间\t开盘\t最高\t最低\t收盘\t成交量\n"
    "2024/07/23\t1.00\t1.10\t0.90\t1.05\t1000\n"
    "2024/07/24\t1.05\t1.15\t1.00\t1.10\t1200\n"
    "bad-date\t1.00\t1.00\t1.00\t1.00\t1\n"
    "2024/07/24\t1.06\t1.16\t1.01\t1.11\t1300\n"
    "数据来源：通达信\n"
)
CSV_OHLCV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2024/07/23,1.00,1.10,0.90,1.05,1000\n"
    "2024/07/24,1.05,1.15,1.00,1.10,\n"
)
CSV_CLOSE_ONLY = "Date,Close\n2024/07/23,1.05\n2024/07/24,1.10\n"


def signup(client: TestClient, email: str = "user@example.com") -> None:
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    client.post("/api/auth/login", json={"email": email, "password": "password123"})


def preview(
    client: TestClient,
    content: bytes,
    filename: str = "data.csv",
    manual_mapping: str | None = None,
    extra_form: dict[str, str] | None = None,
) -> httpx.Response:
    form: dict[str, str] = dict(extra_form or {})
    if manual_mapping is not None:
        form["manual_mapping"] = manual_mapping
    response: httpx.Response = client.post(
        "/api/datasets/preview",
        files={"file": (filename, content, "application/octet-stream")},
        data=form,
    )
    return response


class TestAuthentication:
    def test_unauthenticated_preview_401(self, client: TestClient) -> None:
        response = preview(client, CSV_CLOSE_ONLY.encode())
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_invalid_cookie_401(self, client: TestClient) -> None:
        client.cookies.set("access_token", "garbage")
        assert preview(client, CSV_CLOSE_ONLY.encode()).status_code == 401


class TestFormatSelection:
    def test_xls_accepted_both_cases(self, client: TestClient) -> None:
        signup(client)
        raw = TDX_TEXT.encode("gb18030")
        for name in ("data.xls", "DATA.XLS"):
            response = preview(client, raw, filename=name)
            assert response.status_code == 200
            assert response.json()["detected_format"] == "TDX_XLS"

    def test_csv_accepted_both_cases(self, client: TestClient) -> None:
        signup(client)
        for name in ("data.csv", "DATA.CSV"):
            response = preview(client, CSV_CLOSE_ONLY.encode(), filename=name)
            assert response.status_code == 200
            assert response.json()["detected_format"] == "CSV"

    def test_unsupported_extension(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode(), filename="data.txt")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_binary_ole2_xls_rejected(self, client: TestClient) -> None:
        signup(client)
        raw = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
        response = preview(client, raw, filename="book.xls")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_renamed_xlsx_zip_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, b"PK\x03\x04zipdata", filename="book.xls")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_no_raw_file_written_to_disk(self, client: TestClient, tmp_path: Path) -> None:
        signup(client)
        before = set(tmp_path.rglob("*"))
        assert preview(client, TDX_TEXT.encode("gb18030"), filename="data.xls").status_code == 200
        assert set(tmp_path.rglob("*")) == before


class TestEncoding:
    def test_utf8_sig_csv(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode("utf-8-sig"))
        assert response.json()["detected_encoding"] == "utf-8-sig"

    def test_gb18030_csv(self, client: TestClient) -> None:
        signup(client)
        text = "时间,收盘\n2024/07/23,1.05\n"
        response = preview(client, text.encode("gb18030"))
        assert response.status_code == 200
        assert response.json()["detected_encoding"] == "gb18030"

    def test_utf8_sig_tdx(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, TDX_TEXT.encode("utf-8-sig"), filename="data.xls")
        assert response.json()["detected_encoding"] == "utf-8-sig"

    def test_gb18030_tdx(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, TDX_TEXT.encode("gb18030"), filename="data.xls")
        assert response.json()["detected_encoding"] == "gb18030"

    def test_undecodable_input(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, b"\xff\xff\xff")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "ENCODING_DETECTION_FAILED"


class TestMapping:
    def test_automatic_ohlcv_mapping(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, CSV_OHLCV.encode()).json()
        assert body["data_mode"] == "OHLCV"
        assert body["auto_column_mapping"] == {
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        assert body["column_mapping_used"] == body["auto_column_mapping"]

    def test_automatic_close_only_mapping(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, CSV_CLOSE_ONLY.encode()).json()
        assert body["data_mode"] == "CLOSE_ONLY"
        assert body["column_mapping_used"] == {"date": "Date", "close": "Close"}

    def test_manual_partial_override_merges_with_auto(self, client: TestClient) -> None:
        signup(client)
        csv = "Date,Open,High,Low,Close,Adj,Volume\n2024/07/23,1.00,1.10,0.90,1.05,1.04,1000\n"
        body = preview(client, csv.encode(), manual_mapping='{"close": "Adj"}').json()
        assert body["column_mapping_used"]["close"] == "Adj"
        assert body["column_mapping_used"]["open"] == "Open"
        assert body["auto_column_mapping"]["close"] == "Close"  # auto stays original
        assert body["preview_rows"][0]["close"] == "1.04"

    def test_null_override_clears_to_close_only(self, client: TestClient) -> None:
        signup(client)
        body = preview(
            client,
            CSV_OHLCV.encode(),
            manual_mapping='{"open": null, "high": null, "low": null}',
        ).json()
        assert body["data_mode"] == "CLOSE_ONLY"
        assert "open" not in body["column_mapping_used"]
        assert body["auto_column_mapping"]["open"] == "Open"

    def test_partial_ohlc_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_OHLCV.encode(), manual_mapping='{"open": null}')
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "MISSING_REQUIRED_COLUMN"
        assert body["error"]["details"]["partial_ohlc_fields"] == ["high", "low"]

    def test_missing_date_rejected(self, client: TestClient) -> None:
        signup(client)
        csv = "When,Close\n2024/07/23,1.05\n"
        response = preview(client, csv.encode())
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "MISSING_REQUIRED_COLUMN"
        assert body["error"]["details"]["missing_fields"] == ["date"]

    def test_missing_close_rejected(self, client: TestClient) -> None:
        signup(client)
        csv = "Date,Value\n2024/07/23,1.05\n"
        response = preview(client, csv.encode())
        assert response.status_code == 400
        assert response.json()["error"]["details"]["missing_fields"] == ["close"]

    def test_unknown_canonical_key_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode(), manual_mapping='{"adjusted": "Close"}')
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unknown_source_header_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode(), manual_mapping='{"close": "Nope"}')
        assert response.status_code == 422

    def test_source_column_mapped_twice_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_OHLCV.encode(), manual_mapping='{"open": "Close"}')
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_malformed_json_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode(), manual_mapping="{not json")
        assert response.status_code == 422

    def test_non_object_json_rejected(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode(), manual_mapping="[1, 2]")
        assert response.status_code == 422


class TestCleaning:
    def test_bad_and_duplicate_rows_returned(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, TDX_TEXT.encode("gb18030"), filename="data.xls").json()
        assert body["bad_rows"] == [
            {
                "row_number": 3,
                "reason": "UNPARSEABLE_DATE",
                "raw": {
                    "时间": "bad-date",
                    "开盘": "1.00",
                    "最高": "1.00",
                    "最低": "1.00",
                    "收盘": "1.00",
                    "成交量": "1",
                },
            }
        ]
        (duplicate,) = body["duplicate_rows"]
        assert duplicate["date"] == "2024-07-24"
        assert duplicate["kept_row_number"] == 4
        assert duplicate["discarded_row_number"] == 2
        assert duplicate["reason"] == "DUPLICATE_DATE_DISCARDED"
        # Keep-last-in-file-order: the kept 07-24 row is the later one (1.11).
        assert body["preview_rows"][-1]["close"] == "1.11"

    def test_cleaning_summary_exact(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, TDX_TEXT.encode("gb18030"), filename="data.xls").json()
        assert body["cleaning_summary"] == {
            "total_rows_parsed": 4,
            "valid_rows": 3,
            "bad_rows": 1,
            "duplicate_dates": 1,
            "final_row_count": 2,
            "date_range": {"start": "2024-07-23", "end": "2024-07-24"},
            "data_mode": "OHLCV",
            "bad_row_reasons": {
                "UNPARSEABLE_DATE": 1,
                "MISSING_CLOSE": 0,
                "NON_POSITIVE_PRICE": 0,
                "MISSING_OHLC_FIELD": 0,
                "INVALID_OHLC_RANGE": 0,
                "INVALID_VOLUME": 0,
                "NEGATIVE_VOLUME": 0,
            },
        }

    def test_preview_rows_sorted_with_decimal_strings_and_nulls(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, CSV_OHLCV.encode()).json()
        rows = body["preview_rows"]
        assert [row["date"] for row in rows] == ["2024-07-23", "2024-07-24"]
        assert rows[0]["close"] == "1.05"
        assert isinstance(rows[0]["close"], str)
        assert rows[1]["volume"] is None

    def test_first_and_last_fifty_for_large_files(self, client: TestClient) -> None:
        signup(client)
        start = date(2024, 1, 1)
        lines = ["Date,Close"]
        for offset in range(120):
            day = start + timedelta(days=offset)
            lines.append(f"{day.year}/{day.month:02d}/{day.day:02d},{offset + 1}")
        body = preview(client, "\n".join(lines).encode()).json()
        rows = body["preview_rows"]
        assert len(rows) == 100
        assert len({row["date"] for row in rows}) == 100
        assert rows[0]["date"] == "2024-01-01"
        assert rows[49]["date"] == "2024-02-19"  # bar index 49
        assert rows[50]["date"] == "2024-03-11"  # bar index 70 of 120
        assert rows[-1]["date"] == "2024-04-29"  # bar index 119

    def test_no_duplication_at_or_below_hundred(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, CSV_CLOSE_ONLY.encode()).json()
        assert len(body["preview_rows"]) == 2

    def test_zero_final_rows_rejected_without_token(
        self, client: TestClient, api_app: FastAPI
    ) -> None:
        signup(client)
        response = preview(client, b"Date,Close\nnope,abc\n")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert api_app.state.preview_cache._entries == {}


class TestMetadata:
    def test_tdx_security_metadata_returned(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, TDX_TEXT.encode("gb18030"), filename="data.xls").json()
        assert body["security_name"] == "农业ETF基金"
        assert body["security_code"] == "159825"

    def test_tdx_missing_metadata_null(self, client: TestClient) -> None:
        signup(client)
        raw = "时间\t收盘\n2024/07/23\t1.05\n".encode("gb18030")
        body = preview(client, raw, filename="plain.xls").json()
        assert body["security_name"] is None
        assert body["security_code"] is None

    def test_csv_metadata_null(self, client: TestClient) -> None:
        signup(client)
        body = preview(client, CSV_CLOSE_ONLY.encode()).json()
        assert body["security_name"] is None
        assert body["security_code"] is None

    def test_ohlc_path_hint_accepted_and_unused(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_CLOSE_ONLY.encode(), extra_form={"ohlc_path_hint": "AUTO"})
        assert response.status_code == 200
        assert "ohlc_path_hint" not in response.json()


class TestPersistenceSafety:
    def test_preview_creates_no_database_rows(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        signup(client)
        assert preview(client, CSV_OHLCV.encode()).status_code == 200
        with session_factory() as session:
            assert (
                session.execute(sa.select(sa.func.count()).select_from(Dataset)).scalar_one() == 0
            )
            assert (
                session.execute(sa.select(sa.func.count()).select_from(PriceBar)).scalar_one() == 0
            )

    def test_response_exposes_no_internals(self, client: TestClient) -> None:
        signup(client)
        response = preview(client, CSV_OHLCV.encode())
        assert "source_content_hash" not in response.text
        assert "owner_user_id" not in response.text
        assert "expires_at" not in response.text
        body = response.json()
        assert body["preview_token"]


class TestOpenApi:
    def test_preview_is_multipart_and_save_is_json(self, api_app: FastAPI) -> None:
        paths = api_app.openapi()["paths"]
        preview_body = paths["/api/datasets/preview"]["post"]["requestBody"]["content"]
        assert "multipart/form-data" in preview_body
        save_body = paths["/api/datasets"]["post"]["requestBody"]["content"]
        assert "application/json" in save_body
        assert "/health" in paths
