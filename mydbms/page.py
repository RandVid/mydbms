"""
Slotted page implementation (NSM layout).

Page layout (4096 bytes):
  [0..15]   Page header
  [16..]    Slot directory (grows downward, 4 bytes per slot)
  [middle]  Free space
  [..4095]  Tuple data (grows upward from bottom)

Header (16 bytes, big-endian):
  page_id        uint16
  num_slots      uint16   total slots (including dead)
  num_alive      uint16
  free_lower     uint16   offset just past last slot entry
  free_upper     uint16   offset of first tuple byte from bottom
  flags          uint16
  reserved       uint32

Slot entry (4 bytes):
  offset  uint16   offset from page start to tuple start  (0 = dead)
  length  uint16   byte length of tuple                   (0 = dead)
"""
from __future__ import annotations
import struct
from typing import Iterator

PAGE_SIZE = 4096
_HDR_FMT = ">HHHHHHI"     # 16 bytes
_HDR_SIZE = struct.calcsize(_HDR_FMT)   # 16
_SLOT_FMT = ">HH"          # 4 bytes
_SLOT_SIZE = struct.calcsize(_SLOT_FMT)  # 4

assert _HDR_SIZE == 16


class SlottedPage:
    def __init__(self, page_id: int, data: bytes | None = None):
        if data is not None:
            if len(data) != PAGE_SIZE:
                raise ValueError(f"Page data must be {PAGE_SIZE} bytes, got {len(data)}")
            self._buf = bytearray(data)
        else:
            self._buf = bytearray(PAGE_SIZE)
            self._set_header(
                page_id=page_id,
                num_slots=0,
                num_alive=0,
                free_lower=_HDR_SIZE,
                free_upper=PAGE_SIZE,
                flags=0,
            )

    # ------------------------------------------------------------------
    # Header helpers
    # ------------------------------------------------------------------

    def _get_header(self) -> tuple:
        return struct.unpack_from(_HDR_FMT, self._buf, 0)

    def _set_header(self, **kw) -> None:
        pid, ns, na, fl, fu, flags, _ = self._get_header()
        struct.pack_into(
            _HDR_FMT, self._buf, 0,
            kw.get("page_id", pid),
            kw.get("num_slots", ns),
            kw.get("num_alive", na),
            kw.get("free_lower", fl),
            kw.get("free_upper", fu),
            kw.get("flags", flags),
            0,
        )

    @property
    def page_id(self) -> int:
        return self._get_header()[0]

    @property
    def num_slots(self) -> int:
        return self._get_header()[1]

    @property
    def num_alive(self) -> int:
        return self._get_header()[2]

    @property
    def _free_lower(self) -> int:
        return self._get_header()[3]

    @property
    def _free_upper(self) -> int:
        return self._get_header()[4]

    def free_space(self) -> int:
        return self._free_upper - self._free_lower - _SLOT_SIZE

    # ------------------------------------------------------------------
    # Slot directory helpers
    # ------------------------------------------------------------------

    def _slot_offset_in_buf(self, slot_id: int) -> int:
        return _HDR_SIZE + slot_id * _SLOT_SIZE

    def _read_slot(self, slot_id: int) -> tuple[int, int]:
        off = self._slot_offset_in_buf(slot_id)
        return struct.unpack_from(_SLOT_FMT, self._buf, off)

    def _write_slot(self, slot_id: int, tup_offset: int, length: int) -> None:
        off = self._slot_offset_in_buf(slot_id)
        struct.pack_into(_SLOT_FMT, self._buf, off, tup_offset, length)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def insert_tuple(self, data: bytes) -> int | None:
        """Insert tuple; return slot_id or None if page is full."""
        size = len(data)
        # check if there's a reusable dead slot
        reuse_slot = None
        for s in range(self.num_slots):
            so, sl = self._read_slot(s)
            if so == 0 and sl == 0:
                reuse_slot = s
                break

        needed_slot_space = 0 if reuse_slot is not None else _SLOT_SIZE
        if self._free_upper - size < self._free_lower + needed_slot_space:
            return None  # page full

        # write tuple at top of free space
        tup_start = self._free_upper - size
        self._buf[tup_start:tup_start + size] = data

        if reuse_slot is not None:
            slot_id = reuse_slot
            self._write_slot(slot_id, tup_start, size)
            self._set_header(
                free_upper=tup_start,
                num_alive=self.num_alive + 1,
            )
        else:
            slot_id = self.num_slots
            self._write_slot(slot_id, tup_start, size)
            self._set_header(
                num_slots=self.num_slots + 1,
                num_alive=self.num_alive + 1,
                free_lower=self._free_lower + _SLOT_SIZE,
                free_upper=tup_start,
            )
        return slot_id

    def get_tuple(self, slot_id: int) -> bytes | None:
        if slot_id >= self.num_slots:
            return None
        tup_off, tup_len = self._read_slot(slot_id)
        if tup_off == 0 and tup_len == 0:
            return None  # dead
        return bytes(self._buf[tup_off:tup_off + tup_len])

    def delete_tuple(self, slot_id: int) -> None:
        if slot_id >= self.num_slots:
            return
        tup_off, tup_len = self._read_slot(slot_id)
        if tup_off == 0 and tup_len == 0:
            return  # already dead
        # zero out tuple bytes (optional but clean)
        self._buf[tup_off:tup_off + tup_len] = b"\x00" * tup_len
        self._write_slot(slot_id, 0, 0)
        self._set_header(num_alive=self.num_alive - 1)

    def update_tuple(self, slot_id: int, data: bytes) -> bool:
        """Update in-place if same size; return False if new data is larger."""
        if slot_id >= self.num_slots:
            return False
        tup_off, tup_len = self._read_slot(slot_id)
        if tup_off == 0 and tup_len == 0:
            return False
        if len(data) > tup_len:
            return False
        # write new data (may be shorter — pad with zeros)
        new_size = len(data)
        self._buf[tup_off:tup_off + new_size] = data
        if new_size < tup_len:
            self._buf[tup_off + new_size:tup_off + tup_len] = b"\x00" * (tup_len - new_size)
        self._write_slot(slot_id, tup_off, new_size)
        return True

    def iter_tuples(self) -> Iterator[tuple[int, bytes]]:
        for slot_id in range(self.num_slots):
            tup = self.get_tuple(slot_id)
            if tup is not None:
                yield slot_id, tup

    def to_bytes(self) -> bytes:
        return bytes(self._buf)
