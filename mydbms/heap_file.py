from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Iterator
from mydbms.page import SlottedPage, PAGE_SIZE
from mydbms.buffer_pool import BufferPool
from mydbms.types import ColumnDef, encode_tuple, decode_tuple


@dataclass
class RID:
    page_id: int
    slot_id: int


class PagedHeapFile:
    """One heap file per table. File path: <dbdir>/<table_name>.dat"""

    def __init__(self, dbdir: str):
        self._dbdir = dbdir
        self._pool = BufferPool(capacity=32)
        self._handles: dict[str, object] = {}
        self._page_counts: dict[str, int] = {}

    def _table_path(self, table: str) -> str:
        return os.path.join(self._dbdir, f"{table}.dat")

    def _open(self, table: str):
        if table not in self._handles:
            path = self._table_path(table)
            if os.path.exists(path):
                fh = open(path, "r+b")
            else:
                fh = open(path, "w+b")
            self._handles[table] = fh
        return self._handles[table]

    def _num_pages(self, table: str) -> int:
        if table in self._page_counts:
            return self._page_counts[table]
        fh = self._open(table)
        fh.seek(0, 2)
        size = fh.tell()
        count = size // PAGE_SIZE
        self._page_counts[table] = count
        return count

    def _append_page(self, table: str) -> SlottedPage:
        page_id = self._num_pages(table)
        page = SlottedPage(page_id)
        fh = self._open(table)
        fh.seek(page_id * PAGE_SIZE)
        fh.write(page.to_bytes())
        fh.flush()
        self._page_counts[table] = page_id + 1
        # Register in cache so subsequent reads/writes use this in-memory object
        self._pool.put_page(table, page_id, page)
        return page

    def insert(self, table: str, row: dict, schema: list[ColumnDef]) -> RID:
        data = encode_tuple(row, schema)
        fh = self._open(table)
        n = self._num_pages(table)
        # scan pages for one with enough free space
        for pid in range(n):
            page = self._pool.fetch_page(table, pid, fh)
            slot_id = page.insert_tuple(data)
            if slot_id is not None:
                self._pool.mark_dirty(table, pid)
                return RID(page_id=pid, slot_id=slot_id)
        # no space — append a new page
        page = self._append_page(table)
        slot_id = page.insert_tuple(data)
        self._pool.mark_dirty(table, page.page_id)
        return RID(page_id=page.page_id, slot_id=slot_id)

    def scan(self, table: str, schema: list[ColumnDef]) -> Iterator[tuple[RID, dict]]:
        fh = self._open(table)
        for pid in range(self._num_pages(table)):
            page = self._pool.fetch_page(table, pid, fh)
            for slot_id, raw in page.iter_tuples():
                row = decode_tuple(raw, schema)
                yield RID(page_id=pid, slot_id=slot_id), row

    def get(self, table: str, rid: RID, schema: list[ColumnDef]) -> dict | None:
        fh = self._open(table)
        page = self._pool.fetch_page(table, rid.page_id, fh)
        raw = page.get_tuple(rid.slot_id)
        if raw is None:
            return None
        return decode_tuple(raw, schema)

    def delete(self, table: str, rid: RID) -> None:
        fh = self._open(table)
        page = self._pool.fetch_page(table, rid.page_id, fh)
        page.delete_tuple(rid.slot_id)
        self._pool.mark_dirty(table, rid.page_id)

    def update(self, table: str, rid: RID, new_row: dict, schema: list[ColumnDef]) -> RID:
        fh = self._open(table)
        page = self._pool.fetch_page(table, rid.page_id, fh)
        data = encode_tuple(new_row, schema)
        if page.update_tuple(rid.slot_id, data):
            self._pool.mark_dirty(table, rid.page_id)
            return rid
        # tuple grew — delete old, insert new
        page.delete_tuple(rid.slot_id)
        self._pool.mark_dirty(table, rid.page_id)
        return self.insert(table, new_row, schema)

    def flush(self) -> None:
        self._pool.flush_all(self._handles)

    def close(self) -> None:
        self.flush()
        for fh in self._handles.values():
            fh.close()
        self._handles.clear()
