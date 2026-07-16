"""Text-encoding detection for uploaded market-data files."""

from dataclasses import dataclass

__all__ = ["DecodedText", "EncodingDetectionError", "decode_tdx_bytes"]

_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "gb18030")


@dataclass(frozen=True, slots=True)
class DecodedText:
    text: str
    encoding: str


class EncodingDetectionError(Exception):
    pass


def decode_tdx_bytes(raw: bytes) -> DecodedText:
    for encoding in _ENCODINGS:
        try:
            return DecodedText(text=raw.decode(encoding), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise EncodingDetectionError(f"Unable to decode bytes using any of: {', '.join(_ENCODINGS)}.")
