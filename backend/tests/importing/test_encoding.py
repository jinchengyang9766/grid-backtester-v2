"""Tests for TongdaXin text-encoding detection."""

import pytest
from app.importing.encoding import DecodedText, EncodingDetectionError, decode_tdx_bytes


def test_utf8_text_decodes_as_utf8_sig() -> None:
    raw = "时间\t收盘\n2020-01-02\t1.23\n".encode()
    result = decode_tdx_bytes(raw)
    assert isinstance(result, DecodedText)
    assert result.encoding == "utf-8-sig"
    assert result.text == "时间\t收盘\n2020-01-02\t1.23\n"


def test_utf8_bom_is_removed() -> None:
    raw = "时间\t收盘\n".encode("utf-8-sig")
    result = decode_tdx_bytes(raw)
    assert result.encoding == "utf-8-sig"
    assert not result.text.startswith("﻿")
    assert result.text.startswith("时间")


def test_gb18030_chinese_text_decodes_correctly() -> None:
    raw = "时间\t开盘\t最高\t最低\t收盘\t成交量\n".encode("gb18030")
    result = decode_tdx_bytes(raw)
    assert result.encoding == "gb18030"
    assert result.text == "时间\t开盘\t最高\t最低\t收盘\t成交量\n"


def test_undecodable_bytes_raise_encoding_detection_error() -> None:
    raw = b"\x80\x81\x82\xff\xfe"
    with pytest.raises(EncodingDetectionError):
        decode_tdx_bytes(raw)
