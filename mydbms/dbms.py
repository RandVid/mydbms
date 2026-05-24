"""
HW6* DBMS — typed columns, slotted-page storage.

Usage:
    python -m hw6_star.dbms <path_to_db_directory>
"""
from __future__ import annotations
import os
import sys

from sql.parser import parse, SelectStmt
from sql.errors import DBError
from mydbms.catalog import TypedCatalog
from mydbms.heap_file import PagedHeapFile
from mydbms.executor import execute


class TypedDBMS:
    def __init__(self, dbdir: str):
        self._dbdir = dbdir
        os.makedirs(dbdir, exist_ok=True)
        self._catalog = TypedCatalog(dbdir)
        self._heap = PagedHeapFile(dbdir)

    def execute_sql(self, sql: str):
        sql = sql.strip()
        if not sql:
            return None
        stmt = parse(sql)
        return execute(stmt, self._catalog, self._heap)

    def close(self) -> None:
        self._heap.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _format_result(result) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        if not result:
            return "(0 rows)"
        cols = list(result[0].keys())
        widths = [
            max(len(c), max(len(str(r.get(c, ""))) for r in result))
            for c in cols
        ]
        header = " | ".join(c.ljust(w) for c, w in zip(cols, widths))
        sep = "-+-".join("-" * w for w in widths)
        rows = [
            " | ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, widths))
            for r in result
        ]
        return "\n".join([header, sep] + rows + [f"({len(result)} row(s))"])
    return str(result)


def run_repl(dbdir: str) -> None:
    print(f"MyDBMS (HW6*) — directory: {dbdir}")
    print("Type SQL statements. Enter 'exit' or Ctrl-D to quit.\n")
    with TypedDBMS(dbdir) as db:
        while True:
            try:
                sql = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not sql:
                continue
            if sql.lower() in ("exit", "quit", r"\q"):
                break
            try:
                result = db.execute_sql(sql)
                print(_format_result(result))
            except DBError as e:
                print(f"Error: {e}")
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    dbdir = sys.argv[1] if len(sys.argv) > 1 else "mydb_typed"
    run_repl(dbdir)
