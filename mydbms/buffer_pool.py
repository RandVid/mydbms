from __future__ import annotations
from collections import OrderedDict
from mydbms.page import SlottedPage, PAGE_SIZE


class BufferPool:
    def __init__(self, capacity: int = 16):
        self._capacity = capacity
        self._cache: OrderedDict[tuple[str, int], SlottedPage] = OrderedDict()
        self._dirty: set[tuple[str, int]] = set()

    def _key(self, table: str, page_id: int) -> tuple[str, int]:
        return (table, page_id)

    def fetch_page(self, table: str, page_id: int, fh) -> SlottedPage:
        k = self._key(table, page_id)
        if k in self._cache:
            self._cache.move_to_end(k)
            return self._cache[k]

        fh.seek(page_id * PAGE_SIZE)
        raw = fh.read(PAGE_SIZE)
        if len(raw) == PAGE_SIZE:
            page = SlottedPage(page_id, raw)
        else:
            page = SlottedPage(page_id)

        if len(self._cache) >= self._capacity:
            self._evict(fh)
        self._cache[k] = page
        return page

    def put_page(self, table: str, page_id: int, page: SlottedPage) -> None:
        """Add an in-memory page to the cache (e.g. newly appended pages)."""
        k = self._key(table, page_id)
        if len(self._cache) >= self._capacity:
            self._evict()
        self._cache[k] = page

    def mark_dirty(self, table: str, page_id: int) -> None:
        self._dirty.add(self._key(table, page_id))

    def flush_all(self, file_handles: dict[str, object]) -> None:
        for k in list(self._dirty):
            table, page_id = k
            if table not in file_handles:
                continue
            fh = file_handles[table]
            page = self._cache.get(k)
            if page:
                fh.seek(page_id * PAGE_SIZE)
                fh.write(page.to_bytes())
                fh.flush()
        self._dirty.clear()

    def _evict(self, fh_map=None) -> None:
        k, page = self._cache.popitem(last=False)
        if k in self._dirty and fh_map:
            table, page_id = k
            if table in fh_map:
                fh = fh_map[table]
                fh.seek(page_id * PAGE_SIZE)
                fh.write(page.to_bytes())
                fh.flush()
            self._dirty.discard(k)
