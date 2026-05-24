from __future__ import annotations
import struct
import math
from dataclasses import dataclass
from enum import Enum, auto
from sql.errors import TypeMismatchError


class DataType(Enum):
    INT = auto()
    FLOAT = auto()
    VARCHAR = auto()
    BOOL = auto()


@dataclass
class ColumnDef:
    name: str
    dtype: DataType
    varchar_max: int = 255  # only used for VARCHAR
    index: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "dtype": self.dtype.name,
            "varchar_max": self.varchar_max,
            "index": self.index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ColumnDef":
        return cls(
            name=d["name"],
            dtype=DataType[d["dtype"]],
            varchar_max=d.get("varchar_max", 255),
            index=d.get("index", 0),
        )


# ---------------------------------------------------------------------------
# Per-type encode / decode
# ---------------------------------------------------------------------------

def encode_value(value, col: ColumnDef) -> bytes:
    if value is None:
        return b""  # null — caller sets bitmap bit; no bytes emitted
    match col.dtype:
        case DataType.INT:
            try:
                return struct.pack(">q", int(value))
            except (ValueError, struct.error):
                raise TypeMismatchError(f"Cannot encode '{value}' as INT")
        case DataType.FLOAT:
            try:
                return struct.pack(">d", float(value))
            except (ValueError, struct.error):
                raise TypeMismatchError(f"Cannot encode '{value}' as FLOAT")
        case DataType.BOOL:
            if isinstance(value, bool):
                return struct.pack(">?", value)
            s = str(value).upper()
            if s in ("TRUE", "1"):
                return b"\x01"
            if s in ("FALSE", "0"):
                return b"\x00"
            raise TypeMismatchError(f"Cannot encode '{value}' as BOOL")
        case DataType.VARCHAR:
            s = str(value)
            encoded = s.encode("utf-8")
            if len(encoded) > col.varchar_max:
                raise TypeMismatchError(
                    f"String length {len(encoded)} exceeds VARCHAR({col.varchar_max})"
                )
            return struct.pack(">H", len(encoded)) + encoded
    raise NotImplementedError(col.dtype)


def decode_value(data: bytes, offset: int, col: ColumnDef) -> tuple:
    """Return (python_value, bytes_consumed)."""
    match col.dtype:
        case DataType.INT:
            val = struct.unpack_from(">q", data, offset)[0]
            return val, 8
        case DataType.FLOAT:
            val = struct.unpack_from(">d", data, offset)[0]
            return val, 8
        case DataType.BOOL:
            val = struct.unpack_from(">?", data, offset)[0]
            return val, 1
        case DataType.VARCHAR:
            length = struct.unpack_from(">H", data, offset)[0]
            s = data[offset + 2:offset + 2 + length].decode("utf-8")
            return s, 2 + length
    raise NotImplementedError(col.dtype)


# ---------------------------------------------------------------------------
# Tuple encode / decode
# ---------------------------------------------------------------------------

def encode_tuple(row: dict, schema: list[ColumnDef]) -> bytes:
    n = len(schema)
    bitmap_bytes = math.ceil(n / 8)
    bitmap = bytearray(bitmap_bytes)
    parts = [bytes(bitmap_bytes)]  # placeholder, fill later

    for col in schema:
        val = row.get(col.name)
        if val is None or (isinstance(val, str) and val.upper() == "NULL"):
            bitmap[col.index // 8] |= (1 << (col.index % 8))
            parts.append(b"")
        else:
            parts.append(encode_value(val, col))

    parts[0] = bytes(bitmap)
    return b"".join(parts)


def decode_tuple(data: bytes, schema: list[ColumnDef]) -> dict:
    n = len(schema)
    bitmap_bytes = math.ceil(n / 8)
    bitmap = data[:bitmap_bytes]
    offset = bitmap_bytes
    row = {}
    for col in schema:
        is_null = bool(bitmap[col.index // 8] & (1 << (col.index % 8)))
        if is_null:
            row[col.name] = None
        else:
            val, consumed = decode_value(data, offset, col)
            row[col.name] = val
            offset += consumed
    return row


# ---------------------------------------------------------------------------
# Coerce SQL string tokens to typed Python values
# ---------------------------------------------------------------------------

def coerce(raw: str, col: ColumnDef):
    """Convert a raw string token from the SQL parser to the column's Python type."""
    if raw.upper() == "NULL":
        return None
    match col.dtype:
        case DataType.INT:
            try:
                return int(raw)
            except ValueError:
                raise TypeMismatchError(f"'{raw}' is not a valid INT")
        case DataType.FLOAT:
            try:
                return float(raw)
            except ValueError:
                raise TypeMismatchError(f"'{raw}' is not a valid FLOAT")
        case DataType.BOOL:
            if raw.upper() in ("TRUE", "1"):
                return True
            if raw.upper() in ("FALSE", "0"):
                return False
            raise TypeMismatchError(f"'{raw}' is not a valid BOOL")
        case DataType.VARCHAR:
            return raw
    raise NotImplementedError(col.dtype)
