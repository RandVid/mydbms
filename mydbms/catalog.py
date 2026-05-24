from __future__ import annotations
import json
import os
from mydbms.types import ColumnDef, DataType
from sql.errors import TableExistsError, TableNotFoundError


class TypedCatalog:
    def __init__(self, dbdir: str):
        self._path = os.path.join(dbdir, "catalog.dat")
        self._tables: dict[str, list[ColumnDef]] = {}
        if os.path.exists(self._path):
            self._load()

    def _load(self) -> None:
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for name, tbl in data.get("tables", {}).items():
            cols = [ColumnDef.from_dict(c) for c in tbl["columns"]]
            self._tables[name] = cols

    def _save(self) -> None:
        data = {
            "tables": {
                name: {"columns": [c.to_dict() for c in cols]}
                for name, cols in self._tables.items()
            }
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def create_table(self, name: str, columns: list[ColumnDef]) -> None:
        if name in self._tables:
            raise TableExistsError(f"Table '{name}' already exists")
        self._tables[name] = columns
        self._save()

    def drop_table(self, name: str) -> None:
        if name not in self._tables:
            raise TableNotFoundError(f"Table '{name}' does not exist")
        del self._tables[name]
        self._save()

    def get_schema(self, name: str) -> list[ColumnDef]:
        if name not in self._tables:
            raise TableNotFoundError(f"Table '{name}' does not exist")
        return self._tables[name]

    def table_names(self) -> list[str]:
        return list(self._tables.keys())
